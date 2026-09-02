"""브로커 데이터 모델 — 증권사 독립. (docs/01 §2)

키움 세부 필드명은 broker/kiwoom.py 의 매핑 함수에만 존재하고,
전략 코드는 여기 정의된 dataclass/enum 만 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"      # 로컬 생성, 미제출
    SUBMITTED = "submitted"  # 주문번호 수신(접수)
    PARTIAL = "partial"      # 부분체결
    FILLED = "filled"        # 전량체결
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass
class Order:
    code: str
    name: str
    side: Side
    qty: int
    order_type: OrderType
    price: Optional[int] = None          # 지정가. 시장가면 None
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: Optional[str] = None  # 키움 ord_no
    filled_qty: int = 0
    filled_price: Optional[int] = None
    reason: str = ""                     # 전략상 사유(entry/tp/sl/kill/manual)
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


@dataclass
class Position:
    code: str
    name: str
    qty: int
    avg_price: int
    current_price: int = 0

    @property
    def pnl(self) -> int:
        return (self.current_price - self.avg_price) * self.qty

    @property
    def pnl_pct(self) -> float:
        return (self.current_price / self.avg_price - 1) * 100 if self.avg_price else 0.0


@dataclass
class Balance:
    cash: int          # 주문가능현금(추정예탁자산 기준)
    equity: int        # 총평가금(현금+주식평가)
    stock_value: int   # 주식평가금
    updated_at: Optional[datetime] = None
