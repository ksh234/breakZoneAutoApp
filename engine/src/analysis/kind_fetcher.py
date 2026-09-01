"""KIND 투자경고종목 크롤링.

- Adapter 레이어.
- KIND 는 AJAX POST 로 투자경고 목록을 반환 (초기 페이지 HTML 에는 목록 없음).
- POST 파라미터는 투자주의/경고/위험 통합 페이지의 투자경고 탭(menuIndex=2) 기준.
- 응답 HTML 은 5개 컬럼 테이블: 번호 / 종목명 / 공시일 / 지정일 / 해제조건충족여부
  (투자경고 탭 응답은 유형 컬럼이 없음 — 탭 자체가 투자경고 전용)
- 종목코드는 HTML 에 없으므로 종목명 → FinanceDataReader 매핑 사용 (ticker_mapping).
- 해제판단일 = 지정일 포함 10번째 매매일 (KRX 규정).
- 매매일 캘린더: 과거는 pykrx (정확), 미래는 `holidays` 패키지로 공휴일 반영 + 임시공휴일 수동 파일.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import holidays  # type: ignore
import requests
from bs4 import BeautifulSoup

from . import pykrx_fetcher, ticker_mapping

logger = logging.getLogger(__name__)

# 임시공휴일 수동 추가 파일 경로 (JSON 배열: ["YYYY-MM-DD", ...])
# 정부가 임시공휴일 지정 시 이 파일에 추가하면 매매일 계산에 반영됨.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRA_HOLIDAYS_FILE = _PROJECT_ROOT / "data" / "extra_holidays.json"


class KindFetchError(Exception):
    """KIND 크롤링/파싱 치명적 실패."""


# ─── 데이터 모델 ──────────────────────────────────────
@dataclass
class WarningStock:
    code: str                   # 6자리 종목코드 (매핑 실패 시 "")
    name: str                   # 종목명
    designated_date: date       # 지정일
    release_date: date          # 해제판단일 (지정일 + 10 매매일)


# ─── 설정 상수 ────────────────────────────────────────
KIND_URL = "https://kind.krx.co.kr/investwarn/investattentwarnrisky.do"
INIT_URL = f"{KIND_URL}?method=investattentwarnriskyMain"
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# HTML 에서 실제 데이터가 들어있는 테이블 셀렉터 (KIND 확인됨)
TABLE_SELECTOR = "table.list.type-00"


# ─── 공개 API ─────────────────────────────────────────
def get_warning_stocks(
    *, today: Optional[date] = None,
) -> tuple[list[WarningStock], list[date]]:
    """KIND 에서 투자경고종목을 크롤링하여 활성 종목 전부 반환.

    필터 없음 — KIND 페이지가 현재 활성 투자경고 종목만 제공하므로 모두 반환.
    각 종목의 release_date = 지정일 포함 10번째 매매일 (KRX 규정) 로 계산.
    자동 계산 / 수동 입력 분기는 app.py 에서 "실제 pykrx 종가 조회 성공 여부" 로 결정.

    Returns:
        (stocks, trading_days) 튜플.
        trading_days 는 app.py 가 T-N 날짜 계산에 재사용 (중복 조회 방지).

    Raises:
        KindFetchError: 네트워크/파싱 치명 오류.
    """
    if today is None:
        today = date.today()

    html = _fetch_html(today=today)
    rows = parse_html(html)

    # 매매일 캘린더 구축 (app.py 와 공용).
    # 과거: pykrx 의 실제 매매일 (공휴일 반영). 미래: pykrx 데이터 없으므로
    # holidays 패키지 + 임시공휴일 파일로 보완.
    past_start = today - timedelta(days=90)
    future_end = today + timedelta(days=90)
    try:
        past_days = pykrx_fetcher.get_trading_days(past_start, today)
    except pykrx_fetcher.PykrxFetchError as e:
        logger.warning("과거 매매일 조회 실패 → 공휴일 반영 fallback: %s", e)
        past_days = _business_day_range(past_start, today)

    future_start = past_days[-1] + timedelta(days=1) if past_days else today + timedelta(days=1)
    future_days = _business_day_range(future_start, future_end)
    trading_days = list(past_days) + future_days

    if not trading_days:
        raise KindFetchError("매매일 캘린더를 얻지 못했습니다")

    enriched: list[WarningStock] = []
    skipped_konex = 0
    for name, designated in rows:
        code = ticker_mapping.lookup(name) or ""
        # KONEX 종목은 투자 대상에서 제외 (유동성·거래제약 사유)
        if code and ticker_mapping.is_konex(code):
            skipped_konex += 1
            logger.info("KONEX 제외: %s (%s)", name, code)
            continue
        # release_date = 지정일 포함 10번째 매매일 (KRX 규정)
        release_date = _kth_business_day_on_or_after(trading_days, designated, 10)
        if release_date is None:
            logger.warning("%s: release_date 계산 실패 (designated=%s)", name, designated)
            continue
        enriched.append(WarningStock(
            code=code, name=name,
            designated_date=designated, release_date=release_date,
        ))
    logger.info(
        "KIND parsed %d rows → %d 활성 투자경고 종목 (KONEX %d개 제외)",
        len(rows), len(enriched), skipped_konex,
    )
    return enriched, trading_days


# ─── 매매일 캘린더 유틸 (로컬 리스트 인덱싱) ─────────
def _kth_business_day_on_or_after(
    trading_days: list[date], anchor: date, k: int
) -> Optional[date]:
    """trading_days 중 anchor 이상인 매매일의 k번째 (1-indexed, anchor 포함).

    KRX "지정일 포함 N매매일째" 규정에 대응.
    예: anchor=4/3(금), k=10 → [4/3, 4/6, 4/7, 4/8, 4/9, 4/10, 4/13, 4/14, 4/15, 4/16]
        의 10번째 = 4/16.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    from_ = [d for d in trading_days if d >= anchor]
    if len(from_) < k:
        return None
    return from_[k - 1]


