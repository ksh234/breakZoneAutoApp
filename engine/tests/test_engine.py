"""StrategyEngine tick 흐름 테스트 — broker/relay mock, is_market_open 강제 True."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.analysis.candidates import Candidate
from src.broker.models import Balance, Order, OrderStatus, OrderType, Position, Side
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
    b.cached_price.return_value = None   # 후보 표시 갱신은 테스트에서 무시
    b.get_order_fills.return_value = []
    b.get_day_realized_pnl.return_value = None
    b.place_order.return_value = Order(
        code="005930", name="삼성전자", side=Side.BUY, qty=1,
        order_type=OrderType.LIMIT, price=price, status=OrderStatus.SUBMITTED,
        broker_order_id="1")
    return b


def _cand(drop_ratio=35, status="ok"):
    return Candidate(code="005930", name="삼성전자", designated_date=None, release_date=None,
                     t5_close=None, t15_close=None, recent_15_high=None,
                     release_amount=100000, current_price=9000, drop_ratio=drop_ratio, status=status)


def _engine(broker):
    e = StrategyEngine(broker, MagicMock(), now=NOW)
    e.status = "running"
    e.params = StrategyParams(enabled=True)
    return e


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_tick_places_buy_on_entry_signal(_mock_market):
    broker = _broker(price=9000, positions=[])
    e = _engine(broker)
    e.candidates = {"005930": _cand(drop_ratio=35)}
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}  # 9000 < 9500
    e.prev_close = {"005930": 9500}
    e.tick()
    assert broker.place_order.called
    args = broker.place_order.call_args.args
    assert args[1] == Side.BUY and args[2] == 300_000 // 9000  # one_buy/price


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_tick_no_buy_when_drop_below_threshold(_mock_market):
    broker = _broker(price=9000, positions=[])
    e = _engine(broker)
    e.candidates = {"005930": _cand(drop_ratio=25)}  # 25 < 기준 30 → 매수 안 함
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    e.tick()
    assert not broker.place_order.called


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_tick_partial_take_profit_sell(_mock_market):
    pos = Position(code="005930", name="삼성전자", qty=100, avg_price=10000, current_price=12000)
    broker = _broker(price=12000, positions=[pos], cash=0)
    e = _engine(broker)
    e.candidates = {}  # 진입 없음
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}  # 12000 > 11000
    e.prev_close = {"005930": 11000}
    e.tick()
    assert broker.place_order.called
    args = broker.place_order.call_args.args
    assert args[1] == Side.SELL and args[2] == 50  # 100 * 0.5


@patch("src.strategy.engine.is_market_open", return_value=False)
def test_tick_heartbeat_only_when_closed(_mock_market):
    broker = _broker()
    e = _engine(broker)
    e.candidates = {"005930": _cand()}
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    e.tick()
    assert not broker.place_order.called
    e.relay.push_bot_state.assert_called()  # 하트비트는 발생


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_paused_no_trade(_mock_market):
    broker = _broker(positions=[])
    e = _engine(broker)
    e.status = "paused"
    e.candidates = {"005930": _cand()}
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    e.tick()
    assert not broker.place_order.called


def test_at_limit_up_uses_param():
    e = _engine(_broker())
    e.prev_close = {"005930": 10000}
    e.params = StrategyParams(enabled=True, limit_up_pct=28)
    assert e._at_limit_up("005930", 12800)      # +28% → 전량매도 트리거
    assert not e._at_limit_up("005930", 12700)  # +27% → 아직
    e.params = StrategyParams(enabled=True, limit_up_pct=28, sell_all_on_limit_up=False)
    assert not e._at_limit_up("005930", 13000)  # 기능 off


def test_handle_command_kill_sells_all():
    pos = Position(code="005930", name="삼성전자", qty=100, avg_price=10000, current_price=9000)
    broker = _broker(positions=[pos])
    e = _engine(broker)
    e.handle_command({"type": "kill", "payload": {}})
    assert broker.place_order.called
    args = broker.place_order.call_args.args
    assert args[1] == Side.SELL and args[3] == OrderType.MARKET  # 시장가 전량
    assert e.status == "stopped"


# ── settings 재로드(앱 설정 저장 반영) ──
def _engine_with_clock(settings_row):
    """실제 load_params 경로 사용. clock['now'] 로 시각 조절."""
    clock = {"now": datetime(2026, 9, 2, 10, 0, tzinfo=KST)}
    relay = MagicMock()
    relay.load_settings.return_value = settings_row
    e = StrategyEngine(_broker(), relay, now=lambda: clock["now"])
    e.load_params()                      # startup 로드 → 주기 재로드 활성
    return e, relay, clock


def test_startup_load_params_no_event():
    e, relay, _ = _engine_with_clock({"enabled": False, "extra": {"entry_drop_pct": 33}})
    assert e.params.enabled is False and e.params.entry_drop_pct == 33
    assert not relay.insert_event.called   # 시작 로드는 이벤트 없음


@patch("src.strategy.engine.is_market_open", return_value=False)
def test_periodic_reload_applies_app_settings_even_when_stopped(_m):
    e, relay, clock = _engine_with_clock({"enabled": False, "extra": {}})
    relay.load_settings.return_value = {"enabled": True, "extra": {"entry_drop_pct": 40}}
    clock["now"] += timedelta(seconds=10)
    e.tick()                             # 30초 전 → 아직 반영 안 됨
    assert e.params.enabled is False
    clock["now"] += timedelta(seconds=25)
    e.tick()                             # 35초 경과, status=stopped 여도 반영
    assert e.params.enabled is True and e.params.entry_drop_pct == 40
    kw = relay.insert_event.call_args.kwargs
    assert kw["title"] == "설정 반영" and "enabled=True" in kw["message"]


@patch("src.strategy.engine.is_market_open", return_value=False)
def test_periodic_reload_unchanged_no_event(_m):
    e, relay, clock = _engine_with_clock({"enabled": False, "extra": {}})
    clock["now"] += timedelta(seconds=60)
    e.tick()
    assert not relay.insert_event.called


def test_set_param_command_reloads_immediately():
    e, relay, _ = _engine_with_clock({"enabled": False, "extra": {}})
    relay.load_settings.return_value = {"enabled": True, "extra": {}}
    assert e.handle_command({"type": "set_param", "payload": {}}) == "설정 반영"
    assert e.params.enabled is True
    assert e.handle_command({"type": "set_param", "payload": {}}) == "설정 변경 없음"


def test_load_params_failure_keeps_previous():
    e, relay, _ = _engine_with_clock({"enabled": True, "extra": {}})
    relay.load_settings.side_effect = RuntimeError("down")
    assert e.load_params(source="periodic") is False
    assert e.params.enabled is True


# ── 2026-09-22: 첫 매수 직후 상태 유실 버그 / 추매 저점 반등 ──
def test_state_survives_until_position_appears():
    """매수 주문 후 잔고에 아직 없어도(미체결) 상태를 지우지 않고, 체결 후에도 분할횟수·누적액이 이어진다."""
    clock = {"now": datetime(2026, 9, 22, 13, 45, tzinfo=KST)}
    broker = _broker(price=4770, positions=[])
    e = StrategyEngine(broker, MagicMock(), now=lambda: clock["now"])
    e.status = "running"; e.params = StrategyParams(enabled=True)
    e.candidates = {"005930": _cand(drop_ratio=35)}
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    e.prev_close = {"005930": 5000}
    with patch("src.strategy.engine.is_market_open", return_value=True):
        e.tick()                                                   # 신규 매수
        assert e.states["005930"].entries_done == 1
        inv = e.states["005930"].invested_krw
        # 다음 tick: 잔고엔 아직 없고 미체결 주문만 있음 → 상태 유지, 중복주문 없음
        broker.get_unfilled_orders.return_value = [{"code": "005930", "unfilled_qty": 10}]
        clock["now"] += timedelta(seconds=5)
        e.tick()
        assert e.states["005930"].entries_done == 1 and broker.place_order.call_count == 1
        # 체결: 잔고에 나타남 → 브로커 기반 재구성(1회로 덮어쓰기) 하지 않고 기존 상태 유지
        broker.get_unfilled_orders.return_value = []
        broker.get_positions.return_value = [Position(code="005930", name="삼성전자", qty=62, avg_price=4770, current_price=4770)]
        clock["now"] += timedelta(seconds=5)
        e.tick()
        assert e.states["005930"].entries_done == 1 and e.states["005930"].invested_krw == inv


def test_state_dropped_after_grace_if_never_filled():
    clock = {"now": datetime(2026, 9, 22, 13, 45, tzinfo=KST)}
    e = StrategyEngine(_broker(positions=[]), MagicMock(), now=lambda: clock["now"])
    e.states["005930"] = PositionState("005930", entries_done=1, invested_krw=100000)
    e._buy_at["005930"] = clock["now"]
    e.sync_positions(set())
    assert "005930" in e.states                                   # 유예 내
    clock["now"] += timedelta(seconds=601)
    e.sync_positions(set())
    assert "005930" not in e.states                               # 유예 지남 + 미체결 없음 → 정리


def test_non_holding_candidate_does_not_leave_empty_state():
    broker = _broker(price=9000, positions=[])
    e = _engine(broker)
    e.candidates = {"005930": _cand(drop_ratio=10)}               # 조건 미달 → 매수 없음
    e.envelopes = {"005930": Envelope(ma=10000, upper=11000, lower=9500)}
    with patch("src.strategy.engine.is_market_open", return_value=True):
        e.tick()
    assert "005930" not in e.states
    # 외부 매수로 잔고에 나타나면 브로커 기반 복원이 동작해야 함
    broker.get_positions.return_value = [Position(code="005930", name="삼성전자", qty=10, avg_price=9000, current_price=9000)]
    e.sync_positions(set())
    assert e.states["005930"].entries_done == 1 and e.states["005930"].invested_krw == 90000
    assert e.states["005930"].last_buy_price == 9000                     # 외부매수 복원 시 직전가=평단


def test_heartbeat_pushes_balance_fields():
    broker = _broker()
    broker.get_balance.return_value = Balance(cash=37_987_660, equity=49_982_188, stock_value=12_060_860,
                                              deposit=50_000_000, unrealized_pnl=-17_812)
    e = _engine(broker)
    e._heartbeat(True)
    kw = e.relay.push_bot_state.call_args.kwargs
    assert kw["equity"] == 49_982_188 and kw["cash"] == 37_987_660
    assert kw["stock_value"] == 12_060_860 and kw["deposit"] == 50_000_000 and kw["unrealized_pnl"] == -17_812


def test_recompute_indicators_uses_closes_through_yesterday():
    """2026-09-28: 과거종가 조회 end = 어제. 오늘 포함 시 prev_close 가 장중가로 잡혀 상한가 판정 불가."""
    from datetime import date
    e = _engine(_broker())
    e.candidates = {}; e.positions = {"224060": Position(code="224060", name="더코디", qty=1, avg_price=4307, current_price=5710)}
    with patch("src.strategy.engine.pykrx_fetcher.get_close_range", return_value=[4000] * 19 + [4395]) as g:
        e._recompute_indicators()
    _, start, end = g.call_args.args
    assert end == date(2026, 9, 1) and start < end          # NOW=9/2 → end=9/1
    assert e.prev_close["224060"] == 4395
    assert e._at_limit_up("224060", 5710)                   # 4395*1.29=5669.6 ≤ 5710


# ── 2026-09-28: 체결 동기화(브로커 실데이터 ka10076) + 당일 실현손익(ka10077) ──
def _sell_engine():
    pos = Position(code="224060", name="더코디", qty=2779, avg_price=4307, current_price=5710)
    broker = _broker(price=5710, positions=[pos], cash=0)
    broker.place_order.return_value = Order(code="224060", name="더코디", side=Side.SELL, qty=2779,
                                            order_type=OrderType.LIMIT, price=5710,
                                            status=OrderStatus.SUBMITTED, broker_order_id="0088098")
    broker.get_order_fills.return_value = []
    broker.get_day_realized_pnl.return_value = None
    e = _engine(broker)
    e.relay.insert_order.return_value = "db-1"
    e.candidates = {}; e.prev_close = {"224060": 4395}     # 5710 ≥ 4395*1.29 → 상한가 전량
    return e, broker


def _fill(filled, unfilled, status="체결", price=5710, cmsn=0, tax=0, order_time="110739"):
    return {"ord_no": "0088098", "code": "224060", "qty": 2779, "filled_qty": filled, "unfilled_qty": unfilled,
            "filled_price": price, "commission": cmsn, "tax": tax, "status": status, "order_time": order_time}


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_partial_fill_from_broker_updates_order(_m):
    e, broker = _sell_engine()
    e.tick()                                                   # 매도 주문 → 추적 시작
    assert "0088098" in e._open_orders
    broker.get_unfilled_orders.return_value = [{"ord_no": "0088098", "code": "224060", "unfilled_qty": 2263}]
    broker.get_order_fills.return_value = [_fill(516, 2263)]
    e.tick()
    kw = e.relay.update_order.call_args.kwargs
    assert e.relay.update_order.call_args.args[0] == "db-1"
    assert kw["filled_qty"] == 516 and kw["filled_price"] == 5710 and kw["status"] == "partial"
    assert broker.place_order.call_count == 1                  # 미체결 중 중복 매도 없음
    e.tick()                                                   # 변화 없음 → 추가 갱신 없음
    assert e.relay.update_order.call_count == 1


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_full_fill_marks_filled_with_fees_and_no_resell(_m):
    e, broker = _sell_engine()
    e.tick()
    broker.get_unfilled_orders.return_value = []
    broker.get_order_fills.return_value = [_fill(2779, 0, cmsn=55500, tax=31734)]
    e.tick()
    kw = e.relay.update_order.call_args.kwargs
    assert kw["filled_qty"] == 2779 and kw["status"] == "filled" and "filled_at" in kw
    assert "0088098" not in e._open_orders
    ev = [c.kwargs for c in e.relay.insert_event.call_args_list if c.kwargs["title"] == "매도 체결 완료"]
    assert ev and "수수료 55,500" in ev[0]["message"] and "세금 31,734" in ev[0]["message"]
    assert broker.place_order.call_count == 1                  # 잔고 반영 지연 중 재매도 없음(FILL_GRACE)


@patch("src.strategy.engine.is_market_open", return_value=True)
def test_canceled_order_marked_and_untracked(_m):
    e, broker = _sell_engine()
    e.tick()
    broker.get_unfilled_orders.return_value = []
    broker.get_order_fills.return_value = [_fill(100, 0, status="확인")]   # 취소 확인
    e.tick()
    kw = e.relay.update_order.call_args.kwargs
    assert kw["status"] == "canceled" and kw["filled_qty"] == 100 and "0088098" not in e._open_orders


def test_day_pnl_comes_from_broker_not_computed():
    """실현손익은 봇 계산이 아니라 브로커(ka10077, 수수료·세금 차감) 값(D-016)."""
    broker = _broker()
    broker.get_day_realized_pnl.return_value = 3_768_526
    e = _engine(broker)
    e._heartbeat(True)
    assert e.relay.push_bot_state.call_args.kwargs["day_pnl"] == 3_768_526
    broker.get_day_realized_pnl.return_value = None            # 실패 → 이전 값 유지
    e._day_pnl_at = None
    e._heartbeat(True)
    assert e.relay.push_bot_state.call_args.kwargs["day_pnl"] == 3_768_526


def test_daily_reset_expires_open_orders():
    e = _engine(_broker())
    e._day = datetime(2026, 9, 28, tzinfo=KST).date()
    e._open_orders["x"] = {"db_id": "db-9", "code": "c", "name": "n", "side": "sell", "qty": 100,
                           "price": 1000, "avg_price": 900, "filled": 30, "reason": "limit_up"}
    e._maybe_daily_reset(datetime(2026, 9, 29, 9, 0, tzinfo=KST))
    kw = e.relay.update_order.call_args.kwargs
    assert kw["status"] == "canceled" and kw["filled_qty"] == 30 and e._open_orders == {}


def test_dry_run_does_not_track_orders():
    e, broker = _sell_engine()
    e.set_live(False, "t")
    with patch("src.strategy.engine.is_market_open", return_value=True):
        e.tick()
    assert e._open_orders == {}


# ── 2026-09-28: 미체결 취소 — 괴리율 X% 이상이 N분 지속 (unfilled_cancel_min · unfilled_cancel_dev_pct) ──
def _stale_engine(minutes_ago, limit=10, dev=0.0, price=5710, order_price=5710):
    clock = {"now": datetime(2026, 9, 28, 11, 30, 0, tzinfo=KST)}
    broker = _broker(positions=[], price=price)
    e = StrategyEngine(broker, MagicMock(), now=lambda: clock["now"])
    e.status = "running"
    e.params = StrategyParams(enabled=True, unfilled_cancel_min=limit, unfilled_cancel_dev_pct=dev)
    placed = clock["now"] - timedelta(minutes=minutes_ago)
    fills = [_fill(516, 2263, order_time=placed.strftime("%H%M%S"))]
    fills[0]["order_price"] = order_price
    return e, broker, fills, clock


def test_time_only_mode_cancels_after_limit():
    """괴리율 0 = 접수 후 경과시간만."""
    e, broker, fills, clock = _stale_engine(minutes_ago=11, dev=0)
    e._cancel_stale_orders(fills, clock["now"])
    assert broker.cancel.call_count == 1
    o = broker.cancel.call_args.args[0]
    assert o.broker_order_id == "0088098" and o.code == "224060"
    ev = [c.kwargs for c in e.relay.insert_event.call_args_list if c.kwargs["title"] == "미체결 취소"]
    assert ev and "2263/2779" in ev[0]["message"] and "접수 후 11분" in ev[0]["message"]
    e._cancel_stale_orders(fills, clock["now"])                # 같은 주문 재요청 없음
    assert broker.cancel.call_count == 1


def test_time_only_mode_fresh_order_not_canceled():
    e, broker, fills, clock = _stale_engine(minutes_ago=9, dev=0)
    e._cancel_stale_orders(fills, clock["now"])
    assert not broker.cancel.called


def test_deviation_mode_requires_persistence():
    """괴리 1%: 접수 30분 지났어도 괴리 상태가 10분 지속돼야 취소. 주문가 5710, 현재가 5600(-1.9%)."""
    e, broker, fills, clock = _stale_engine(minutes_ago=30, dev=1.0, price=5600)
    e._cancel_stale_orders(fills, clock["now"])                # 괴리 시작(타이머 0분)
    assert not broker.cancel.called and "0088098" in e._dev_since
    clock["now"] += timedelta(minutes=9)
    e._cancel_stale_orders(fills, clock["now"])                # 9분 → 아직
    assert not broker.cancel.called
    clock["now"] += timedelta(minutes=1)
    e._cancel_stale_orders(fills, clock["now"])                # 10분 지속 → 취소
    assert broker.cancel.call_count == 1
    msg = [c.kwargs for c in e.relay.insert_event.call_args_list if c.kwargs["title"] == "미체결 취소"][0]["message"]
    assert "괴리 1.9%" in msg and "10분 지속" in msg


def test_deviation_mode_no_cancel_while_price_at_order_price():
    """상한가처럼 현재가 = 주문가면(괴리 0%) 아무리 오래 미체결이어도 취소 안 함(대기열 유지)."""
    e, broker, fills, clock = _stale_engine(minutes_ago=60, dev=1.0, price=5710)
    for _ in range(4):
        e._cancel_stale_orders(fills, clock["now"]); clock["now"] += timedelta(minutes=5)
    assert not broker.cancel.called and "0088098" not in e._dev_since


def test_deviation_timer_resets_when_price_returns():
    e, broker, fills, clock = _stale_engine(minutes_ago=30, dev=1.0, price=5600)
    e._cancel_stale_orders(fills, clock["now"])                # 괴리 시작
    clock["now"] += timedelta(minutes=8)
    broker.get_price.return_value = 5700                       # 괴리 0.2% → 해소
    e._cancel_stale_orders(fills, clock["now"])
    assert "0088098" not in e._dev_since
    broker.get_price.return_value = 5600                       # 다시 괴리 → 0분부터
    clock["now"] += timedelta(minutes=9)
    e._cancel_stale_orders(fills, clock["now"])
    clock["now"] += timedelta(minutes=9)
    e._cancel_stale_orders(fills, clock["now"])                # 9분 → 아직
    assert not broker.cancel.called


def test_cancel_disabled_when_zero_or_dry_run():
    e, broker, fills, clock = _stale_engine(minutes_ago=30, limit=0)
    e._cancel_stale_orders(fills, clock["now"])
    assert not broker.cancel.called
    e2, broker2, fills2, clock2 = _stale_engine(minutes_ago=30, dev=0)
    e2.set_live(False, "t")
    e2._cancel_stale_orders(fills2, clock2["now"])
    assert not broker2.cancel.called


def test_fully_filled_order_not_canceled():
    e, broker, fills, clock = _stale_engine(minutes_ago=30, dev=0)
    fills[0]["unfilled_qty"] = 0
    e._cancel_stale_orders(fills, clock["now"])
    assert not broker.cancel.called


def test_cancel_failure_emits_and_retries_next_tick():
    from src.broker.errors import BrokerError
    e, broker, fills, clock = _stale_engine(minutes_ago=30, dev=0)
    broker.cancel.side_effect = BrokerError("거부")
    e._cancel_stale_orders(fills, clock["now"])
    assert any(c.kwargs["title"] == "미체결 취소 실패" for c in e.relay.insert_event.call_args_list)
    broker.cancel.side_effect = None
    e._cancel_stale_orders(fills, clock["now"])
    assert broker.cancel.call_count == 2                      # 실패분은 재시도
