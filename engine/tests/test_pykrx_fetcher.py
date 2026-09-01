"""pykrx_fetcher.py 단위 테스트 — pykrx 외부 호출은 mock 처리."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.analysis import pykrx_fetcher as pf
from src.analysis.pykrx_fetcher import (
    PykrxFetchError,
    get_close,
    get_close_range,
    get_previous_business_day,
    get_trading_days,
    n_business_days_before,
)


def _make_ohlcv(dates: list[str], closes: list[int] | None = None) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    closes = closes or [10000] * len(dates)
    return pd.DataFrame({"종가": closes}, index=idx)


# ── 매매일 유틸 ───────────────────────────────────────
class TestTradingDays:
    def test_get_trading_days_happy(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = _make_ohlcv(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        )
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = get_trading_days(date(2024, 1, 1), date(2024, 1, 5))
        assert result == [
            date(2024, 1, 2), date(2024, 1, 3),
            date(2024, 1, 4), date(2024, 1, 5),
        ]

    def test_get_trading_days_reversed(self):
        result = get_trading_days(date(2024, 1, 10), date(2024, 1, 5))
        assert result == []

    def test_get_trading_days_empty(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = pd.DataFrame()
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = get_trading_days(date(2024, 1, 1), date(2024, 1, 5))
        assert result == []

    def test_get_trading_days_error_wrapped(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.side_effect = RuntimeError("network")
        with patch.object(pf, "_get_stock_module", return_value=fake):
            with pytest.raises(PykrxFetchError):
                get_trading_days(date(2024, 1, 1), date(2024, 1, 5))


class TestPreviousBusinessDay:
    def test_returns_latest_in_range(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = _make_ohlcv(
            ["2026-04-14", "2026-04-15", "2026-04-16"]
        )
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = get_previous_business_day(date(2026, 4, 16))
        assert result == date(2026, 4, 16)

    def test_error_when_no_days(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = pd.DataFrame()
        with patch.object(pf, "_get_stock_module", return_value=fake):
            with pytest.raises(PykrxFetchError):
                get_previous_business_day(date(2026, 4, 16))


class TestNBusinessDaysBefore:
    def test_happy(self):
        """4월 16일(목) 에서 5 매매일 이전 = 4월 9일(목). 주말 2회 끼임."""
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = _make_ohlcv([
            "2026-04-08", "2026-04-09", "2026-04-10",  # 수/목/금
            "2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16",  # 월~목
        ])
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = n_business_days_before(date(2026, 4, 16), 5)
        # base 이하 매매일: [4/8, 4/9, 4/10, 4/13, 4/14, 4/15, 4/16]
        # 5 매매일 이전 = filtered[-(5+1)] = filtered[-6] = 4/9
        assert result == date(2026, 4, 9)

    def test_n_must_be_positive(self):
        with pytest.raises(ValueError):
            n_business_days_before(date(2026, 4, 16), 0)

    def test_insufficient_days(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = _make_ohlcv([
            "2026-04-15", "2026-04-16"
        ])
        with patch.object(pf, "_get_stock_module", return_value=fake):
            with pytest.raises(PykrxFetchError):
                n_business_days_before(date(2026, 4, 16), 5)


# ── 종가 조회 ────────────────────────────────────────
class TestClose:
    def test_get_close_returns_int(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = _make_ohlcv(
            ["2026-04-15"], closes=[12345]
        )
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = get_close("005930", date(2026, 4, 15))
        assert result == 12345

    def test_get_close_empty_df_returns_none(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = pd.DataFrame()
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = get_close("005930", date(2026, 4, 15))
        assert result is None

    def test_get_close_range_happy(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.return_value = _make_ohlcv(
            ["2026-04-01", "2026-04-02", "2026-04-03"],
            closes=[10000, 11000, 12000],
        )
        with patch.object(pf, "_get_stock_module", return_value=fake):
            result = get_close_range(
                "005930", date(2026, 4, 1), date(2026, 4, 3)
            )
        assert result == [10000, 11000, 12000]

    def test_get_close_range_reversed_returns_empty(self):
        result = get_close_range("005930", date(2026, 4, 10), date(2026, 4, 1))
        assert result == []

    def test_get_close_error_wrapped(self):
        fake = MagicMock()
        fake.get_market_ohlcv_by_date.side_effect = RuntimeError("network")
        with patch.object(pf, "_get_stock_module", return_value=fake):
            with pytest.raises(PykrxFetchError):
                get_close("005930", date(2026, 4, 15))
