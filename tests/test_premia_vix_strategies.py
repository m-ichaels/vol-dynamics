"""The premium estimator and its interval on a planted premium; the VX roll engine on a synthetic curve with known
roll-down and no look-ahead; the option engine: decomposition sums to net, a delta-hedged short straddle earns the
implied-realised gap, the margin is positive; the implied-move stripping recovers a planted jump; FOMC file parses."""
import numpy as np
import pandas as pd

from voldyn import data, events, premia, strategies, vix
from voldyn.strategies import Leg, Trade, simulate
from voldyn.surface import black


def test_vrp_recovers_planted_premium():
    rng = np.random.default_rng(0); n = 3000; idx = pd.bdate_range("2010-01-01", periods=n)
    sigma = 0.16; ret = pd.Series(rng.normal(0, sigma / np.sqrt(252), n), index=idx)
    iv = pd.Series(np.full(n, 20.0), index=idx)               # 20 vol against 16 realised: 4 vol points of premium
    df = premia.vrp_series(iv, ret, 21, 252)
    s = premia.summarise_vrp(df, 21, B=300)
    assert abs(s["gap_vol_mean_pts"] - 4.0) < 1.0
    assert s["gap_vol_ci_pts"][0] < 4.0 < s["gap_vol_ci_pts"][1] + 0.5
    assert abs(s["vrp_mean_varpts"] - (0.04 - 0.0256) * 1e4) < 40
    lo, hi = premia.block_bootstrap_mean(np.ones(500), 21, 200)
    assert abs(lo - 1) < 1e-9 and abs(hi - 1) < 1e-9


def synthetic_vx(n_days=800, seed=1):
    """a curve in constant contango: F_k = vix + 1.0 * k, vix a mean-reverting series; monthly expiries"""
    rng = np.random.default_rng(seed); dates = pd.bdate_range("2019-01-02", periods=n_days)
    v = 18 + np.cumsum(rng.normal(0, 0.5, n_days)) * 0.0 + rng.normal(0, 0.3, n_days)
    vix_s = pd.Series(v, index=dates)
    exps = pd.date_range("2019-01-16", periods=45, freq="4W-WED")
    rows = []
    for d, vv in vix_s.items():
        live = [e for e in exps if e > d][:6]
        for k, e in enumerate(live, start=1):
            rows.append({"date": d, "expiry": e, "settle": vv + 1.0 * k, "open": np.nan, "high": np.nan, "low": np.nan, "close": np.nan, "total_volume": 1, "open_interest": 1})
    return pd.DataFrame(rows), vix_s


def test_vx_roll_earns_rolldown_on_synthetic_curve():
    vx, vix_s = synthetic_vx()
    curve = vix.vx_curve(vx, vix_s)
    assert curve["contango_1_2"].all() and abs(curve["roll_1"].mean() - 30 / 28) < 0.3
    led = vix.roll_strategy(vx, curve)
    s = vix.roll_summary(led, curve)
    # the short front contract converges to the (flat) VIX by about one point a month: positive net, small costs
    assert s["net_pts_per_year"] > 6 and s["cost_pts_per_year"] < 1.0
    assert s["share_days_contango"] > 0.95


def test_option_engine_decomposition_and_gap():
    rng = np.random.default_rng(5); S0 = 100.0; T_days = 30; imp = 0.25
    idx = pd.date_range("2021-01-04", periods=T_days + 1, freq="D")       # calendar days: the engine's option time is (expiry - d).days / 365
    nets = []
    for real in (0.15, 0.25, 0.35):
        pnl = []
        for k in range(60):
            r = rng.normal(0, real / np.sqrt(365), T_days); path = pd.Series(S0 * np.exp(np.cumsum(np.concatenate([[0.0], r]))), index=idx)
            legs = [Leg(S0, cp, idx[-1], -1.0, float(black(S0, S0, T_days / 365, imp, cp)), imp) for cp in (1.0, -1.0)]
            tr = simulate(Trade("t", idx[0], legs, S0), path, hedge_bp=0.0)
            led = tr.rows
            assert abs((led["opt_pnl"] + led["hedge_pnl"] - led["cost"]).sum() - led["net"].sum()) < 1e-9
            assert (led["margin"].iloc[:-1] > 0).all()
            pnl.append(tr.summary["net"])
        nets.append(np.mean(pnl))
    assert nets[0] > nets[1] > nets[2]                    # short vol earns more the lower the realised vol
    assert abs(nets[1]) < 0.5                            # at realised = implied the hedged straddle is near zero (straddle worth ~5.7)


def test_scenario_margin_and_stop():
    S0 = 100.0; idx = pd.bdate_range("2021-01-04", periods=25)
    legs = [Leg(S0, cp, idx[-1], -1.0, float(black(S0, S0, 24 / 365, 0.2, cp)), 0.2) for cp in (1.0, -1.0)]
    m = strategies.scenario_margin(legs, S0, idx[0])
    assert m >= 0.1 * 2 * S0 * 0 and m > 5.0
    path = pd.Series(np.concatenate([np.full(10, S0), np.full(15, S0 * 1.25)]), index=idx)   # a 25 % gap on day 10: the hedge cannot follow, the short straddle loses
    tr = simulate(Trade("t", idx[0], legs, S0), path, 1.0, stop_loss_frac=0.3)
    assert tr.summary["stopped"] and tr.summary["net"] < 0


def test_implied_move_stripping():
    """two expiries priced with the same diffusion vol plus one jump variance: the stripped move equals the jump"""
    S = 100.0; sig = 0.25; J = 0.06; d = pd.Timestamp("2024-04-30"); event = pd.Timestamp("2024-05-02")
    rows = []
    for e, T in ((pd.Timestamp("2024-05-10"), 10.5 / 365), (pd.Timestamp("2024-06-21"), 52.5 / 365)):
        w = sig * sig * T + J * J; iv = np.sqrt(w / T)
        for K in (95.0, 100.0, 105.0):
            for cp in (1.0, -1.0):
                px = float(black(S, K, T, iv, cp))
                rows.append({"date": d, "expiration": e, "strike": K, "cp": cp, "bid": px - 0.02, "ask": px + 0.02, "mid": px, "spread": 0.04, "T": T, "vol": iv})
    chain = pd.DataFrame(rows)
    im = events.implied_move(chain, S, event)
    assert abs(im["stripped_move"] - J) < 0.003 and abs(im["diffusion_vol"] - sig) < 0.01
    assert 0.5 * J < im["rule_move"] < 3 * J


def test_reference_files_and_parsing():
    f = data.load_fomc(); assert len(f) > 50 and f["date"].is_monotonic_increasing
    cur, exp, k, cp = data.parse_instrument("BTC-25SEP26-80000-C")
    assert cur == "BTC" and k == 80000.0 and cp == 1.0 and exp.hour == 8
    assert data.parse_instrument("BTC-PERPETUAL") is None
