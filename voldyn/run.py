"""Pipeline.   python -m voldyn <step> [--quick]      steps: build | forecast | premia | events | vix | strategies | all

build       realised measures (US daily estimators, crypto 5-minute RV and jumps), the crypto implied term structure from
            every print, SSVI slices per day (BTC from prints, SPY from the chains)      -> data/derived/*.parquet, results/build.json
forecast    HAR / HAR-IV / GARCH / random walk walk-forward per asset, QLIKE, DM tests    -> results/forecast.json
premia      the variance risk premium by asset and tenor with block-bootstrap intervals, regimes, skew stickiness
                                                                                        -> results/premia.json
events      earnings (implied against realised move, seller P&L) and FOMC                -> results/events.json, data/derived/events_earnings.parquet
vix         term-structure states, VX curve and roll-down, the roll strategy, VVIX        -> results/vix.json, data/derived/vx_curve.parquet
strategies  SPY straddles (unconditional, contango, stop-loss walk-forward), SPY calendars, BTC straddles
                                                                                        -> results/strategies.json, data/derived/strategy_*.parquet"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from . import chains, crypto, data, events, forecast, premia, realised, strategies, vix
from .data import DER, RES
from .surface import fit_slice

QUICK = False


def save_json(obj, name):
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, default=_default)


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, (pd.Timestamp,)):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def load_json(name):
    with open(os.path.join(RES, name), encoding="utf-8") as f:
        return json.load(f)


# ---- build ---------------------------------------------------------------------------------------------------------------------------
def slices_from_prints(currency: str, months: list, min_strikes: int = 6) -> pd.DataFrame:
    """per UTC day, SSVI fit of the expiry nearest 30 days from the day's prints: median IV per strike within |k| < 0.6"""
    tr = data.load_trades(currency, months, ["timestamp", "instrument_name", "iv", "index_price", "amount"])
    if tr.empty:
        return pd.DataFrame()
    tr = data.add_instrument_columns(tr)
    tr = tr[(tr["iv"] > 1) & (tr["iv"] < 500) & (tr["T"] > 3 / 365) & (tr["T"] < 0.4)].copy()
    tr["day"] = pd.to_datetime(tr["timestamp"], unit="ms", utc=True).dt.tz_convert(None).dt.normalize()
    tr["k"] = np.log(tr["strike"] / tr["index_price"])
    tr = tr[tr["k"].abs() < 0.6]
    rows = []
    for d, g in tr.groupby("day"):
        g = g.copy(); g["dist"] = (g["T"] - 30 / 365).abs()
        # the expiry nearest 30 days with enough strikes
        best = None
        for e, ge in g.groupby("expiry_ms"):
            if ge["strike"].nunique() >= min_strikes and (best is None or ge["dist"].iloc[0] < best[1]):
                best = (e, ge["dist"].iloc[0], ge)
        if best is None:
            continue
        ge = best[2]; F = float(ge["index_price"].median()); T = float(ge["T"].median())
        per_k = ge.groupby("strike")["iv"].median() / 100.0
        sl = fit_slice(per_k.index.values, per_k.values, T, F)
        if sl is None:
            continue
        rows.append({"date": d, "T": T, "F": F, "theta": sl.theta, "rho": sl.rho, "psi": sl.psi, "n": sl.n, "rmse_vol": sl.rmse_vol, "atm_vol": sl.atm_vol(), "skew_25": sl.skew_25(), "butterfly_ok": sl.butterfly_ok})
    return pd.DataFrame(rows)


