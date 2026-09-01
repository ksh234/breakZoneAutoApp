"""candidates.build_candidates 단위 테스트 — 모든 외부 I/O mock (네트워크 없음)."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from src.analysis import candidates as cand
from src.analysis import kind_fetcher as kf


def _weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


RELEASE = date(2026, 4, 16)
TRADING_DAYS = _weekdays(date(2026, 3, 1), RELEASE)
T5 = kf._n_business_days_before(TRADING_DAYS, RELEASE, 5)
T15 = kf._n_business_days_before(TRADING_DAYS, RELEASE, 15)
RANGE_DAYS = [d for d in TRADING_DAYS if T15 <= d <= T5]


def _fake_ohlcv() -> pd.DataFrame:
    """T15..T5 구간 종가 df. T15=500, T5=1000, 최고가=1200, 나머지=800."""
    closes = []
    for d in RANGE_DAYS:
        if d == T15:
            closes.append(500)
        elif d == T5:
            closes.append(1000)
        elif d == RANGE_DAYS[len(RANGE_DAYS) // 2]:
            closes.append(1200)   # 구간 최고가
        else:
            closes.append(800)
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in RANGE_DAYS])
    return pd.DataFrame({"종가": closes}, index=idx)


def _stock(code="005930", name="삼성전자"):
    return kf.WarningStock(code=code, name=name,
                           designated_date=date(2026, 4, 1), release_date=RELEASE)


def test_happy_candidate_values():
    fake_mod = MagicMock()
    fake_mod.get_market_ohlcv_by_date.return_value = _fake_ohlcv()
    with patch.object(cand.kind_fetcher, "get_warning_stocks",
                      return_value=([_stock()], TRADING_DAYS)), \
         patch.object(cand.pykrx_fetcher, "_get_stock_module", return_value=fake_mod), \
         patch.object(cand.naver_fetcher, "get_current_price", return_value=900):
        result = cand.build_candidates()

    assert len(result) == 1
    c = result[0]
    # price1=1000*1.6=1600, price2=500*2=1000, price3(max)=1200 → release=min=1000
    assert c.t5_close == 1000
    assert c.t15_close == 500
    assert c.recent_15_high == 1200
    assert c.release_amount == 1000
    assert c.current_price == 900
    # drop = (1000-900)/1000*100 = 10
    assert c.drop_ratio == 10
    assert c.status == "ok"
    assert c.signal == "none"


def test_no_price_option_skips_current():
    fake_mod = MagicMock()
    fake_mod.get_market_ohlcv_by_date.return_value = _fake_ohlcv()
    with patch.object(cand.kind_fetcher, "get_warning_stocks",
                      return_value=([_stock()], TRADING_DAYS)), \
         patch.object(cand.pykrx_fetcher, "_get_stock_module", return_value=fake_mod):
        result = cand.build_candidates(fetch_current_price=False)
    c = result[0]
    assert c.current_price is None
    assert c.drop_ratio is None
    assert c.status == "partial"      # current 없음 → partial


def test_unmapped_code_is_pending():
    with patch.object(cand.kind_fetcher, "get_warning_stocks",
                      return_value=([_stock(code="")], TRADING_DAYS)):
        result = cand.build_candidates()
    c = result[0]
    assert c.status == "pending"
    assert c.release_amount is None
    assert "매핑 실패" in (c.error or "")


def test_per_stock_failure_isolated():
    """한 종목이 예기치 못한 예외로 실패해도 나머지는 정상 산출된다(격리)."""
    good, bad = _stock(code="005930", name="삼성전자"), _stock(code="000660", name="SK하이닉스")

    def _price(code):
        if code == "005930":
            return 900
        raise RuntimeError("net")   # NaverFetchError 아닌 예기치 못한 예외 → 종목 전체 실패

    fake_mod = MagicMock()
    fake_mod.get_market_ohlcv_by_date.return_value = _fake_ohlcv()
    with patch.object(cand.kind_fetcher, "get_warning_stocks",
                      return_value=([good, bad], TRADING_DAYS)), \
         patch.object(cand.pykrx_fetcher, "_get_stock_module", return_value=fake_mod), \
         patch.object(cand.naver_fetcher, "get_current_price", side_effect=_price):
        result = cand.build_candidates()
    assert len(result) == 2
    by_code = {c.code: c for c in result}
    assert by_code["005930"].status == "ok"          # 정상 종목은 영향 없음
    assert by_code["000660"].status == "error"       # 실패 종목은 error 로 격리
    assert "net" in (by_code["000660"].error or "")


def test_to_row_serializes_dates():
    c = cand.Candidate(
        code="005930", name="삼성전자",
        designated_date=date(2026, 4, 1), release_date=RELEASE,
        t5_close=1000, t15_close=500, recent_15_high=1200,
        release_amount=1000, current_price=900, drop_ratio=10, status="ok",
    )
    row = c.to_row()
    assert row["designated_date"] == "2026-04-01"
    assert row["release_date"] == "2026-04-16"
    assert row["signal"] == "none"
