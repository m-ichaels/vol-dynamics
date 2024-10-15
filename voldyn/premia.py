"""The variance risk premium and the dynamics of the surface.

    VRP_t = IV_t^2 - RV_{t+1:t+21}^2        (annualised variance points; IV the model-free 30-day index, RV the
                                             subsequently realised variance over the 21 trading days the index covers)

reported in variance points and as the vol-point gap IV - RV, by asset and by tenor where the term structure exists
(VIX9D / VIX / VIX3M / VIX6M against 6 / 21 / 63 / 126 trading days), with a circular block bootstrap over days (block
length the horizon) for the intervals, by year, and conditionally on the level of the index and the slope of the term
structure.  Regressions of realised on implied (Canina-Figlewski / Christensen-Prabhala): RV = a + b IV + e, b < 1 is the
premium's dependence on the level.

Skew stickiness (Bergomi 2009): with ATM vol sigma_ATM and the 25-delta skew S from daily SSVI fits, regress the daily
change in ATM vol on the index return:  d sigma_ATM = -SSR * S * d ln F.  SSR = 1 is sticky strike, 0 sticky delta, 2 the
value a pure local-volatility model gives.  Sticky-strike versus sticky-delta is tested directly on the fitted slices:
does the vol at a fixed strike or at a fixed moneyness move less from one day to the next?"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data


def realised_forward(ret: pd.Series, h: int, ann: int) -> pd.Series:
    """annualised realised variance over the next h observations (exclusive of t), aligned to t"""
    r2 = ret ** 2
    fwd = r2[::-1].rolling(h).mean()[::-1].shift(-1)
    return fwd * ann


def vrp_series(iv_pct: pd.Series, ret: pd.Series, h: int, ann: int) -> pd.DataFrame:
    """iv in per cent vol points; ret log returns of the underlying.  Returns per-day IV^2, RV^2 (forward), VRP and vol gap."""
    iv = (iv_pct / 100.0) ** 2
    rv = realised_forward(ret, h, ann).reindex(iv.index)
    df = pd.DataFrame({"iv2": iv, "rv2": rv}).dropna()
    df["vrp"] = df["iv2"] - df["rv2"]
    df["gap_vol"] = np.sqrt(df["iv2"]) - np.sqrt(df["rv2"])
    df["log_ratio"] = np.log(df["iv2"] / df["rv2"])
    return df


def block_bootstrap_mean(x: np.ndarray, block: int, B: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95 % interval for the mean of a serially dependent series by circular block bootstrap"""
    x = np.asarray(x, dtype=float); n = len(x); rng = np.random.default_rng(seed)
    if n < 2 * block:
        return np.nan, np.nan
    nb = int(np.ceil(n / block)); means = np.empty(B)
    for b in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel() % n
        means[b] = x[idx[:n]].mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def summarise_vrp(df: pd.DataFrame, h: int, B: int = 2000) -> dict:
    v = df["vrp"].values; g = df["gap_vol"].values
    lo, hi = block_bootstrap_mean(v, h, B); glo, ghi = block_bootstrap_mean(g, h, B)
    out = {"n": int(len(df)), "start": str(df.index[0].date()), "end": str(df.index[-1].date()),
           "iv_mean_vol": float(np.sqrt(df["iv2"].mean())), "rv_mean_vol": float(np.sqrt(df["rv2"].mean())),
           "vrp_mean_varpts": float(v.mean() * 1e4), "vrp_ci_varpts": [lo * 1e4, hi * 1e4],
           "gap_vol_mean_pts": float(g.mean() * 100), "gap_vol_ci_pts": [glo * 100, ghi * 100],
           "share_positive": float((v > 0).mean()), "log_ratio_mean": float(df["log_ratio"].mean()),
           "by_year": {int(y): {"vrp_varpts": float(gg["vrp"].mean() * 1e4), "gap_vol_pts": float(gg["gap_vol"].mean() * 100), "share_positive": float((gg["vrp"] > 0).mean()), "n": int(len(gg))} for y, gg in df.groupby(df.index.year)}}
    # RV on IV regression (variance units): slope below one means the premium grows with the level
    A = np.column_stack([np.ones(len(df)), df["iv2"].values]); b, *_ = np.linalg.lstsq(A, df["rv2"].values, rcond=None)
    resid = df["rv2"].values - A @ b
    # Newey-West standard error of the slope with h-1 lags
    X = A; n = len(df); q = h - 1
    S = np.zeros((2, 2))
    u = resid[:, None] * X
    for k in range(q + 1):
        w = 1 - k / (q + 1)
        G = u[k:].T @ u[:n - k] / n
        S += w * (G + G.T) if k > 0 else G
    XtX_inv = np.linalg.inv(X.T @ X / n)
    V = XtX_inv @ S @ XtX_inv / n
    out["rv_on_iv"] = {"intercept": float(b[0] * 1e4), "slope": float(b[1]), "slope_se_nw": float(np.sqrt(V[1, 1])), "r2": float(1 - resid.var() / df["rv2"].var())}
    return out


