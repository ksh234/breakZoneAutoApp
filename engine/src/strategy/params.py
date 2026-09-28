"""전략 파라미터 — settings(앱에서 조절)에서 로드. 전부 조절 가능. docs/03 §6."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


PARAMS_VERSION = 2   # 2: 모든 비율 파라미터가 %(소수 1자리). 1: 일부가 0~1 비율(구 앱/설정)
RATIO_TO_PCT_FIELDS = ("env_band", "entry_rebound_pct", "entry_split_pct", "add_on_drop_pct",
                       "first_sell_portion", "post_sell_stop_pct")


@dataclass
class StrategyParams:
    enabled: bool = False
    mode: str = "demo"
    # Envelope
    env_period: int = 20
    env_band: float = 10.0          # Envelope 밴드(%) ±. (2026-09-28 단위 % 통일, 소수 1자리)
    # 진입
    entry_drop_pct: float = 30.0   # 진입 하락비율 기준(%). 현재가가 해제금액 대비 이 % 이상 하락해야 매수구간
    entry_rebound_pct: float = 0.0 # 저가 반등 매수(%): 매수구간 저점에서 이 % 상승 시 매수. 0=즉시(반등 안 봄)
    min_price: int = 1000          # 최소 매수가(원) — 이 미만 종목은 매수 안 함(0=무제한)
    per_stock_krw: int = 1_000_000
    entry_split_pct: float = 30.0  # 1회 매수 비중(%) — 종목당 총액 대비
    max_entries: int = 4
    add_on_drop_pct: float = 7.0   # 추가매수 하락 기준(%) — 직전 매수가 대비
    max_positions: int = 5
    # 청산
    take_profit_pct: float = 15.0
    first_sell_portion: float = 50.0 # 첫 분할매도 비중(%)
    post_sell_stop_pct: float = 5.0  # 분할매도 후 고점 대비 하락 전량매도(%)
    post_sell_gain_pct: float = 0.0    # 분할매도 후 1차 매도가 대비 +이 % 이상이면 잔량 전량매도(0=끔). 2026-09-04
    sell_all_on_limit_up: bool = True
    limit_up_pct: float = 29.0     # 분할매도 후 전일종가 대비 +이 % 이상이면 전량매도(예 29≈상한가)
    # 리스크/운영
    max_unrealized_loss_krw: int = 500_000   # 보유 평가손실이 이 금액 이상이면 신규매수 중단(하락장 방어)
    order_type: str = "limit"      # limit | market
    tick_seconds: int = 5
    unfilled_cancel_min: int = 10        # 미체결 취소 지속시간(분): 아래 괴리 상태가 이 시간 이상 지속되면 취소(매수·매도 공통). 0=안 함
    unfilled_cancel_dev_pct: float = 1.0 # 미체결 취소 괴리율(%): 현재가가 주문가에서 이 % 이상 벗어난 상태 기준. 0=괴리 무관(접수 후 시간만). 2026-09-28

    @classmethod
    def from_settings(cls, settings_row: dict[str, Any] | None) -> "StrategyParams":
        """settings 행(dict)에서 로드. 값 우선순위: extra(jsonb) > 컬럼 > 기본값.

        신규 전략 파라미터는 주로 settings.extra 에 저장(docs/03). 일부는 컬럼에도 존재.
        **단위 호환(2026-09-28):** `extra.params_version` < 2(또는 없음)이면 옛 0~1 비율 필드를 ×100 해 % 로 변환.
        """
        s = settings_row or {}
        extra = s.get("extra") or {}
        version = int(extra.get("params_version") or 1)
        out: dict[str, Any] = {}
        for f in fields(cls):
            if f.name in extra and extra[f.name] is not None:
                out[f.name] = extra[f.name]
            elif f.name in s and s[f.name] is not None:
                out[f.name] = s[f.name]
        if version < PARAMS_VERSION:
            for k in RATIO_TO_PCT_FIELDS:
                if k in out:
                    out[k] = round(float(out[k]) * 100, 1)
        return cls(**out)

    def one_buy_krw(self) -> int:
        """1회 분할매수 금액 = 종목당 총액 × 1회 비중(%)."""
        return round(self.per_stock_krw * self.entry_split_pct / 100)   # 부동소수 오차 방지(33.3% → 333,000)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
