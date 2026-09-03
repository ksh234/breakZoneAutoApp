"""드라이런 Relay — Supabase 쓰기 전부 무시(로그만), 읽기는 실제 Relay 위임. docs/05 §4, docs/06.

용도:
- PC 에서 새 코드를 장중에 돌려보며 판정만 관찰(BOT_DRY_RUN=1). 클라우드 봇의 상태를 덮어쓰지 않음.
- 락 미획득 봇의 관찰 모드(다른 인스턴스가 운용 중).
엔진은 이 객체를 Relay 대신 쓰므로 쓰기 경로에 분기가 없어도 안전.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_READS = {"load_settings", "load_strategy_states"}


class DryRunRelay:
    def __init__(self, real: Any):
        self._real = real
        self.owner = getattr(real, "owner", "")

    def __getattr__(self, name: str):
        if name in _READS:
            return getattr(self._real, name)

        def _noop(*args: Any, **kwargs: Any):
            logger.debug("[DRY] relay.%s 무시", name)
            return "" if name == "insert_order" else False if name == "acquire_lock" else None
        return _noop
