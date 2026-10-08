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
        """kt00018(총자산·주식평가·평가손익) + kt00001(예수금·주문가능금액) — 영웅문 정의(2026-09-23)."""
        b = _broker()
        b._session.post.side_effect = [
            _resp({"return_code": 0, "prsm_dpst_aset_amt": "000000049982188", "tot_evlt_amt": "000000012060860",
                   "tot_evlt_pl": "-00000000017812"}),
            _resp({"return_code": 0, "entr": "000000050000000", "ord_alow_amt": "000000037987660"}),
        ]
        bal = b.get_balance()
        assert bal.equity == 49_982_188 and bal.stock_value == 12_060_860
        assert bal.unrealized_pnl == -17_812
        assert bal.deposit == 50_000_000 and bal.cash == 37_987_660   # 근사(37,921,328)가 아닌 키움 값
        assert b._session.post.call_count == 2

    def test_get_balance_cash_uses_100pct_margin_field(self):
        """미수 금지: 주문가능금액은 현금 100% 증거금 기준 필드(100stk_ord_alow_amt) 우선."""
        b = _broker()
        b._session.post.side_effect = [
            _resp({"return_code": 0, "prsm_dpst_aset_amt": "50,000,000", "tot_evlt_amt": "0", "tot_evlt_pl": "0"}),
            _resp({"return_code": 0, "entr": "50,000,000", "ord_alow_amt": "189,938,300",   # 20% 증거금 계좌 가정
                   "100stk_ord_alow_amt": "37,987,660"}),
        ]
        assert b.get_balance().cash == 37_987_660

    def test_get_order_fills_maps_ka10076(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0, "cntr": [
            {"ord_no": "0088098", "stk_cd": "224060", "ord_qty": "2779", "cntr_qty": "516", "oso_qty": "2263",
             "cntr_pric": "5710", "tdy_trde_cmsn": "10000", "tdy_trde_tax": "5000", "ord_stt": "체결",
             "ord_tm": "110739", "ord_pric": "5710"}]})
        f = b.get_order_fills()[0]
        assert f["order_time"] == "110739" and f["order_price"] == 5710
        assert f["ord_no"] == "0088098" and f["code"] == "224060" and f["qty"] == 2779
        assert f["filled_qty"] == 516 and f["unfilled_qty"] == 2263 and f["filled_price"] == 5710
        assert f["commission"] == 10000 and f["tax"] == 5000 and f["status"] == "체결"
        assert b._session.post.call_args.kwargs.get("headers", {}).get("api-id", "ka10076") == "ka10076"

    def test_get_day_realized_pnl_ka10077_account_total(self):
        b = _broker()
        b._session.post.return_value = _resp({"return_code": 0, "tdy_rlzt_pl": "3768526"})
        assert b.get_day_realized_pnl() == 3_768_526
        body = b._session.post.call_args.kwargs.get("json") or b._session.post.call_args[1].get("json")
        assert body["stk_cd"] == "000000"
        b._session.post.return_value = _resp({"return_code": 3, "return_msg": "err"})
        assert b.get_day_realized_pnl() is None

    def test_get_balance_falls_back_when_deposit_query_fails(self):
        b = _broker()
        b._session.post.side_effect = [
            _resp({"return_code": 0, "prsm_dpst_aset_amt": "10,000,000", "tot_evlt_amt": "3,000,000"}),
            _resp({"return_code": 3, "return_msg": "err"}),
        ]
        bal = b.get_balance()
        assert bal.cash == 7_000_000 and bal.deposit == 0

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
        """WS 연결이 살아 있고 현재 연결에서 받은 틱이면 REST 없이 캐시 사용."""
        b = _broker()
        b._ws_live, b._ws_login_at = True, 100.0
        b._prices = {"005930": 71000}; b._tick_at = {"005930": 150.0}
        assert b.get_price("005930") == 71000
        b._session.post.assert_not_called()

    def test_get_price_ignores_ws_cache_when_disconnected(self):
        """멈춘 가격 방지(2026-10-08): WS 끊김 → 옛 캐시 무시하고 REST, TTL 내 재사용."""
        b = _broker()
        b._ws_live, b._ws_login_at = False, 100.0
        b._prices = {"005930": 71000}; b._tick_at = {"005930": 150.0}
        b._session.post.return_value = _resp({"return_code": 0, "cur_prc": "68000"})
        assert b.get_price("005930") == 68000
        assert b.get_price("005930") == 68000                  # 4초 TTL 내 → REST 1회
        assert b._session.post.call_count == 1
        assert b.cached_price("005930") == 68000               # 신선한 REST 값
        b._rest_prices["005930"] = (68000, 0.0)                 # TTL 만료 → 재조회
        b._session.post.return_value = _resp({"return_code": 0, "cur_prc": "67500"})
        assert b.get_price("005930") == 67500 and b._session.post.call_count == 2

    def test_get_price_ignores_tick_from_previous_connection(self):
        """재접속 직후 아직 새 틱이 없는 종목(거래 뜸)은 이전 연결의 값 대신 REST."""
        b = _broker()
        b._ws_live, b._ws_login_at = True, 200.0
        b._prices = {"005930": 71000}; b._tick_at = {"005930": 150.0}   # 이전 연결의 틱
        b._session.post.return_value = _resp({"return_code": 0, "cur_prc": "69000"})
        assert b.get_price("005930") == 69000

    def test_get_price_returns_none_not_stale_when_rest_fails(self):
        b = _broker()
        b._ws_live = False
        b._prices = {"005930": 71000}; b._tick_at = {"005930": 1.0}
        b._session.post.return_value = _resp({"return_code": 10, "return_msg": "점검"})
        assert b.get_price("005930") is None                   # 옛 가격(71000) 사용 안 함
        assert b.cached_price("005930") is None

    def test_in_trading_session(self):
        from src.broker.kiwoom import in_trading_session
        assert in_trading_session(datetime(2026, 10, 8, 9, 40, tzinfo=KST))        # 수 09:40
        assert not in_trading_session(datetime(2026, 10, 7, 20, 5, tzinfo=KST))    # 수 20:05
        assert not in_trading_session(datetime(2026, 10, 8, 7, 53, tzinfo=KST))    # 07:53
        assert not in_trading_session(datetime(2026, 10, 10, 10, 0, tzinfo=KST))   # 토요일

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
    assert b._tick_at["005930"] > 0                      # 틱 시각 기록(신선도 판단)
    assert ticks == [("005930", 71500)]
