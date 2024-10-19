#!/usr/bin/env python3
"""Figures from results/*.json and data/derived/*.parquet -> results/figures/*.png"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.ticker
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from voldyn import data  # noqa: E402

RES = os.path.join(ROOT, "results"); FIG = os.path.join(RES, "figures"); DER = os.path.join(ROOT, "data", "derived")
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 130})
CLS_COL = {"equity index": "#1f77b4", "rates": "#2ca02c", "commodity": "#ff7f0e", "single name": "#9467bd", "crypto": "#d62728"}


def load(name):
    p = os.path.join(RES, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def fig_premia(pr):
    ca = pr["cross_asset"]; keys = sorted(ca, key=lambda k: (list(CLS_COL).index(ca[k]["asset_class"]), -ca[k]["gap_vol_mean_pts"]))
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
    y = np.arange(len(keys))
    for i, k in enumerate(keys):
        v = ca[k]; lo, hi = v["gap_vol_ci_pts"]
        ax[0].barh(i, v["gap_vol_mean_pts"], color=CLS_COL[v["asset_class"]], alpha=0.85)
        ax[0].plot([lo, hi], [i, i], color="k", lw=1)
    ax[0].set_yticks(y); ax[0].set_yticklabels([f"{ca[k]['label']} ({k})" for k in keys], fontsize=7); ax[0].invert_yaxis()
    ax[0].set_xlabel("implied minus subsequently realised vol, points (95 % block-bootstrap CI)"); ax[0].set_title("the 30-day variance risk premium by asset")
    ax[0].axvline(0, color="k", lw=0.6)
    # by year for the S&P, BTC
    for k, col in (("VIX", CLS_COL["equity index"]), ("DVOLX_BTC", CLS_COL["crypto"]), ("OVX", CLS_COL["commodity"]), ("VXTLT", CLS_COL["rates"])):
        if k in ca:
            by = ca[k]["by_year"]; ax[1].plot([int(yy) for yy in by], [v["gap_vol_pts"] for v in by.values()], "o-", ms=3, color=col, label=ca[k]["label"])
    ax[1].axhline(0, color="k", lw=0.6); ax[1].set_title("premium by year (vol points)"); ax[1].legend(fontsize=7); ax[1].tick_params(axis="x", rotation=45)
    ax[1].xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    # term structure of the premium: S&P and BTC
    ts = pr.get("spx_by_tenor", {})
    if ts:
        xs = [ts[k]["tenor_calendar_days"] for k in ts]; ys = [ts[k]["gap_vol_mean_pts"] for k in ts]; ci = np.array([ts[k]["gap_vol_ci_pts"] for k in ts])
        o = np.argsort(xs); xs, ys, ci = np.array(xs)[o], np.array(ys)[o], ci[o]
        ax[2].errorbar(xs, ys, yerr=[ys - ci[:, 0], ci[:, 1] - ys], fmt="o-", color=CLS_COL["equity index"], capsize=3, label="S&P 500 (VIX9D / VIX / VIX3M / VIX6M)")
    for ccy, col in (("BTC", CLS_COL["crypto"]), ("ETH", "#e377c2")):
        ct = pr.get("crypto_by_tenor", {}).get(ccy, {})
        pts = [(int(k), v["gap_vol_mean_pts"], v["gap_vol_ci_pts"]) for k, v in ct.items() if k.isdigit()]
        if pts:
            pts.sort(); xs = [p[0] for p in pts]; ys = np.array([p[1] for p in pts]); ci = np.array([p[2] for p in pts])
            ax[2].errorbar(xs, ys, yerr=[ys - ci[:, 0], ci[:, 1] - ys], fmt="s--", color=col, capsize=3, label=f"{ccy} (from every Deribit print)")
    ax[2].set_xscale("log"); ax[2].set_xlabel("tenor, calendar days"); ax[2].set_ylabel("vol points"); ax[2].set_title("premium by tenor"); ax[2].legend(fontsize=7); ax[2].axhline(0, color="k", lw=0.6)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "premia.png")); plt.close(fig)


def fig_forecast(fc):
    a = fc["assets"]; keys = [k for k in a if "har_iv" in a[k]["models"]]
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    x = np.arange(len(keys)); w = 0.2
    for j, (m, col, lab) in enumerate((("rw", "#bbb", "random walk"), ("garch", "#999", "GARCH(1,1)"), ("har", "#1f77b4", "HAR-RV"), ("har_iv", "#d62728", "HAR + implied"), ("iv_only", "#ff7f0e", "implied only"))):
        vals = [a[k]["models"].get(m, {}).get("qlike", np.nan) for k in keys]
        ax[0].bar(x + (j - 2) * w, vals, w, color=col, label=lab)
    ax[0].set_xticks(x); ax[0].set_xticklabels([a[k]["label"] for k in keys], rotation=40, ha="right", fontsize=7); ax[0].set_ylabel("QLIKE (lower is better)"); ax[0].set_ylim(0, min(2.0, ax[0].get_ylim()[1])); ax[0].set_title("out-of-sample forecast loss, 21-day variance"); ax[0].legend(fontsize=7)
    # DM statistics of HAR+IV vs HAR
    dm = [a[k]["models"]["har_iv"]["dm_vs_har_qlike"]["dm"] for k in keys]
    ax[1].barh(x, dm, color=["#d62728" if d < 0 else "#999" for d in dm]); ax[1].set_yticks(x); ax[1].set_yticklabels([a[k]["label"] for k in keys], fontsize=7); ax[1].invert_yaxis()
    ax[1].axvline(-1.96, color="k", ls=":", lw=0.8); ax[1].axvline(1.96, color="k", ls=":", lw=0.8); ax[1].set_xlabel("Diebold-Mariano statistic, HAR+IV against HAR (negative favours adding implied vol)"); ax[1].set_title("does implied vol add to the realised history?")
    # encompassing weights
    enc = [(a[k]["label"], a[k].get("encompassing_log_weights", {})) for k in keys]
    lab = [e[0] for e in enc]; wiv = [e[1].get("iv_only", np.nan) for e in enc]; whar = [e[1].get("har", np.nan) for e in enc]
    ax[2].barh(x - 0.2, wiv, 0.4, color="#ff7f0e", label="weight on the implied-only forecast"); ax[2].barh(x + 0.2, whar, 0.4, color="#1f77b4", label="weight on HAR-RV")
    ax[2].set_yticks(x); ax[2].set_yticklabels(lab, fontsize=7); ax[2].invert_yaxis(); ax[2].axvline(0, color="k", lw=0.6); ax[2].set_title("encompassing regression of realised on both forecasts (log)"); ax[2].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "forecast.png")); plt.close(fig)


def fig_vix(vx):
    curve = pd.read_parquet(os.path.join(DER, "vx_curve.parquet")).set_index("date"); led = pd.read_parquet(os.path.join(DER, "vx_roll_ledger.parquet")).set_index("date")
    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    ax[0, 0].plot(curve.index, curve["vix"], color="#333", lw=0.8, label="VIX"); ax[0, 0].plot(curve.index, curve["F1"], color="#1f77b4", lw=0.8, label="front VX"); ax[0, 0].plot(curve.index, curve["F3"], color="#ff7f0e", lw=0.8, label="third VX")
    ax[0, 0].set_title("VIX and the futures curve"); ax[0, 0].legend(fontsize=7)
    r = vx["curve"]["roll_pts_per_30d"]; rm = vx["curve"]["roll_pts_per_30d_median"]
    ax[0, 1].bar(range(len(r)), list(r.values()), color="#1f77b4", alpha=0.6, label="mean"); ax[0, 1].plot(range(len(rm)), list(rm.values()), "ko", label="median")
    ax[0, 1].set_xticks(range(len(r))); ax[0, 1].set_xticklabels(["VIX→F1", "F1→F2", "F2→F3", "F3→F4", "F4→F5"]); ax[0, 1].set_ylabel("index points per 30 days"); ax[0, 1].set_title("roll-down along the curve, 2013–2026"); ax[0, 1].legend(fontsize=7)
    ax[1, 0].plot(led.index, led["cum_gross"], color="#999", label="gross"); ax[1, 0].plot(led.index, led["cum_net"], color="#d62728", label=f"net of bid-ask (Sharpe {vx['roll_strategy']['sharpe']:.2f}, {vx['roll_strategy']['net_pts_per_year']:.1f} pts/yr)")
    ax[1, 0].set_title("short front-month VX, rolled over the last five days, one contract"); ax[1, 0].set_ylabel("cumulative index points"); ax[1, 0].legend(fontsize=7)
    st = vx["states"]; names = [k for k in st if k != "transition"]
    ax[1, 1].bar(np.arange(len(names)) - 0.2, [st[k]["vix_mean"] for k in names], 0.4, color="#333", label="VIX")
    ax[1, 1].bar(np.arange(len(names)) + 0.2, [st[k]["fwd_rv_mean"] for k in names], 0.4, color="#1f77b4", label="realised over the next 21 days")
    for i, k in enumerate(names):
        ax[1, 1].text(i, max(st[k]["vix_mean"], st[k]["fwd_rv_mean"]) + 0.5, f"{st[k]['share_of_days']:.0%} of days", ha="center", fontsize=7)
    ax[1, 1].set_xticks(range(len(names))); ax[1, 1].set_xticklabels(names); ax[1, 1].set_title("index term-structure state (VIX9D / VIX / VIX3M) and what follows"); ax[1, 1].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "vix.png")); plt.close(fig)


def fig_events(ev):
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    fo = ev.get("fomc", {})
    for k, col in (("VIX1D", "#d62728"), ("VIX9D", "#ff7f0e"), ("VIX", "#1f77b4"), ("VXTLT", "#2ca02c")):
        p = fo.get("paths", {}).get(k)
        if p:
            ax[0].plot(p["offsets"], p["mean"], "o-", ms=3, color=col, label=f"{k} (n = {p['n']})")
    ax[0].axvline(0, color="k", lw=0.6); ax[0].axhline(0, color="k", lw=0.6); ax[0].set_xlabel("trading days from the FOMC decision"); ax[0].set_ylabel("change from the day before, vol points"); ax[0].set_title("implied vol into and out of FOMC"); ax[0].legend(fontsize=7)
    p = os.path.join(DER, "events_earnings.parquet")
    if os.path.exists(p):
        e = pd.read_parquet(p).dropna(subset=["stripped_move"])
        ax[1].scatter(e["stripped_move"] * 100, e["abs_real"] * 100, s=6, alpha=0.4, color="#9467bd")
        lim = [0, np.nanpercentile(np.concatenate([e["stripped_move"], e["abs_real"]]) * 100, 99)]
        ax[1].plot(lim, lim, "k:", lw=0.8); ax[1].set_xlim(lim); ax[1].set_ylim(lim); ax[1].set_xlabel("implied move stripped of diffusion, %"); ax[1].set_ylabel("realised |close-to-close| move, %")
        es = ev.get("earnings", {}).get("all", {})
        ax[1].set_title(f"earnings: {len(e)} events, {e['symbol'].nunique()} names; implied {es.get('implied_move_stripped_pct', 0):.1f} % vs realised {es.get('realised_abs_move_pct', 0):.1f} %")
        by = e.groupby("year")[["stripped_move", "abs_real"]].mean() * 100
        ax[2].plot(by.index, by["stripped_move"], "o-", color="#9467bd", label="implied move (stripped)"); ax[2].plot(by.index, by["abs_real"], "s-", color="#333", label="realised |move|")
        rms = e.groupby("year").apply(lambda g: pd.Series({"imp": np.sqrt((g["stripped_move"] ** 2).mean()) * 100, "real": np.sqrt((g["realised_cc"] ** 2).mean()) * 100}), include_groups=False)
        ax[2].plot(rms.index, rms["imp"], "o:", color="#9467bd", alpha=0.6, label="implied, RMS"); ax[2].plot(rms.index, rms["real"], "s:", color="#333", alpha=0.6, label="realised, RMS")
        ax[2].set_title("earnings premium by year (%)"); ax[2].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "events.png")); plt.close(fig)


def fig_crypto(bd, ev, pr):
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    for ccy, col in (("BTC", "#d62728"), ("ETH", "#e377c2")):
        p = os.path.join(DER, f"implied_{ccy}.parquet"); q = os.path.join(DER, f"realised_{ccy}.parquet")
        if not os.path.exists(p):
            continue
        cm = pd.read_parquet(p).set_index("day"); rv = pd.read_parquet(q).set_index("day")
        cm.index = pd.to_datetime(cm.index); rv.index = pd.to_datetime(rv.index)
        ax[0].plot(cm.index, cm["iv30"] * 100, color=col, lw=0.7, label=f"{ccy} 30-day implied (from prints)")
        r30 = np.sqrt(rv["rv"].rolling(30).mean() * 365) * 100
        ax[0].plot(r30.index, r30, color=col, lw=0.7, ls=":", alpha=0.7, label=f"{ccy} 30-day realised (5-min)")
        try:
            dv = data.load_dvol(ccy); ax[0].plot(dv.index, dv, color="k", lw=0.5, alpha=0.5, label=f"{ccy} DVOL" if ccy == "BTC" else None)
        except Exception:  # noqa: BLE001
            pass
    ax[0].set_ylim(0, 200); ax[0].set_title("crypto implied and realised vol (%)"); ax[0].legend(fontsize=6.5)
    cal = ev.get("crypto_calendar", {}).get("BTC", {}).get("realised", {})
    if cal:
        h = cal["by_hour_utc"]; ax[1].bar([int(k) for k in h], [v * 100 for v in h.values()], color="#d62728", alpha=0.7)
        ax[1].set_xlabel("hour, UTC"); ax[1].set_ylabel("annualised vol, %"); ax[1].set_title(f"BTC realised vol by hour of day (5-min); weekend/weekday variance {cal['weekend_to_weekday_var_ratio']:.2f}")
        for hh in (0, 8, 16):
            ax[1].axvline(hh, color="k", ls=":", lw=0.8)
        ax[1].set_ylim(0, max(v * 100 for v in h.values()) * 1.35)
        wk = cal["weekend_ratio_by_year"]
        ins = ax[1].inset_axes([0.42, 0.62, 0.55, 0.33]); ins.plot([int(k) for k in wk], list(wk.values()), "ko-", ms=3); ins.set_ylim(0, 1.0); ins.set_title("weekend / weekday variance by year", fontsize=7); ins.tick_params(labelsize=6); ins.grid(alpha=0.3)
    sk = pr.get("skew", {})
    for name, col in (("BTC", "#d62728"), ("SPY", "#1f77b4")):
        p = os.path.join(DER, f"slices_{name}.parquet")
        if os.path.exists(p):
            sl = pd.read_parquet(p); sl["date"] = pd.to_datetime(sl["date"]); sl = sl[sl["butterfly_ok"] & (sl["n"] >= 8) & (sl["rmse_vol"] < 0.05)]
            ax[2].plot(sl["date"], sl["skew_25"] * 100, color=col, lw=0.6, label=f"{name} 25-delta skew (put minus call), SSR {sk.get(name, {}).get('ssr', {}).get('ssr', float('nan')):.2f}")
    ax[2].axhline(0, color="k", lw=0.6); ax[2].set_ylabel("vol points"); ax[2].set_title("30-day skew from daily SSVI fits"); ax[2].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "crypto.png")); plt.close(fig)


def fig_strategies(st):
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    for name, col, ann in (("spy_straddle", "#1f77b4", 252), ("btc_straddle", "#d62728", 365), ("eth_straddle", "#e377c2", 365), ("spy_calendar", "#2ca02c", 252)):
        p = os.path.join(DER, f"strategy_{name}_daily.parquet")
        if not os.path.exists(p):
            p2 = os.path.join(DER, f"strategy_{name}.parquet")
            if os.path.exists(p2):
                s = pd.read_parquet(p2).sort_values("entry"); ax[0].plot(s["exit"], (s["net"] / s["spot0"]).cumsum() * 100, color=col, drawstyle="steps-post", label=f"{name} (per trade, % of spot)")
            continue
        d = pd.read_parquet(p).groupby("date")[["net", "opt_pnl", "hedge_pnl", "cost"]].sum()
        s = pd.read_parquet(os.path.join(DER, f"strategy_{name}.parquet")); spot = s["spot0"].mean()
        prog = st["spy_straddle"]["unconditional"] if name == "spy_straddle" else st.get(name, {})
        ax[0].plot(d.index, d["net"].cumsum() / spot * 100, color=col, label=f"{name}: {prog.get('return_on_margin_pct', float('nan')):.0f} % on margin, Sharpe {prog.get('daily_sharpe', float('nan')):.2f}")
        ax[0].plot(d.index, (d["opt_pnl"] + d["hedge_pnl"]).cumsum() / spot * 100, color=col, ls=":", lw=0.8)
    ax[0].axhline(0, color="k", lw=0.6); ax[0].set_ylabel("cumulative net P&L, % of average spot (dotted: before costs)"); ax[0].set_title("delta-hedged short straddles, one unit"); ax[0].legend(fontsize=7)
    # per-trade distribution
    for name, col in (("spy_straddle", "#1f77b4"), ("btc_straddle", "#d62728")):
        p = os.path.join(DER, f"strategy_{name}.parquet")
        if os.path.exists(p):
            s = pd.read_parquet(p); ax[1].hist(s["net"] / s["spot0"] * 100, bins=40, alpha=0.5, color=col, label=f"{name}: hit {float((s['net'] > 0).mean()):.0%}, worst {float((s['net'] / s['spot0']).min() * 100):.1f} %")
    ax[1].axvline(0, color="k", lw=0.6); ax[1].set_xlabel("net P&L per trade, % of spot"); ax[1].set_title("the seller's distribution"); ax[1].legend(fontsize=7)
    # summary bars: return on margin gross vs net across programs
    progs = [(k, v) for k, v in st.items() if isinstance(v, dict) and "return_on_margin_pct" in v and v.get("n_trades", 0) > 0]
    progs += [("spy_straddle", st["spy_straddle"]["unconditional"])] if "spy_straddle" in st and "unconditional" in st["spy_straddle"] else []
    progs += [(f"spy_straddle_{c}", st["spy_straddle"][c]) for c in ("contango", "backwardation") if "spy_straddle" in st and c in st["spy_straddle"] and st["spy_straddle"][c].get("n_trades", 0) > 0]
    names = [p[0] for p in progs]; x = np.arange(len(names))
    ax[2].bar(x - 0.2, [p[1]["gross_per_year"] / p[1]["avg_margin"] * 100 if p[1]["avg_margin"] else np.nan for p in progs], 0.4, color="#999", label="gross")
    ax[2].bar(x + 0.2, [p[1]["return_on_margin_pct"] for p in progs], 0.4, color="#d62728", label="net of spread and hedging")
    ax[2].set_xticks(x); ax[2].set_xticklabels(names, rotation=35, ha="right", fontsize=7); ax[2].set_ylabel("% per year on average scenario margin"); ax[2].axhline(0, color="k", lw=0.6); ax[2].set_title("return on margin by program"); ax[2].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "strategies.png")); plt.close(fig)


def main():
    pr, fc, vx, ev, st, bd = (load(n) for n in ("premia.json", "forecast.json", "vix.json", "events.json", "strategies.json", "build.json"))
    if pr:
        fig_premia(pr)
    if fc:
        fig_forecast(fc)
    if vx:
        fig_vix(vx)
    if ev:
        fig_events(ev)
    if bd and ev and pr:
        fig_crypto(bd, ev, pr)
    if st:
        fig_strategies(st)
    print("figures ->", FIG)


if __name__ == "__main__":
    main()
