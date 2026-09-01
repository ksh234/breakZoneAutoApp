"""네이버 금융 현재가 크롤링.

- Adapter 레이어.
- URL: https://finance.naver.com/item/main.naver?code={code}
- 파싱: no_today 요소의 span.blind 텍스트 (장중/장마감 모두 동일 구조)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class NaverFetchError(Exception):
    """네이버 크롤링 실패 (종목별 격리 가능)."""


NAVER_URL_TEMPLATE = "https://finance.naver.com/item/main.naver?code={code}"
REQUEST_TIMEOUT = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_current_price(code: str) -> int:
    """네이버 금융에서 현재가(원)를 조회.

    Args:
        code: 종목코드 6자리 문자열 (예: "005930")

    Raises:
        NaverFetchError: 네트워크/파싱 실패.
    """
    if not re.fullmatch(r"\d{6}", code):
        raise NaverFetchError(f"invalid code format: {code!r}")

    url = NAVER_URL_TEMPLATE.format(code=code)
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise NaverFetchError(f"네이버 요청 실패 code={code}: {e}") from e

    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"

    return parse_price(resp.text, code=code)


def parse_price(html: str, *, code: str = "") -> int:
    """HTML 에서 현재가 추출 (순수 함수).

    네이버 페이지 구조:
        <p class="no_today">
            <em>
                <span class="blind">57,800</span>
                ...
            </em>
        </p>
    """
    soup = BeautifulSoup(html, "html.parser")

    # 우선순위: .no_today .blind → .no_today em 전체 텍스트
    candidates = soup.select("p.no_today em span.blind")
    if not candidates:
        candidates = soup.select("p.no_today em")
    if not candidates:
        raise NaverFetchError(
            f"no_today 요소를 찾지 못했습니다 (code={code})"
        )

    text = candidates[0].get_text(strip=True)
    # "57,800" 형태에서 숫자만 추출
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        raise NaverFetchError(f"현재가 파싱 실패 (code={code}, raw={text!r})")
    return int(digits)
