"""Supabase 중계 클라이언트 (docs/02 §7). 봇→DB 상태 push + 명령 구독 + 락 + 전략상태.

- service_role(secret) 키 사용(서버 전용, RLS 우회). owner 는 앱 사용자 uuid.
- 명령 수신은 폴링 방식(백그라운드 스레드, 기본 1.5초). Realtime 은 후속 개선.
  (D-011 동기+스레드 기조. 폴링이 단순·견고하고 acceptance "1~2초 내 수신" 충족)
- 통신 안정화(2026-09-04): supabase-py 기본 HTTP/2 세션을 두 스레드(메인 tick·명령 폴링)가
  공유하면 "Server disconnected"/"cannot receive data before headers" 가 간헐 발생 →
  ① HTTP/1.1 + 짧은 keepalive 세션으로 교체 ② 모든 요청을 스레드 락으로 직렬화
  ③ 전송 오류 시 세션 재생성 후 1회 재시도.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from ..analysis.candidates import Candidate
from ..broker.models import Order, Position

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
HTTP_LIMITS = httpx.Limits(max_connections=4, max_keepalive_connections=2, keepalive_expiry=15.0)
RETRY_DELAY_SEC = 0.5


def _now() -> str:
    return datetime.now(KST).isoformat()


class Relay:
    def __init__(self, url: str, service_role_key: str, owner: str):
        if not (url and service_role_key and owner):
            raise ValueError("url / service_role_key / owner 필수")
        from supabase import create_client  # 지연 import
        self.owner = owner
        self.sb = create_client(url, service_role_key)
        self._lock = threading.Lock()          # 스레드 간 HTTP 세션 공유 직렬화
        self._cmd_stop = threading.Event()
        self._cmd_thread: Optional[threading.Thread] = None
        self._harden_http()

    # ── HTTP 세션 안정화 ──────────────────────────────
    def _harden_http(self) -> None:
        """postgrest 세션(HTTP/2)을 같은 base_url·헤더의 HTTP/1.1 세션으로 교체. 구조가 다르면 건너뜀."""
        try:
            pg = self.sb.postgrest
            old = getattr(pg, "session", None)
            if not isinstance(old, httpx.Client):
                return
            new = httpx.Client(base_url=old.base_url, headers=dict(old.headers), timeout=HTTP_TIMEOUT,
                               limits=HTTP_LIMITS, follow_redirects=True, http2=False)
            pg.session = new
            try:
                old.close()
            except Exception:
                pass
        except Exception:
            logger.warning("HTTP 세션 교체 실패 — 기본 세션 유지", exc_info=True)

    def _exec(self, build: Callable[[], Any]) -> Any:
        """build() 로 요청 빌더를 만들어 execute. 락으로 직렬화, 전송 오류 시 세션 재생성 후 1회 재시도."""
        with self._lock:
            try:
                return build().execute()
            except httpx.TransportError as e:
                logger.warning("Supabase 전송 오류 → 세션 재생성 후 재시도: %s", e)
                self._harden_http()
                time.sleep(RETRY_DELAY_SEC)
                return build().execute()

    # ── 초기화 ────────────────────────────────────────
    def ensure_singletons(self) -> None:
        """settings/bot_state 싱글턴 1행 보장(기존 값은 보존)."""
        self._exec(lambda: self.sb.table("settings").upsert(
            {"id": 1, "owner": self.owner}, on_conflict="id", ignore_duplicates=True))
        self._exec(lambda: self.sb.table("bot_state").upsert(
            {"id": 1, "owner": self.owner}, on_conflict="id", ignore_duplicates=True))

    # ── 상태 push ─────────────────────────────────────
    def push_bot_state(self, **fields: Any) -> None:
        row = {"id": 1, "owner": self.owner, "heartbeat_at": _now(), **fields}
        self._exec(lambda: self.sb.table("bot_state").upsert(row, on_conflict="id"))

    def upsert_candidates(self, candidates: list[Candidate]) -> None:
        if not candidates:
            return
        rows = []
        for c in candidates:
            row = c.to_row()
            row.pop("error", None)          # candidates 테이블에 없는 컬럼 제거
            row["owner"] = self.owner
            rows.append(row)
        self._exec(lambda: self.sb.table("candidates").upsert(rows, on_conflict="owner,code"))

    def remove_candidate(self, code: str) -> None:
        self._exec(lambda: self.sb.table("candidates").delete().eq("owner", self.owner).eq("code", code))

    def prune_candidates(self, keep_codes: list[str]) -> None:
        """현재 후보 목록에 없는 후보 행 삭제(스테일 정리). keep_codes 비면 전체 삭제."""
        def build():
            q = self.sb.table("candidates").delete().eq("owner", self.owner)
            if keep_codes:
                q = q.not_.in_("code", keep_codes)
            return q
        self._exec(build)

    def upsert_positions(self, positions: list[Position]) -> None:
        rows = [{
            "owner": self.owner, "code": p.code, "name": p.name, "qty": p.qty,
            "avg_price": p.avg_price, "current_price": p.current_price,
            "pnl": p.pnl, "pnl_pct": round(p.pnl_pct, 2),
        } for p in positions]
        if rows:
            self._exec(lambda: self.sb.table("positions").upsert(rows, on_conflict="owner,code"))

    def remove_position(self, code: str) -> None:
        self._exec(lambda: self.sb.table("positions").delete().eq("owner", self.owner).eq("code", code))

    def insert_order(self, order: Order) -> str:
        row = {
            "owner": self.owner, "code": order.code, "name": order.name,
            "side": order.side.value, "qty": order.qty, "order_type": order.order_type.value,
            "price": order.price, "status": order.status.value,
            "broker_order_id": order.broker_order_id, "filled_qty": order.filled_qty,
            "filled_price": order.filled_price, "reason": order.reason,
        }
        res = self._exec(lambda: self.sb.table("orders").insert(row))
        return res.data[0]["id"]

    def update_order(self, order_id: str, **fields: Any) -> None:
        self._exec(lambda: self.sb.table("orders").update(fields).eq("id", order_id))

    def insert_event(self, type: str, severity: str, title: str,
                     message: str = "", payload: Optional[dict] = None) -> None:
        self._exec(lambda: self.sb.table("events").insert({
            "owner": self.owner, "type": type, "severity": severity,
            "title": title, "message": message, "payload": payload or {},
        }))

    def load_settings(self) -> dict:
        res = self._exec(lambda: self.sb.table("settings").select("*").eq("id", 1).limit(1))
        return res.data[0] if res.data else {}

    # ── 전략상태 영속화(strategy_state) ───────────────
    def load_strategy_states(self) -> list[dict]:
        res = self._exec(lambda: self.sb.table("strategy_state").select("*").eq("owner", self.owner))
        return res.data or []

    def save_strategy_state(self, code: str, **fields: Any) -> None:
        row = {"owner": self.owner, "code": code, "updated_at": _now(), **fields}
        self._exec(lambda: self.sb.table("strategy_state").upsert(row, on_conflict="owner,code"))

    def delete_strategy_state(self, code: str) -> None:
        self._exec(lambda: self.sb.table("strategy_state").delete().eq("owner", self.owner).eq("code", code))

    # ── 이중 실행 방지 락(bot_lock) ───────────────────
    def acquire_lock(self, holder: str, stale_sec: int = 90) -> bool:
        """획득 또는 갱신(내가 보유 중이면 heartbeat 갱신). 다른 봇이 살아있으면 False."""
        res = self._exec(lambda: self.sb.rpc("acquire_bot_lock", {
            "p_owner": self.owner, "p_holder": holder, "p_stale_sec": stale_sec}))
        return bool(res.data)

    def release_lock(self, holder: str) -> None:
        self._exec(lambda: self.sb.rpc("release_bot_lock", {"p_owner": self.owner, "p_holder": holder}))

    # ── 명령 구독(폴링) ───────────────────────────────
    def start_command_listener(self, handler: Callable[[dict], Optional[str]],
                               interval: float = 1.5) -> None:
        """commands(status='pending') 폴링 → ack → handler → done/failed.

        handler(row) 는 결과 문자열(or None) 반환. 예외 시 failed 로 기록.
        """
        if self._cmd_thread and self._cmd_thread.is_alive():
            return
        self._cmd_stop.clear()
        self._cmd_thread = threading.Thread(
            target=self._cmd_loop, args=(handler, interval), name="cmd-listener", daemon=True)
        self._cmd_thread.start()

    def _cmd_loop(self, handler: Callable[[dict], Optional[str]], interval: float) -> None:
        while not self._cmd_stop.is_set():
            try:
                res = self._exec(lambda: self.sb.table("commands").select("*")
                                 .eq("owner", self.owner).eq("status", "pending")
                                 .order("created_at"))
                for row in res.data or []:
                    self.ack_command(row["id"], "acked")
                    try:
                        result = handler(row)
                        self.ack_command(row["id"], "done", result or "")
                    except Exception as e:
                        logger.exception("명령 처리 실패 %s", row.get("type"))
                        self.ack_command(row["id"], "failed", str(e))
            except Exception as e:
                logger.warning("commands 폴링 오류: %s", e)
            self._cmd_stop.wait(interval)

    def ack_command(self, command_id: str, status: str, result: str = "") -> None:
        fields: dict[str, Any] = {"status": status, "result": result}
        if status in ("done", "failed"):
            fields["processed_at"] = _now()
        self._exec(lambda: self.sb.table("commands").update(fields).eq("id", command_id))

    def stop(self) -> None:
        self._cmd_stop.set()