def slices_from_chains(symbol: str, min_strikes: int = 6) -> pd.DataFrame:
    """per chain date, SSVI fit of the expiry nearest 30 days: forward and discount from parity, vols from the mids on
    that forward, out-of-the-money side of each strike"""
    ch = data.load_chains(symbol); px = data.load_prices(); px = px[px["symbol"] == symbol].set_index("date")["close"]; rates = data.load_rates()
    rows = []
    for d, g in ch.groupby("date"):
        spot = px.loc[:d]
        if spot.empty:
            continue
        S = float(spot.iloc[-1]); r0 = float(rates.loc[:d].iloc[-1]) if len(rates.loc[:d]) else 0.0
        g = g[(g["mid"] > 0) & (g["T"] > 3 / 365)].copy(); g["dist"] = (g["T"] - 30 / 365).abs()
        for e, ge in sorted(g.groupby("expiration"), key=lambda kv: kv[1]["dist"].iloc[0]):
            T = float(ge["T"].iloc[0]); F, df, how = chains.expiry_forward(ge, S, T, r0)
            ge = chains.with_vols(ge, F, df)
            ge = ge[((ge["cp"] > 0) & (ge["strike"] >= F)) | ((ge["cp"] < 0) & (ge["strike"] < F))]
            ge = ge[(ge["iv"] > 0.02) & (ge["iv"] < 3) & (ge["spread"] / ge["mid"] < 1.0)]
            if ge["strike"].nunique() < min_strikes:
                continue
            sl = fit_slice(ge["strike"].values, ge["iv"].values, T, F)
            if sl is not None:
                rows.append({"date": d, "T": T, "F": F, "df": df, "fwd_how": how, "theta": sl.theta, "rho": sl.rho, "psi": sl.psi, "n": sl.n, "rmse_vol": sl.rmse_vol, "atm_vol": sl.atm_vol(), "skew_25": sl.skew_25(), "butterfly_ok": sl.butterfly_ok})
            break
    return pd.DataFrame(rows)


def step_build() -> dict:
    t = time.time(); os.makedirs(DER, exist_ok=True); out = {}
    # US realised measures per underlying
    us = []
    for iv_name, (under, proxy, cls, label) in data.IV_MAP.items():
        if iv_name.startswith("DVOL"):
            continue
        try:
            o = data.ohlc(under)
        except Exception:  # noqa: BLE001
            continue
        d = realised.daily_estimators(o); d["yz21"] = realised.yang_zhang(o); d["symbol"] = under
        us.append(d.reset_index())
    us = pd.concat(us, ignore_index=True); us.to_parquet(os.path.join(DER, "realised_us.parquet"))
    out["us_realised"] = {"symbols": sorted(us["symbol"].unique()), "rows": int(len(us))}
    est = us.dropna().groupby("symbol")[["cc", "park", "gk", "rs", "yz21"]].mean()
    out["estimator_ratio_to_cc"] = (est.div(est["cc"], axis=0)).round(3).to_dict()
    # crypto
    cr = {}
    for ccy in ("BTC", "ETH"):
        if not data.trade_files(ccy):
            continue
        rv = crypto.realised_daily(ccy); rv["ccy"] = ccy; rv.reset_index().to_parquet(os.path.join(DER, f"realised_{ccy}.parquet"))
        cm, atm = crypto.implied_from_trades(ccy); cm.reset_index().to_parquet(os.path.join(DER, f"implied_{ccy}.parquet")); atm.to_parquet(os.path.join(DER, f"atm_by_expiry_{ccy}.parquet"))
        dv = data.load_dvol(ccy)
        cr[ccy] = {"days_realised": int(len(rv)), "jump_share_5pct": float(rv["jump"].mean()), "jump_share_1pct": float((rv["z_bns"] > 2.326).mean()), "jv_share_of_rv": float(rv["jv"].sum() / rv["rv"].sum()),
                   "ann_vol_rv": float(np.sqrt(rv["rv"].mean() * 365)), "ann_vol_cc": float(np.sqrt(rv["cc"].mean() * 365)), "days_implied": int(len(cm)), "implied_first": str(cm.index[0].date()), "implied_last": str(cm.index[-1].date()),
                   "prints_used": int(atm["n"].sum()), "dvol_check": crypto.compare_with_dvol(cm, dv)}
        months = sorted(f[-14:-8] for f in data.trade_files(ccy))
        if QUICK:
            months = months[-12:]
        sl = pd.concat([slices_from_prints(ccy, months[i:i + 6]) for i in range(0, len(months), 6)], ignore_index=True)
        sl.to_parquet(os.path.join(DER, f"slices_{ccy}.parquet"))
        cr[ccy]["slices"] = {"n_days": int(len(sl)), "rmse_vol_points_median": float(sl["rmse_vol"].median() * 100), "butterfly_ok_share": float(sl["butterfly_ok"].mean()), "atm_vol_mean": float(sl["atm_vol"].mean()), "skew_25_mean": float(sl["skew_25"].mean())}
    out["crypto"] = cr
    # SPY slices
    if "SPY" in data.chain_symbols():
        sl = slices_from_chains("SPY"); sl.to_parquet(os.path.join(DER, "slices_SPY.parquet"))
        out["spy_slices"] = {"n_days": int(len(sl)), "rmse_vol_points_median": float(sl["rmse_vol"].median() * 100), "butterfly_ok_share": float(sl["butterfly_ok"].mean()), "atm_vol_mean": float(sl["atm_vol"].mean()), "skew_25_mean": float(sl["skew_25"].mean()), "first": str(sl["date"].min().date()), "last": str(sl["date"].max().date())}
    out["seconds"] = round(time.time() - t)
    save_json(out, "build.json"); print("build:", json.dumps({k: v for k, v in out.items() if k in ("us_realised", "spy_slices", "seconds")}, default=_default)[:400])
    return out


