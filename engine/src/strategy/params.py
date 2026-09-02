"""전략 파라미터 — settings(앱에서 조절)에서 로드. 전부 조절 가능. docs/03 §6."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class StrategyParams:
    enabled: bool = False
    mode: str = "demo"
    # Envelope
    env_period: int = 20
    env_band: float = 0.10
    # 진입
    entry_drop_min: float = 30.0
    entry_drop_max: float = 40.0
    min_price: int = 1000          # 최소 매수가(원) — 이 미만 종목은 매수 안 함(0=무제한)
    per_stock_krw: int = 1_000_000
    entry_split_pct: float = 0.30
    max_entries: int = 4
    add_on_drop_pct: float = 0.07
    max_positions: int = 5
    # 청산
    take_profit_pct: float = 15.0
    first_sell_portion: float = 0.50
    post_sell_stop_pct: float = 0.05
    sell_all_on_limit_up: bool = True
    # 리스크/운영
    daily_max_loss_krw: int = 500_000
    order_type: str = "limit"      # limit | market
    tick_seconds: int = 5

    @classmethod
    def from_settings(cls, settings_row: dict[str, Any] | None) -> "StrategyParams":
        """settings 행(dict)에서 로드. 값 우선순위: extra(jsonb) > 컬럼 > 기본값.

        신규 전략 파라미터는 주로 settings.extra 에 저장(docs/03). 일부는 컬럼에도 존재.
        """
        s = settings_row or {}
        extra = s.get("extra") or {}
        out: dict[str, Any] = {}
        for f in fields(cls):
            if f.name in extra and extra[f.name] is not None:
                out[f.name] = extra[f.name]
            elif f.name in s and s[f.name] is not None:
                out[f.name] = s[f.name]
        return cls(**out)

    def one_buy_krw(self) -> int:
        """1회 분할매수 금액 = 종목당 총액 × 1회 비중."""
        return int(self.per_stock_krw * self.entry_split_pct)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
