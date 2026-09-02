"""장 시간 판단 (KST). 정규장 09:00~15:30, 주말·공휴일 제외. docs/00 §5."""
from __future__ import annotations

from datetime import date, datetime, time

import holidays  # type: ignore

_KR = holidays.KR()
OPEN = time(9, 0)
CLOSE = time(15, 30)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _KR


def is_market_open(now: datetime) -> bool:
    """now(KST)가 정규장 시간인지."""
    return is_trading_day(now.date()) and OPEN <= now.time() <= CLOSE
