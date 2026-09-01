"""해제조건 / 하락비율 계산 — 순수 함수만 포함. 외부 의존성 0."""
from __future__ import annotations

from typing import Iterable, Optional


def _round_int(value: float) -> int:
    """파이썬의 banker's rounding 회피를 위한 표준 반올림 (0.5 올림)."""
    # int(value + 0.5) 는 음수에서 다르게 동작하므로 분기
    if value >= 0:
        return int(value + 0.5)
    return -int(-value + 0.5)


def compute_price_1(close_t5: Optional[int]) -> Optional[int]:
    """해제조건 ① : Close(T-5) × 1.60 (반올림)."""
    if close_t5 is None:
        return None
    return _round_int(close_t5 * 1.60)


def compute_price_2(close_t15: Optional[int]) -> Optional[int]:
    """해제조건 ② : Close(T-15) × 2.00 (반올림)."""
    if close_t15 is None:
        return None
    return _round_int(close_t15 * 2.00)


def compute_price_3(recent_highs: Optional[Iterable[int]]) -> Optional[int]:
    """해제조건 ③ : 직전 15 매매일 최고가 (max)."""
    if recent_highs is None:
        return None
    highs = [h for h in recent_highs if h is not None]
    if not highs:
        return None
    return max(highs)


def compute_release_amount(
    price_1: Optional[int],
    price_2: Optional[int],
    price_3: Optional[int],
) -> Optional[int]:
    """해제금액 = min(Price①, Price②, Price③).

    None 이 섞여 있으면 해당 항목은 비교에서 제외한다.
    전체가 None 이면 None 반환.
    """
    candidates = [p for p in (price_1, price_2, price_3) if p is not None]
    if not candidates:
        return None
    return min(candidates)


def compute_release_prices(
    close_t5: Optional[int],
    close_t15: Optional[int],
    recent_highs: Optional[Iterable[int]],
) -> dict:
    """해제조건 3종 + 해제금액을 한 번에 계산한 dict 반환."""
    p1 = compute_price_1(close_t5)
    p2 = compute_price_2(close_t15)
    p3 = compute_price_3(recent_highs)
    return {
        "price_1": p1,
        "price_2": p2,
        "price_3": p3,
        "release_amount": compute_release_amount(p1, p2, p3),
    }


def compute_drop_ratio(
    release_amount: Optional[int],
    current_price: Optional[int],
) -> Optional[int]:
    """하락비율 = ROUND((해제금액 - 현재가) / 해제금액 × 100).

    해제금액 대비 현재가가 얼마나 낮은지(또는 높은지)를 %로 표현.
    - 양수: 현재가 < 해제금액 (해제조건 미달, "이만큼 올라야 해제")
    - 0: 현재가 = 해제금액
    - 음수: 현재가 > 해제금액 (이미 해제금액 초과)

    None 안전 + release_amount=0 안전.
    """
    if release_amount is None or current_price is None:
        return None
    if release_amount == 0:
        return None
    ratio = (release_amount - current_price) / release_amount * 100.0
    return _round_int(ratio)
