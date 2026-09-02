"""broker 패키지 — 증권사 독립 어댑터 + 키움 구현체.

전략 코드는 `BrokerAdapter` 와 models(Order/Position/Balance/Side/OrderType)만 사용한다.
"""
from __future__ import annotations

from .base import BrokerAdapter
from .errors import AuthError, BrokerError, OrderRejected, RateLimited, TransientError
from .models import Balance, Order, OrderStatus, OrderType, Position, Side

__all__ = [
    "BrokerAdapter", "create_broker",
    "Order", "Position", "Balance", "Side", "OrderType", "OrderStatus",
    "BrokerError", "AuthError", "OrderRejected", "RateLimited", "TransientError",
]


def create_broker(app_key: str, secret: str, account_no: str = "", mode: str = "demo", **kw) -> BrokerAdapter:
    """설정으로 브로커 구현체 생성. 지금은 키움 하나뿐(팩토리 경계만 마련)."""
    from .kiwoom import KiwoomRestBroker
    return KiwoomRestBroker(app_key, secret, account_no, mode=mode, **kw)
