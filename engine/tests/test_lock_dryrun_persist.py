"""이중 실행 락 · 드라이런 · 전략상태 영속화 테스트 (클라우드 이관 1단계, D-015)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.analysis.candidates import Candidate
from src.broker.models import Balance, Order, OrderStatus, OrderType, Position, Side
from src.relay.dry_run import DryRunRelay
from src.strategy.engine import StrategyEngine
from src.strategy.indicators import Envelope
from src.strategy.params import StrategyParams
from src.strategy.state import PositionState

KST = timezone(timedelta(hours=9))
NOW = lambda: datetime(2026, 9, 2, 10, 0, tzinfo=KST)


def _broker(price=9000, positions=None, cash=1_000_000):
    b = MagicMock()
    b.get_price.return_value = price
    b.get_positions.return_value = positions or []
    b.get_unfilled_orders.return_value = []
    b.get_balance.return_value = Balance(cash=cash, equity=cash, stock_value=0)
    b.cached_price.return_value = None
    b.place_order.return_value = Order(
        code="005930", name="삼성전자", side=Side.BUY, qty=1, order_type=OrderType.LIMIT,
        price=price, status=OrderStatus.SUBMITTED, broker_order_id="1")
    return b


def _cand(drop_ratio=35, status="ok"):
    return Candidate(code="005930", name="삼성전자", designated_date=None, release_date=None,
                     t5_close=None, t15_close=None, recent_15_high=None,
                     release_amount=100000, current_price=9000, drop_ratio=drop_ratio, status=status)


def _engine(broker, relay=None):
    e = StrategyEngine(broker, relay or MagicMock(), now=NOW)
    e.status = "running"
    e.params = StrategyParams(enabled=True)
    e.candidates = {"005930": _cand()}
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    e.prev_close = {"005930": 9500}
    return e


# ── Relay: 락 rpc / strategy_state ──
def _relay(data=None, rpc_data=None):
    sb = MagicMock()
    q = sb.table.return_value
    for m in ("upsert", "insert", "select", "eq", "order", "limit", "update", "delete"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=data if data is not None else [])
    sb.rpc.return_value.execute.return_value = SimpleNamespace(data=rpc_data)
    with patch("supabase.create_client", return_value=sb):
        from src.relay import Relay
        r = Relay("http://x", "key", "owner-uuid")
    return r, sb, q


def test_acquire_lock_calls_rpc_and_returns_bool():
    r, sb, _ = _relay(rpc_data=True)
    assert r.acquire_lock("cloud-seoul", 90) is True
    name, params = sb.rpc.call_args.args
    assert name == "acquire_bot_lock"
    assert params == {"p_owner": "owner-uuid", "p_holder": "cloud-seoul", "p_stale_sec": 90}
    r2, _, _ = _relay(rpc_data=False)
    assert r2.acquire_lock("home-pc") is False


def test_release_lock_rpc():
    r, sb, _ = _relay(rpc_data=True)
    r.release_lock("cloud-seoul")
    assert sb.rpc.call_args.args[0] == "release_bot_lock"


def test_save_strategy_state_upsert_by_owner_code():
    r, _, q = _relay()
    r.save_strategy_state("005930", entries_done=2, invested_krw=600_000,
                          partial_sold=False, peak_since_partial=0, zone_low=8800)
    row = q.upsert.call_args.args[0]
    assert row["owner"] == "owner-uuid" and row["code"] == "005930"
    assert row["entries_done"] == 2 and row["zone_low"] == 8800 and "updated_at" in row
    assert q.upsert.call_args.kwargs["on_conflict"] == "owner,code"


def test_load_strategy_states_filters_owner():
    r, _, q = _relay(data=[{"code": "005930", "entries_done": 1}])
    assert r.load_strategy_states() == [{"code": "005930", "entries_done": 1}]
    q.eq.assert_called_with("owner", "owner-uuid")


# ── DryRunRelay ──
def test_dry_run_relay_ignores_writes_and_delegates_reads():
    real = MagicMock()
    real.owner = "o"
    real.load_settings.return_value = {"enabled": True}
    d = DryRunRelay(real)
    d.push_bot_state(status="running")
    d.insert_event(type="x", severity="info", title="t")
    assert d.insert_order(MagicMock()) == ""
    d.upsert_candidates([]); d.save_strategy_state("c", entries_done=1); d.start_command_listener(lambda r: None)
    assert d.acquire_lock("h") is False
    assert d.load_settings() == {"enabled": True}
    assert not real.push_bot_state.called and not real.insert_event.called
    assert not real.insert_order.called and not real.start_command_listener.called


# ── 엔진: 드라이런 ──
@patch("src.strategy.engine.is_market_open", return_value=True)
def test_dry_run_engine_no_orders_no_writes(_m):
    broker = _broker()
    real = MagicMock()
    e = _engine(broker, real)
    e.set_live(False, "test")
    assert isinstance(e.relay, DryRunRelay)
    e.tick()
    assert not broker.place_order.called          # 주문 없음
    assert not real.push_bot_state.called         # 하트비트 등 쓰기 없음
    assert not real.insert_order.called and not real.save_strategy_state.called
    # 매수 시뮬 로그는 1회만(중복 억제)
    assert "buy:005930:new" in e._dry_logged
    e.tick()
    assert not broker.place_order.called


def test_dry_run_kill_and_close_position_do_not_order():
    pos = Position(code="005930", name="삼성전자", qty=10, avg_price=10000, current_price=9000)
    broker = _broker(positions=[pos])
    e = _engine(broker)
    e.positions = {"005930": pos}
    e.set_live(False, "test")
    e.kill()
    assert not broker.place_order.called and e.status == "stopped"
    assert e.close_position("005930") == "드라이런 — 주문 안 함"
    assert not broker.place_order.called


def test_set_live_back_restores_real_relay():
    real = MagicMock()
    e = _engine(_broker(), real)
    e.set_live(False, "a"); e.set_live(True, "b")
    assert e.relay is real and e.live


# ── 엔진: 영속화 ──
@patch("src.strategy.engine.is_market_open", return_value=True)
def test_buy_persists_strategy_state(_m):
    broker = _broker()
    real = MagicMock()
    e = _engine(broker, real)
    e.tick()
    assert broker.place_order.called
    kw = real.save_strategy_state.call_args.kwargs
    assert real.save_strategy_state.call_args.args[0] == "005930"
    assert kw["entries_done"] == 1 and kw["invested_krw"] == 33 * 9000 and kw["zone_low"] == 9000


def test_restore_state_rebuilds_states_and_lows():
    real = MagicMock()
    real.load_strategy_states.return_value = [
        {"code": "005930", "entries_done": 2, "invested_krw": 600000, "partial_sold": True,
         "peak_since_partial": 12000, "partial_sell_price": 11500, "zone_low": None},
        {"code": "000660", "entries_done": 0, "invested_krw": 0, "partial_sold": False,
         "peak_since_partial": 0, "zone_low": 8800},
    ]
    e = StrategyEngine(_broker(), real, now=NOW)
    assert e.restore_state() == 2
    st = e.states["005930"]
    assert st.entries_done == 2 and st.partial_sold and st.peak_since_partial == 12000
    assert st.partial_sell_price == 11500
    assert "000660" not in e.states and e.candidate_lows == {"000660": 8800}


def test_restore_state_failure_is_safe():
    real = MagicMock()
    real.load_strategy_states.side_effect = RuntimeError("down")
    e = StrategyEngine(_broker(), real, now=NOW)
    assert e.restore_state() == 0 and e.states == {}


def test_sync_positions_keeps_restored_state_and_deletes_closed():
    pos = Position(code="005930", name="삼성전자", qty=10, avg_price=10000, current_price=9000)
    real = MagicMock()
    e = _engine(_broker(positions=[pos]), real)
    e.states = {"005930": PositionState("005930", entries_done=3, invested_krw=900000),
                "000660": PositionState("000660", entries_done=1, invested_krw=100000)}  # 청산됨
    e.sync_positions()
    assert e.states["005930"].entries_done == 3          # 복원값 유지(1로 덮지 않음)
    assert "000660" not in e.states
    real.delete_strategy_state.assert_called_with("000660")


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_peak_change_persists(_m):
    pos = Position(code="005930", name="삼성전자", qty=10, avg_price=10000, current_price=12000)
    real = MagicMock()
    e = _engine(_broker(price=12000, positions=[pos]), real)
    e.positions = {"005930": pos}
    e.states = {"005930": PositionState("005930", entries_done=1, invested_krw=100000,
                                        partial_sold=True, peak_since_partial=11000)}
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    e._evaluate_exits(set())
    kw = real.save_strategy_state.call_args.kwargs
    assert kw["peak_since_partial"] == 12000 and kw["partial_sold"] is True
    assert "partial_sell_price" in kw


def test_candidate_low_change_persists_and_reset_deletes():
    real = MagicMock()
    broker = _broker()
    broker.cached_price.return_value = 9000
    e = _engine(broker, real)
    e._update_candidate_lows()
    assert real.save_strategy_state.call_args.kwargs["zone_low"] == 9000
    broker.cached_price.return_value = 9000          # 변화 없음 → 추가 저장 없음
    n = real.save_strategy_state.call_count
    e._update_candidate_lows()
    assert real.save_strategy_state.call_count == n
    e.candidates["005930"].drop_ratio = 10           # 구간 이탈 → 저점 리셋 → 행 삭제
    e._update_candidate_lows()
    real.delete_strategy_state.assert_called_with("005930")


# ── LockKeeper(main) ──
def test_lock_keeper_start_live_and_lose():
    from src.main import LockKeeper
    relay = MagicMock()
    relay.acquire_lock.return_value = True
    e = _engine(_broker(), relay)
    lk = LockKeeper(relay, e, "cloud", 90, 0)
    assert lk.start() is True and e.live
    relay.ensure_singletons.assert_called_once()
    relay.start_command_listener.assert_called_once()
    relay.acquire_lock.return_value = False          # 갱신 실패 → 관찰 모드
    lk.tick()
    assert lk.held is False and e.live is False
    relay.stop.assert_called()
    relay.acquire_lock.return_value = True           # 재획득 → LIVE 복귀
    lk.tick()
    assert lk.held and e.live and relay.start_command_listener.call_count == 2


def test_lock_keeper_start_observe_when_held_elsewhere():
    from src.main import LockKeeper
    relay = MagicMock()
    relay.acquire_lock.return_value = False
    e = _engine(_broker(), relay)
    lk = LockKeeper(relay, e, "home-pc", 90, 0)
    assert lk.start() is False and e.live is False
    assert not relay.start_command_listener.called and not relay.ensure_singletons.called
    lk.release()
    assert not relay.release_lock.called             # 미보유 시 해제 호출 없음
