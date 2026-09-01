"""pykrx 기반 매매일 / 종가 유틸.

- Adapter 레이어 (pykrx 만 외부 의존).
- 매매일 계산: `get_market_ohlcv_by_date` 의 DataFrame index 를 매매일 캘린더로 활용
  (pykrx 1.2.6 의 `get_previous_business_days()` 는 내부 호출 실패가 잦아 사용하지 않음).
- 종가: `stock.get_market_ohlcv_by_date(fromdate, todate, code)`.
- 매매일 캘린더 기준 종목: 삼성전자 (005930) — 거래량이 충분해 모든 매매일에 데이터가 존재.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class PykrxFetchError(Exception):
    """pykrx 호출 실패를 래핑."""


# 매매일 캘린더 기준 종목 (대형주 + 거래량 풍부 → 매매일이면 반드시 데이터 존재)
_CALENDAR_TICKER = "005930"  # 삼성전자


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


def _get_stock_module():
    """pykrx 모듈 지연 import — 테스트에서 monkeypatch 가능하게."""
    from pykrx import stock  # type: ignore
    return stock


def _to_date(ts) -> date:
    """pandas Timestamp → datetime.date."""
    if isinstance(ts, date) and not isinstance(ts, datetime):
        return ts
    if hasattr(ts, "date"):
        return ts.date()
    if isinstance(ts, str):
        return datetime.strptime(ts[:10], "%Y-%m-%d").date()
    raise TypeError(f"cannot convert {type(ts)} to date")


def get_trading_days(fromdate: date, todate: date) -> list[date]:
    """[fromdate, todate] 구간의 KRX 매매일 리스트 (오름차순).

    삼성전자 OHLCV 의 index 를 매매일 캘린더로 사용.
    """
    if fromdate > todate:
        return []
    try:
        stock = _get_stock_module()
        df = stock.get_market_ohlcv_by_date(
            _fmt(fromdate), _fmt(todate), _CALENDAR_TICKER
        )
        if df is None or df.empty:
            return []
        return [_to_date(d) for d in df.index]
    except Exception as e:
        raise PykrxFetchError(
            f"get_trading_days({fromdate}..{todate}) failed: {e}"
        ) from e


def get_previous_business_day(base: date) -> date:
    """base 이하의 가장 가까운 매매일 (base 자체가 매매일이면 base)."""
    # 공휴일 연속을 고려해 최대 2주 여유
    start = base - timedelta(days=14)
    days = get_trading_days(start, base)
    if not days:
        raise PykrxFetchError(f"no trading day found before {base}")
    return days[-1]


def n_business_days_before(base: date, n: int) -> date:
    """base 로부터 n 매매일 이전의 KRX 매매일 (n>0).

    예: n=5, base=2026-04-16(목) → 매매일 기준 5일 이전
    """
    if n <= 0:
        raise ValueError("n must be positive")
    # 달력일 여유: n * 2 + 30 (설연휴·추석 등 긴 연휴 대응)
    slack_days = max(n * 2 + 30, 60)
    start = base - timedelta(days=slack_days)
    days = get_trading_days(start, base)
    # base 이하 매매일 중 n 번째 이전
    filtered = [d for d in days if d <= base]
    if len(filtered) <= n:
        raise PykrxFetchError(
            f"insufficient trading days: need {n+1}, got {len(filtered)} "
            f"(base={base}, start={start})"
        )
    return filtered[-(n + 1)]


def get_close(code: str, target: date) -> Optional[int]:
    """특정 매매일의 종가(int). 데이터 없으면 None."""
    try:
        stock = _get_stock_module()
        fromdate = _fmt(target)
        todate = _fmt(target)
        df = stock.get_market_ohlcv_by_date(fromdate, todate, code)
        if df is None or df.empty:
            return None
        close_val = df["종가"].iloc[0]
        if close_val is None:
            return None
        return int(close_val)
    except Exception as e:
        raise PykrxFetchError(f"get_close({code}, {target}) failed: {e}") from e


def get_close_range(code: str, start: date, end: date) -> list[int]:
    """[start, end] 구간의 종가 리스트 (오름차순, None 제외)."""
    if start > end:
        return []
    try:
        stock = _get_stock_module()
        df = stock.get_market_ohlcv_by_date(_fmt(start), _fmt(end), code)
        if df is None or df.empty:
            return []
        return [int(v) for v in df["종가"].tolist() if v is not None]
    except Exception as e:
        raise PykrxFetchError(
            f"get_close_range({code}, {start}..{end}) failed: {e}"
        ) from e
