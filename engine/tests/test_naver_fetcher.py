"""naver_fetcher.py 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.analysis import naver_fetcher as nf
from src.analysis.naver_fetcher import NaverFetchError, get_current_price, parse_price


SAMPLE_HTML_WITH_PRICE = """
<html>
<body>
<div class="rate_info">
  <p class="no_today">
    <em class="no_up">
      <span class="blind">57,800</span>
      <span class="no5">5</span>
      <span class="no7">7</span>
      <span class="shim">,</span>
      <span class="no8">8</span>
      <span class="no0">0</span>
      <span class="no0">0</span>
    </em>
  </p>
</div>
</body>
</html>
"""

SAMPLE_HTML_NO_TODAY_MISSING = """
<html><body><p>No price element</p></body></html>
"""


class TestParsePrice:
    def test_happy(self):
        assert parse_price(SAMPLE_HTML_WITH_PRICE) == 57800

    def test_missing_element_raises(self):
        with pytest.raises(NaverFetchError):
            parse_price(SAMPLE_HTML_NO_TODAY_MISSING)

    def test_handles_large_number(self):
        html = (
            '<p class="no_today"><em><span class="blind">1,234,567</span></em></p>'
        )
        assert parse_price(html) == 1234567


class TestGetCurrentPrice:
    def test_invalid_code_format(self):
        with pytest.raises(NaverFetchError):
            get_current_price("12345")  # 5자리
        with pytest.raises(NaverFetchError):
            get_current_price("abc123")

    def test_network_error_wrapped(self):
        with patch.object(nf.requests, "get",
                          side_effect=requests.ConnectionError("no net")):
            with pytest.raises(NaverFetchError):
                get_current_price("005930")

    def test_happy_integration(self):
        fake_resp = MagicMock()
        fake_resp.text = SAMPLE_HTML_WITH_PRICE
        fake_resp.encoding = "utf-8"
        fake_resp.raise_for_status = MagicMock()
        with patch.object(nf.requests, "get", return_value=fake_resp):
            result = get_current_price("005930")
        assert result == 57800
