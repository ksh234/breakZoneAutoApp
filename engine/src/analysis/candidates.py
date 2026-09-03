"""경고주 후보 산출 — breakZone `app.py::_compute_stock_row` 로직 이식(순수 서비스).

KIND 경고주 목록 → 종목별로 (매매일/과거종가/현재가 조회 + 해제금액·하락비율 계산) →
`Candidate` 리스트 반환. 대시보드의 [조회] 결과와 동일한 값을 산출한다.

- 매매(주문)·Supabase 없음. 분석만.
- 현재가 소스는 현재 네이버(이식본). Phase 2에서 키움 실시간으로 교체 예정(D-005).
- 종목별 failure isolation: 한 종목이 실패해도 나머지는 계속 산출.
- Candidate 필드는 docs/02 `candidates` 테이블과 1:1 (owner/updated_at 은 DB 관리).

콘솔 실행(현재 경고주 후보 출력):
    cd engine
    python -m src.analysis.candidates            # 현재가 포함(네이버)
    python -m src.analysis.candidates --no-price # 현재가 조회 생략(빠름)
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from . import calculator, kind_fetcher, naver_fetcher, pykrx_fetcher

logger = logging.getLogger(__name__)

# breakZone 대시보드 강조 기준(하락비율 ≤ 이 값). 참고용 — 매매 트리거 아님.
DROP_HIGHLIGHT = 25


@dataclass
class Candidate:
    """경고주 후보 1건 (docs/02 candidates 테이블 매핑)."""
    code: str
    name: str
    designated_date: Optional[date]
    release_date: Optional[date]
    t5_close: Optional[int]
    t15_close: Optional[int]
    recent_15_high: Optional[int]
    release_amount: Optional[int]        # min(price1, price2, price3)
    current_price: Optional[int]
    drop_ratio: Optional[int]            # (해제금액-현재가)/해제금액*100
    status: str                          # ok | partial | pending | error
    signal: str = "none"                 # none|watch|enter|hold|exit (Phase 4에서 산출)
    error: Optional[str] = None

    def to_row(self) -> dict[str, Any]:
        """Supabase upsert 용 dict (날짜는 ISO 문자열)."""
        d = asdict(self)
        d["designated_date"] = self.designated_date.isoformat() if self.designated_date else None
        d["release_date"] = self.release_date.isoformat() if self.release_date else None
        return d


def compute_status(t5_close, t15_close, recent_15_high, current_price) -> str:
    """후보 상태. 해제금액·하락비율이 정확하려면 4개 값 모두 필요.
    pending(T-5 미확정) / partial(T-5 있으나 T-15·최고가·현재가 중 누락) / ok(모두 확정).
    """
    if t5_close is None:
        return "pending"
    if t15_close is None or recent_15_high is None or current_price is None:
        return "partial"
    return "ok"


def build_candidates(
    *, today: Optional[date] = None, fetch_current_price: bool = True,
) -> list[Candidate]:
    """현재 경고주 후보 리스트 산출.

    Args:
        today: 기준일(테스트용 주입). None 이면 date.today().
        fetch_current_price: False 면 현재가 네이버 조회를 생략(하락비율=None).

    Raises:
        kind_fetcher.KindFetchError: KIND 크롤링 자체가 실패한 경우(전체 중단).
        종목 개별 실패는 status="error" 후보로 격리되어 리스트에 포함된다.
    """
    warnings, trading_days = kind_fetcher.get_warning_stocks(today=today)
    logger.info("경고주 %d종목 후보 산출 시작 (순차)", len(warnings))

    out: list[Candidate] = []
    for idx, stock in enumerate(warnings):
        try:
            logger.info("[%d/%d] %s (%s)", idx + 1, len(warnings), stock.name, stock.code)
            out.append(_compute_candidate(stock, trading_days, fetch_current_price))
        except Exception as e:  # 종목별 격리
            logger.warning("후보 산출 실패 %s: %s", stock.code, e, exc_info=True)
            out.append(_error_candidate(stock, str(e)))
    return out


def _compute_candidate(
    stock: kind_fetcher.WarningStock,
    trading_days: list[date],
    fetch_current_price: bool,
) -> Candidate:
    """한 종목의 조회 플로우 → Candidate. (breakZone _compute_stock_row 이식)"""
    t_minus_5 = kind_fetcher._n_business_days_before(trading_days, stock.release_date, 5)
    t_minus_15 = kind_fetcher._n_business_days_before(trading_days, stock.release_date, 15)

    # 종목코드 매핑 실패 — 가격 조회 불가(수동 입력 대상).
    if not stock.code:
        return Candidate(
            code=stock.code, name=stock.name,
            designated_date=stock.designated_date, release_date=stock.release_date,
            t5_close=None, t15_close=None, recent_15_high=None,
            release_amount=None, current_price=None, drop_ratio=None,
            status="pending", error="종목코드 매핑 실패 — T-5 종가 수동 입력 필요",
        )

    # ── OHLCV 1회 조회: release_date-40일 ~ release_date ──
    window_start = stock.release_date - timedelta(days=40)
    window_end = stock.release_date
    df = None
    try:
        stock_mod = pykrx_fetcher._get_stock_module()
        df = stock_mod.get_market_ohlcv_by_date(
            window_start.strftime("%Y%m%d"),
            window_end.strftime("%Y%m%d"),
            stock.code,
        )
    except Exception as e:
        logger.warning("OHLCV 조회 실패 %s: %s", stock.code, e)

    # 날짜별 종가 dict (실제 pykrx 응답에 존재하는 매매일만)
    closes_by_date: dict[date, int] = {}
    if df is not None and not getattr(df, "empty", True):
        for idx_ts, close_val in zip(df.index, df["종가"].tolist()):
            try:
                d = pykrx_fetcher._to_date(idx_ts)
                closes_by_date[d] = int(close_val)
            except Exception:
                continue

    close_t5 = closes_by_date.get(t_minus_5) if t_minus_5 else None
    close_t15 = closes_by_date.get(t_minus_15) if t_minus_15 else None

    # "15일 최고" = T-15 ~ T-5 구간 종가 최고 (약 11 매매일)
    recent_highs: list[int] = []
    if t_minus_5 is not None and t_minus_15 is not None:
        range_days = [d for d in trading_days if t_minus_15 <= d <= t_minus_5]
        recent_highs = [closes_by_date[d] for d in range_days if d in closes_by_date]

    prices = calculator.compute_release_prices(close_t5, close_t15, recent_highs)
    release_amount = prices["release_amount"]

    # 현재가 (네이버) — Phase 2에서 키움 실시간으로 교체
    current: Optional[int] = None
    if fetch_current_price:
        try:
            current = naver_fetcher.get_current_price(stock.code)
        except naver_fetcher.NaverFetchError as e:
            logger.warning("현재가 조회 실패 %s: %s", stock.code, e)

    drop_ratio = calculator.compute_drop_ratio(release_amount, current)

    status = compute_status(close_t5, close_t15, prices["price_3"], current)

    return Candidate(
        code=stock.code, name=stock.name,
        designated_date=stock.designated_date, release_date=stock.release_date,
        t5_close=close_t5, t15_close=close_t15, recent_15_high=prices["price_3"],
        release_amount=release_amount, current_price=current, drop_ratio=drop_ratio,
        status=status,
    )


def _error_candidate(stock: kind_fetcher.WarningStock, message: str) -> Candidate:
    return Candidate(
        code=stock.code, name=stock.name,
        designated_date=stock.designated_date, release_date=stock.release_date,
        t5_close=None, t15_close=None, recent_15_high=None,
        release_amount=None, current_price=None, drop_ratio=None,
        status="error", error=message,
    )


# ─── 콘솔 실행 ─────────────────────────────────────────
def _print_table(cands: list[Candidate]) -> None:
    def _s(v: Any) -> str:
        return "-" if v is None else str(v)

    # 하락비율 오름차순(작을수록 해제금액에 근접 → 관심). None 은 뒤로.
    ordered = sorted(cands, key=lambda c: (c.drop_ratio is None, c.drop_ratio if c.drop_ratio is not None else 0))
    header = f"{'종목명':<12} {'코드':<7} {'해제금액':>9} {'현재가':>9} {'하락%':>6} {'상태':<8}"
    print(header)
    print("-" * len(header))
    for c in ordered:
        mark = " *" if (c.drop_ratio is not None and c.drop_ratio <= DROP_HIGHLIGHT) else ""
        name = (c.name[:11] + "…") if len(c.name) > 12 else c.name
        print(f"{name:<12} {_s(c.code):<7} {_s(c.release_amount):>9} "
              f"{_s(c.current_price):>9} {_s(c.drop_ratio):>6} {c.status:<8}{mark}")
    print(f"\n총 {len(cands)}종목  (* = 하락비율 ≤ {DROP_HIGHLIGHT}% 강조, breakZone 기준)")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="경고주 후보 산출(분석 전용)")
    parser.add_argument("--no-price", action="store_true", help="현재가 조회 생략(빠름)")
    parser.add_argument("--log", default="WARNING", help="로그 레벨(기본 WARNING)")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.WARNING),
                        format="%(levelname)s %(name)s: %(message)s")

    print("경고주 후보 산출 중… (KIND 크롤링 + pykrx 조회, 수십 초 걸릴 수 있음)\n")
    try:
        cands = build_candidates(fetch_current_price=not args.no_price)
    except kind_fetcher.KindFetchError as e:
        print(f"[실패] KIND 크롤링 오류: {e}")
        return 1
    if not cands:
        print("현재 투자경고 종목이 없습니다.")
        return 0
    _print_table(cands)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