# ---- forecast ----------------------------------------------------------------------------------------------------------------------
def step_forecast() -> dict:
    t = time.time(); cb = data.load_cboe_all(); us = pd.read_parquet(os.path.join(DER, "realised_us.parquet"))
    out = {"horizon_days": 21, "window": 1000, "refit_every": 21, "assets": {}}
    names = [k for k in data.IV_MAP if not k.startswith("DVOLX")] if not QUICK else ["VIX", "VXN", "GVZ", "DVOL_BTC"]
    for iv_name in names:
        under = data.IV_MAP[iv_name][0]
        if iv_name.startswith("DVOL"):
            ccy = iv_name.split("_")[1]; p = os.path.join(DER, f"realised_{ccy}.parquet")
            if not os.path.exists(p):
                continue
            rv = pd.read_parquet(p).set_index("day"); rv.index = pd.to_datetime(rv.index)
            cm = pd.read_parquet(os.path.join(DER, f"implied_{ccy}.parquet")).set_index("day"); cm.index = pd.to_datetime(cm.index)
            iv = cm["iv30"] * 100; series = rv["rv"]; ret = rv["ret"]; ann = 365; h = 30; window = 730
        else:
            if iv_name not in cb:
                continue
            g = us[us["symbol"] == under].set_index("date"); series = g["cc"].dropna(); ret = g["ret"]; iv = cb[iv_name]; ann = 252; h = 21; window = 1000
        fc = forecast.rolling_forecasts(series, iv, ret, h=h, ann=ann, window=window, step=21)
        if fc.empty:
            continue
        sc = forecast.score(fc, h); sc.update({"underlying": under, "label": data.IV_MAP[iv_name][3], "first": str(fc.index[0].date()), "last": str(fc.index[-1].date())})
        # by year QLIKE for har and har_iv
        if "har_iv" in fc:
            c = fc.dropna(subset=["har", "har_iv", "y_real"])
            sc["qlike_by_year"] = {int(y): {"har": float(forecast.qlike(g["har"].values, g["y_real"].values).mean()), "har_iv": float(forecast.qlike(g["har_iv"].values, g["y_real"].values).mean())} for y, g in c.groupby(c.index.year)}
        out["assets"][iv_name] = sc
        fc.reset_index().rename(columns={"index": "date"}).to_parquet(os.path.join(DER, f"forecast_{iv_name}.parquet"))
        print(f"  forecast {iv_name}: n {sc['n']}, QLIKE har {sc['models']['har']['qlike']:.3f}" + (f", har_iv {sc['models']['har_iv']['qlike']:.3f} (DM p {sc['models']['har_iv']['dm_vs_har_qlike']['p']:.3f})" if "har_iv" in sc["models"] else ""), flush=True)
    out["seconds"] = round(time.time() - t); save_json(out, "forecast.json"); return out


