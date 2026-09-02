"""전략 오케스트레이션 — 분석·브로커·중계·규칙을 엮는 매매 루프. docs/00 §2, docs/03 §4.

책임: 후보/지표 갱신 → 보유 청산 평가 → 후보 진입 평가 → 리스크 통과분만 주문 →
     포지션/주문/이벤트 Supabase 반영 + 하트비트 + 앱 명령 처리 + kill-switch.
전략 판정은 rules/risk(순수)에 위임. 이 파일은 배선·부수효과(주문·DB·로그)만.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..analysis import pykrx_fetcher
from ..analysis.candidates import Candidate, build_candidates
from ..broker.base import BrokerAdapter
from ..broker.errors import BrokerError
from ..broker.models import OrderType, Position, Side
from ..relay import Relay
from .indicators import Envelope, compute_envelope
from .market import is_market_open
from .params import StrategyParams
from .risk import ok_buy, ok_sell
from .rules import should_enter, should_exit
from .state import PositionState

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


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

    # ── 수명주기 / 명령 ───────────────────────────────
    def load_params(self) -> None:
        try:
            self.params = StrategyParams.from_settings(self.relay.load_settings())
        except Exception:
            logger.exception("settings 로드 실패 — 기존 파라미터 유지")

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
            self.load_params(); return "설정 반영"
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
        self.candidates = {c.code: c for c in cands if c.code}
        try:
            self.relay.upsert_candidates(cands)
        except Exception:
            logger.exception("candidates upsert 실패")
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
        self._maybe_daily_reset(now)
        market = is_market_open(now)
        if self.status != "running" or not market:
            self._heartbeat(market)
            return
        self.sync_positions()
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
        try:
            self.relay.upsert_positions(positions)
        except Exception:
            logger.exception("positions upsert 실패")

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
            st.update_peak(price)
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

    def _evaluate_entries(self, pending: set[str]) -> None:
        if not self.params.enabled:
            return
        if self.day_realized_pnl <= -self.params.daily_max_loss_krw:
            return
        try:
            cash = self.broker.get_balance().cash
        except BrokerError:
            return
        for code, cand in self.candidates.items():
            price = self._price(code)
            if not price:
                continue
            pos = self.positions.get(code)
            holding = pos is not None and pos.qty > 0
            st = self.states.setdefault(code, PositionState(code))
            d = should_enter(
                drop_ratio=cand.drop_ratio, status=cand.status, price=price,
                env=self.envelopes.get(code), params=self.params, state=st,
                holding=holding, avg_price=pos.avg_price if pos else None,
                positions_cnt=len(self.positions), cash=cash)
            if not d.enter or code in pending:
                continue
            r = ok_buy(qty=d.qty, price=price, params=self.params, cash=cash,
                       positions_cnt=len(self.positions), holding=holding,
                       invested_krw=st.invested_krw, pending_same_dir=code in pending,
                       daily_realized_pnl=self.day_realized_pnl, prev_close=self.prev_close.get(code))
            if not r.ok:
                self._emit("risk_block", "warn", "매수 차단", f"{cand.name}: {r.reason}")
                continue
            self._buy(cand, d, price)
            cash -= d.qty * price

    # ── 주문 실행 + 반영 ──────────────────────────────
    def _order_type(self) -> OrderType:
        return OrderType.LIMIT if self.params.order_type == "limit" else OrderType.MARKET

    def _buy(self, cand: Candidate, d, price: int) -> None:
        ot = self._order_type()
        try:
            order = self.broker.place_order(cand.code, Side.BUY, d.qty, ot,
                                            price=price if ot == OrderType.LIMIT else None,
                                            name=cand.name, reason=d.kind)
        except BrokerError as e:
            self._emit("error", "warn", "매수 실패", f"{cand.name}: {e}")
            return
        self.states.setdefault(cand.code, PositionState(cand.code)).on_buy(d.qty, price)
        self._record_order(order)
        self._emit("entry", "info", "매수 접수", f"{cand.name} {d.kind} {d.qty}주 @ {price:,}")

    def _sell(self, pos: Position, d, price: int) -> None:
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
        realized = (price - pos.avg_price) * d.qty
        self.day_realized_pnl += realized
        self._record_order(order)
        self._emit("exit", "info", "매도 접수",
                   f"{pos.name} {d.reason} {d.qty}주 @ {price:,} (실현 {realized:,})")

    def kill(self) -> None:
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
