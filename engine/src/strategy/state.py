"""포지션 전략상태 — 분할매수/매도 추적 (브로커 잔고 외 엔진 로컬). docs/03 §2.2b."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionState:
    code: str
    entries_done: int = 0        # 분할매수 실행 횟수
    invested_krw: int = 0        # 누적 매수금액(종목당 총액 상한 체크용)
    partial_sold: bool = False   # 첫 분할매도(익절) 실행 여부
    peak_since_partial: int = 0  # 분할매도 이후 고점(트레일링 기준)

    def on_buy(self, qty: int, price: int) -> None:
        self.entries_done += 1
        self.invested_krw += qty * price

    def on_partial_sell(self, price: int) -> None:
        self.partial_sold = True
        self.peak_since_partial = max(self.peak_since_partial, price)

    def update_peak(self, price: int) -> None:
        if self.partial_sold and price > self.peak_since_partial:
            self.peak_since_partial = price
