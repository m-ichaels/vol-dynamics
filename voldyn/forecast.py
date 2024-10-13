"""Realised-variance forecasting: HAR-RV (Corsi 2009), HAR with implied variance, GARCH(1,1) by maximum likelihood, a
random-walk floor; rolling-window refits; QLIKE and MSE losses; the Diebold-Mariano test with a Newey-West variance.

All models forecast the average daily variance over the next h days, log-space for HAR (Gaussian errors in log RV,
back-transformed with the half-variance correction).

    HAR:      log RV_{t+1:t+h} = b0 + b_d log RV_t + b_w log RV_{t-4:t} + b_m log RV_{t-21:t} + e
    HAR-IV:   ... + b_iv log IV_t^2 / ann
    GARCH:    sigma^2_{t+1} = omega + alpha r_t^2 + beta sigma^2_t, iterated to the horizon
    QLIKE(sigma^2, RV) = RV / sigma^2 - log(RV / sigma^2) - 1"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def har_features(rv: pd.Series) -> pd.DataFrame:
    lrv = np.log(rv.clip(lower=1e-10))
    return pd.DataFrame({"d": lrv, "w": np.log(rv.rolling(5).mean().clip(lower=1e-10)), "m": np.log(rv.rolling(22).mean().clip(lower=1e-10))})


def target(rv: pd.Series, h: int) -> pd.Series:
    """log of the mean daily variance over the next h days"""
    fwd = rv[::-1].rolling(h).mean()[::-1].shift(-1)
    return np.log(fwd.clip(lower=1e-10))


def ols(X: np.ndarray, y: np.ndarray):
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    return beta, float(np.var(resid))


def predict(beta, X, s2):
    A = np.column_stack([np.ones(len(X)), X])
    return np.exp(A @ beta + 0.5 * s2)


def garch_fit(r: np.ndarray):
    """GARCH(1,1) with zero mean by Gaussian ML; returns (omega, alpha, beta) and the last conditional variance"""
    r = np.asarray(r, dtype=float); v0 = float(np.var(r))

    def nll(p):
        om, al, be = np.exp(p[0]), 1 / (1 + np.exp(-p[1])), 1 / (1 + np.exp(-p[2]))
        if al + be >= 0.9999:
            return 1e10
        s2 = np.empty(len(r)); s2[0] = v0
        for t in range(1, len(r)):
            s2[t] = om + al * r[t - 1] ** 2 + be * s2[t - 1]
        s2 = np.maximum(s2, 1e-14)
        return 0.5 * np.sum(np.log(s2) + r ** 2 / s2)

    x0 = np.array([np.log(v0 * 0.05), np.log(0.08 / 0.92), np.log(0.9 / 0.1)])
    res = minimize(nll, x0, method="Nelder-Mead", options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-6})
    om, al, be = np.exp(res.x[0]), 1 / (1 + np.exp(-res.x[1])), 1 / (1 + np.exp(-res.x[2]))
    s2 = v0
    for t in range(1, len(r)):
        s2 = om + al * r[t - 1] ** 2 + be * s2
    s2_next = om + al * r[-1] ** 2 + be * s2
    return (om, al, be), s2_next


def garch_horizon(params, s2_next, h):
    om, al, be = params
    out = []; s = s2_next
    for _ in range(h):
        out.append(s); s = om + (al + be) * s
    return float(np.mean(out))


def garch_path(params, s2_start, r_block, h):
    """run the recursion through a block of returns with fixed parameters; the h-day forecast made at the end of each
    day of the block (the day's own return is known when the forecast is made)"""
    om, al, be = params; s = s2_start; out = []
    for rt in r_block:
        s_next = om + al * rt ** 2 + be * s
        out.append(garch_horizon(params, s_next, h)); s = s_next
    return np.array(out)


def qlike(pred, real):
    x = real / pred
    return x - np.log(x) - 1


def diebold_mariano(l1: np.ndarray, l2: np.ndarray, h: int) -> dict:
    """DM statistic for the loss differential d = l1 - l2 (negative favours model 1); Newey-West with h-1 lags"""
    d = np.asarray(l1) - np.asarray(l2); d = d[np.isfinite(d)]; n = len(d)
    if n < 20:
        return {"dm": np.nan, "p": np.nan, "n": n}
    dbar = d.mean(); q = max(h - 1, 0)
    gamma = [np.sum((d[k:] - dbar) * (d[:n - k] - dbar)) / n for k in range(q + 1)]
    var = gamma[0] + 2 * sum((1 - k / (q + 1)) * gamma[k] for k in range(1, q + 1))
    var = max(var, 1e-18)
    dm = dbar / np.sqrt(var / n)
    from scipy.stats import norm
    return {"dm": float(dm), "p": float(2 * (1 - norm.cdf(abs(dm)))), "n": int(n), "mean_diff": float(dbar)}


def rolling_forecasts(rv: pd.Series, iv: pd.Series | None, ret: pd.Series, h: int, ann: int, window: int = 1000, step: int = 21) -> pd.DataFrame:
    """Walk-forward: every `step` days refit on the trailing `window` days and forecast the next `step` days ahead
    (each day's forecast uses only data to that day).  Returns per-day forecasts and the realised target."""
    feats = har_features(rv); y = target(rv, h)
    df = feats.copy(); df["y"] = y
    if iv is not None:
        df["iv"] = np.log((iv.reindex(rv.index) / 100.0) ** 2 / ann)
    df["rv"] = rv; df["ret"] = ret.reindex(rv.index)
    df["rw"] = rv.rolling(h, min_periods=max(2, h // 2)).mean().clip(lower=1e-10)     # the trailing h-day mean, the no-model floor
    df = df.dropna(subset=["d", "w", "m"])
    idx = df.index; out = []
    start = window
    while start < len(idx):
        tr = df.iloc[max(0, start - window):start]
        tr_fit = tr.dropna(subset=["y"])
        tr_fit = tr_fit.iloc[:-h] if len(tr_fit) > h else tr_fit          # the last h targets are not yet observed at the fit date
        te = df.iloc[start:start + step]
        if len(tr_fit) < 200 or te.empty:
            start += step; continue
        b_har, s2_har = ols(tr_fit[["d", "w", "m"]].values, tr_fit["y"].values)
        p_har = predict(b_har, te[["d", "w", "m"]].values, s2_har)
        row = pd.DataFrame({"y_real": np.exp(te["y"]), "har": p_har, "rw": te["rw"].values}, index=te.index)
        if iv is not None:
            m = tr_fit.dropna(subset=["iv"])
            if len(m) >= 200 and te["iv"].notna().any():
                b_iv, s2_iv = ols(m[["d", "w", "m", "iv"]].values, m["y"].values)
                Xte = te[["d", "w", "m", "iv"]].values
                p_iv = predict(b_iv, np.nan_to_num(Xte, nan=0.0), s2_iv); p_iv[~np.isfinite(Xte).all(axis=1)] = np.nan
                row["har_iv"] = p_iv
                b_only, s2_only = ols(m[["iv"]].values, m["y"].values)
                row["iv_only"] = np.where(np.isfinite(Xte[:, 3]), predict(b_only, np.nan_to_num(Xte[:, 3:4], nan=0.0), s2_only), np.nan)
                row["iv_raw"] = np.exp(te["iv"]).values
        r_tr = tr["ret"].dropna().values
        if len(r_tr) >= 300:
            try:
                params, s2n = garch_fit(r_tr[-min(len(r_tr), window):])
                # s2n is the variance for the first test day; step through the block with each day's realised return
                om, al, be = params; s_prev = (s2n - om - al * r_tr[-1] ** 2) / max(be, 1e-6)
                r_te = te["ret"].fillna(0.0).values
                path = garch_path(params, s_prev, np.concatenate([[r_tr[-1]], r_te]), h)[1:]
                row["garch"] = path
            except Exception:  # noqa: BLE001
                row["garch"] = np.nan
        out.append(row)
        start += step
    return pd.concat(out) if out else pd.DataFrame()


def score(fc: pd.DataFrame, h: int) -> dict:
    """QLIKE and MSE per model on the common sample, the DM test of each model against HAR"""
    models = [c for c in fc.columns if c not in ("y_real",)]
    common = fc.dropna(subset=["y_real", "har"] + [m for m in ("har_iv", "iv_only") if m in models])
    out = {"n": int(len(common)), "models": {}}
    for m in models:
        c = common.dropna(subset=[m])
        if len(c) < 50:
            continue
        ql = qlike(c[m].values, c["y_real"].values); mse = (np.sqrt(c[m].values) - np.sqrt(c["y_real"].values)) ** 2
        out["models"][m] = {"qlike": float(np.mean(ql)), "rmse_vol_daily": float(np.sqrt(np.mean(mse))), "n": int(len(c)), "bias_log": float(np.mean(np.log(c[m].values / c["y_real"].values)))}
        if m != "har":
            out["models"][m]["dm_vs_har_qlike"] = diebold_mariano(ql, qlike(c["har"].values, c["y_real"].values), h)
    # encompassing: does HAR add to IV alone?  regress the realised on both forecasts
    if "har_iv" in models and "iv_only" in models:
        c = common
        A = np.column_stack([np.ones(len(c)), np.log(c["iv_only"].values), np.log(c["har"].values)])
        b, *_ = np.linalg.lstsq(A, np.log(c["y_real"].values), rcond=None)
        out["encompassing_log_weights"] = {"const": float(b[0]), "iv_only": float(b[1]), "har": float(b[2])}
    return out
