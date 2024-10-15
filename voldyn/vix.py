"""The VIX complex: the index term structure (VIX9D, VIX, VIX3M, VIX6M), the VX futures curve from the per-contract
settlement files, roll-down by contract month, the short-front-month roll strategy net of bid-ask, and VVIX against the
slope.

Roll-down of the n-th contract: with F_n the settlement of the n-th listed contract and tau_n its days to expiry, the
carry a short position earns if the curve does not move is (F_n - F_{n-1}) per (tau_n - tau_{n-1}) days, F_0 = VIX.  The
strategy shorts the front contract from the day after the previous expiry to the day before expiry (rolling to the second
contract over the last five days), sized at one contract per unit of the daily-marked notional, and pays half the
quoted VX spread (0.05 index points = $50 a contract) on each entry and roll leg; the settlement (final value) is the
Cboe special opening quotation, taken as the day's settle in the file."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from .premia import block_bootstrap_mean as _bb

HALF_SPREAD_PTS = 0.025      # half the 0.05 minimum tick, the usual quoted spread for the front two months
POINT_VALUE = 1000.0


def term_structure(cboe: pd.DataFrame) -> pd.DataFrame:
    """the index term structure per day with the slopes slope_short = VIX - VIX9D and slope_long = VIX3M - VIX and the
    four states their signs make: contango (both up), backwardation (both down), a front kink (VIX9D above VIX with the
    3M above it too: a short-dated event priced in) and a hump (VIX above both neighbours)"""
    cols = [c for c in data.TERM if c in cboe]
    ts = cboe[cols].dropna(subset=["VIX"]).copy()
    if "VIX9D" in ts and "VIX3M" in ts:
        ts["slope_short"] = ts["VIX"] - ts["VIX9D"]; ts["slope_long"] = ts["VIX3M"] - ts["VIX"]
        up_s, up_l = ts["slope_short"] > 0, ts["slope_long"] > 0
        ok = ts["slope_short"].notna() & ts["slope_long"].notna()
        ts["state"] = np.select([ok & up_s & up_l, ok & ~up_s & ~up_l, ok & ~up_s & up_l, ok & up_s & ~up_l], ["contango", "backwardation", "front kink (9D > VIX < 3M)", "hump (9D < VIX > 3M)"], None)
    if "VIX6M" in ts and "VIX3M" in ts:
        ts["slope_6m_3m"] = ts["VIX6M"] - ts["VIX3M"]
    return ts


def state_stats(ts: pd.DataFrame, ret: pd.Series, h: int = 21) -> dict:
    """time in each state, the forward realised vol and the VIX change that follow each state"""
    rv_f = np.sqrt(((ret ** 2)[::-1].rolling(h).mean()[::-1].shift(-1) * 252)).reindex(ts.index) * 100
    dv = ts["VIX"].shift(-h) - ts["VIX"]
    out = {}
    for s, g in ts.groupby("state"):
        out[s] = {"share_of_days": float(len(g) / len(ts)), "vix_mean": float(g["VIX"].mean()), "fwd_rv_mean": float(rv_f.loc[g.index].mean()), "premium_pts": float((g["VIX"] - rv_f.loc[g.index]).mean()), "vix_change_21d": float(dv.loc[g.index].mean()), "n": int(len(g))}
    # transition matrix of the daily state
    st = ts["state"]; nxt = st.shift(-1)
    out["transition"] = pd.crosstab(st, nxt, normalize="index").round(3).to_dict()
    return out


def vx_curve(vx: pd.DataFrame, vix: pd.Series) -> pd.DataFrame:
    """per day: the first six listed contracts' settles, days to expiry, and the roll-down per month"""
    rows = []
    for d, g in vx.groupby("date"):
        g = g[g["expiry"] > d].sort_values("expiry")
        if len(g) < 2:
            continue
        r = {"date": d, "vix": vix.get(d, np.nan)}
        for i, (_, row) in enumerate(g.head(6).iterrows(), start=1):
            r[f"F{i}"] = row["settle"]; r[f"tau{i}"] = (row["expiry"] - d).days; r[f"oi{i}"] = row["open_interest"]
        rows.append(r)
    c = pd.DataFrame(rows).set_index("date").sort_index()
    for i in range(1, 6):
        if f"F{i + 1}" in c:
            c[f"roll_{i}"] = (c[f"F{i + 1}"] - c[f"F{i}"]) / (c[f"tau{i + 1}"] - c[f"tau{i}"]).replace(0, np.nan) * 30     # points per 30 days
    c["roll_0"] = (c["F1"] - c["vix"]) / c["tau1"].replace(0, np.nan) * 30
    c["contango_1_2"] = c["F2"] > c["F1"]
    # constant-maturity 30-day future by linear interpolation between the two contracts that straddle 30 days
    lam = ((30 - c["tau1"]) / (c["tau2"] - c["tau1"])).clip(0, 1)
    c["F30"] = (1 - lam) * c["F1"] + lam * c["F2"]
    return c


