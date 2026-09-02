"""Relay 매핑/페이로드 단위 테스트 — supabase 클라이언트는 mock (네트워크 없음)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.analysis.candidates import Candidate
from src.broker.models import Order, OrderStatus, OrderType, Position, Side


def _relay(data=None):
    """Relay 인스턴스 + 체이닝되는 가짜 supabase 쿼리(q) 반환."""
    sb = MagicMock()
    q = sb.table.return_value
    for m in ("upsert", "insert", "select", "eq", "order", "limit", "update", "delete"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=data if data is not None else [])
    with patch("supabase.create_client", return_value=sb):
        from src.relay import Relay
        r = Relay("http://x", "key", "owner-uuid")
    return r, q


def test_upsert_candidates_drops_error_and_sets_owner():
    r, q = _relay()
    c = Candidate(code="005930", name="삼성전자", designated_date=date(2026, 4, 1),
                  release_date=date(2026, 4, 16), t5_close=70000, t15_close=35000,
                  recent_15_high=72000, release_amount=70000, current_price=68000,
                  drop_ratio=3, status="ok", signal="watch", error="무시될값")
    r.upsert_candidates([c])
    rows = q.upsert.call_args.args[0]
    row = rows[0]
    assert row["owner"] == "owner-uuid"
    assert "error" not in row                      # 테이블에 없는 컬럼 제거
    assert row["designated_date"] == "2026-04-01"  # 날짜 ISO 직렬화
    assert row["signal"] == "watch"
    assert q.upsert.call_args.kwargs["on_conflict"] == "owner,code"


def test_push_bot_state_includes_owner_and_heartbeat():
    r, q = _relay()
    r.push_bot_state(status="running", equity=1000)
    row = q.upsert.call_args.args[0]
    assert row["id"] == 1 and row["owner"] == "owner-uuid"
    assert row["status"] == "running" and row["equity"] == 1000
    assert "heartbeat_at" in row


def test_insert_order_maps_and_returns_id():
    r, q = _relay(data=[{"id": "ord-uuid-1"}])
    o = Order(code="005930", name="삼성전자", side=Side.BUY, qty=10,
              order_type=OrderType.LIMIT, price=70000, status=OrderStatus.SUBMITTED,
              broker_order_id="0000140", reason="entry")
    oid = r.insert_order(o)
    assert oid == "ord-uuid-1"
    row = q.insert.call_args.args[0]
    assert row["side"] == "buy" and row["order_type"] == "limit"
    assert row["status"] == "submitted" and row["broker_order_id"] == "0000140"
    assert row["owner"] == "owner-uuid"


def test_upsert_positions_computes_pnl():
    r, q = _relay()
    p = Position(code="005930", name="삼성전자", qty=10, avg_price=70000, current_price=71000)
    r.upsert_positions([p])
    row = q.upsert.call_args.args[0][0]
    assert row["pnl"] == (71000 - 70000) * 10
    assert row["owner"] == "owner-uuid" and row["qty"] == 10


def test_load_settings_returns_first_row():
    r, q = _relay(data=[{"id": 1, "mode": "demo", "enabled": False, "per_trade_krw": 1000000}])
    s = r.load_settings()
    assert s["mode"] == "demo" and s["per_trade_krw"] == 1000000


def test_ack_command_sets_processed_at_on_done():
    r, q = _relay()
    r.ack_command("cmd-1", "done", "ok")
    fields = q.update.call_args.args[0]
    assert fields["status"] == "done" and fields["result"] == "ok"
    assert "processed_at" in fields
