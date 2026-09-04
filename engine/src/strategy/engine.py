"""전략 오케스트레이션 — 분석·브로커·중계·규칙을 엮는 매매 루프. docs/00 §2, docs/03 §4.

책임: 후보/지표 갱신 → 보유 청산 평가 → 후보 진입 평가 → 리스크 통과분만 주문 →
     포지션/주문/이벤트 Supabase 반영 + 하트비트 + 앱 명령 처리 + kill-switch.
전략 판정은 rules/risk(순수)에 위임. 이 파일은 배선·부수효과(주문·DB·로그)만.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..analysis import pykrx_fetcher
from ..analysis.calculator import compute_drop_ratio
from ..analysis.candidates import Candidate, build_candidates, compute_status
from ..broker.base import BrokerAdapter
from ..broker.errors import BrokerError
from ..broker.models import OrderType, Position, Side
from ..relay import DryRunRelay, Relay
from .indicators import Envelope, compute_envelope
from .market import is_market_open
from .params import StrategyParams
from .risk import ok_buy, ok_sell
from .rules import should_enter, should_exit
from .state import PositionState

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
PARAMS_RELOAD_SEC = 30  # settings 주기 재로드(앱 set_param 명령 유실·대시보드 직접 수정 대비 안전망)


class StrategyEngine:
    def __init__(self, broker: BrokerAdapter, relay: Relay, *, now=None):
        self.broker = broker
        self.relay = relay
        self._now = now or (lambda: datetime.now(KST))
        self.params = StrategyParams()
        self.status = "stopped"            # stopped|running|paused|stopping|error
        self.candidates: dict[str, Candidate] = {}
        self.positions: dict[str, Position] = {}
        self.states: dict[str, PositionState] = {}
        self.envelopes: dict[str, Envelope] = {}
        self.prev_close: dict[str, int] = {}
        self.day_realized_pnl = 0
        self._day = None
        self._subscribed: set[str] = set()
        self._entry_blocked = False
        self.candidate_lows: dict[str, int] = {}   # 매수구간 종목별 저점(저가 반등 매수용)
        self._params_loaded_at: datetime | None = None  # 마지막 settings 로드 시각(None=아직 미로드 → 주기 재로드 비활성)
        self._real_relay = relay
        self.live = True                   # False=드라이런/관찰: 주문 금지 + Supabase 쓰기 무시(DryRunRelay)
        self._dry_logged: set[str] = set() # 드라이런 판정 로그 중복 방지(일 단위 리셋)

    # ── 라이브/드라이런 전환 ──────────────────────────
    def set_live(self, live: bool, reason: str = "") -> None:
        """live=False: 주문 안 냄 + relay 쓰기 전부 무시. 락 미획득/BOT_DRY_RUN 용."""
        if live == self.live:
            return
        self.live = live
        self.relay = self._real_relay if live else DryRunRelay(self._real_relay)
        logger.warning("모드 전환 → %s (%s)", "LIVE" if live else "DRY-RUN/관찰", reason)

    def restore_state(self) -> int:
        """strategy_state 에서 분할매수/매도·저점 복원(재시작·재배포). 반환: 복원 행 수."""
        try:
            rows = self.relay.load_strategy_states()
        except Exception:
            logger.exception("strategy_state 로드 실패 — 빈 상태로 시작")
            return 0
        for r in rows:
            code = r["code"]
            if r.get("entries_done") or r.get("partial_sold"):
                self.states[code] = PositionState(
                    code, entries_done=int(r.get("entries_done") or 0),
                    invested_krw=int(r.get("invested_krw") or 0),
                    partial_sold=bool(r.get("partial_sold")),
                    peak_since_partial=int(r.get("peak_since_partial") or 0),
                    partial_sell_price=int(r.get("partial_sell_price") or 0))
            if r.get("zone_low"):
                self.candidate_lows[code] = int(r["zone_low"])
        if rows:
            logger.info("전략상태 복원 %d행 (포지션 %d, 저점 %d)", len(rows), len(self.states), len(self.candidate_lows))
        return len(rows)

    def _persist_state(self, code: str) -> None:
        """종목 전략상태(+저점) 저장. 둘 다 없으면 행 삭제. 실패는 로그만(매매 흐름 방해 금지)."""
        st = self.states.get(code)
        low = self.candidate_lows.get(code)
        try:
            if st is None and low is None:
                self.relay.delete_strategy_state(code)
            else:
                self.relay.save_strategy_state(
                    code,
                    entries_done=st.entries_done if st else 0,
                    invested_krw=st.invested_krw if st else 0,
                    partial_sold=st.partial_sold if st else False,
                    peak_since_partial=st.peak_since_partial if st else 0,
                    partial_sell_price=st.partial_sell_price if st else 0,
                    zone_low=low)
        except Exception:
            logger.exception("strategy_state 저장 실패 %s", code)

    # ── 수명주기 / 명령 ───────────────────────────────
    def load_params(self, *, source: str = "startup") -> bool:
        """settings 로드. 값이 바뀌었으면 True + 이벤트(startup 제외). 실패 시 기존 유지."""
        try:
            new = StrategyParams.from_settings(self.relay.load_settings())
        except Exception:
            logger.exception("settings 로드 실패 — 기존 파라미터 유지")
            return False
        self._params_loaded_at = self._now()
        if new == self.params:
            return False
        old, self.params = self.params, new
        diff = ", ".join(f"{k}={v}" for k, v in vars(new).items() if getattr(old, k) != v)
        logger.info("설정 반영(%s): %s", source, diff)
        if source != "startup":
            self._emit("state", "info", "설정 반영", diff)
        return True

    def _maybe_reload_params(self, now: datetime) -> None:
        """PARAMS_RELOAD_SEC 마다 settings 재로드. 시작 시 load_params 이후에만 동작(테스트/미로드 상태 보호)."""
        if self._params_loaded_at is None:
            return
        if (now - self._params_loaded_at).total_seconds() >= PARAMS_RELOAD_SEC:
            self.load_params(source="periodic")

    def handle_command(self, row: dict):
        t = row.get("type")
        payload = row.get("payload") or {}
        if t == "start":
            self.status = "running"; self._emit("state", "info", "봇 시작")
        elif t == "stop":
            self.status = "stopped"; self._emit("state", "info", "봇 정지")
        elif t == "pause":
            self.status = "paused"; self._emit("state", "info", "일시정지")
        elif t == "resume":
            self.status = "running"; self._emit("state", "info", "재개")
        elif t == "kill":
            self.kill()
        elif t == "set_param":
            return "설정 반영" if self.load_params(source="command") else "설정 변경 없음"
        elif t == "close_position":
            return self.close_position(payload.get("code", ""))
        else:
            return f"알 수 없는 명령: {t}"
        return str(t)

    # ── 갱신(주기적) ──────────────────────────────────
    def refresh(self) -> None:
        """후보 수집 + 지표 재계산 + watchlist 구독. 장초 1회 + N분 주기(main에서 호출)."""
        try:
            cands = build_candidates(fetch_current_price=False)
        except Exception:
            logger.exception("후보 수집 실패")
            return
        # 현재가·하락비율을 키움 현재가로 채움(앱 후보탭 표시용)
        try:
            prices = self.broker.get_prices([c.code for c in cands if c.code])
            for c in cands:
                p = prices.get(c.code)
                if p:
                    c.current_price = p
                    c.drop_ratio = compute_drop_ratio(c.release_amount, p)
                    c.status = compute_status(c.t5_close, c.t15_close, c.recent_15_high, p)
        except Exception:
            logger.exception("후보 현재가 조회 실패")
        self.candidates = {c.code: c for c in cands if c.code}
        try:
            self.relay.upsert_candidates(cands)
            self.relay.prune_candidates(list(self.candidates.keys()))  # 경고 해제된 스테일 후보 정리
        except Exception:
            logger.exception("candidates upsert/정리 실패")
        self._recompute_indicators()
        self._resubscribe()

    def _recompute_indicators(self) -> None:
        codes = set(self.candidates) | set(self.positions)
        end = self._now().date()
        start = end - timedelta(days=self.params.env_period * 3 + 20)
        for code in codes:
            try:
                closes = pykrx_fetcher.get_close_range(code, start, end)
            except Exception:
                closes = []
            if closes:
                self.prev_close[code] = closes[-1]
                env = compute_envelope(closes, self.params.env_period, self.params.env_band)
                if env:
                    self.envelopes[code] = env

    def _resubscribe(self) -> None:
        codes = set(self.candidates) | set(self.positions)
        if codes and codes != self._subscribed:
            try:
                self.broker.subscribe_realtime(sorted(codes), self._on_tick)
                self._subscribed = codes
            except Exception:
                logger.exception("실시간 구독 실패")

    def _on_tick(self, code: str, price: int) -> None:
        pass  # 브로커가 내부 캐시 갱신. 엔진은 get_price 로 읽음.

    # ── 매매 루프 (tick) ──────────────────────────────
    def tick(self) -> None:
        now = self._now()
        self._maybe_reload_params(now)   # 정지/장외 상태에서도 설정(enabled 등) 변경을 따라감
        self._maybe_daily_reset(now)
        market = is_market_open(now)
        if self.status != "running" or not market:
            self._heartbeat(market)
            return
        self.sync_positions()
        self._sync_candidate_display()
        self._update_candidate_lows()
        pending = self._pending_codes()
        self._evaluate_exits(pending)
        self._evaluate_entries(pending)
        self._heartbeat(market)

    def sync_positions(self) -> None:
        try:
            positions = self.broker.get_positions()
        except BrokerError:
            logger.exception("포지션 조회 실패")
            return
        self.positions = {p.code: p for p in positions}
        for code, p in self.positions.items():
            if code not in self.states:  # 재시작/외부매수 복원: 보유=1회 매수로 간주
                self.states[code] = PositionState(code, entries_done=1, invested_krw=p.avg_price * p.qty)
        for code in list(self.states):    # 청산 완료분 정리
            if code not in self.positions:
                self.states.pop(code, None)
                try:
                    self.relay.remove_position(code)
                except Exception:
                    pass
                self._persist_state(code)
        try:
            self.relay.upsert_positions(positions)
        except Exception:
            logger.exception("positions upsert 실패")

    def _sync_candidate_display(self) -> None:
        """후보 현재가/하락비율을 실시간(WS) 캐시로 갱신해 Supabase 반영(변경분만, REST 없음)."""
        changed = []
        for code, cand in self.candidates.items():
            p = self.broker.cached_price(code)
            if p and p != cand.current_price:
                cand.current_price = p
                cand.drop_ratio = compute_drop_ratio(cand.release_amount, p)
                cand.status = compute_status(cand.t5_close, cand.t15_close, cand.recent_15_high, p)
                changed.append(cand)
        if changed:
            try:
                self.relay.upsert_candidates(changed)
            except Exception:
                logger.exception("후보 현재가 갱신 실패")

    def _update_candidate_lows(self) -> None:
        """매수구간(drop_ratio≥기준) 종목의 저점을 추적. 구간 벗어나면 리셋. (저가 반등 매수용)"""
        for code in list(self.candidate_lows):
            if code not in self.candidates:
                self.candidate_lows.pop(code, None)
        for code, cand in self.candidates.items():
            price = self.broker.cached_price(code) or cand.current_price
            if not price:
                continue
            dr = cand.drop_ratio
            prev = self.candidate_lows.get(code)
            if dr is not None and dr >= self.params.entry_drop_pct:
                self.candidate_lows[code] = min(prev, price) if prev else price
            else:
                self.candidate_lows.pop(code, None)
            if self.candidate_lows.get(code) != prev:
                self._persist_state(code)

    def _pending_codes(self) -> set[str]:
        try:
            return {u["code"] for u in self.broker.get_unfilled_orders()}
        except Exception:
            return set()

    def _evaluate_exits(self, pending: set[str]) -> None:
        for code, pos in list(self.positions.items()):
            price = self._price(code)
            if not price:
                continue
            st = self.states.setdefault(code, PositionState(code))
            peak_before = st.peak_since_partial
            st.update_peak(price)
            if st.peak_since_partial != peak_before:
                self._persist_state(code)
            d = should_exit(qty=pos.qty, avg_price=pos.avg_price, price=price,
                            env=self.envelopes.get(code), params=self.params, state=st,
                            at_limit_up=self._at_limit_up(code, price))
            if not d.exit or code in pending:
                continue
            r = ok_sell(qty=d.qty, held_qty=pos.qty)
            if not r.ok:
                self._emit("risk_block", "warn", "매도 차단", f"{pos.name}: {r.reason}")
                continue
            self._sell(pos, d, price)

    def _unrealized_pnl(self) -> int:
        """보유 전체 평가손익(음수=평가손실). 실시간가 우선, 없으면 잔고상 현재가."""
        total = 0
        for code, pos in self.positions.items():
            price = self._price(code) or pos.current_price
            total += (price - pos.avg_price) * pos.qty
        return total

    def _evaluate_entries(self, pending: set[str]) -> None:
        if not self.params.enabled:
            return
        unrealized = self._unrealized_pnl()
        if unrealized <= -self.params.max_unrealized_loss_krw:
            if not self._entry_blocked:  # 전환 시 1회만 알림(스팸 방지)
                self._emit("risk_block", "warn", "신규매수 중단",
                           f"평가손실 {unrealized:,} ≤ 한도 -{self.params.max_unrealized_loss_krw:,}")
            self._entry_blocked = True
            return
        self._entry_blocked = False
        try:
            cash = self.broker.get_balance().cash
        except BrokerError:
            return
        today = self._now().date()
        for code, cand in self.candidates.items():
            price = self._price(code)
            if not price:
                continue
            pos = self.positions.get(code)
            holding = pos is not None and pos.qty > 0
            st = self.states.setdefault(code, PositionState(code))
            release_passed = cand.release_date is not None and today > cand.release_date
            d = should_enter(
                drop_ratio=cand.drop_ratio, status=cand.status, price=price,
                env=self.envelopes.get(code), params=self.params, state=st,
                holding=holding, avg_price=pos.avg_price if pos else None,
                positions_cnt=len(self.positions), cash=cash,
                release_passed=release_passed, low_price=self.candidate_lows.get(code))
            if not d.enter or code in pending:
                continue
            r = ok_buy(qty=d.qty, price=price, params=self.params, cash=cash,
                       positions_cnt=len(self.positions), holding=holding,
                       invested_krw=st.invested_krw, pending_same_dir=code in pending,
                       unrealized_pnl=unrealized, prev_close=self.prev_close.get(code))
            if not r.ok:
                self._emit("risk_block", "warn", "매수 차단", f"{cand.name}: {r.reason}")
                continue
            self._buy(cand, d, price)
            cash -= d.qty * price

    # ── 주문 실행 + 반영 ──────────────────────────────
    def _order_type(self) -> OrderType:
        return OrderType.LIMIT if self.params.order_type == "limit" else OrderType.MARKET

    def _dry_log(self, key: str, msg: str) -> bool:
        """드라이런이면 판정을 로그(같은 key 는 하루 1회)하고 True. 라이브면 False."""
        if self.live:
            return False
        if key not in self._dry_logged:
            self._dry_logged.add(key)
            logger.info("[DRY] %s", msg)
        return True

    def _buy(self, cand: Candidate, d, price: int) -> None:
        if self._dry_log(f"buy:{cand.code}:{d.kind}", f"매수 시뮬 {cand.name} {d.kind} {d.qty}주 @ {price:,}"):
            return
        ot = self._order_type()
        try:
            order = self.broker.place_order(cand.code, Side.BUY, d.qty, ot,
                                            price=price if ot == OrderType.LIMIT else None,
                                            name=cand.name, reason=d.kind)
        except BrokerError as e:
            self._emit("error", "warn", "매수 실패", f"{cand.name}: {e}")
            return
        self.states.setdefault(cand.code, PositionState(cand.code)).on_buy(d.qty, price)
        self._persist_state(cand.code)
        self._record_order(order)
        self._emit("entry", "info", "매수 접수", f"{cand.name} {d.kind} {d.qty}주 @ {price:,}")

    def _sell(self, pos: Position, d, price: int) -> None:
        if self._dry_log(f"sell:{pos.code}:{d.reason}", f"매도 시뮬 {pos.name} {d.reason} {d.qty}주 @ {price:,}"):
            return
        ot = self._order_type()
        try:
            order = self.broker.place_order(pos.code, Side.SELL, d.qty, ot,
                                            price=price if ot == OrderType.LIMIT else None,
                                            name=pos.name, reason=d.reason)
        except BrokerError as e:
            self._emit("error", "warn", "매도 실패", f"{pos.name}: {e}")
            return
        st = self.states.setdefault(pos.code, PositionState(pos.code))
        if d.mark_partial_sold:
            st.on_partial_sell(price)
            self._persist_state(pos.code)
        realized = (price - pos.avg_price) * d.qty
        self.day_realized_pnl += realized
        self._record_order(order)
        self._emit("exit", "info", "매도 접수",
                   f"{pos.name} {d.reason} {d.qty}주 @ {price:,} (실현 {realized:,})")

    def kill(self) -> None:
        if not self.live:
            logger.warning("[DRY] kill 요청 — 드라이런이라 주문 없이 status=stopped")
            self.status = "stopped"
            return
        self._emit("kill", "critical", "긴급정지(kill)", "전량 시장가 청산 시작")
        try:
            positions = self.broker.get_positions()
        except BrokerError:
            positions = list(self.positions.values())
        for pos in positions:
            try:
                order = self.broker.place_order(pos.code, Side.SELL, pos.qty, OrderType.MARKET,
                                                name=pos.name, reason="kill")
                self._record_order(order)
            except BrokerError as e:
                self._emit("error", "critical", "청산 실패", f"{pos.name}: {e} — 수동 개입 필요")
        self.status = "stopped"
        self._heartbeat(False)

    def close_position(self, code: str) -> str:
        pos = self.positions.get(code)
        if not pos:
            return "보유 없음"
        if not self.live:
            return "드라이런 — 주문 안 함"
        try:
            order = self.broker.place_order(code, Side.SELL, pos.qty, OrderType.MARKET,
                                            name=pos.name, reason="manual")
            self._record_order(order)
        except BrokerError as e:
            return f"청산 실패: {e}"
        self._emit("exit", "info", "수동 청산", f"{pos.name} 전량 청산 주문")
        return f"{pos.name} 청산 주문"

    # ── 헬퍼 ──────────────────────────────────────────
    def _price(self, code: str):
        try:
            return self.broker.get_price(code)
        except BrokerError:
            return None

    def _at_limit_up(self, code: str, price: int) -> bool:
        if not self.params.sell_all_on_limit_up:
            return False
        pc = self.prev_close.get(code)
        return bool(pc and price >= pc * (1 + self.params.limit_up_pct / 100))

    def _maybe_daily_reset(self, now: datetime) -> None:
        d = now.date()
        if self._day != d:
            self._day = d
            self.day_realized_pnl = 0
            self._dry_logged.clear()

    def _record_order(self, order) -> None:
        try:
            self.relay.insert_order(order)
        except Exception:
            logger.exception("order 기록 실패")

    def _heartbeat(self, market: bool) -> None:
        fields = {"status": self.status, "market_open": market,
                  "day_pnl": self.day_realized_pnl, "positions_cnt": len(self.positions)}
        try:
            bal = self.broker.get_balance()
            fields.update(equity=bal.equity, cash=bal.cash)
        except Exception:
            pass
        try:
            self.relay.push_bot_state(**fields)
        except Exception:
            logger.exception("하트비트 실패")

    def _emit(self, type: str, severity: str, title: str, message: str = "") -> None:
        logger.info("[%s] %s %s", severity, title, message)
        if severity not in ("info", "warn", "high", "critical"):
            severity = "info"
        try:
            self.relay.insert_event(type=type, severity=severity, title=title, message=message)
        except Exception:
            logger.exception("event 기록 실패")
