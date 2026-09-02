"""기술적 지표 — Envelope. 순수 함수(외부 의존 0)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class Envelope:
    ma: float       # 이동평균
    upper: float    # ma * (1 + band)
    lower: float    # ma * (1 - band)


def compute_envelope(closes: Sequence[int], period: int, band: float) -> Optional[Envelope]:
    """일봉 종가 시퀀스로 Envelope 계산.

    Args:
        closes: 오름차순 종가(과거→최근). 최근 `period` 개 사용.
        period: 이동평균 기간(예 20).
        band: 밴드 비율(예 0.10 = ±10%).

    Returns:
        데이터가 없으면 None. period 보다 적으면 있는 만큼으로 평균(부분).
    """
    vals = [c for c in closes if c is not None]
    if not vals or period <= 0:
        return None
    window = vals[-period:]
    ma = sum(window) / len(window)
    return Envelope(ma=ma, upper=ma * (1 + band), lower=ma * (1 - band))
