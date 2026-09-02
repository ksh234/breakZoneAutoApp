"""Supabase 중계 클라이언트 (docs/02 §7). 봇→DB 상태 push + 명령 구독.

- service_role 키 사용(서버 전용, RLS 우회). owner 는 앱 사용자 uuid.
- 명령 수신은 폴링 방식(백그라운드 스레드, 기본 1.5초). Realtime 은 후속 개선.
  (D-011 동기+스레드 기조. 폴링이 단순·견고하고 acceptance "1~2초 내 수신" 충족)
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from ..analysis.candidates import Candidate
from ..broker.models import Order, Position

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(KST).isoformat()


class Relay:
    def __init__(self, url: str, service_role_key: str, owner: str):
        if not (url and service_role_key and owner):
            raise ValueError("url / service_role_key / owner 필수")
        from supabase import create_client  # 지연 import
        self.owner = owner
        self.sb = create_client(url, service_role_key)
        self._cmd_stop = threading.Event()
        self._cmd_thread: Optional[threading.Thread] = None

    # ── 초기화 ────────────────────────────────────────
    def ensure_singletons(self) -> None:
        """settings/bot_state 싱글턴 1행 보장(기존 값은 보존)."""
        self.sb.table("settings").upsert(
            {"id": 1, "owner": self.owner}, on_conflict="id", ignore_duplicates=True
        ).execute()
        self.sb.table("bot_state").upsert(
            {"id": 1, "owner": self.owner}, on_conflict="id", ignore_duplicates=True
        ).execute()

    # ── 상태 push ─────────────────────────────────────
    def push_bot_state(self, **fields: Any) -> None:
        row = {"id": 1, "owner": self.owner, "heartbeat_at": _now(), **fields}
        self.sb.table("bot_state").upsert(row, on_conflict="id").execute()

    def upsert_candidates(self, candidates: list[Candidate]) -> None:
        if not candidates:
            return
        rows = []
        for c in candidates:
            row = c.to_row()
            row.pop("error", None)          # candidates 테이블에 없는 컬럼 제거
            row["owner"] = self.owner
            rows.append(row)
        self.sb.table("candidates").upsert(rows, on_conflict="owner,code").execute()

    def upsert_positions(self, positions: list[Position]) -> None:
        rows = [{
            "owner": self.owner, "code": p.code, "name": p.name, "qty": p.qty,
            "avg_price": p.avg_price, "current_price": p.current_price,
            "pnl": p.pnl, "pnl_pct": round(p.pnl_pct, 2),
        } for p in positions]
        if rows:
            self.sb.table("positions").upsert(rows, on_conflict="owner,code").execute()

    def remove_position(self, code: str) -> None:
        self.sb.table("positions").delete().eq("owner", self.owner).eq("code", code).execute()

    def insert_order(self, order: Order) -> str:
        row = {
            "owner": self.owner, "code": order.code, "name": order.name,
            "side": order.side.value, "qty": order.qty, "order_type": order.order_type.value,
            "price": order.price, "status": order.status.value,
            "broker_order_id": order.broker_order_id, "filled_qty": order.filled_qty,
            "filled_price": order.filled_price, "reason": order.reason,
        }
        res = self.sb.table("orders").insert(row).execute()
        return res.data[0]["id"]

    def update_order(self, order_id: str, **fields: Any) -> None:
        self.sb.table("orders").update(fields).eq("id", order_id).execute()

    def insert_event(self, type: str, severity: str, title: str,
                     message: str = "", payload: Optional[dict] = None) -> None:
        self.sb.table("events").insert({
            "owner": self.owner, "type": type, "severity": severity,
            "title": title, "message": message, "payload": payload or {},
        }).execute()

    def load_settings(self) -> dict:
        res = self.sb.table("settings").select("*").eq("id", 1).limit(1).execute()
        return res.data[0] if res.data else {}

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
                res = (self.sb.table("commands").select("*")
                       .eq("owner", self.owner).eq("status", "pending")
                       .order("created_at").execute())
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
        self.sb.table("commands").update(fields).eq("id", command_id).execute()

    def stop(self) -> None:
        self._cmd_stop.set()