# ---- premia -------------------------------------------------------------------------------------------------------------------------
def step_premia() -> dict:
    t = time.time(); B = 300 if QUICK else 2000
    cb = data.load_cboe_all(); prices = data.price_panel("adjclose")
    dvol = {}
    for ccy in ("BTC", "ETH"):
        p = os.path.join(DER, f"realised_{ccy}.parquet")
        if os.path.exists(p):
            rv = pd.read_parquet(p).set_index("day"); rv.index = pd.to_datetime(rv.index)
            cm = pd.read_parquet(os.path.join(DER, f"implied_{ccy}.parquet")).set_index("day"); cm.index = pd.to_datetime(cm.index)
            dvol[ccy] = {"iv": cm["iv30"] * 100, "ret": rv["ret"]}
    out = {"cross_asset": premia.cross_asset(prices, cb, dvol, h=21, B=B)}
    ret = np.log(prices["^GSPC"]).diff().dropna()
    out["spx_by_tenor"] = premia.term_structure_premia(cb, ret, B=B)
    # crypto by tenor from the print-implied term structure (7 / 30 / 60 / 90 against 7 / 30 / 60 / 90 calendar days)
    out["crypto_by_tenor"] = {}
    for ccy, d in dvol.items():
        cm = pd.read_parquet(os.path.join(DER, f"implied_{ccy}.parquet")).set_index("day"); cm.index = pd.to_datetime(cm.index)
        rv = pd.read_parquet(os.path.join(DER, f"realised_{ccy}.parquet")).set_index("day"); rv.index = pd.to_datetime(rv.index)
        out["crypto_by_tenor"][ccy] = {}
        for tn in (7, 30, 60, 90):
            df = premia.vrp_series(cm[f"iv{tn}"] * 100, rv["ret"], tn, 365)
            if len(df) > 300:
                out["crypto_by_tenor"][ccy][tn] = premia.summarise_vrp(df, tn, B)
        # also with 5-minute RV as the realised leg (the cleaner measure) at 30 days
        rv5 = rv["rv"]; fwd = rv5[::-1].rolling(30).mean()[::-1].shift(-1) * 365
        df = pd.DataFrame({"iv2": (cm["iv30"]) ** 2, "rv2": fwd}).dropna(); df["vrp"] = df["iv2"] - df["rv2"]; df["gap_vol"] = np.sqrt(df["iv2"]) - np.sqrt(df["rv2"]); df["log_ratio"] = np.log(df["iv2"] / df["rv2"])
        out["crypto_by_tenor"][ccy]["30_rv5min"] = premia.summarise_vrp(df, 30, B)
        # DVOL as the implied leg (Deribit's variance-swap-style 30-day index, 2021 on) against the same realised
        dvs = data.load_dvol(ccy)
        d2 = premia.vrp_series(dvs, rv["ret"], 30, 365)
        if len(d2) > 300:
            out["crypto_by_tenor"][ccy]["30_dvol"] = premia.summarise_vrp(d2, 30, B)
            # and the print-implied ATM over the same window, for the like-for-like comparison
            d3 = premia.vrp_series((cm["iv30"] * 100)[cm.index >= dvs.index[0]], rv["ret"], 30, 365)
            out["crypto_by_tenor"][ccy]["30_atm_since_2021"] = premia.summarise_vrp(d3, 30, B)
    # regimes for the S&P
    ts = vix.term_structure(cb)
    df = premia.vrp_series(cb["VIX"], ret, 21, 252)
    out["spx_conditional"] = premia.conditional(df, cb["VIX"], ts["slope_long"] if "slope_long" in ts else None, 21, B=min(B, 1000))
    # skew stickiness
    out["skew"] = {}
    for name in ("BTC", "SPY"):
        p = os.path.join(DER, f"slices_{name}.parquet")
        if os.path.exists(p):
            sl = pd.read_parquet(p); sl["date"] = pd.to_datetime(sl["date"])
            sl = sl[sl["butterfly_ok"] & (sl["rmse_vol"] < 0.05)]
            if len(sl) > 100:
                from .surface import ssvi
                def surf_iv(row, K):
                    k = np.log(K / row["F"]); return float(np.sqrt(max(ssvi.ssvi_w(k, row["theta"], row["rho"], row["psi"]), 1e-12) / row["T"]))
                out["skew"][name] = {"ssr": premia.skew_stickiness(sl), "sticky": premia.sticky_test(sl, surf_iv), "n_slices": int(len(sl)), "skew_25_mean_pts": float(sl["skew_25"].mean() * 100), "skew_25_sd_pts": float(sl["skew_25"].std() * 100)}
    # the single-name cross-section from the vendor table
    names = sorted(os.path.basename(p)[8:-6] for p in __import__("glob").glob(os.path.join(data.RAW, "dolt", "volhist_*.jsonl")))
    if names:
        out["single_names"] = premia.single_name_panel([n for n in names if n not in ("SPY", "XLF")], prices, 21, B=min(B, 500))
    out["seconds"] = round(time.time() - t); save_json(out, "premia.json")
    print("premia:", {k: round(v["gap_vol_mean_pts"], 2) for k, v in out["cross_asset"].items()})
    return out


