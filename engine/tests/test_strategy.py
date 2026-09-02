"""전략 순수 코어 테스트 — indicators/params/rules/risk/state. 외부 의존 0."""
from __future__ import annotations

from src.strategy.indicators import Envelope, compute_envelope
from src.strategy.params import StrategyParams
from src.strategy.rules import should_enter, should_exit
from src.strategy.risk import ok_buy, ok_sell
from src.strategy.state import PositionState


def _params(**kw) -> StrategyParams:
    base = dict(enabled=True)
    base.update(kw)
    return StrategyParams(**base)


# ── Envelope ──────────────────────────────────────────
class TestEnvelope:
    def test_basic(self):
        env = compute_envelope([100, 200, 300], period=3, band=0.10)
        assert env.ma == 200
        assert env.upper == 200 * 1.10 and env.lower == 200 * 0.90

    def test_uses_last_period(self):
        env = compute_envelope([1, 2, 3, 10, 20], period=2, band=0.0)
        assert env.ma == 15  # (10+20)/2

    def test_empty_none(self):
        assert compute_envelope([], 20, 0.1) is None


# ── Params ────────────────────────────────────────────
class TestParams:
    def test_from_settings_extra_over_column(self):
        row = {"enabled": True, "entry_drop_min": 25,
               "extra": {"env_band": 0.15, "take_profit_pct": 20}}
        p = StrategyParams.from_settings(row)
        assert p.enabled is True
        assert p.entry_drop_min == 25       # 컬럼
        assert p.env_band == 0.15           # extra 우선
        assert p.take_profit_pct == 20      # extra
        assert p.env_period == 20           # 기본값

    def test_one_buy_krw(self):
        p = _params(per_stock_krw=1_000_000, entry_split_pct=0.30)
        assert p.one_buy_krw() == 300_000


# ── 진입 규칙 ─────────────────────────────────────────
class TestShouldEnter:
    def _env(self):
        return Envelope(ma=10000, upper=11000, lower=9500)

    def test_new_entry_happy(self):
        p = _params()
        st = PositionState("005930")
        d = should_enter(drop_ratio=35, status="ok", price=9000, env=self._env(),
                         params=p, state=st, holding=False, avg_price=None,
                         positions_cnt=0, cash=1_000_000)
        assert d.enter and d.kind == "new"
        assert d.qty == 300_000 // 9000   # one_buy 30만 / 9000

    def test_new_reject_drop_out_of_range(self):
        d = should_enter(drop_ratio=50, status="ok", price=9000, env=self._env(),
                         params=_params(), state=PositionState("x"), holding=False,
                         avg_price=None, positions_cnt=0, cash=1_000_000)
        assert not d.enter

    def test_new_reject_price_above_lower(self):
        d = should_enter(drop_ratio=35, status="ok", price=9600, env=self._env(),
                         params=_params(), state=PositionState("x"), holding=False,
                         avg_price=None, positions_cnt=0, cash=1_000_000)
        assert not d.enter  # 9600 > lower 9500

    def test_new_reject_status_pending(self):
        d = should_enter(drop_ratio=35, status="pending", price=9000, env=self._env(),
                         params=_params(), state=PositionState("x"), holding=False,
                         avg_price=None, positions_cnt=0, cash=1_000_000)
        assert not d.enter

    def test_new_reject_max_positions(self):
        d = should_enter(drop_ratio=35, status="ok", price=9000, env=self._env(),
                         params=_params(max_positions=5), state=PositionState("x"),
                         holding=False, avg_price=None, positions_cnt=5, cash=1_000_000)
        assert not d.enter

    def test_disabled(self):
        d = should_enter(drop_ratio=35, status="ok", price=9000, env=self._env(),
                         params=_params(enabled=False), state=PositionState("x"),
                         holding=False, avg_price=None, positions_cnt=0, cash=1_000_000)
        assert not d.enter

    def test_reject_below_min_price(self):
        # 현재가 900 < 최소매수가 1000 → 매수 안 함 (다른 조건 다 충족해도)
        d = should_enter(drop_ratio=35, status="ok", price=900,
                         env=Envelope(ma=1000, upper=1100, lower=950),
                         params=_params(min_price=1000), state=PositionState("x"),
                         holding=False, avg_price=None, positions_cnt=0, cash=1_000_000)
        assert not d.enter

    def test_min_price_adjustable(self):
        # 최소매수가를 500 으로 낮추면 900 도 매수 가능
        d = should_enter(drop_ratio=35, status="ok", price=900,
                         env=Envelope(ma=1000, upper=1100, lower=950),
                         params=_params(min_price=500), state=PositionState("x"),
                         holding=False, avg_price=None, positions_cnt=0, cash=1_000_000)
        assert d.enter and d.kind == "new"   # 900 < lower 950, drop 35 in range, price>=min500

    def test_add_on_dip(self):
        p = _params(add_on_drop_pct=0.07)
        st = PositionState("005930", entries_done=1, invested_krw=300_000)
        d = should_enter(drop_ratio=35, status="ok", price=9000, env=self._env(),
                         params=p, state=st, holding=True, avg_price=10000,
                         positions_cnt=1, cash=1_000_000)
        assert d.enter and d.kind == "add"   # 9000 <= 10000*0.93=9300

    def test_add_reject_small_dip(self):
        st = PositionState("005930", entries_done=1, invested_krw=300_000)
        d = should_enter(drop_ratio=35, status="ok", price=9500, env=self._env(),
                         params=_params(), state=st, holding=True, avg_price=10000,
                         positions_cnt=1, cash=1_000_000)
        assert not d.enter   # 9500 > 9300

    def test_budget_exhausted(self):
        st = PositionState("005930", entries_done=3, invested_krw=1_000_000)
        d = should_enter(drop_ratio=35, status="ok", price=9000, env=self._env(),
                         params=_params(), state=st, holding=True, avg_price=10000,
                         positions_cnt=1, cash=1_000_000)
        assert not d.enter   # remaining 0