def conditional(df: pd.DataFrame, level: pd.Series, slope: pd.Series | None, h: int, B: int = 1000) -> dict:
    """the premium by tercile of the implied level and by sign of the term-structure slope"""
    out = {}
    lv = level.reindex(df.index)
    terc = pd.qcut(lv.rank(method="first"), 3, labels=["low", "mid", "high"])
    out["by_level"] = {}
    for k, g in df.groupby(terc, observed=True):
        lo, hi = block_bootstrap_mean(g["vrp"].values, h, B)
        out["by_level"][str(k)] = {"n": int(len(g)), "level_mean": float(lv.loc[g.index].mean()), "vrp_varpts": float(g["vrp"].mean() * 1e4), "ci": [lo * 1e4, hi * 1e4], "gap_vol_pts": float(g["gap_vol"].mean() * 100), "share_positive": float((g["vrp"] > 0).mean())}
    if slope is not None:
        sl = slope.reindex(df.index)
        out["by_slope"] = {}
        for name, m in (("contango (long above short)", sl > 0), ("backwardation", sl <= 0)):
            g = df[m.fillna(False).values]
            if len(g) < 2 * h:
                continue
            lo, hi = block_bootstrap_mean(g["vrp"].values, h, B)
            out["by_slope"][name] = {"n": int(len(g)), "vrp_varpts": float(g["vrp"].mean() * 1e4), "ci": [lo * 1e4, hi * 1e4], "gap_vol_pts": float(g["gap_vol"].mean() * 100), "share_positive": float((g["vrp"] > 0).mean())}
    return out


def cross_asset(prices: pd.DataFrame, cboe: pd.DataFrame, dvol: dict, h: int = 21, B: int = 2000) -> dict:
    """the 30-day premium for every implied-vol series in data.IV_MAP against its own underlying"""
    out = {}
    lp = np.log(prices)
    for iv_name, (under, proxy, cls, label) in data.IV_MAP.items():
        if iv_name.startswith("DVOL"):
            ccy = iv_name.split("_")[1]
            if ccy not in dvol:
                continue
            iv = data.load_dvol(ccy) if iv_name.startswith("DVOLX") else dvol[ccy]["iv"]; ret = dvol[ccy]["ret"]; hh = 30; ann = 365
        else:
            if iv_name not in cboe or under not in lp:
                continue
            iv = cboe[iv_name].dropna(); ret = lp[under].diff().dropna(); hh = h; ann = 252
        df = vrp_series(iv, ret, hh, ann)
        if len(df) < 500:
            continue
        s = summarise_vrp(df, hh, B); s.update({"underlying": under, "proxy": proxy, "asset_class": cls, "label": label, "horizon_days": hh})
        out[iv_name] = s
    return out


