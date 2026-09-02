"""market.is_market_open 테스트."""
from __future__ import annotations

from datetime import datetime

from src.strategy.market import is_market_open, is_trading_day


def test_weekend_closed():
    assert not is_market_open(datetime(2026, 9, 5, 10, 0))  # 토
    assert not is_market_open(datetime(2026, 9, 6, 10, 0))  # 일


def test_hours_on_trading_day():
    d = datetime(2026, 9, 2, 10, 0)  # 수
    if is_trading_day(d.date()):
        assert is_market_open(datetime(2026, 9, 2, 10, 0))     # 장중
        assert not is_market_open(datetime(2026, 9, 2, 8, 0))  # 장전
        assert not is_market_open(datetime(2026, 9, 2, 16, 0)) # 장후
