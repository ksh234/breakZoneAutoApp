"""종목명 → 6자리 코드 매핑 (FinanceDataReader 기반, 프로세스 내 캐시).

- KIND HTML 에는 6자리 종목코드가 없고 ISU ID(5자리)만 있음.
- 따라서 pykrx/네이버 호출을 위해 종목명 → 6자리 변환 필요.
- FinanceDataReader.StockListing('KRX') 가 한 번의 네트워크 호출로 전체 2800+ 종목 반환.
- 최초 호출 시 1회 빌드, 이후 프로세스 생애주기 동안 메모리 캐시.

매핑 실패 대응 (KIND 종목명과 FinanceDataReader 종목명 차이):
  1. 자동 정규화 — "(주)" / "주식회사" 접두·접미 제거, 공백 통일
  2. 수동 overrides — data/ticker_overrides.json 에서 사용자 예외 지정
     예) {"아하정보통신": "102950"}
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TickerMappingError(Exception):
    """종목 매핑 로드 실패."""


_CACHE: dict[str, str] = {}
# 코드 → 시장 구분 ('KOSPI' / 'KOSDAQ' / 'KONEX' — FinanceDataReader 원문 값)
_MARKET_BY_CODE: dict[str, str] = {}
_LOCK = threading.Lock()

# 수동 오버라이드 파일 — 사용자가 KIND 종목명 → 6자리 코드를 직접 지정
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDES_FILE = _PROJECT_ROOT / "data" / "ticker_overrides.json"

# 정규화 시 제거할 접두·접미 패턴 ("(주)", "주식회사" 등)
_PREFIX_RE = re.compile(r'^\s*(\(주\)|주식회사)\s*')
_SUFFIX_RE = re.compile(r'\s*(\(주\)|주식회사)\s*$')


def _normalize(name: str) -> str:
    """종목명 정규화 — 접두/접미 회사형태 표기 제거 + 공백 정리."""
    if not name:
        return ""
    s = name.strip()
    s = _PREFIX_RE.sub('', s)
    s = _SUFFIX_RE.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _load_overrides() -> dict[str, str]:
    """사용자 수동 매핑 파일 로드 (없으면 빈 dict)."""
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        raw = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        # 정규화된 key 로 저장
        result: dict[str, str] = {}
        for k, v in raw.items():
            code = str(v).strip().zfill(6)
            if code.isdigit() and len(code) == 6:
                result[_normalize(str(k))] = code
        return result
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("ticker_overrides.json 파싱 실패: %s", e)
        return {}


def _build_mapping() -> tuple[dict[str, str], dict[str, str]]:
    """FinanceDataReader 로 전체 KRX 종목 리스트 다운로드 후 매핑 생성.

    Returns:
        (name→code, code→market) 튜플.
        market 값: 'STK'(KOSPI), 'KSQ'(KOSDAQ), 'KNX'(KONEX).
    """
    try:
        import FinanceDataReader as fdr  # type: ignore
    except ImportError as e:
        raise TickerMappingError(
            "finance-datareader 패키지가 필요합니다. "
            "`pip install finance-datareader` 후 재시도하세요."
        ) from e

    try:
        df = fdr.StockListing("KRX")
    except Exception as e:
        raise TickerMappingError(f"StockListing 호출 실패: {e}") from e

    if df is None or df.empty or "Name" not in df.columns or "Code" not in df.columns:
        raise TickerMappingError("StockListing 응답 형식이 예상과 다릅니다")

    has_market = "Market" in df.columns

    mapping: dict[str, str] = {}
    market_by_code: dict[str, str] = {}
    for _, row in df.iterrows():
        name = str(row["Name"]).strip()
        code = str(row["Code"]).strip().zfill(6)
        if name and code and code.isdigit() and len(code) == 6:
            mapping[_normalize(name)] = code
            if has_market:
                market_by_code[code] = str(row["Market"]).strip().upper()

    # 수동 오버라이드 — 자동 매핑을 덮어씀
    overrides = _load_overrides()
    if overrides:
        logger.info("Ticker overrides loaded: %d entries", len(overrides))
        mapping.update(overrides)

    konex_count = sum(1 for m in market_by_code.values() if m == "KNX")
    logger.info(
        "Ticker mapping built: %d entries (KONEX %d)",
        len(mapping), konex_count,
    )
    return mapping, market_by_code


def _ensure_cache() -> None:
    """캐시가 비어 있으면 빌드."""
    if not _CACHE:
        mapping, market = _build_mapping()
        _CACHE.update(mapping)
        _MARKET_BY_CODE.update(market)


def lookup(name: str) -> Optional[str]:
    """종목명으로 6자리 코드 조회. 매핑에 없으면 None.

    정규화 규칙:
      - "(주)한싹" → "한싹"
      - "주식회사 카카오" → "카카오"
      - 공백 다중 → 단일

    이후 수동 overrides 와 자동 매핑의 합집합에서 조회.
    """
    if not name:
        return None
    normalized = _normalize(name)
    with _LOCK:
        _ensure_cache()
    return _CACHE.get(normalized)


def get_market(code: str) -> Optional[str]:
    """6자리 코드의 시장 구분 반환. 'KOSPI' / 'KOSDAQ' / 'KONEX'."""
    if not code:
        return None
    with _LOCK:
        _ensure_cache()
    return _MARKET_BY_CODE.get(code)


def is_konex(code: str) -> bool:
    """해당 종목이 KONEX 시장인지."""
    return get_market(code) == "KONEX"


def reload() -> int:
    """매핑 강제 재빌드 (신규 상장·오버라이드 파일 변경 반영).

    반환값은 새 매핑의 항목 수.
    """
    with _LOCK:
        _CACHE.clear()
        _MARKET_BY_CODE.clear()
        mapping, market = _build_mapping()
        _CACHE.update(mapping)
        _MARKET_BY_CODE.update(market)
    return len(_CACHE)


def size() -> int:
    """현재 캐시된 매핑 항목 수 (0 이면 아직 미로드)."""
    with _LOCK:
        return len(_CACHE)
