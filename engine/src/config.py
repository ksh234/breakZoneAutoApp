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
# 봇은 secret key(sb_secret_…, 신규) 권장. legacy service_role 도 폴백 지원(2026말 폐기).
def _norm_supabase_url(u: str) -> str:
    """base URL 만 남긴다(끝의 /rest/v1 · 슬래시 제거). 클라이언트가 경로를 붙임."""
    u = u.strip().rstrip("/")
    for suffix in ("/rest/v1", "/rest"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u.rstrip("/")


SUPABASE_URL = _norm_supabase_url(_get("SUPABASE_URL"))
SUPABASE_SECRET_KEY = _get("SUPABASE_SECRET_KEY") or _get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_OWNER_UUID = _get("SUPABASE_OWNER_UUID")

# ── 봇 인스턴스 / 이중 실행 방지 / 드라이런 (docs/05 §4, docs/06) ──
import socket
BOT_HOLDER_ID = _get("BOT_HOLDER_ID") or socket.gethostname()      # 락 보유자 식별(호스트명 기본)
BOT_LOCK_STALE_SEC = int(_get("BOT_LOCK_STALE_SEC", "90"))           # 이 시간 넘게 하트비트 없으면 승계 가능
BOT_LOCK_RENEW_SEC = int(_get("BOT_LOCK_RENEW_SEC", "15"))           # 락 갱신/재시도 주기
BOT_DRY_RUN = _get("BOT_DRY_RUN", "0").lower() in ("1", "true", "yes")  # 1=주문·Supabase쓰기 전부 금지(관찰)

# ── 기타 ──
LOG_LEVEL = _get("LOG_LEVEL", "INFO").upper()
LOG_DIR = _get("LOG_DIR", "logs")      # 회전 로그 파일 폴더(engine/ 기준 상대경로). 0=파일 로그 끔(journald 등)


def require(*names: str) -> None:
    """필수 env 누락 시 명확한 오류."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(f".env 에 다음 값이 필요합니다: {', '.join(missing)}")
