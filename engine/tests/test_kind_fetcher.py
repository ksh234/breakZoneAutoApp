"""kind_fetcher.py 단위 테스트 — HTML 파싱, 매핑, 순연 필터.

네트워크 호출은 하지 않음. fixtures/kind_sample.html 사용.
컬럼 구조 (투자경고 탭 menuIndex=2): [번호, 종목명, 공시일, 지정일, 해제조건]
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.analysis import kind_fetcher as kf
from src.analysis.kind_fetcher import (
    KindFetchError,
    WarningStock,
    compute_release_date,
    parse_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "kind_sample.html"


@pytest.fixture
def sample_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ─── HTML 파싱 ────────────────────────────────────────
class TestParseHtml:
    def test_returns_name_and_designated_date(self, sample_html: str):
        rows = parse_html(sample_html)
        assert len(rows) == 3
        names = [r[0] for r in rows]
        assert names == ["SK텔레콤", "삼성전자", "네이버"]

    def test_parses_multiple_date_formats(self, sample_html: str):
        rows = parse_html(sample_html)
        by_name = {r[0]: r[1] for r in rows}
        assert by_name["SK텔레콤"] == date(2026, 3, 25)
        assert by_name["삼성전자"] == date(2026, 4, 3)
        assert by_name["네이버"] == date(2026, 4, 15)  # YYYY/MM/DD 포맷

    def test_no_table_raises(self):
        html = "<html><body>No table here</body></html>"
        with pytest.raises(KindFetchError):
            parse_html(html)


# ─── 해제판단일 계산 ─────────────────────────────────
class TestComputeReleaseDate:
    def test_weekday_only_fallback(self):
        """pykrx 실패 시 주말만 제외하는 fallback."""
        # 4/16(목) + 10 평일 = 4/30(목)
        with patch.object(kf.pykrx_fetcher, "get_previous_business_day",
                          side_effect=kf.pykrx_fetcher.PykrxFetchError("mock")):
            result = compute_release_date(date(2026, 4, 16))
        assert result == date(2026, 4, 30)

    def test_uses_pykrx_when_available(self):
        def _mock_business_day(d: date) -> date:
            current = d
            while current.weekday() >= 5:
                current = current - timedelta(days=1)
            return current

        with patch.object(kf.pykrx_fetcher, "get_previous_business_day",
                          side_effect=_mock_business_day):
            result = compute_release_date(date(2026, 4, 16))
        assert result == date(2026, 4, 30)


# ─── get_warning_stocks 통합 ─────────────────────────
def _patch_calendar_fallback():
    """pykrx 호출을 실패시켜 주말 제외 fallback 매매일 캘린더를 사용하게 함."""
    return patch.object(
        kf.pykrx_fetcher, "get_trading_days",
        side_effect=kf.pykrx_fetcher.PykrxFetchError("mock"),
    )


class TestGetWarningStocks:
    def test_returns_tuple_of_stocks_and_calendar(self, sample_html: str):
        """튜플 (stocks, trading_days) 반환."""
        with patch.object(kf, "_fetch_html", return_value=sample_html), \
             patch.object(kf.ticker_mapping, "lookup", return_value=None), \
             _patch_calendar_fallback():
            result = kf.get_warning_stocks(today=date(2026, 4, 16))
        assert isinstance(result, tuple)
        assert len(result) == 2
        stocks, trading_days = result
        assert isinstance(stocks, list)
        assert isinstance(trading_days, list)
        assert len(trading_days) > 0

    def test_all_active_stocks_included_no_filter(self, sample_html: str):
        """필터 없음 — 활성 종목 3개 전부 반환."""
        with patch.object(kf, "_fetch_html", return_value=sample_html), \
             patch.object(kf.ticker_mapping, "lookup", return_value=None), \
             _patch_calendar_fallback():
            stocks, _ = kf.get_warning_stocks(today=date(2026, 4, 16))
        assert len(stocks) == 3
        names = sorted(s.name for s in stocks)
        assert names == ["SK텔레콤", "네이버", "삼성전자"]

    def test_release_date_calculated_correctly(self, sample_html: str):
        """KRX 규정: 지정일 포함 10번째 매매일."""
        with patch.object(kf, "_fetch_html", return_value=sample_html), \
             patch.object(kf.ticker_mapping, "lookup", return_value=None), \
             _patch_calendar_fallback():
            stocks, _ = kf.get_warning_stocks(today=date(2026, 4, 16))
        by_name = {s.name: s.release_date for s in stocks}
        # 지정 4/3 → release 4/16 (흥아해운 케이스와 동일)
        assert by_name["삼성전자"] == date(2026, 4, 16)
        # 지정 3/25 → release 4/7
        assert by_name["SK텔레콤"] == date(2026, 4, 7)
        # 지정 4/15 → release 4/28
        assert by_name["네이버"] == date(2026, 4, 28)

    def test_maps_code_for_known_names(self, sample_html: str):
        code_map = {"삼성전자": "005930", "SK텔레콤": "017670", "네이버": "035420"}
        with patch.object(kf, "_fetch_html", return_value=sample_html), \
             patch.object(kf.ticker_mapping, "lookup",
                          side_effect=lambda n: code_map.get(n)), \
             _patch_calendar_fallback():
            stocks, _ = kf.get_warning_stocks(today=date(2026, 4, 16))
        by_name = {s.name: s.code for s in stocks}
        assert by_name["삼성전자"] == "005930"
        assert by_name["SK텔레콤"] == "017670"
        assert by_name["네이버"] == "035420"

    def test_missing_mapping_returns_empty_code(self, sample_html: str):
        with patch.object(kf, "_fetch_html", return_value=sample_html), \
             patch.object(kf.ticker_mapping, "lookup", return_value=None), \
             _patch_calendar_fallback():
            stocks, _ = kf.get_warning_stocks(today=date(2026, 4, 16))
        assert len(stocks) == 3
        assert all(s.code == "" for s in stocks)

    def test_network_error_wrapped(self):
        with patch.object(kf.requests.Session, "get",
                          side_effect=kf.requests.ConnectionError("no net")):
            with pytest.raises(KindFetchError):
                kf.get_warning_stocks(today=date(2026, 4, 16))


# ─── 매매일 캘린더 유틸 ───────────────────────────────
class TestTradingDayUtils:
    def test_kth_business_day_on_or_after(self):
        # 이식 조정: breakZone 원본 테스트가 참조한 _n_business_days_after 는 소스에 없음.
        # 실제 함수 _kth_business_day_on_or_after(anchor 포함, k번째 1-indexed) 로 대체.
        cal = [date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15),
               date(2026, 4, 16), date(2026, 4, 17)]
        assert kf._kth_business_day_on_or_after(cal, date(2026, 4, 14), 1) == date(2026, 4, 14)
        assert kf._kth_business_day_on_or_after(cal, date(2026, 4, 14), 3) == date(2026, 4, 16)
        assert kf._kth_business_day_on_or_after(cal, date(2026, 4, 14), 10) is None

    def test_n_business_days_before(self):
        cal = [date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15),
               date(2026, 4, 16), date(2026, 4, 17)]
        assert kf._n_business_days_before(cal, date(2026, 4, 17), 1) == date(2026, 4, 16)
        assert kf._n_business_days_before(cal, date(2026, 4, 17), 4) == date(2026, 4, 13)
        assert kf._n_business_days_before(cal, date(2026, 4, 17), 10) is None
        assert kf._n_business_days_before(cal, None, 1) is None

    def test_weekday_only_range_skips_weekends(self):
        # 2026-04-16(목) ~ 2026-04-20(월): 16목, 17금, 20월 (18토/19일 제외)
        result = kf._weekday_only_range(date(2026, 4, 16), date(2026, 4, 20))
        assert result == [date(2026, 4, 16), date(2026, 4, 17), date(2026, 4, 20)]