# ── 청산 규칙 ─────────────────────────────────────────
class TestShouldExit:
    def _env(self):
        return Envelope(ma=10000, upper=11000, lower=9500)

    def test_partial_take_profit(self):
        p = _params(take_profit_pct=15, first_sell_portion=0.5)
        st = PositionState("005930")
        d = should_exit(qty=100, avg_price=10000, price=12000, env=self._env(),
                        params=p, state=st)
        assert d.exit and d.reason == "take_profit_partial"
        assert d.qty == 50 and d.mark_partial_sold        # 12000>upper11000, +20%>=15

    def test_no_take_profit_low_pnl(self):
        d = should_exit(qty=100, avg_price=10000, price=10800, env=self._env(),
                        params=_params(), state=PositionState("x"))
        assert not d.exit   # +8% < 15

    def test_no_take_profit_below_upper(self):
        d = should_exit(qty=100, avg_price=8000, price=10900, env=self._env(),
                        params=_params(), state=PositionState("x"))
        assert not d.exit   # pnl +36% 이지만 price 10900 < upper 11000

    def test_trailing_stop_after_partial(self):
        p = _params(post_sell_stop_pct=0.05)
        st = PositionState("005930", partial_sold=True, peak_since_partial=13000)
        d = should_exit(qty=50, avg_price=10000, price=12300, env=self._env(),
                        params=p, state=st)
        assert d.exit and d.reason == "trailing_stop" and d.qty == 50  # 12300<=13000*0.95=12350

    def test_no_trailing_when_holding_high(self):
        st = PositionState("005930", partial_sold=True, peak_since_partial=13000)
        d = should_exit(qty=50, avg_price=10000, price=12500, env=self._env(),
                        params=_params(), state=st)
        assert not d.exit   # 12500 > 12350

    def test_limit_up_after_partial(self):
        st = PositionState("005930", partial_sold=True, peak_since_partial=13000)
        d = should_exit(qty=50, avg_price=10000, price=13000, env=self._env(),
                        params=_params(), state=st, at_limit_up=True)
        assert d.exit and d.reason == "limit_up" and d.qty == 50


# ── 리스크 가드 ───────────────────────────────────────
class TestRisk:
    def test_ok_buy_happy(self):
        r = ok_buy(qty=30, price=9000, params=_params(), cash=1_000_000,
                   positions_cnt=0, holding=False, invested_krw=0,
                   pending_same_dir=False, daily_realized_pnl=0)
        assert r.ok

    def test_buy_cash_short(self):
        r = ok_buy(qty=30, price=9000, params=_params(), cash=100_000,
                   positions_cnt=0, holding=False, invested_krw=0,
                   pending_same_dir=False, daily_realized_pnl=0)
        assert not r.ok and "현금" in r.reason

    def test_buy_budget_exceed(self):
        r = ok_buy(qty=50, price=9000, params=_params(per_stock_krw=300_000),
                   cash=1_000_000, positions_cnt=0, holding=False,
                   invested_krw=0, pending_same_dir=False, daily_realized_pnl=0)
        assert not r.ok and "예산" in r.reason

    def test_buy_max_positions(self):
        r = ok_buy(qty=1, price=9000, params=_params(max_positions=5), cash=1_000_000,
                   positions_cnt=5, holding=False, invested_krw=0,
                   pending_same_dir=False, daily_realized_pnl=0)
        assert not r.ok

    def test_buy_duplicate(self):
        r = ok_buy(qty=1, price=9000, params=_params(), cash=1_000_000,
                   positions_cnt=0, holding=False, invested_krw=0,
                   pending_same_dir=True, daily_realized_pnl=0)
        assert not r.ok and "중복" in r.reason

    def test_buy_daily_loss_halt(self):
        r = ok_buy(qty=1, price=9000, params=_params(daily_max_loss_krw=500_000),
                   cash=1_000_000, positions_cnt=0, holding=False, invested_krw=0,
                   pending_same_dir=False, daily_realized_pnl=-500_000)
        assert not r.ok and "손실" in r.reason

    def test_buy_price_sanity(self):
        r = ok_buy(qty=1, price=14000, params=_params(), cash=1_000_000,
                   positions_cnt=0, holding=False, invested_krw=0,
                   pending_same_dir=False, daily_realized_pnl=0, prev_close=10000)
        assert not r.ok and "sanity" in r.reason  # +40% > ±30%

    def test_ok_sell(self):
        assert ok_sell(qty=10, held_qty=10).ok
        assert not ok_sell(qty=11, held_qty=10).ok


# ── 상태 ──────────────────────────────────────────────
def test_position_state_transitions():
    st = PositionState("005930")
    st.on_buy(30, 9000)
    assert st.entries_done == 1 and st.invested_krw == 270_000
    st.on_partial_sell(12000)
    assert st.partial_sold and st.peak_since_partial == 12000
    st.update_peak(12500)
    assert st.peak_since_partial == 12500
    st.update_peak(12100)
    assert st.peak_since_partial == 12500  # 고점 유지
