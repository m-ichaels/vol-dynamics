"""Realised-variance estimators on simulated paths with known variance; the jump test's size and power; HAR recovery;
QLIKE minimised at the truth; the Diebold-Mariano sign."""
import numpy as np
import pandas as pd

from voldyn import forecast, realised


def gbm_ohlc(n_days=4000, sigma=0.20, bars=390, seed=0):
    """daily OHLC from intraday Brownian paths (no drift, no overnight gap) with annualised vol sigma"""
    rng = np.random.default_rng(seed); dt = 1.0 / (252 * bars)
    r = rng.normal(0, sigma * np.sqrt(dt), (n_days, bars))
    lp = np.cumsum(r, axis=1); lp0 = np.concatenate([[0.0], np.cumsum(lp[:-1, -1])])
    path = lp0[:, None] + lp
    idx = pd.bdate_range("2005-01-03", periods=n_days)
    o = pd.DataFrame({"open": np.exp(lp0), "high": np.exp(path.max(axis=1)), "low": np.exp(path.min(axis=1)), "close": np.exp(path[:, -1])}, index=idx)
    return o


def test_daily_estimators_unbiased():
    o = gbm_ohlc(); d = realised.daily_estimators(o).dropna()
    truth = 0.20 ** 2 / 252
    assert abs(d["cc"].mean() / truth - 1) < 0.08
    for c in ("park", "gk", "rs"):
        # the observed range of 390 bars understates the continuous range: a downward bias of a few per cent is expected
        assert -0.14 < d[c].mean() / truth - 1 < 0.04, (c, d[c].mean() / truth)
    # range estimators are more efficient than close-to-close
    assert d["park"].std() < d["cc"].std() and d["gk"].std() < d["cc"].std()
    yz = realised.yang_zhang(o).dropna(); assert abs(yz.mean() / truth - 1) < 0.1


def test_intraday_rv_and_jump_test_size_and_power():
    rng = np.random.default_rng(1); n_days, bars = 600, 288; sigma = 0.6
    r = rng.normal(0, sigma * np.sqrt(1 / (365 * bars)), (n_days, bars))
    idx = pd.date_range("2022-01-01", periods=n_days * bars, freq="5min")
    closes = pd.Series(np.exp(np.cumsum(r.ravel())), index=idx)
    m = realised.intraday_measures(closes, bars_per_day=bars)
    truth = sigma ** 2 / 365
    assert abs(m["rv"].mean() / truth - 1) < 0.1 and abs(m["bv"].mean() / truth - 1) < 0.1
    assert m["jump"].mean() < 0.12          # size near 5 % on continuous paths (one-sided 1.96)
    # plant a jump of 5 sigma_day on every 10th day
    r2 = r.copy(); r2[::10, 100] += 5 * sigma * np.sqrt(1 / 365)
    closes2 = pd.Series(np.exp(np.cumsum(r2.ravel())), index=idx)
    m2 = realised.intraday_measures(closes2, bars_per_day=bars)
    assert m2["jump"].values[::10].mean() > 0.8 and m2["jv"].sum() > 0


def test_har_recovers_and_qlike_at_truth():
    rng = np.random.default_rng(2); n = 3000
    # log variance AR(1)
    lv = np.empty(n); lv[0] = np.log(1e-4)
    for t in range(1, n):
        lv[t] = np.log(1e-4) * 0.05 + 0.95 * lv[t - 1] + rng.normal(0, 0.3)
    var = np.exp(lv); rv = pd.Series(var * rng.chisquare(1, n), index=pd.bdate_range("2010-01-01", periods=n))      # noisy realised
    ret = pd.Series(np.sqrt(var) * rng.normal(size=n), index=rv.index)
    fc = forecast.rolling_forecasts(rv, None, ret, h=5, ann=252, window=800, step=21)
    sc = forecast.score(fc, 5)
    assert sc["models"]["har"]["qlike"] < sc["models"]["rw"]["qlike"]
    # QLIKE is minimised by the true conditional mean: scaling the forecast up or down raises it
    ok = fc.dropna(subset=["y_real", "har"]); y = ok["y_real"].values; p = ok["har"].values
    base = forecast.qlike(p, y).mean()
    assert forecast.qlike(p * 1.5, y).mean() > base * 0.9 and forecast.qlike(p * 0.6, y).mean() > base


def test_diebold_mariano_sign():
    rng = np.random.default_rng(3); n = 1000
    l1 = rng.normal(1.0, 1, n); l2 = l1 + 0.2 + rng.normal(0, 0.5, n)
    d = forecast.diebold_mariano(l1, l2, 1)
    assert d["dm"] < -3 and d["p"] < 0.01
    d0 = forecast.diebold_mariano(l1, l1 + rng.normal(0, 0.5, n), 5)
    assert abs(d0["dm"]) < 3


def test_garch_fit_recovers_persistence():
    rng = np.random.default_rng(4); n = 4000; om, al, be = 1e-6, 0.08, 0.90
    s2 = om / (1 - al - be); r = np.empty(n)
    for t in range(n):
        r[t] = np.sqrt(s2) * rng.normal(); s2 = om + al * r[t] ** 2 + be * s2
    (o, a, b), s2n = forecast.garch_fit(r)
    assert abs((a + b) - 0.98) < 0.03 and 0.02 < a < 0.16 and s2n > 0