def _n_business_days_before(
    trading_days: list[date], anchor: Optional[date], n: int
) -> Optional[date]:
    """trading_days 중 anchor 보다 작은 것들의 뒤에서 n번째. 없으면 None.

    n=0 은 anchor 자체를 의미 (T-0 = release_date).
    """
    if anchor is None:
        return None
    if n == 0:
        return anchor
    before = [d for d in trading_days if d < anchor]
    if len(before) < n:
        return None
    return before[-n]


def _weekday_only_range(start: date, end: date) -> list[date]:
    """pykrx 실패 시 주말만 제외한 평일 리스트 fallback (공휴일 무관)."""
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d = d + timedelta(days=1)
    return out


def _load_extra_holidays() -> set[date]:
    """사용자가 지정한 임시공휴일 파일 로드 (없으면 빈 set)."""
    if not EXTRA_HOLIDAYS_FILE.exists():
        return set()
    try:
        raw = json.loads(EXTRA_HOLIDAYS_FILE.read_text(encoding="utf-8"))
        return {date.fromisoformat(s) for s in raw}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("extra_holidays.json 파싱 실패: %s", e)
        return set()


def _business_day_range(start: date, end: date) -> list[date]:
    """주말 + 한국 공휴일(대체휴일 포함) + 임시공휴일(수동 파일) 제외한 매매일 리스트.

    `holidays.KR()` 로 법정 공휴일·대체휴일·선거일까지 자동 반영.
    추가로 data/extra_holidays.json 의 임시공휴일 합집합으로 제외.
    KRX 특별 휴장일(대체거래일 등)은 드물어서 현재 미반영 — 필요 시 extra_holidays.json 에 추가.
    """
    if start > end:
        return []
    years = list(range(start.year, end.year + 1))
    kr_holidays = holidays.KR(years=years)
    extras = _load_extra_holidays()
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in kr_holidays and d not in extras:
            out.append(d)
        d = d + timedelta(days=1)
    return out


