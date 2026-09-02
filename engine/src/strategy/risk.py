"""리스크 가드 — 모든 주문이 통과해야 하는 검사. 절대 우회 금지. docs/03 §3, docs/05.

순수 함수(스칼라 입력 → 판정). 실패 시 사유 문자열 → 호출측이 주문 차단 + risk_block 이벤트.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .params import StrategyParams

# 국내주식 가격제한폭(±30%). 가격 sanity 2차 방어.
PRICE_LIMIT_PCT = 0.30


@dataclass
class RiskResult:
    ok: bool
    reason: str = ""


def ok_buy(
    *, qty: int, price: int, params: StrategyParams, cash: int,
    positions_cnt: int, holding: bool, invested_krw: int,
    pending_same_dir: bool, unrealized_pnl: int,
    prev_close: Optional[int] = None,
) -> RiskResult:
    """매수 주문 리스크 검사. unrealized_pnl=보유 전체 평가손익(음수=평가손실)."""
    if qty <= 0:
        return RiskResult(False, "수량 0 이하")
    amount = qty * price
    if amount > cash:
        return RiskResult(False, f"현금 부족(주문 {amount:,} > 현금 {cash:,})")
    if invested_krw + amount > params.per_stock_krw:
        return RiskResult(False, f"종목 예산 초과(누적 {invested_krw+amount:,} > {params.per_stock_krw:,})")
    if not holding and positions_cnt >= params.max_positions:
        return RiskResult(False, f"최대 보유종목수({params.max_positions}) 도달")
    if pending_same_dir:
        return RiskResult(False, "동일종목 매수 미체결 주문 존재(중복주문 차단)")
    if unrealized_pnl <= -params.max_unrealized_loss_krw:
        return RiskResult(False, f"평가손실 한도({params.max_unrealized_loss_krw:,}) 도달 — 신규진입 중단")
    if prev_close and prev_close > 0:
        if price > prev_close * (1 + PRICE_LIMIT_PCT) or price < prev_close * (1 - PRICE_LIMIT_PCT):
            return RiskResult(False, f"가격 sanity 이탈(현재가 {price:,} vs 전일 {prev_close:,})")
    return RiskResult(True)


def ok_sell(*, qty: int, held_qty: int) -> RiskResult:
    """매도 주문 리스크 검사(청산은 일손실 상한과 무관 — 항상 허용)."""
    if qty <= 0:
        return RiskResult(False, "수량 0 이하")
    if qty > held_qty:
        return RiskResult(False, f"보유수량 초과(매도 {qty} > 보유 {held_qty})")
    return RiskResult(True)


def clamp_real_mode(params: StrategyParams) -> StrategyParams:
    """mode='real' 실전 하드 상한 강제(docs/05). Phase 7 에서 값 확정 — 지금은 골격.

    설정이 더 크더라도 보수적 상한으로 클램프. (실전 전환 게이트 전까지 실제 적용 안 함)
    """
    if params.mode != "real":
        return params
    # TODO(Phase 7): 카나리 한도 확정 후 클램프 적용.
    return params
