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
from ..broker.models import Order, OrderType, Position, Side
from ..relay import DryRunRelay, Relay
from .indicators import Envelope, compute_envelope
from .market import is_market_open
from .params import StrategyParams
from .risk import ok_buy, ok_sell
from .rules import should_enter, should_exit
from .state import PositionState

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
BUY_GRACE_SEC = 600  # 매수 주문 후 이 시간 동안은 잔고에 안 보여도 전략상태를 지우지 않음(체결 지연·잔고 반영 지연)
FILL_GRACE_SEC = 30  # 매도 전량체결 직후 잔고 반영 지연 동안 같은 종목 재매도 금지(중복 매도 방지)
PARAMS_RELOAD_SEC = 30  # settings 주기 재로드(앱 set_param 명령 유실·대시보드 직접 수정 대비 안전망)
DAY_PNL_REFRESH_SEC = 30  # 당일 실현손익(브로커 ka10077) 재조회 주기


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
        self._buy_at: dict[str, datetime] = {}  # 종목별 마지막 매수 주문 시각(상태 보호 유예용)
        # 체결 추적(2026-09-28): broker_order_id → {db_id, code, name, side, qty, price, avg_price, filled, reason}
        # 매 tick 미체결 조회로 체결수량을 갱신해 orders 테이블·실현손익에 반영. 재시작 시 추적 소실(문서화).
        self._open_orders: dict[str, dict] = {}
        self._sell_done_at: dict[str, datetime] = {}  # 종목별 매도 전량체결 시각(FILL_GRACE_SEC 재매도 금지)
        self._day_pnl_at: datetime | None = None      # 당일 실현손익 마지막 조회 시각
        self._cancel_requested: set[str] = set()      # 취소 요청 보낸 주문번호(중복 취소 요청 방지)
        self._dev_since: dict[str, datetime] = {}     # 주문번호별 "현재가-주문가 괴리 ≥ 기준" 상태 시작 시각

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
                    partial_sell_price=int(r.get("partial_sell_price") or 0),
                    last_buy_price=int(r.get("last_buy_price") or 0))
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
                    last_buy_price=st.last_buy_price if st else 0,
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
        # 어제까지만: 오늘 날짜를 포함하면 pykrx 가 장중 현재가를 오늘 '종가'로 돌려줘
        # prev_close=오늘가 → 상한가 판정 불가, envelope 에도 오늘가 혼입 (2026-09-28 버그 수정)
        end = self._now().date() - timedelta(days=1)
        start = end - timedelta(days=self.params.env_period * 3 + 20)
        for code in codes:
            try:
                closes = pykrx_fetcher.get_close_range(code, start, end)
            except Exception:
                closes = []
            if closes:
                self.prev_close[code] = closes[-1]
                env = compute_envelope(closes, self.params.env_period, self.params.env_band / 100)
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
        unfilled = self._unfilled_orders()
        pending = {u["code"] for u in unfilled}
        fills = self._order_fills()
        self._sync_fills(fills)
        self._cancel_stale_orders(fills, now)
        self.sync_positions(pending)
        self._sync_candidate_display()
        self._update_candidate_lows()
        self._evaluate_exits(pending)
        self._evaluate_entries(pending)
        self._heartbeat(market)

    def _state_protected(self, code: str, pending: set[str]) -> bool:
        """잔고에 없어도 전략상태를 지우면 안 되는 경우: 매수 미체결 주문 있음 / 최근 BUY_GRACE_SEC 내 매수 주문.
        (2026-09-22 버그: 첫 매수 직후 잔고 반영 전에 상태가 지워져 분할횟수·누적액이 0부터 다시 세어짐 → 예산 상한 무력화)"""
        if code in pending:
            return True
        t = self._buy_at.get(code)
        return bool(t and (self._now() - t).total_seconds() < BUY_GRACE_SEC)

    def sync_positions(self, pending: set[str] | None = None) -> None:
        pending = pending or set()
        try:
            positions = self.broker.get_positions()
        except BrokerError:
            logger.exception("포지션 조회 실패")
            return
        self.positions = {p.code: p for p in positions}
        for code, p in self.positions.items():
            if code not in self.states:  # 재시작/외부매수 복원: 보유=1회 매수로 간주
                self.states[code] = PositionState(code, entries_done=1, invested_krw=p.avg_price * p.qty,
                                                  last_buy_price=p.avg_price)
        for code in list(self.states):    # 청산 완료분 정리
            if code not in self.positions:
                if self._state_protected(code, pending):
                    continue
                self.states.pop(code, None)
                self._buy_at.pop(code, None)
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

    def _unfilled_orders(self) -> list[dict]:
        try:
            return self.broker.get_unfilled_orders()
        except Exception:
            return []

    def _pending_codes(self) -> set[str]:
        return {u["code"] for u in self._unfilled_orders()}

    def _order_fills(self) -> list[dict]:
        try:
            return self.broker.get_order_fills()
        except Exception:
            logger.exception("체결 조회 실패")
            return []

    # ── 미체결 취소 ───────────────────────────────────
    def _cancel_stale_orders(self, fills: list[dict], now: datetime) -> None:
        """미체결 취소(2026-09-28 사용자 설정, 같은 날 업그레이드):
        현재가가 주문가에서 `unfilled_cancel_dev_pct`% 이상 벗어난 상태가 `unfilled_cancel_min`분 이상 **지속**되면
        취소(매수·매도 공통, 추적 여부 무관). 괴리율 0 이면 접수 후 경과시간만으로 취소. 취소 후 다음 tick 부터 재평가."""
        limit = self.params.unfilled_cancel_min
        dev_lim = self.params.unfilled_cancel_dev_pct
        if limit <= 0 or not self.live:
            return
        seen: set[str] = set()
        for f in fills:
            ord_no = f["ord_no"]
            if f.get("unfilled_qty", 0) <= 0 or ord_no in self._cancel_requested:
                continue
            seen.add(ord_no)
            # 기준 시각: 괴리율 0 → 접수 시각 / 괴리율>0 → 괴리 상태가 시작된 시각(연속 유지 중일 때만)
            if dev_lim > 0:
                price = self._price(f["code"])
                op = f.get("order_price") or 0
                if not price or not op:
                    continue
                dev = abs(price - op) / op * 100
                if dev < dev_lim:
                    self._dev_since.pop(ord_no, None)          # 괴리 해소 → 타이머 리셋
                    continue
                start = self._dev_since.setdefault(ord_no, now)
                why = f"현재가 {price:,} vs 주문가 {op:,} 괴리 {dev:.1f}%(기준 {dev_lim:g}%) {((now - start).total_seconds() / 60):.0f}분 지속(기준 {limit}분)"
            else:
                tm = f.get("order_time") or ""
                if len(tm) < 6:
                    continue
                try:
                    start = now.replace(hour=int(tm[:2]), minute=int(tm[2:4]), second=int(tm[4:6]), microsecond=0)
                except ValueError:
                    continue
                why = f"접수 후 {((now - start).total_seconds() / 60):.0f}분 경과(기준 {limit}분)"
            if (now - start).total_seconds() / 60 < limit:
                continue
            o = self._open_orders.get(ord_no)
            order = Order(code=f["code"], name=(o or {}).get("name", f["code"]),
                          side=Side.SELL if (o or {}).get("side") == "sell" else Side.BUY,
                          qty=f["qty"], order_type=OrderType.LIMIT, broker_order_id=ord_no)
            try:
                self.broker.cancel(order)
            except BrokerError as e:
                self._emit("error", "warn", "미체결 취소 실패", f"{order.name} ord_no={ord_no}: {e}")
                continue
            self._cancel_requested.add(ord_no)
            self._dev_since.pop(ord_no, None)
            self._emit("cancel", "info", "미체결 취소",
                       f"{order.name} 주문 {ord_no} — {why}, 미체결 {f['unfilled_qty']}/{f['qty']}주")
        for k in list(self._dev_since):                         # 사라진 주문의 타이머 정리
            if k not in seen:
                self._dev_since.pop(k, None)

    # ── 체결 동기화 ───────────────────────────────────
    def _sync_fills(self, fills_list: list[dict]) -> None:
        """추적 중인 주문의 체결을 **브로커 체결 조회(ka10076) 실데이터**로 갱신 → orders(filled_qty/filled_price/status).
        실현손익은 여기서 계산하지 않음(브로커 당일실현손익을 하트비트에서 조회, D-016)."""
        if not self._open_orders:
            return
        fills = {f["ord_no"]: f for f in fills_list}
        for ord_no, o in list(self._open_orders.items()):
            f = fills.get(ord_no)
            if not f:
                continue
            filled = f["filled_qty"]
            canceled = ("취소" in f.get("status", "")) or ("확인" in f.get("status", ""))
            done = (not canceled) and (filled >= o["qty"] or (f["unfilled_qty"] == 0 and filled > 0))
            if filled <= o["filled"] and not canceled:
                continue
            o["filled"] = filled
            fields = {"filled_qty": filled, "status": "filled" if done else ("canceled" if canceled else "partial")}
            if f.get("filled_price"):
                fields["filled_price"] = f["filled_price"]
            if done:
                fields["filled_at"] = self._now().isoformat()
            try:
                self.relay.update_order(o["db_id"], **fields)
            except Exception:
                logger.exception("order 체결 갱신 실패 %s", ord_no)
            if done or canceled:
                self._open_orders.pop(ord_no, None)
                self._cancel_requested.discard(ord_no)
                if o["side"] == "sell" and filled > 0:
                    self._sell_done_at[o["code"]] = self._now()
                side = "매도" if o["side"] == "sell" else "매수"
                if done:
                    self._emit("fill", "info", f"{side} 체결 완료",
                               f"{o['name']} {filled}주 @ {f.get('filled_price') or o['price']:,} "
                               f"(수수료 {f.get('commission', 0):,} 세금 {f.get('tax', 0):,})")
                else:
                    self._emit("fill", "warn", f"{side} 주문 취소/만료", f"{o['name']} 체결 {filled}/{o['qty']}주")
            else:
                logger.info("부분체결 %s %s %d/%d", o["name"], o["side"], filled, o["qty"])

    def _expire_open_orders(self) -> None:
        """날짜가 바뀌면 남은 추적 주문은 당일 만료(취소)로 마감."""
        for ord_no, o in list(self._open_orders.items()):
            try:
                self.relay.update_order(o["db_id"], status="canceled", filled_qty=o["filled"])
            except Exception:
                logger.exception("order 만료 처리 실패 %s", ord_no)
        self._open_orders.clear()

    def _evaluate_exits(self, pending: set[str]) -> None:
        for code, pos in list(self.positions.items()):
            t = self._sell_done_at.get(code)
            if t and (self._now() - t).total_seconds() < FILL_GRACE_SEC:
                continue   # 전량체결 직후 잔고 반영 대기 — 중복 매도 방지
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
            # 미보유 종목의 빈 상태를 states 에 넣지 않는다(넣으면 체결 후 sync_positions 의 잔고 기반 복원이 막힘)
            st = self.states.get(code) or PositionState(code)
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
        self._buy_at[cand.code] = self._now()
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
        self._record_order(order, avg_price=pos.avg_price)
        self._emit("exit", "info", "매도 접수", f"{pos.name} {d.reason} {d.qty}주 @ {price:,}")

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
                self._record_order(order, avg_price=pos.avg_price)
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
            self._record_order(order, avg_price=pos.avg_price)
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
            if self._day is not None:
                self._expire_open_orders()
            self._day = d
            self.day_realized_pnl = 0
            self._dry_logged.clear()

    def _record_order(self, order, avg_price: int | None = None) -> None:
        try:
            db_id = self.relay.insert_order(order)
        except Exception:
            logger.exception("order 기록 실패")
            return
        if db_id and order.broker_order_id:
            price = order.price or self._price(order.code) or 0
            self._open_orders[order.broker_order_id] = {
                "db_id": db_id, "code": order.code, "name": order.name, "side": order.side.value,
                "qty": order.qty, "price": price, "avg_price": avg_price or 0, "filled": 0,
                "reason": order.reason}

    def _refresh_day_pnl(self) -> None:
        """당일 실현손익 = 브로커 값(수수료·세금 차감, D-016). DAY_PNL_REFRESH_SEC 마다. 실패 시 이전 값 유지."""
        now = self._now()
        if self._day_pnl_at and (now - self._day_pnl_at).total_seconds() < DAY_PNL_REFRESH_SEC:
            return
        self._day_pnl_at = now
        try:
            v = self.broker.get_day_realized_pnl()
        except Exception:
            v = None
        if v is not None:
            self.day_realized_pnl = v

    def _heartbeat(self, market: bool) -> None:
        self._refresh_day_pnl()
        fields = {"status": self.status, "market_open": market,
                  "day_pnl": self.day_realized_pnl, "positions_cnt": len(self.positions)}
        try:
            bal = self.broker.get_balance()
            fields.update(equity=bal.equity, cash=bal.cash, stock_value=bal.stock_value,
                          deposit=bal.deposit, unrealized_pnl=bal.unrealized_pnl)
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
