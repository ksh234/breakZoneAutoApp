"""calculator.py 단위 테스트."""
from __future__ import annotations

from src.analysis.calculator import (
    compute_drop_ratio,
    compute_price_1,
    compute_price_2,
    compute_price_3,
    compute_release_amount,
    compute_release_prices,
)


# ── Price ① (T-5 × 1.60) ───────────────────────────────
class TestPrice1:
    def test_happy(self):
        assert compute_price_1(10000) == 16000

    def test_rounding_up(self):
        # 1234 * 1.6 = 1974.4 → 1974
        assert compute_price_1(1234) == 1974

    def test_rounding_half(self):
        # 1875 * 1.6 = 3000.0
        assert compute_price_1(1875) == 3000

    def test_none_in_none_out(self):
        assert compute_price_1(None) is None

    def test_zero(self):
        assert compute_price_1(0) == 0


# ── Price ② (T-15 × 2.00) ──────────────────────────────
class TestPrice2:
    def test_happy(self):
        assert compute_price_2(5000) == 10000

    def test_none_in_none_out(self):
        assert compute_price_2(None) is None


# ── Price ③ (최근 15일 최고) ───────────────────────────
class TestPrice3:
    def test_happy(self):
        assert compute_price_3([10000, 12000, 11000, 9000]) == 12000

    def test_single(self):
        assert compute_price_3([5000]) == 5000

    def test_none_in_none_out(self):
        assert compute_price_3(None) is None

    def test_empty_iterable(self):
        assert compute_price_3([]) is None

    def test_skips_none(self):
        assert compute_price_3([None, 10000, None, 12000]) == 12000

    def test_all_none(self):
        assert compute_price_3([None, None]) is None


# ── 해제금액 ───────────────────────────────────────────
class TestReleaseAmount:
    def test_happy_all_present(self):
        # min(16000, 10000, 12000) = 10000
        assert compute_release_amount(16000, 10000, 12000) == 10000

    def test_one_none_ignored(self):
        assert compute_release_amount(16000, None, 12000) == 12000

    def test_two_none_ignored(self):
        assert compute_release_amount(None, 10000, None) == 10000

    def test_all_none(self):
        assert compute_release_amount(None, None, None) is None


# ── 통합: compute_release_prices ──────────────────────
class TestReleasePrices:
    def test_happy_path(self):
        result = compute_release_prices(
            close_t5=10000, close_t15=5000, recent_highs=[10000, 12000, 11000]
        )
        assert result == {
            "price_1": 16000,
            "price_2": 10000,
            "price_3": 12000,
            "release_amount": 10000,
        }

    def test_partial_t15_missing(self):
        # T-15 미도래 → price_2 None, release_amount 는 나머지로 계산
        result = compute_release_prices(
            close_t5=10000, close_t15=None, recent_highs=[10000, 12000]
        )
        assert result == {
            "price_1": 16000,
            "price_2": None,
            "price_3": 12000,
            "release_amount": 12000,
        }

    def test_all_none(self):
        result = compute_release_prices(
            close_t5=None, close_t15=None, recent_highs=None
        )
        assert result == {
            "price_1": None,
            "price_2": None,
            "price_3": None,
            "release_amount": None,
        }


# ── 하락비율 ───────────────────────────────────────────
class TestDropRatio:
    """하락비율 = ROUND((해제금액 - 현재가) / 해제금액 * 100)"""

    def test_happy(self):
        # (10000 - 9500) / 10000 * 100 = 5.0 → 5
        assert compute_drop_ratio(10000, 9500) == 5

    def test_rounding(self):
        # (10000 - 9000) / 10000 * 100 = 10.0 → 10
        assert compute_drop_ratio(10000, 9000) == 10

    def test_negative_when_current_higher(self):
        # 현재가가 해제금액보다 높으면 음수
        # (10000 - 12000) / 10000 * 100 = -20.0 → -20
        assert compute_drop_ratio(10000, 12000) == -20

    def test_흥아해운_case(self):
        # 사용자 케이스: 현재가가 해제금액을 28% 초과 → drop_ratio = -28
        # (78 - 100) / 100 * 100 = -22 예시. 실제 숫자 대입:
        # 해제금액 500, 현재가 640 → (500 - 640) / 500 * 100 = -28
        assert compute_drop_ratio(500, 640) == -28

    def test_zero_drop(self):
        assert compute_drop_ratio(10000, 10000) == 0

    def test_release_none(self):
        assert compute_drop_ratio(None, 9500) is None

    def test_current_none(self):
        assert compute_drop_ratio(10000, None) is None

    def test_both_none(self):
        assert compute_drop_ratio(None, None) is None

    def test_release_zero_safe(self):
        # 해제금액이 0이면 0으로 나눔 방지
        assert compute_drop_ratio(0, 9500) is None
