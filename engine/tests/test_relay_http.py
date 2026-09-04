"""Relay 통신 안정화 테스트 — HTTP/1.1 세션 교체 · 전송오류 재시도 · 종료 시 stopped 반영 (2026-09-04)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from src.relay import supabase_client as sc


def _relay(sb=None):
    sb = sb or MagicMock()
    with patch("supabase.create_client", return_value=sb):
        return sc.Relay("http://x", "key", "owner-uuid"), sb


def test_harden_http_replaces_http2_session_with_http1_keeping_base_and_headers():
    sb = MagicMock()
    old = httpx.Client(base_url="https://proj.supabase.co/rest/v1", headers={"apikey": "k", "Authorization": "Bearer k"})
    sb.postgrest.session = old
    r, _ = _relay(sb)
    new = sb.postgrest.session
    assert new is not old and isinstance(new, httpx.Client)
    assert str(new.base_url).startswith("https://proj.supabase.co/rest/v1")
    assert new.headers["apikey"] == "k" and new.headers["authorization"] == "Bearer k"
    assert new._transport._pool._http2 is False          # HTTP/1.1 강제
    assert old.is_closed
    new.close()


def test_harden_http_skips_when_session_is_not_httpx_client():
    r, sb = _relay()                                     # MagicMock 세션 → 교체 안 함, 예외 없음
    assert not isinstance(sb.postgrest.session, httpx.Client)


def test_exec_retries_once_on_transport_error(monkeypatch):
    r, _ = _relay()
    monkeypatch.setattr(sc, "RETRY_DELAY_SEC", 0)
    builder = MagicMock()
    builder.execute.side_effect = [httpx.RemoteProtocolError("Server disconnected"), SimpleNamespace(data=[1])]
    rebuilt = MagicMock(return_value=None)
    r._harden_http = rebuilt
    res = r._exec(lambda: builder)
    assert res.data == [1] and builder.execute.call_count == 2
    rebuilt.assert_called_once()                         # 재시도 전에 세션 재생성


def test_exec_gives_up_after_second_failure(monkeypatch):
    r, _ = _relay()
    monkeypatch.setattr(sc, "RETRY_DELAY_SEC", 0)
    builder = MagicMock()
    builder.execute.side_effect = httpx.ConnectError("down")
    r._harden_http = MagicMock()
    try:
        r._exec(lambda: builder)
        assert False, "예외가 나야 함"
    except httpx.TransportError:
        pass
    assert builder.execute.call_count == 2


def test_exec_does_not_retry_non_transport_errors():
    r, _ = _relay()
    builder = MagicMock()
    builder.execute.side_effect = RuntimeError("postgrest 4xx")
    try:
        r._exec(lambda: builder)
        assert False
    except RuntimeError:
        pass
    assert builder.execute.call_count == 1


def test_all_public_calls_go_through_exec():
    """쓰기/읽기 메서드가 전부 _exec(락·재시도) 경유하는지 — 우회 호출 방지."""
    r, sb = _relay()
    calls = []
    r._exec = lambda build: (calls.append(1), SimpleNamespace(data=[{"id": "x"}]))[1]
    r.push_bot_state(status="running"); r.upsert_positions([]); r.insert_event(type="t", severity="info", title="a")
    r.load_settings(); r.load_strategy_states(); r.save_strategy_state("c", entries_done=1)
    r.delete_strategy_state("c"); r.acquire_lock("h"); r.release_lock("h"); r.ack_command("id", "done")
    r.remove_position("c"); r.remove_candidate("c"); r.prune_candidates(["c"]); r.update_order("id", status="filled")
    assert len(calls) == 13
    assert not sb.table.return_value.execute.called    # 직접 execute 호출 없음


def test_shutdown_pushes_stopped_and_releases_lock():
    from src.main import shutdown
    engine = MagicMock()
    engine.status = "running"
    lock = MagicMock()
    shutdown(engine, lock)
    assert engine.status == "stopped"
    engine._heartbeat.assert_called_once_with(False)
    engine._emit.assert_called_once()
    lock.release.assert_called_once()


def test_shutdown_without_lock_and_heartbeat_failure_is_safe():
    from src.main import shutdown
    engine = MagicMock()
    engine._heartbeat.side_effect = RuntimeError("db down")
    shutdown(engine, None)
    assert engine.status == "stopped" and engine._emit.called