# ---- events -------------------------------------------------------------------------------------------------------------------------
def step_events() -> dict:
    t = time.time(); cb = data.load_cboe_all(); prices = data.load_prices(); fomc = data.load_fomc()
    out = {}
    fo, fdf = events.fomc_study(cb, prices, fomc); out["fomc"] = fo; fdf.to_parquet(os.path.join(DER, "events_fomc.parquet"))
    syms = [s for s in data.chain_symbols() if s != "SPY"]
    if syms:
        ed = events.earnings_study(syms)
        if not ed.empty:
            ed.to_parquet(os.path.join(DER, "events_earnings.parquet")); out["earnings"] = events.earnings_summary(ed)
            print(f"  earnings: {len(ed)} events, {ed['symbol'].nunique()} names; implied (stripped) {out['earnings']['all']['implied_move_stripped_pct']:.2f} % vs realised {out['earnings']['all']['realised_abs_move_pct']:.2f} %")
    # crypto calendar effects
    out["crypto_calendar"] = {}
    for ccy in ("BTC", "ETH"):
        p = os.path.join(DER, f"implied_{ccy}.parquet")
        if os.path.exists(p):
            cm = pd.read_parquet(p).set_index("day"); cm.index = pd.to_datetime(cm.index)
            out["crypto_calendar"][ccy] = {"realised": crypto.calendar_effects(ccy), "implied_weekend": crypto.implied_weekend(cm)}
    out["seconds"] = round(time.time() - t); save_json(out, "events.json"); return out


# ---- vix -----------------------------------------------------------------------------------------------------------------------------
def step_vix() -> dict:
    t = time.time(); cb = data.load_cboe_all(); vx = data.load_vx(); prices = data.price_panel("adjclose")
    ret = np.log(prices["^GSPC"]).diff().dropna()
    ts = vix.term_structure(cb); curve = vix.vx_curve(vx, cb["VIX"]); led = vix.roll_strategy(vx, curve)
    curve.reset_index().to_parquet(os.path.join(DER, "vx_curve.parquet")); led.reset_index().to_parquet(os.path.join(DER, "vx_roll_ledger.parquet")); ts.reset_index().rename(columns={"index": "date", "DATE": "date"}).to_parquet(os.path.join(DER, "vix_term.parquet"))
    out = {"states": vix.state_stats(ts.dropna(subset=["state"]), ret), "curve": {"n_days": int(len(curve)), "first": str(curve.index[0].date()), "last": str(curve.index[-1].date()), "share_contango_1_2": float(curve["contango_1_2"].mean()),
           "roll_pts_per_30d": {k: float(curve[k].mean()) for k in ("roll_0", "roll_1", "roll_2", "roll_3", "roll_4") if k in curve}, "roll_pts_per_30d_median": {k: float(curve[k].median()) for k in ("roll_0", "roll_1", "roll_2", "roll_3", "roll_4") if k in curve},
           "roll_1_by_year": {int(y): float(g["roll_1"].mean()) for y, g in curve.groupby(curve.index.year)}},
           "roll_strategy": vix.roll_summary(led, curve), "vvix": vix.vvix_analysis(cb, ts, curve)}
    out["seconds"] = round(time.time() - t); save_json(out, "vix.json"); print("vix:", {k: round(v, 2) for k, v in out["roll_strategy"].items() if isinstance(v, float)}); return out