def term_structure_premia(cboe: pd.DataFrame, ret: pd.Series, B: int = 2000) -> dict:
    """the S&P premium by tenor from the VIX family"""
    out = {}
    for name, days in data.TERM_DAYS.items():
        if name not in cboe or name == "VIX1D":
            continue
        h = max(int(round(days * 252 / 365)), 2)
        df = vrp_series(cboe[name].dropna(), ret, h, 252)
        if len(df) < 500:
            continue
        s = summarise_vrp(df, h, B); s["tenor_calendar_days"] = days; s["horizon_trading_days"] = h
        out[name] = s
    return out


# ---- skew stickiness from daily surface fits ---------------------------------------------------------------------------------------
def skew_stickiness(fits: pd.DataFrame, min_T: float = 0.04, max_T: float = 0.25) -> dict:
    """fits: one row per (date, expiry slice) with columns date, T, F, atm_vol, skew_25 (put minus call 25-delta vol),
    theta, rho, psi.  For each date take the slice nearest 30 days; regress d atm_vol on d ln F to get the SSR, and
    compare the day-to-day change of vol at fixed strike against fixed moneyness."""
    f = fits[(fits["T"] >= min_T) & (fits["T"] <= max_T)].copy()
    f["dist"] = (f["T"] - 30 / 365).abs()
    near = f.sort_values("dist").groupby("date").head(1).sort_values("date").set_index("date")
    d = pd.DataFrame({"d_atm": near["atm_vol"].diff(), "d_lnF": np.log(near["F"]).diff(), "skew": near["skew_25"].shift(1), "atm": near["atm_vol"].shift(1)}).dropna()
    d = d[(d["skew"].abs() > 1e-4)]
    # d sigma_ATM = -SSR * S_k * d ln F, with S_k the skew per unit log-moneyness: skew_25 is per ~1.35 total vol of moneyness
    d["skew_per_k"] = d["skew"] / (2 * 0.6745 * d["atm"] * np.sqrt(30 / 365))
    x = -d["skew_per_k"] * d["d_lnF"]; y = d["d_atm"]
    ok = np.isfinite(x) & np.isfinite(y) & (x.abs() < 0.5) & (y.abs() < 0.5)
    x, y = x[ok].values, y[ok].values
    A = np.column_stack([np.ones(len(x)), x]); b, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ b
    se = np.sqrt(resid.var() / max(np.sum((x - x.mean()) ** 2), 1e-12))
    out = {"n_days": int(ok.sum()), "ssr": float(b[1]), "ssr_se": float(se), "r2": float(1 - resid.var() / max(y.var(), 1e-18))}
    # the regime split: SSR by year
    dd = d[ok].copy(); dd["x"] = x; dd["y"] = y
    out["ssr_by_year"] = {}
    for yr, g in dd.groupby(dd.index.year):
        if len(g) > 40:
            A = np.column_stack([np.ones(len(g)), g["x"].values]); bb, *_ = np.linalg.lstsq(A, g["y"].values, rcond=None)
            out["ssr_by_year"][int(yr)] = float(bb[1])
    return out