def roll_strategy(vx: pd.DataFrame, curve: pd.DataFrame, half_spread: float = HALF_SPREAD_PTS, roll_days: int = 5) -> pd.DataFrame:
    """short one front-month VX contract, rolled to the second contract over the last `roll_days` trading days before
    expiry.  Daily P&L in index points from settlement to settlement; costs at each leg.  Returns the daily ledger."""
    dates = curve.index; rows = []
    pos = {}          # expiry -> contracts (negative = short)
    prev_settle = {}  # expiry -> yesterday's settle
    by_day = {d: g.set_index("expiry")["settle"] for d, g in vx.groupby("date")}
    for d in dates:
        s = by_day.get(d)
        if s is None:
            continue
        live = sorted([e for e in s.index if e > d])
        if len(live) < 2:
            continue
        front, second = live[0], live[1]
        pnl = 0.0; cost = 0.0
        # mark existing positions
        for e, q in list(pos.items()):
            if e in s.index and e in prev_settle:
                pnl += q * (s[e] - prev_settle[e])
        # expired contract: settled at its last settle, position gone
        for e in list(pos):
            if e <= d:
                pos.pop(e, None)
        target_front = front if (front - d).days > roll_days else second
        # roll: move the front short to the second over the roll window in equal pieces
        want = {target_front: -1.0}
        if (front - d).days <= roll_days and (front - d).days > 0 and front in s.index:
            k = (front - d).days
            want = {front: -k / roll_days, second: -(1 - k / roll_days)}
        for e in set(pos) | set(want):
            q0 = pos.get(e, 0.0); q1 = want.get(e, 0.0)
            if abs(q1 - q0) > 1e-9 and e in s.index:
                cost += abs(q1 - q0) * half_spread
                pos[e] = q1
            elif e not in want:
                pos.pop(e, None)
        for e in pos:
            prev_settle[e] = s[e]
        rows.append({"date": d, "pnl_pts": pnl, "cost_pts": cost, "net_pts": pnl - cost, "front": front, "front_settle": s[front], "vix": curve.loc[d, "vix"]})
    led = pd.DataFrame(rows).set_index("date")
    led["cum_net"] = led["net_pts"].cumsum(); led["cum_gross"] = led["pnl_pts"].cumsum()
    return led


def roll_summary(led: pd.DataFrame, curve: pd.DataFrame) -> dict:
    yrs = (led.index[-1] - led.index[0]).days / 365.25
    dd = (led["cum_net"].cummax() - led["cum_net"]).max()
    out = {"years": round(yrs, 2), "gross_pts_per_year": float(led["pnl_pts"].sum() / yrs), "cost_pts_per_year": float(led["cost_pts"].sum() / yrs), "net_pts_per_year": float(led["net_pts"].sum() / yrs),
           "net_usd_per_contract_year": float(led["net_pts"].sum() / yrs * POINT_VALUE), "daily_sd_pts": float(led["net_pts"].std()), "sharpe": float(led["net_pts"].mean() / led["net_pts"].std() * np.sqrt(252)),
           "max_drawdown_pts": float(dd), "worst_day_pts": float(led["net_pts"].min()), "worst_day": str(led["net_pts"].idxmin().date()),
           "by_year": {int(y): float(g["net_pts"].sum()) for y, g in led.groupby(led.index.year)}}
    # conditional on the curve state known at the start of the day (the previous settlement)
    st = curve["contango_1_2"].shift(1).reindex(led.index).fillna(False).astype(bool)
    out["net_pts_per_day_contango"] = float(led.loc[st.values, "net_pts"].mean()); out["net_pts_per_day_backwardation"] = float(led.loc[~st.values, "net_pts"].mean())
    out["share_days_contango"] = float(st.mean())
    # conditional strategy: short only when yesterday's curve was in contango
    cond = led["net_pts"].where(st.values, 0.0)
    out["contango_only"] = {"net_pts_per_year": float(cond.sum() / yrs), "sharpe": float(cond.mean() / cond.std() * np.sqrt(252)) if cond.std() > 0 else np.nan, "max_drawdown_pts": float((cond.cumsum().cummax() - cond.cumsum()).max())}
    return out


def vvix_analysis(cboe: pd.DataFrame, ts: pd.DataFrame, curve: pd.DataFrame | None = None) -> dict:
    """VVIX against the level and the slope; the forward realised vol of the 30-day constant-maturity VX future (what
    VIX options are written on) and of the spot index against VVIX"""
    df = pd.DataFrame({"vvix": cboe["VVIX"], "vix": ts["VIX"], "slope": ts.get("slope_long")}).dropna()
    rv_vix = (np.log(df["vix"]).diff() ** 2)[::-1].rolling(21).mean()[::-1].shift(-1)
    df["rv_vix_fwd"] = np.sqrt(rv_vix * 252) * 100
    out = {"n": int(len(df)), "corr_vvix_vix": float(df["vvix"].corr(df["vix"])), "corr_vvix_slope": float(df["vvix"].corr(df["slope"])),
           "vvix_mean": float(df["vvix"].mean()), "rv_of_spot_vix_mean": float(df["rv_vix_fwd"].mean()), "corr_vvix_fwd_rv_vix": float(df["vvix"].corr(df["rv_vix_fwd"]))}
    if curve is not None and "F30" in curve:
        f30 = curve["F30"].reindex(df.index)
        rv_f = (np.log(f30).diff() ** 2)[::-1].rolling(21).mean()[::-1].shift(-1)
        df["rv_f30_fwd"] = np.sqrt(rv_f * 252) * 100
        d2 = df.dropna(subset=["rv_f30_fwd"])
        out["rv_of_30d_future_mean"] = float(d2["rv_f30_fwd"].mean()); out["vol_of_vol_premium_pts"] = float((d2["vvix"] - d2["rv_f30_fwd"]).mean())
        out["vol_of_vol_premium_ci"] = [x for x in _bb(d2["vvix"].values - d2["rv_f30_fwd"].values, 21)]
        out["corr_vvix_fwd_rv_f30"] = float(d2["vvix"].corr(d2["rv_f30_fwd"])); out["n_f30"] = int(len(d2))
    # slope terciles
    t = pd.qcut(df["slope"].rank(method="first"), 3, labels=["backwardated", "flat", "steep"])
    out["vvix_by_slope"] = {str(k): float(g["vvix"].mean()) for k, g in df.groupby(t, observed=True)}
    return out
