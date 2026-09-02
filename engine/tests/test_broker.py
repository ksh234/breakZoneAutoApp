"""KiwoomRestBroker 단위 테스트 — HTTP는 전부 mock (네트워크/실계좌 없음)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.broker import (AuthError, BrokerError, OrderRejected, OrderStatus,
                        OrderType, Side)
from src.broker.kiwoom import KST, KiwoomRestBroker, clean_code, first_list, to_int
from src.broker.models import Order


def _resp(json_data, status=200, headers=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.headers = headers or {}
    return m


def _broker():
    b = KiwoomRestBroker("appkey", "secret", "ACC123", mode="demo")
    b._token = "tok"
    b._token_exp = datetime.now(KST) + timedelta(hours=1)
    b._session = MagicMock()
    return b


# ── 순수 유틸 ─────────────────────────────────────────
class TestUtils:
    def test_to_int(self):
        assert to_int("+57,800") == 57800
        assert to_int("-1200") == 1200            # 부호 무시(기본)
        assert to_int("-1200", signed=True) == -1200
        assert to_int("00123") == 123
        assert to_int("") == 0 and to_int(None) == 0

    def test_clean_code(self):
        assert clean_code("A005930") == "005930"
        assert clean_code("5930") == "005930"
        assert clean_code(None) == ""

    def test_first_list(self):
        assert first_list({"a": 1, "b": [1, 2]}) == [1, 2]
        assert first_list({"a": 1}) == []


# ── 토큰 ──────────────────────────────────────────────
def test_connect_issues_token():
    b = KiwoomRestBroker("k", "s", mode="demo")
    b._session = MagicMock()
    b._session.post.return_value = _resp(
        {"return_code": 0, "token": "abc", "token_type": "bearer", "expires_dt": "20261231235959"})
    b.connect()
    assert b._token == "abc"
    # /oauth2/token 로 요청했는지
    assert b._session.post.call_args.args[0].endswith("/oauth2/token")


def test_token_failure_raises_auth():
    b = KiwoomRestBroker("k", "s", mode="demo")
    b._session = MagicMock()
    b._session.post.return_value = _resp({"return_code": 3, "return_msg": "invalid"}, status=200)
    with pytest.raises(AuthError):
        b.connect()


# ── 주문 ──────────────────────────────────────────────
class TestOrders:
    def test_buy_limit_body_and_parse(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0, "ord_no": "0000140"})
        o = b.place_order("005930", Side.BUY, 10, OrderType.LIMIT, price=70000,
                          name="삼성전자", reason="entry")
        assert o.broker_order_id == "0000140"
        assert o.status == OrderStatus.SUBMITTED
        kw = b._session.post.call_args.kwargs
        assert kw["headers"]["api-id"] == "kt10000"
        assert kw["json"] == {"dmst_stex_tp": "KRX", "stk_cd": "005930", "ord_qty": "10",
                              "trde_tp": "0", "ord_uv": "70000", "cond_uv": ""}

    def test_sell_market_body(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0, "ord_no": "7"})
        b.place_order("005930", Side.SELL, 5, OrderType.MARKET)
        kw = b._session.post.call_args.kwargs
        assert kw["headers"]["api-id"] == "kt10001"
        assert kw["json"]["trde_tp"] == "3" and kw["json"]["ord_uv"] == ""

    def test_reject_bad_qty(self):
        b = _broker()
        with pytest.raises(OrderRejected):
            b.place_order("005930", Side.BUY, 0, OrderType.MARKET)

    def test_reject_limit_without_price(self):
        b = _broker()
        with pytest.raises(OrderRejected):
            b.place_order("005930", Side.BUY, 10, OrderType.LIMIT, price=None)

    def test_missing_ord_no_rejected(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0})
        with pytest.raises(OrderRejected):
            b.place_order("005930", Side.BUY, 10, OrderType.MARKET)

    def test_cancel_body(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0})
        o = Order(code="005930", name="", side=Side.BUY, qty=10,
                  order_type=OrderType.LIMIT, price=70000, broker_order_id="0000140")
        b.cancel(o)
        kw = b._session.post.call_args.kwargs
        assert kw["headers"]["api-id"] == "kt10003"
        assert kw["json"]["orig_ord_no"] == "0000140" and kw["json"]["cncl_qty"] == "0"


# ── 계좌/시세 ─────────────────────────────────────────
class TestAccount:
    def test_get_balance(self):
        b = _broker()
        b._session.post.return_value = _resp({
            "return_code": 0, "prsm_dpst_aset_amt": "10,000,000", "tot_evlt_amt": "3,000,000"})
        bal = b.get_balance()
        assert bal.equity == 10_000_000
        assert bal.stock_value == 3_000_000
        assert bal.cash == 7_000_000

    def test_get_positions_filters_and_maps(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0, "acnt_evlt_remn_indv_tot": [
            {"stk_cd": "A005930", "stk_nm": "삼성전자", "rmnd_qty": "10",
             "pur_pric": "70000", "cur_prc": "+71000"},
            {"stk_cd": "000660", "stk_nm": "SK하이닉스", "rmnd_qty": "0",
             "pur_pric": "1", "cur_prc": "1"},   # 수량0 → 제외
        ]})
        pos = b.get_positions()
        assert len(pos) == 1
        p = pos[0]
        assert p.code == "005930" and p.qty == 10 and p.avg_price == 70000 and p.current_price == 71000
        assert p.pnl == (71000 - 70000) * 10

    def test_get_price_cache_first(self):
        b = _broker()
        b._prices = {"005930": 71000}
        assert b.get_price("005930") == 71000
        b._session.post.assert_not_called()

    def test_get_price_rest_fallback(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0, "cur_prc": "-70500"})
        assert b.get_price("005930") == 70500  # 부호 무시, 절대값

    def test_rc_nonzero_raises(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 10, "return_msg": "오류"})
        with pytest.raises(BrokerError):
            b.get_balance()


# ── 실시간 파싱 ───────────────────────────────────────
def test_handle_real_updates_cache_and_callback():
    b = _broker()
    ticks = []
    b._on_tick = lambda code, price: ticks.append((code, price))
    b._handle_real([{"type": "0B", "item": "005930", "values": {"10": "+71500", "20": "0930"}}])
    assert b._prices["005930"] == 71500
    assert ticks == [("005930", 71500)]