# ---- strategies ---------------------------------------------------------------------------------------------------------------------
def step_strategies() -> dict:
    t = time.time(); cb = data.load_cboe_all(); prices = data.load_prices(); out = {}
    if "SPY" in data.chain_symbols():
        ch = data.load_chains("SPY"); px = prices[prices["symbol"] == "SPY"].set_index("date").sort_index(); rates = data.load_rates()
        # walk-forward stop-loss: candidates on the first half of the entries, the chosen one reported on the second
        entries = strategies.spy_entries(ch, px); split = entries[len(entries) // 2][0] if entries else pd.Timestamp("2023-01-01")
        by_stop = {}
        for sl in (None, 0.5, 1.0, 2.0):
            trs = strategies.run_spy_straddles(ch, px, cb, stop_loss_frac=sl, condition="all", rates=rates)
            by_stop["none" if sl is None else f"stop_{sl}x_premium"] = trs
        out["spy_straddle"] = {"unconditional": strategies.program_summary(by_stop["none"], 252), "stop_loss_walk_forward": strategies.choose_stop(by_stop, split)}
        for cond in ("contango", "backwardation"):
            trs = strategies.run_spy_straddles(ch, px, cb, condition=cond, rates=rates); out["spy_straddle"][cond] = strategies.program_summary(trs, 252)
        out["spy_straddle"]["no_hedge_cost"] = strategies.program_summary(strategies.run_spy_straddles(ch, px, cb, condition="all", rates=rates, hedge_bp=0.0), 252)
        pd.DataFrame([x.summary for x in by_stop["none"]]).to_parquet(os.path.join(DER, "strategy_spy_straddle.parquet"))
        pd.concat([x.rows.assign(entry=x.entry) for x in by_stop["none"]]).reset_index().to_parquet(os.path.join(DER, "strategy_spy_straddle_daily.parquet"))
        cal = strategies.run_spy_calendars(ch, px, rates); out["spy_calendar"] = strategies.program_summary(cal, 252)
        if cal:
            pd.DataFrame([x.summary for x in cal]).to_parquet(os.path.join(DER, "strategy_spy_calendar.parquet"))
        print(f"  spy straddle: {out['spy_straddle']['unconditional'].get('n_trades')} trades, net/trade {out['spy_straddle']['unconditional'].get('net_per_trade_pct_spot', float('nan')):.2f} % of spot, RoM {out['spy_straddle']['unconditional'].get('return_on_margin_pct', float('nan')):.1f} %")
    for ccy in ("BTC", "ETH"):
        p = os.path.join(DER, f"implied_{ccy}.parquet")
        if not os.path.exists(p):
            continue
        cm = pd.read_parquet(p).set_index("day"); cm.index = pd.to_datetime(cm.index)
        idx = crypto.daily_index(ccy)
        cm = cm[cm.index >= idx.index[0]]
        trs = strategies.run_btc_straddles(cm, idx)
        out[f"{ccy.lower()}_straddle"] = strategies.program_summary(trs, 365)
        # conditioned on the term structure: only when iv60 > iv30 (upward sloping)
        slope = (cm["iv60"] - cm["iv30"])
        cond_trs = [x for x in trs if slope.get(x.entry, np.nan) > 0]; out[f"{ccy.lower()}_straddle_contango"] = strategies.program_summary(cond_trs, 365)
        cond_trs = [x for x in trs if slope.get(x.entry, np.nan) <= 0]; out[f"{ccy.lower()}_straddle_backwardation"] = strategies.program_summary(cond_trs, 365)
        # costless version
        out[f"{ccy.lower()}_straddle_costless"] = strategies.program_summary(strategies.run_btc_straddles(cm, idx, half_spread_vol=0.0), 365) if not QUICK else {}
        pd.DataFrame([x.summary for x in trs]).to_parquet(os.path.join(DER, f"strategy_{ccy.lower()}_straddle.parquet"))
        pd.concat([x.rows.assign(entry=x.entry) for x in trs]).reset_index().to_parquet(os.path.join(DER, f"strategy_{ccy.lower()}_straddle_daily.parquet"))
        print(f"  {ccy} straddle: {out[f'{ccy.lower()}_straddle']['n_trades']} trades, net/trade {out[f'{ccy.lower()}_straddle']['net_per_trade_pct_spot']:.2f} % of spot, RoM {out[f'{ccy.lower()}_straddle']['return_on_margin_pct']:.1f} %")
    out["seconds"] = round(time.time() - t); save_json(out, "strategies.json"); return out


def main(argv=None):
    global QUICK
    ap = argparse.ArgumentParser(); ap.add_argument("step", choices=["build", "forecast", "premia", "events", "vix", "strategies", "all"]); ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv); QUICK = a.quick
    steps = ["build", "forecast", "premia", "events", "vix", "strategies"] if a.step == "all" else [a.step]
    for s in steps:
        globals()[f"step_{s}"]()


if __name__ == "__main__":
    main()
