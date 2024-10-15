"""Event volatility: earnings and FOMC.

Earnings.  On the last chain date before the announcement (the day before, when the table has it; up to five business
days before otherwise), the front expiry that spans the event gives the ATM straddle.  Its price as a fraction of spot,
divided by the Black-Scholes factor sqrt(2/pi) * sqrt(T_remaining)... is not the implied move: the straddle prices the
diffusion until expiry plus the jump.  The implied move is recovered by stripping the diffusion:

    implied_move^2 = straddle_var_total - sigma_base^2 * T_remaining,   sigma_base = the ATM vol of the second expiry
                     (which spans the event too but dilutes it) solved jointly from the two expiries' total variances:
    w1 = sigma_d^2 T1 + J^2,   w2 = sigma_d^2 T2 + J^2   =>   J^2 = (w1 T2 - w2 T1) / (T2 - T1),

and the plain straddle rule  move ~ 0.8 * straddle / spot  is reported beside it.  The realised move is the log return
from the close before the announcement to the close after (open after, for the gap).  The premium is the ratio of
implied to realised absolute move and, for a seller, the P&L of the straddle held over the event and closed at the next
chain date, marked with the post-event chain when it exists.

FOMC.  The path of VIX1D, VIX9D and VIX into and out of the decision day, the realised S&P and TLT moves on the day
against the implied daily move (VIX / sqrt(252), VIX1D where it exists), and the vol crush: the change in VIX9D from the
day before to the day after."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import chains, data
from .surface import black, implied_vol


def straddle_atm(chain_day: pd.DataFrame, spot: float, expiry: pd.Timestamp, r_prior: float = 0.0) -> dict | None:
    """ATM straddle on one expiry: forward and discount from parity, the strike nearest the forward with both legs"""
    g = chain_day[chain_day["expiration"] == expiry]
    if g.empty:
        return None
    T = float(g["T"].iloc[0])
    F, df, _ = chains.expiry_forward(g, spot, T, r_prior)
    st = chains.atm_straddle(g, F, df, spot)
    if st is None:
        return None
    return {"K": st["K"], "straddle": st["mid"], "bid": st["bid"], "ask": st["ask"], "T": T, "iv": st["iv"], "w": st["w"], "spread": st["spread"], "F": F, "df": df}


def implied_move(chain_day: pd.DataFrame, spot: float, event_date: pd.Timestamp) -> dict | None:
    exps = sorted(e for e in chain_day["expiration"].unique() if e >= event_date)
    if not exps:
        return None
    s1 = straddle_atm(chain_day, spot, exps[0])
    if s1 is None:
        return None
    out = {"expiry1": exps[0], "T1": s1["T"], "iv1": s1["iv"], "straddle_pct": s1["straddle"] / spot, "rule_move": 0.8 * s1["straddle"] / spot, "spread_pct_of_straddle": s1["spread"] / s1["straddle"]}
    if len(exps) > 1:
        s2 = straddle_atm(chain_day, spot, exps[1])
        if s2 is not None and s2["T"] > s1["T"]:
            J2 = (s1["w"] * s2["T"] - s2["w"] * s1["T"]) / (s2["T"] - s1["T"])
            out.update({"expiry2": exps[1], "T2": s2["T"], "iv2": s2["iv"], "jump_var": J2, "stripped_move": float(np.sqrt(max(J2, 0.0))), "diffusion_vol": float(np.sqrt(max((s1["w"] - J2) / s1["T"], 0.0)))})
    return out


def earnings_study(symbols: list, lookback_days: int = 5) -> pd.DataFrame:
    prices = data.load_prices()
    rows = []
    for sym in symbols:
        ch = data.load_chains(sym); ev = data.load_earnings(sym)
        if ch.empty or ev.empty:
            continue
        px = prices[prices["symbol"] == sym].set_index("date").sort_index()
        dates = np.array(sorted(ch["date"].unique()))
        for _, e in ev.iterrows():
            d = e["date"]
            if d < ch["date"].min() or d > px.index.max():
                continue
            # the announcement's market impact is the session after it: after the close -> next day; before the open -> the day
            if e["after_close"]:
                pre_close_day = d; post_day = px.index[px.index > d][:1]
            else:
                pre_close_day = px.index[px.index < d][-1:]; post_day = px.index[px.index >= d][:1]
                pre_close_day = pre_close_day[0] if len(pre_close_day) else None
            if pre_close_day is None or len(post_day) == 0 or pre_close_day not in px.index:
                continue
            post_day = post_day[0]
            cand = dates[(dates <= pre_close_day) & (dates >= pre_close_day - pd.Timedelta(days=lookback_days + 2))]
            if len(cand) == 0:
                continue
            cd = cand[-1]
            day = ch[ch["date"] == cd]
            spot = float(px.loc[:cd, "close"].iloc[-1])
            im = implied_move(day, spot, post_day)
            if im is None:
                continue
            realised_cc = float(np.log(px.loc[post_day, "close"] / px.loc[pre_close_day, "close"]))
            realised_gap = float(np.log(px.loc[post_day, "open"] / px.loc[pre_close_day, "close"]))
            # seller's P&L: short the straddle at the pre-event mid, settle at the first chain date after the event if it
            # exists within 5 days (marked at mid), else at intrinsic on the post day's close (the front expiry is near)
            after = dates[(dates >= post_day) & (dates <= post_day + pd.Timedelta(days=7))]
            exit_val = None; exit_kind = None
            if len(after):
                da = ch[(ch["date"] == after[0]) & (ch["expiration"] == im["expiry1"])]
                c = da[(da["cp"] > 0) & (da["strike"] == im.get("K", np.nan))]; p = da[(da["cp"] < 0) & (da["strike"] == im.get("K", np.nan))]
                s1 = straddle_atm(day, spot, im["expiry1"])
                cK = da[(da["cp"] > 0) & (da["strike"] == s1["K"])]["mid"]; pK = da[(da["cp"] < 0) & (da["strike"] == s1["K"])]["mid"]
                if len(cK) and len(pK) and np.isfinite(cK.iloc[0]) and np.isfinite(pK.iloc[0]):
                    exit_val = float(cK.iloc[0] + pK.iloc[0]); exit_kind = "chain mid " + str(after[0].date())
            s1 = straddle_atm(day, spot, im["expiry1"])
            if exit_val is None:
                # no chain after the event: mark the straddle on the post-event close with Black at the diffusion vol
                # (the event's jump variance has been realised; what remains is the ordinary vol to expiry)
                S_post = float(px.loc[post_day, "close"]); T_rem = max((im["expiry1"] - post_day).days, 0) / 365.0
                v_post = im.get("diffusion_vol", np.nan)
                if not (np.isfinite(v_post) and v_post > 0.02):
                    v_post = im.get("iv2", im["iv1"] * 0.85)
                F_post = S_post * np.exp(np.log(s1["F"] / spot) / s1["T"] * T_rem) if T_rem > 0 else S_post
                exit_val = float(s1["df"] ** (T_rem / s1["T"]) * (black(F_post, s1["K"], T_rem, v_post, 1.0) + black(F_post, s1["K"], T_rem, v_post, -1.0))) if T_rem > 0 else abs(S_post - s1["K"])
                exit_kind = "model at diffusion vol"
            rows.append({"symbol": sym, "event": d, "when": e["when"], "chain_date": cd, "days_before": int((pre_close_day - cd).days), "spot": spot, "expiry": im["expiry1"], "T1": im["T1"], "iv1": im["iv1"],
                         "straddle_pct": im["straddle_pct"], "rule_move": im["rule_move"], "stripped_move": im.get("stripped_move", np.nan), "diffusion_vol": im.get("diffusion_vol", np.nan), "iv2": im.get("iv2", np.nan),
                         "realised_cc": realised_cc, "realised_gap": realised_gap, "spread_pct": im["spread_pct_of_straddle"],
                         "seller_pnl_pct": (s1["straddle"] - exit_val) / spot, "seller_pnl_after_spread_pct": (s1["bid"] - exit_val - 0.5 * s1["spread"]) / spot, "exit": exit_kind})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["abs_real"] = df["realised_cc"].abs()
    df["ratio_rule"] = df["rule_move"] / df["abs_real"].replace(0, np.nan)
    df["ratio_stripped"] = df["stripped_move"] / df["abs_real"].replace(0, np.nan)
    df["year"] = df["event"].dt.year
    return df


def earnings_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    d = df.dropna(subset=["stripped_move"])
    def blk(g):
        return {"n": int(len(g)), "implied_move_rule_pct": float(g["rule_move"].mean() * 100), "implied_move_stripped_pct": float(g["stripped_move"].mean() * 100), "realised_abs_move_pct": float(g["abs_real"].mean() * 100),
                "median_ratio_stripped": float(g["ratio_stripped"].median()), "share_implied_above_realised": float((g["stripped_move"] > g["abs_real"]).mean()),
                "rms_implied_pct": float(np.sqrt((g["stripped_move"] ** 2).mean()) * 100), "rms_realised_pct": float(np.sqrt((g["realised_cc"] ** 2).mean()) * 100),
                "seller_pnl_mean_pct": float(g["seller_pnl_pct"].mean() * 100), "seller_pnl_after_spread_pct": float(g["seller_pnl_after_spread_pct"].mean() * 100), "seller_hit_rate": float((g["seller_pnl_after_spread_pct"] > 0).mean()),
                "seller_pnl_sd_pct": float(g["seller_pnl_pct"].std() * 100), "worst_pct": float(g["seller_pnl_after_spread_pct"].min() * 100)}
    out = {"all": blk(d), "by_symbol": {s: blk(g) for s, g in d.groupby("symbol") if len(g) >= 6}, "by_year": {int(y): blk(g) for y, g in d.groupby("year") if len(g) >= 6},
           "by_days_before": {int(k): blk(g) for k, g in d.groupby("days_before") if len(g) >= 10}}
    # the calibration of the implied move: regress realised^2 on implied^2 (a slope of one means the market is right on average)
    A = np.column_stack([np.ones(len(d)), d["stripped_move"].values ** 2]); b, *_ = np.linalg.lstsq(A, d["realised_cc"].values ** 2, rcond=None)
    out["realised_sq_on_implied_sq"] = {"intercept": float(b[0]), "slope": float(b[1])}
    # rank correlation: do bigger implied moves predict bigger realised ones?
    from scipy.stats import spearmanr
    out["spearman_implied_vs_abs_realised"] = float(spearmanr(d["stripped_move"], d["abs_real"])[0])
    return out


def fomc_study(cboe: pd.DataFrame, prices: pd.DataFrame, fomc: pd.DataFrame, window: int = 5) -> dict:
    """the vol path around decision days and the implied against realised daily move"""
    lp = np.log(prices.pivot(index="date", columns="symbol", values="adjclose").sort_index())
    spx = lp["^GSPC"].diff(); tlt = lp["TLT"].diff()
    idx = cboe.index
    paths = {k: [] for k in ("VIX", "VIX9D", "VIX1D", "VVIX", "VXTLT")}
    rows = []
    for d in fomc["date"]:
        if d not in idx:
            continue
        i = idx.get_loc(d)
        for k in paths:
            if k in cboe:
                seg = cboe[k].iloc[max(0, i - window):i + window + 1]
                if len(seg) == 2 * window + 1 and seg.notna().all():
                    paths[k].append(seg.values - seg.values[window - 1])          # relative to the day before
        rows.append({"date": d, "vix_before": cboe["VIX"].iloc[i - 1], "vix_on": cboe["VIX"].iloc[i], "vix_after": cboe["VIX"].iloc[i + 1] if i + 1 < len(idx) else np.nan,
                     "vix9d_before": cboe["VIX9D"].iloc[i - 1] if "VIX9D" in cboe else np.nan, "vix9d_after": cboe["VIX9D"].iloc[i + 1] if ("VIX9D" in cboe and i + 1 < len(idx)) else np.nan,
                     "vix1d_before": cboe["VIX1D"].iloc[i - 1] if "VIX1D" in cboe else np.nan,
                     "spx_move": spx.get(d, np.nan), "tlt_move": tlt.get(d, np.nan), "vxtlt_before": cboe["VXTLT"].iloc[i - 1] if "VXTLT" in cboe else np.nan})
    df = pd.DataFrame(rows).dropna(subset=["spx_move"])
    df["implied_daily_spx"] = df["vix_before"] / 100 / np.sqrt(252); df["implied_daily_1d"] = df["vix1d_before"] / 100 / np.sqrt(252)
    df["implied_daily_tlt"] = df["vxtlt_before"] / 100 / np.sqrt(252)
    # the same statistics on all other days for comparison
    all_days = pd.DataFrame({"spx": spx, "vix_prev": cboe["VIX"].shift(1)}).dropna()
    all_days = all_days[~all_days.index.isin(df["date"])]
    out = {"n_events": int(len(df)), "spx_abs_move_fomc_pct": float(df["spx_move"].abs().mean() * 100), "spx_abs_move_other_pct": float(all_days["spx"].abs().mean() * 100),
           "spx_rms_fomc_pct": float(np.sqrt((df["spx_move"] ** 2).mean()) * 100), "implied_daily_from_vix_pct": float(df["implied_daily_spx"].mean() * 100),
           "ratio_realised_to_implied_rms_fomc": float(np.sqrt((df["spx_move"] ** 2).mean()) / df["implied_daily_spx"].mean()),
           "ratio_realised_to_implied_rms_other": float(np.sqrt((all_days["spx"] ** 2).mean()) / (all_days["vix_prev"] / 100 / np.sqrt(252)).mean()),
           "tlt_abs_move_fomc_pct": float(df["tlt_move"].abs().mean() * 100), "tlt_abs_move_other_pct": float(tlt[~tlt.index.isin(df["date"])].abs().mean() * 100),
           "tlt_rms_to_implied_fomc": float(np.sqrt((df["tlt_move"] ** 2).mean()) / df["implied_daily_tlt"].mean()),
           "vix_change_on_day": float((df["vix_on"] - df["vix_before"]).mean()), "vix_change_before_to_after": float((df["vix_after"] - df["vix_before"]).mean()),
           "vix9d_crush_before_to_after": float((df["vix9d_after"] - df["vix9d_before"]).mean()), "share_vix_down_on_day": float((df["vix_on"] < df["vix_before"]).mean())}
    v1 = df.dropna(subset=["vix1d_before"])
    if len(v1) >= 10:
        out["vix1d"] = {"n": int(len(v1)), "implied_daily_from_vix1d_pct": float(v1["implied_daily_1d"].mean() * 100), "rms_realised_pct": float(np.sqrt((v1["spx_move"] ** 2).mean()) * 100), "ratio_realised_to_vix1d": float(np.sqrt((v1["spx_move"] ** 2).mean()) / v1["implied_daily_1d"].mean())}
    out["paths"] = {k: {"n": len(v), "mean": np.mean(v, axis=0).round(3).tolist(), "offsets": list(range(-window, window + 1))} for k, v in paths.items() if v}
    return out, df