def sticky_test(fits: pd.DataFrame, surface_iv, min_T: float = 0.04, max_T: float = 0.25) -> dict:
    """day-to-day change of implied vol at a fixed strike (yesterday's ATM strike) against at fixed moneyness (today's
    ATM): the smaller mean absolute change says which frame the surface moves in.  surface_iv(row, K) evaluates the
    fitted slice at strike K."""
    f = fits[(fits["T"] >= min_T) & (fits["T"] <= max_T)].copy()
    f["dist"] = (f["T"] - 30 / 365).abs()
    near = f.sort_values("dist").groupby("date").head(1).sort_values("date").reset_index(drop=True)
    fixed_k, fixed_m, moves = [], [], []
    for i in range(1, len(near)):
        a, b = near.iloc[i - 1], near.iloc[i]
        if (b["date"] - a["date"]).days > 4:
            continue
        v_yest_atm = a["atm_vol"]
        v_today_at_old_strike = surface_iv(b, a["F"])
        v_today_atm = b["atm_vol"]
        fixed_k.append(v_today_at_old_strike - v_yest_atm); fixed_m.append(v_today_atm - v_yest_atm); moves.append(np.log(b["F"] / a["F"]))
    fk, fm, mv = np.array(fixed_k), np.array(fixed_m), np.array(moves)
    big = np.abs(mv) > np.quantile(np.abs(mv), 0.75)
    return {"n": int(len(fk)), "mean_abs_change_fixed_strike": float(np.nanmean(np.abs(fk))), "mean_abs_change_fixed_moneyness": float(np.nanmean(np.abs(fm))),
            "large_moves": {"n": int(big.sum()), "fixed_strike": float(np.nanmean(np.abs(fk[big]))), "fixed_moneyness": float(np.nanmean(np.abs(fm[big])))},
            "verdict": "closer to sticky strike" if np.nanmean(np.abs(fk)) < np.nanmean(np.abs(fm)) else "closer to sticky delta / moneyness"}


# ---- the single-name cross-section from the vendor's IV table ------------------------------------------------------------------------
def single_name_panel(symbols: list, prices: pd.DataFrame, h: int = 21, B: int = 500) -> dict:
    """the vendor's current implied vol per name (DoltHub volatility_history, weekly to 2023 then daily) against the vol
    realised over the following 21 trading days from Yahoo closes: the premium per name and pooled, and the vendor's IV
    against the Cboe index for the five names that have one"""
    lp = np.log(prices)
    rows = {}; pooled = []
    for s in symbols:
        vh = data.load_volhist(s)
        if vh.empty or s not in lp:
            continue
        iv = vh.set_index("date")["iv_current"].dropna() * 100
        ret = lp[s].diff().dropna()
        # align each (possibly weekend) table date to the last trading day on or before it
        idx = ret.index
        pos = idx.searchsorted(iv.index, side="right") - 1
        ok = pos >= 0
        iv = pd.Series(iv.values[ok], index=idx[pos[ok]]); iv = iv[~iv.index.duplicated(keep="last")]
        df = vrp_series(iv, ret, h, 252)
        if len(df) < 100:
            continue
        rows[s] = {"n": int(len(df)), "iv_mean": float(np.sqrt(df["iv2"].mean()) * 100), "rv_mean": float(np.sqrt(df["rv2"].mean()) * 100), "gap_vol_pts": float(df["gap_vol"].mean() * 100), "share_positive": float((df["vrp"] > 0).mean())}
        pooled.append(df["gap_vol"].values)
    allv = np.concatenate(pooled) if pooled else np.array([])
    out = {"n_names": len(rows), "by_name": rows}
    if len(allv):
        gaps = np.array([r["gap_vol_pts"] for r in rows.values()])
        out["cross_section"] = {"mean_gap_pts": float(gaps.mean()), "median_gap_pts": float(np.median(gaps)), "share_names_positive": float((gaps > 0).mean()), "min": float(gaps.min()), "max": float(gaps.max()), "pooled_obs": int(len(allv))}
    # vendor IV against the Cboe single-name index
    checks = {}
    cb = data.load_cboe_all()
    for iv_name, s in (("VXAPL", "AAPL"), ("VXAZN", "AMZN"), ("VXGOG", "GOOGL"), ("VXIBM", "IBM"), ("VXGS", "GS")):
        vh = data.load_volhist(s)
        if vh.empty or iv_name not in cb:
            continue
        v = vh.set_index("date")["iv_current"].dropna() * 100
        j = pd.DataFrame({"vendor": v, "cboe": cb[iv_name]}).dropna()
        if len(j) > 50:
            checks[s] = {"n": int(len(j)), "corr": float(j["vendor"].corr(j["cboe"])), "mean_diff_pts": float((j["vendor"] - j["cboe"]).mean())}
    out["vendor_vs_cboe"] = checks
    return out
