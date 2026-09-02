"""BrokerAdapter — 증권사 독립 계약 (동기 버전, D-011).

전략 코드는 오직 이 인터페이스만 사용한다. 키움→한투/토스 교체 시 구현체만 바꾼다.
실시간 시세는 백그라운드 스레드가 on_tick 콜백으로 밀어준다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from .models import Balance, Order, OrderType, Position, Side


class BrokerAdapter(ABC):
    @abstractmethod
    def connect(self) -> None:
        """인증(토큰 발급). 실패 시 AuthError."""

    @abstractmethod
    def get_price(self, code: str) -> Optional[int]:
        """현재가(원). 실시간 캐시 우선, 없으면 REST 조회. 실패 시 None."""

    @abstractmethod
    def get_prices(self, codes: list[str]) -> dict[str, int]:
        """여러 종목 현재가 일괄(조회 성공분만)."""

    @abstractmethod
    def place_order(
        self, code: str, side: Side, qty: int,
        order_type: OrderType = OrderType.LIMIT,
        price: Optional[int] = None, *, name: str = "", reason: str = "",
    ) -> Order:
        """주문 제출. 성공 시 broker_order_id 채워진 Order 반환. 거부 시 OrderRejected."""

    @abstractmethod
    def cancel(self, order: Order, qty: Optional[int] = None) -> None:
        """주문 취소(qty=None 이면 잔량 전부)."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    def get_balance(self) -> Balance:
        ...

    @abstractmethod
    def subscribe_realtime(
        self, codes: list[str], on_tick: Callable[[str, int], None],
    ) -> None:
        """codes 실시간 체결가 구독. 틱마다 on_tick(code, price). 내부 스레드에서 자동 재연결."""

    def place_buy(self, code: str, qty: int, **kw) -> Order:
        return self.place_order(code, Side.BUY, qty, **kw)

    def place_sell(self, code: str, qty: int, **kw) -> Order:
        return self.place_order(code, Side.SELL, qty, **kw)

    def close(self) -> None:
        """자원 정리(WebSocket 종료 등). 기본 no-op."""
