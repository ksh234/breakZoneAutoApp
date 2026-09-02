"""StrategyEngine tick 흐름 테스트 — broker/relay mock, is_market_open 강제 True."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.analysis.candidates import Candidate
from src.broker.models import Balance, Order, OrderStatus, OrderType, Position, Side
from src.strategy.engine import StrategyEngine
from src.strategy.indicators import Envelope
from src.strategy.params import StrategyParams

KST = timezone(timedelta(hours=9))
NOW = lambda: datetime(2026, 9, 2, 10, 0, tzinfo=KST)


def _broker(price=9000, positions=None, cash=1_000_000):
    b = MagicMock()
    b.get_price.return_value = price
    b.get_positions.return_value = positions or []
    b.get_unfilled_orders.return_value = []
    b.get_balance.return_value = Balance(cash=cash, equity=cash, stock_value=0)
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
def test_tick_no_buy_when_out_of_range(_mock_market):
    broker = _broker(price=9000, positions=[])
    e = _engine(broker)
    e.candidates = {"005930": _cand(drop_ratio=50)}  # 구간 밖
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
