"""엔진 환경설정 로드 (.env). 시크릿은 여기서만 읽고, 로그에 평문 출력 금지."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENGINE_ROOT = Path(__file__).resolve().parents[1]  # engine/
load_dotenv(_ENGINE_ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()

# ── 키움 ──
KIWOOM_MODE = _get("KIWOOM_MODE", "demo").lower()
KIWOOM_APP_KEY = _get("KIWOOM_APP_KEY")
KIWOOM_SECRET = _get("KIWOOM_SECRET")
KIWOOM_ACCOUNT_NO = _get("KIWOOM_ACCOUNT_NO")

# ── Supabase ──
SUPABASE_URL = _get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = _get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_OWNER_UUID = _get("SUPABASE_OWNER_UUID")

# ── 기타 ──
LOG_LEVEL = _get("LOG_LEVEL", "INFO").upper()


def require(*names: str) -> None:
    """필수 env 누락 시 명확한 오류."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(f".env 에 다음 값이 필요합니다: {', '.join(missing)}")