# ─── HTTP ─────────────────────────────────────────────
def _fetch_html(*, today: date) -> str:
    """KIND AJAX POST 로 투자경고 목록 HTML 조회."""
    today_str = today.strftime("%Y-%m-%d")
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": USER_AGENT})
        # 1. 세션 쿠키 획득 (초기 메뉴 페이지)
        sess.get(INIT_URL, timeout=REQUEST_TIMEOUT)
        # 2. AJAX POST — 투자경고 탭 (menuIndex=2, forward=invstwarnisu_sub)
        data = {
            "method": "investattentwarnriskySub",
            "currentPageSize": "100",
            "pageIndex": "1",
            "orderMode": "",
            "orderStat": "",
            "searchCodeType": "",
            "searchCorpName": "",
            "repIsuSrtCd": "",
            "menuIndex": "2",
            "forward": "invstwarnisu_sub",
            "searchFromDate": today_str,
            "marketType": "",
            "searchCorpNameTmp": "",
            "etsIsuSrtCd": "",
            "startDate": today_str,
            "endDate": today_str,
        }
        resp = sess.post(
            KIND_URL, data=data,
            headers={"Referer": INIT_URL, "X-Requested-With": "XMLHttpRequest"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.RequestException as e:
        raise KindFetchError(f"KIND request failed: {e}") from e


# ─── HTML 파싱 ────────────────────────────────────────
def parse_html(html: str) -> list[tuple[str, date]]:
    """HTML → [(종목명, 지정일), ...] 반환 (투자경고 탭 응답).

    순수(네트워크 호출 없음). 테스트에서 직접 호출 가능.
    컬럼 구조 (투자경고 탭 전용): [번호, 종목명, 공시일, 지정일, 해제조건충족여부]
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(TABLE_SELECTOR)
    if table is None:
        raise KindFetchError(
            f"KIND 테이블({TABLE_SELECTOR})을 찾지 못했습니다 — "
            "페이지 구조가 변경되었을 수 있습니다"
        )

    rows: list[tuple[str, date]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue  # 헤더 또는 빈 행 스킵
        # 투자경고 탭: [번호, 종목명, 공시일, 지정일, ...]
        name = _extract_name(cells[1])
        designated = _extract_date(cells[3].get_text(strip=True))
        if not name or designated is None:
            continue
        rows.append((name, designated))
    return rows


def _extract_name(cell) -> str:
    """종목명 셀에서 종목명 텍스트 추출 (이미지/심볼 제외)."""
    # <td title="삼성전자"> 구조이므로 title 이 가장 정확
    title = cell.get("title", "")
    if title:
        return title.strip()
    # fallback: 텍스트 전체
    a = cell.find("a")
    if a is not None:
        return a.get_text(strip=True)
    return cell.get_text(" ", strip=True)


def _extract_date(text: str) -> Optional[date]:
    """'2026-04-16', '2026.04.16', '2026/04/16' 등에서 date 객체 추출."""
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ─── 해제판단일 계산 (지정일 + 10 매매일) ─────────────
def compute_release_date(designated: date) -> date:
    """지정일 + 10 매매일 = 해제판단일.

    pykrx 매매일 캘린더(OHLCV index) 기반. 실패 시 주말 제외 근사 fallback.
    """
    count = 0
    current = designated
    while count < 10:
        current = current + timedelta(days=1)
        if _is_business_day(current):
            count += 1
    return current


def _is_business_day(d: date) -> bool:
    """d 가 KRX 매매일인지 확인. pykrx 실패 시 주말 제외로 근사."""
    try:
        prev = pykrx_fetcher.get_previous_business_day(d)
        return prev == d
    except pykrx_fetcher.PykrxFetchError:
        return d.weekday() < 5  # Mon-Fri
