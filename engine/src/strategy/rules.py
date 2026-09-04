"""진입/청산 규칙 — 순수 함수(외부 의존 0). docs/03 §2. 100% 단위테스트 대상.

전략 수치는 StrategyParams 로 주입 → 앱에서 조절 가능.
외부 데이터(현재가·envelope·상한가여부)는 인자로 받고, 여기선 판정만 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .indicators import Envelope
from .params import StrategyParams
from .state import PositionState


@dataclass
class EnterDecision:
    enter: bool
    qty: int = 0
    kind: str = ""      # 'new' | 'add'
    note: str = ""


@dataclass
class ExitDecision:
    exit: bool
    qty: int = 0
    reason: str = ""    # 'take_profit_partial' | 'trailing_stop' | 'limit_up'
    mark_partial_sold: bool = False
    note: str = ""


def _no_enter(note: str) -> EnterDecision:
    return EnterDecision(False, note=note)


def should_enter(
    *, drop_ratio: Optional[float], status: str, price: Optional[int],
    env: Optional[Envelope], params: StrategyParams, state: PositionState,
    holding: bool, avg_price: Optional[int], positions_cnt: int, cash: int,
    release_passed: bool = False, low_price: Optional[int] = None,
) -> EnterDecision:
    """매수 판정. 신규 진입(E1) 또는 추가매수/물타기(E2)."""
    if not params.enabled:
        return _no_enter("자동매매 off")
    if not price or price <= 0 or env is None:
        return _no_enter("시세/envelope 없음")
    # 매수 적기는 해제일 이전(T-5~해제일). 해제일 지난 종목은 신규·추가 매수 제외.
    if release_passed:
        return _no_enter("해제일 지남 — 매수 제외")

    # 최소 매수가 필터(신규·추가매수 공통). 0 이면 무제한.
    if params.min_price and price < params.min_price:
        return _no_enter(f"현재가 {price} < 최소매수가 {params.min_price}")

    # 분할매수 예산·횟수 상한
    remaining = params.per_stock_krw - state.invested_krw
    if remaining <= 0 or state.entries_done >= params.max_entries:
        return _no_enter("종목 예산/횟수 소진")
    one = min(params.one_buy_krw(), remaining, cash)
    qty = one // price
    if qty < 1:
        return _no_enter("주문가능수량 0(현금/예산 부족)")

    # 값 확정 게이트: 해제금액·하락비율이 정확하려면 T-5·T-15·최고가·현재가가 모두
    # 확정돼야 함(status=='ok'). 하나라도 없으면 신규·추가매수 금지. (사용자 규칙, 2026-09-03)
    if status != "ok":
        return _no_enter(f"값 미확정(status={status}) — 해제금액/하락비율 부정확")

    if not holding:
        # E1 · 신규 진입
        if drop_ratio is None:
            return _no_enter("drop_ratio 없음")
        if drop_ratio < params.entry_drop_pct:
            return _no_enter(f"drop_ratio {drop_ratio} < 기준 {params.entry_drop_pct}")
        # 저점 반등 확인: 매수구간 저가 대비 entry_rebound_pct 이상 상승해야 매수(급락 중 매수 방지)
        if params.entry_rebound_pct > 0:
            if not low_price or price < low_price * (1 + params.entry_rebound_pct):
                return _no_enter(f"저점 반등 대기(저가 {low_price} 대비 +{params.entry_rebound_pct:.0%} 미달)")
        if not (price < env.lower):
            return _no_enter("현재가가 envelope 하단 위")
        if positions_cnt >= params.max_positions:
            return _no_enter("최대 보유종목수 도달")
        return EnterDecision(True, qty, "new", "신규진입")

    # E2 · 추가매수(물타기): 평단 대비 add_on_drop_pct 하락
    if avg_price and price <= avg_price * (1 - params.add_on_drop_pct):
        return EnterDecision(True, qty, "add", f"평단대비 {params.add_on_drop_pct:.0%} 하락")
    return _no_enter("추가매수 조건 미충족")


def should_exit(
    *, qty: int, avg_price: Optional[int], price: Optional[int],
    env: Optional[Envelope], params: StrategyParams, state: PositionState,
    at_limit_up: bool = False,
) -> ExitDecision:
    """매도 판정. 분할익절(X1) 시작 → 이후 트레일링(X2)/상한가(X3) 전량."""
    if qty <= 0 or not price or price <= 0:
        return ExitDecision(False, note="시세/수량 없음")
    pnl_pct = (price / avg_price - 1) * 100 if avg_price else 0.0

    if not state.partial_sold:
        # X1 · 분할익절 시작
        if env is not None and price > env.upper and pnl_pct >= params.take_profit_pct:
            sell_qty = max(1, int(qty * params.first_sell_portion))
            return ExitDecision(True, sell_qty, "take_profit_partial", mark_partial_sold=True,
                                note=f"+{pnl_pct:.1f}% & env상단 돌파")
        return ExitDecision(False, note="익절 조건 미충족")

    # 분할매도 이후: 잔량 전량 청산 트리거 (우선순위: 상한가 → 2차 상승 → 트레일링)
    if params.sell_all_on_limit_up and at_limit_up:
        return ExitDecision(True, qty, "limit_up", note="상한가 전량")
    # X2b · 2차 상승 전량매도: 1차(분할) 매도가 대비 +post_sell_gain_pct% 도달 (0=끔)
    if params.post_sell_gain_pct > 0 and state.partial_sell_price > 0:
        target = round(state.partial_sell_price * (1 + params.post_sell_gain_pct / 100))  # 원 단위(부동소수 오차 방지)
        if price >= target:
            return ExitDecision(True, qty, "post_sell_gain",
                                note=f"1차 매도가 {state.partial_sell_price} 대비 +{params.post_sell_gain_pct:g}% 도달")
    peak = state.peak_since_partial or price
    if price <= peak * (1 - params.post_sell_stop_pct):
        return ExitDecision(True, qty, "trailing_stop",
                            note=f"고점 {peak} 대비 -{params.post_sell_stop_pct:.0%}")
    return ExitDecision(False, note="보유 유지")
