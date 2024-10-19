#!/usr/bin/env python3
"""results/*.json -> results/summary.md"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")


def load(name):
    p = os.path.join(RES, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def f(x, d=2):
    return "-" if x is None or (isinstance(x, float) and x != x) else (f"{x:.{d}f}" if isinstance(x, (int, float)) else str(x))


def ci(v, d=2):
    return f"[{f(v[0], d)}, {f(v[1], d)}]" if v and v[0] is not None else "-"


def main():
    bd, fc, pr, ev, vx, st = (load(n) for n in ("build.json", "forecast.json", "premia.json", "events.json", "vix.json", "strategies.json"))
    L = ["# Results summary\n", "Generated from `results/*.json` by `scripts/summarize.py`.\n"]
    # data
    if bd:
        L.append("## Data built\n")
        cr = bd.get("crypto", {})
        for c, v in cr.items():
            dc = v.get("dvol_check", {})
            L.append(f"- {c}: {v['prints_used']:,} near-the-money prints into {v['days_implied']:,} days of implied term structure ({v['implied_first']} to {v['implied_last']}); {v['days_realised']:,} days of 5-minute realised variance, annualised {v['ann_vol_rv'] * 100:.0f} % (close-to-close {v['ann_vol_cc'] * 100:.0f} %); BNS jump days {v['jump_share_5pct']:.0%} at 5 %, {v['jump_share_1pct']:.0%} at 1 %, jump variation {v['jv_share_of_rv']:.0%} of RV; 30-day print-implied against DVOL: corr {f(dc.get('corr'), 3)}, mean gap {f(dc.get('mean_diff_pts'))} pts on {dc.get('n', 0):,} days; SSVI slices {v.get('slices', {}).get('n_days', 0):,} days, median RMSE {f(v.get('slices', {}).get('rmse_vol_points_median'))} vol points, butterfly-free {f(v.get('slices', {}).get('butterfly_ok_share', 0) * 100, 0)} %.")
        if "spy_slices" in bd:
            s = bd["spy_slices"]; L.append(f"- SPY: {s['n_days']:,} daily SSVI slices ({s['first']} to {s['last']}), median RMSE {f(s['rmse_vol_points_median'])} vol points, butterfly-free {f(s['butterfly_ok_share'] * 100, 0)} %, mean 25-delta skew {f(s['skew_25_mean'] * 100, 1)} points.")
        L.append(f"- US daily estimators for {len(bd['us_realised']['symbols'])} underlyings, {bd['us_realised']['rows']:,} rows; mean ratio of each estimator to close-to-close: " + ", ".join(f"{k} {f(sum(v.values()) / len(v), 3)}" for k, v in bd["estimator_ratio_to_cc"].items() if k != "cc") + ".\n")
    # premia
    if pr:
        L.append("## The variance risk premium\n")
        L.append("30-day premium by asset: implied (the Cboe index or, for crypto, the print-implied 30-day vol) against the vol realised over the following 21 trading days (30 calendar days for crypto). Intervals are circular block bootstraps with the horizon as block length. Slope: realised variance regressed on implied variance (Newey-West s.e.).\n")
        L.append("| implied index | underlying | class | from | to | n days | mean implied | mean realised | gap (vol pts) | 95 % CI | share positive | RV-on-IV slope (s.e.) |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for k, v in sorted(pr["cross_asset"].items(), key=lambda kv: -kv[1]["gap_vol_mean_pts"]):
            L.append(f"| {k} | {v['label']} | {v['asset_class']} | {v['start'][:4]} | {v['end'][:4]} | {v['n']:,} | {f(v['iv_mean_vol'] * 100, 1)} | {f(v['rv_mean_vol'] * 100, 1)} | {f(v['gap_vol_mean_pts'])} | {ci(v['gap_vol_ci_pts'])} | {f(v['share_positive'] * 100, 0)} % | {f(v['rv_on_iv']['slope'])} ({f(v['rv_on_iv']['slope_se_nw'])}) |")
        L.append("")
        if pr.get("spx_by_tenor"):
            L.append("S&P 500 premium by tenor (VIX family):\n")
            L.append("| index | tenor (days) | n | implied | realised | gap (vol pts) | 95 % CI | share positive |")
            L.append("|---|---|---|---|---|---|---|---|")
            for k, v in sorted(pr["spx_by_tenor"].items(), key=lambda kv: kv[1]["tenor_calendar_days"]):
                L.append(f"| {k} | {v['tenor_calendar_days']} | {v['n']:,} | {f(v['iv_mean_vol'] * 100, 1)} | {f(v['rv_mean_vol'] * 100, 1)} | {f(v['gap_vol_mean_pts'])} | {ci(v['gap_vol_ci_pts'])} | {f(v['share_positive'] * 100, 0)} % |")
            L.append("")
        for ccy, ct in pr.get("crypto_by_tenor", {}).items():
            L.append(f"{ccy} premium by tenor (print-implied term structure; the last row uses 5-minute realised variance as the realised leg):\n")
            L.append("| tenor | n | implied | realised | gap (vol pts) | 95 % CI | share positive |")
            L.append("|---|---|---|---|---|---|---|")
            for k, v in ct.items():
                L.append(f"| {k} | {v['n']:,} | {f(v['iv_mean_vol'] * 100, 1)} | {f(v['rv_mean_vol'] * 100, 1)} | {f(v['gap_vol_mean_pts'])} | {ci(v['gap_vol_ci_pts'])} | {f(v['share_positive'] * 100, 0)} % |")
            L.append("")
        c = pr.get("spx_conditional", {})
        if c:
            L.append("S&P premium by regime (VIX terciles, then by the sign of VIX3M minus VIX on the day):\n")
            L.append("| regime | n | mean VIX | gap (vol pts) | VRP (var pts) | 95 % CI | share positive |")
            L.append("|---|---|---|---|---|---|---|")
            for k, v in c["by_level"].items():
                L.append(f"| VIX {k} | {v['n']:,} | {f(v['level_mean'], 1)} | {f(v['gap_vol_pts'])} | {f(v['vrp_varpts'], 0)} | {ci(v['ci'], 0)} | {f(v['share_positive'] * 100, 0)} % |")
            for k, v in c.get("by_slope", {}).items():
                L.append(f"| {k} | {v['n']:,} | - | {f(v['gap_vol_pts'])} | {f(v['vrp_varpts'], 0)} | {ci(v['ci'], 0)} | {f(v['share_positive'] * 100, 0)} % |")
            L.append("")
        sk = pr.get("skew", {})
        if sk:
            L.append("Skew dynamics from daily SSVI fits of the expiry nearest 30 days:\n")
            L.append("| surface | slices | mean 25-delta skew (pts) | SSR (s.e.) | R² | mean |change| at fixed strike | at fixed moneyness | on large moves: strike / moneyness | verdict |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            for k, v in sk.items():
                s, t = v["ssr"], v["sticky"]
                L.append(f"| {k} | {v['n_slices']:,} | {f(v['skew_25_mean_pts'], 1)} | {f(s['ssr'])} ({f(s['ssr_se'])}) | {f(s['r2'])} | {f(t['mean_abs_change_fixed_strike'] * 100)} | {f(t['mean_abs_change_fixed_moneyness'] * 100)} | {f(t['large_moves']['fixed_strike'] * 100)} / {f(t['large_moves']['fixed_moneyness'] * 100)} | {t['verdict']} |")
            L.append("")
    # forecast
    if fc:
        L.append("## Forecasting realised variance\n")
        L.append(f"Walk-forward, refit every {fc['refit_every']} days on the trailing window, horizon 21 trading days (30 for crypto). QLIKE and the RMSE of the forecast vol (daily units x 1e4); DM: Diebold-Mariano of HAR+IV against HAR on QLIKE (negative favours adding implied vol); encompassing weights from a log regression of realised on the implied-only and HAR forecasts.\n")
        L.append("| asset | n | RW QLIKE | GARCH | HAR | HAR+IV | IV only | DM (p) | weight IV / HAR | HAR+IV RMSE vs HAR |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for k, v in fc["assets"].items():
            m = v["models"]; hi = m.get("har_iv", {}); dm = hi.get("dm_vs_har_qlike", {}); enc = v.get("encompassing_log_weights", {})
            L.append(f"| {v['label']} | {v['n']:,} | {f(m.get('rw', {}).get('qlike'))} | {f(m.get('garch', {}).get('qlike'))} | {f(m['har']['qlike'])} | {f(hi.get('qlike'))} | {f(m.get('iv_only', {}).get('qlike'))} | {f(dm.get('dm'), 1)} ({f(dm.get('p'), 3)}) | {f(enc.get('iv_only'))} / {f(enc.get('har'))} | {f(hi.get('rmse_vol_daily', 0) * 1e4, 1)} vs {f(m['har']['rmse_vol_daily'] * 1e4, 1)} |")
        L.append("")
    # events
    if ev:
        L.append("## Events\n")
        fo = ev.get("fomc", {})
        if fo:
            L.append(f"FOMC ({fo['n_events']} decision days, 2019-2026): S&P |move| {f(fo['spx_abs_move_fomc_pct'])} % against {f(fo['spx_abs_move_other_pct'])} % on other days; RMS move over implied daily move (VIX / sqrt(252) the day before) {f(fo['ratio_realised_to_implied_rms_fomc'])} on FOMC days against {f(fo['ratio_realised_to_implied_rms_other'])} otherwise; TLT |move| {f(fo['tlt_abs_move_fomc_pct'])} % vs {f(fo['tlt_abs_move_other_pct'])} %, RMS over VXTLT-implied {f(fo['tlt_rms_to_implied_fomc'])}. VIX change on the day {f(fo['vix_change_on_day'])} pts (down on {f(fo['share_vix_down_on_day'] * 100, 0)} % of days), VIX9D from the day before to the day after {f(fo['vix9d_crush_before_to_after'])} pts." + (f" VIX1D ({fo['vix1d']['n']} events since 2022): implied daily move {f(fo['vix1d']['implied_daily_from_vix1d_pct'])} %, realised RMS {f(fo['vix1d']['rms_realised_pct'])} %, ratio {f(fo['vix1d']['ratio_realised_to_vix1d'])}." if "vix1d" in fo else "") + "\n")
        ea = ev.get("earnings", {})
        if ea:
            a = ea["all"]
            L.append(f"Earnings ({a['n']:,} events): implied move from the front straddle by the 0.8 x straddle rule {f(a['implied_move_rule_pct'])} %, stripped of the diffusion {f(a['implied_move_stripped_pct'])} %; realised |close-to-close| {f(a['realised_abs_move_pct'])} % (RMS implied {f(a['rms_implied_pct'])} vs RMS realised {f(a['rms_realised_pct'])}); implied above realised on {f(a['share_implied_above_realised'] * 100, 0)} % of events, median ratio {f(a['median_ratio_stripped'])}; Spearman(implied, |realised|) {f(ea['spearman_implied_vs_abs_realised'])}; realised² on implied² slope {f(ea['realised_sq_on_implied_sq']['slope'])}. Seller of the straddle: mean {f(a['seller_pnl_mean_pct'])} % of spot per event, {f(a['seller_pnl_after_spread_pct'])} % after the quoted spread, hit rate {f(a['seller_hit_rate'] * 100, 0)} %, sd {f(a['seller_pnl_sd_pct'])} %, worst {f(a['worst_pct'])} %.\n")
            L.append("| year | n | implied (stripped) % | realised % | RMS implied / realised | seller after spread % | hit |")
            L.append("|---|---|---|---|---|---|---|")
            for y, v in ea["by_year"].items():
                L.append(f"| {y} | {v['n']} | {f(v['implied_move_stripped_pct'])} | {f(v['realised_abs_move_pct'])} | {f(v['rms_implied_pct'])} / {f(v['rms_realised_pct'])} | {f(v['seller_pnl_after_spread_pct'])} | {f(v['seller_hit_rate'] * 100, 0)} % |")
            L.append("")
            L.append("| name | n | implied (stripped) % | realised % | seller after spread % | hit |")
            L.append("|---|---|---|---|---|---|")
            for s, v in sorted(ea["by_symbol"].items(), key=lambda kv: -kv[1]["n"]):
                L.append(f"| {s} | {v['n']} | {f(v['implied_move_stripped_pct'])} | {f(v['realised_abs_move_pct'])} | {f(v['seller_pnl_after_spread_pct'])} | {f(v['seller_hit_rate'] * 100, 0)} % |")
            L.append("")
        cc = ev.get("crypto_calendar", {})
        for ccy, v in cc.items():
            r, w = v["realised"], v["implied_weekend"]
            L.append(f"{ccy} calendar: weekend/weekday variance ratio {f(r['weekend_to_weekday_var_ratio'])} (annualised {f(r['ann_vol_weekend'] * 100, 0)} % vs {f(r['ann_vol_weekday'] * 100, 0)} %), by year " + ", ".join(f"{y}: {f(x)}" for y, x in r["weekend_ratio_by_year"].items()) + f"; the half-hours after the 00/08/16 UTC funding marks run {f(r['var_ratio_funding_to_other'])} x the variance of other hours. Implied: the 7-day vol on Fridays is {f(w['fri_minus_mon_7d_vol_pts'])} ± {f(w['se'])} pts against the following Monday (lower on {f(w['share_fri_lower'] * 100, 0)} % of {w['n_weeks']} weeks).\n")
    # vix
    if vx:
        L.append("## The VIX complex\n")
        st_ = vx["states"]; L.append("| state (VIX9D / VIX / VIX3M) | share of days | mean VIX | realised next 21 days | premium (pts) | VIX change over 21 days |")
        L.append("|---|---|---|---|---|---|")
        for k, v in st_.items():
            if k != "transition":
                L.append(f"| {k} | {f(v['share_of_days'] * 100, 1)} % | {f(v['vix_mean'], 1)} | {f(v['fwd_rv_mean'], 1)} | {f(v['premium_pts'])} | {f(v['vix_change_21d'])} |")
        c = vx["curve"]; r = vx["roll_strategy"]
        L.append(f"\nVX curve {c['first']} to {c['last']}, {c['n_days']:,} days, in contango (F2 > F1) {f(c['share_contango_1_2'] * 100, 0)} % of days. Roll-down in index points per 30 days, mean (median): " + ", ".join(f"{k.replace('roll_', 'F').replace('F0', 'VIX→F1')} {f(v)} ({f(c['roll_pts_per_30d_median'][k])})" for k, v in c["roll_pts_per_30d"].items()) + ".\n")
        L.append(f"Short front-month roll, one contract, {r['years']} years: gross {f(r['gross_pts_per_year'], 1)} pts/yr, bid-ask {f(r['cost_pts_per_year'])} pts/yr, net {f(r['net_pts_per_year'], 1)} pts/yr (${r['net_usd_per_contract_year']:,.0f} a contract-year), Sharpe {f(r['sharpe'])}, max drawdown {f(r['max_drawdown_pts'], 1)} pts, worst day {f(r['worst_day_pts'], 1)} on {r['worst_day']}. Net per day when yesterday's curve was in contango {f(r['net_pts_per_day_contango'], 3)} against {f(r['net_pts_per_day_backwardation'], 3)} in backwardation; shorting only after contango days: {f(r['contango_only']['net_pts_per_year'], 1)} pts/yr, Sharpe {f(r['contango_only']['sharpe'])}.\n")
        L.append("| year | " + " | ".join(str(y) for y in r["by_year"]) + " |"); L.append("|---|" + "---|" * len(r["by_year"])); L.append("| net pts | " + " | ".join(f(v, 1) for v in r["by_year"].values()) + " |\n")
        v = vx["vvix"]
        L.append(f"VVIX: mean {f(v['vvix_mean'], 1)}; realised vol of the 30-day constant-maturity future over the next 21 days {f(v.get('rv_of_30d_future_mean'), 1)} (vol-of-vol premium {f(v.get('vol_of_vol_premium_pts'), 1)} pts, CI {ci(v.get('vol_of_vol_premium_ci'), 1)}); of the spot index {f(v['rv_of_spot_vix_mean'], 1)}. Correlation with the VIX level {f(v['corr_vvix_vix'])}, with the 3M-1M slope {f(v['corr_vvix_slope'])}; VVIX by slope tercile: " + ", ".join(f"{k} {f(x, 1)}" for k, x in v["vvix_by_slope"].items()) + ".\n")
    # strategies
    if st:
        L.append("## Strategies\n")
        L.append("All programs: one unit (one straddle on one share / one coin), daily delta hedge, spread paid at entry (and exit where closed early), scenario margin = worst loss over ±15 % spot × ±30 % vol. Return on margin is net P&L per year over the average margin.\n")
        L.append("| program | trades | years | hit | gross / trade (% spot) | cost / trade | net / trade | worst trade | opt / hedge share of gross | return on margin (%/yr) | max DD (% margin) | daily Sharpe |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        def row(name, v):
            if not v or v.get("n_trades", 0) == 0:
                return
            L.append(f"| {name} | {v['n_trades']} | {v['years']} | {f(v['hit_rate'] * 100, 0)} % | {f(v['gross_per_trade_pct_spot'])} | {f(v['cost_per_trade_pct_spot'])} | {f(v['net_per_trade_pct_spot'])} | {f(v['worst_trade_pct_spot'], 1)} | {f(v['opt_pnl_share'])} / {f(v['hedge_pnl_share'])} | {f(v['return_on_margin_pct'], 1)} | {f(v['max_drawdown_pct_margin'], 0)} | {f(v['daily_sharpe'])} |")
        if "spy_straddle" in st:
            s = st["spy_straddle"]; row("SPY short straddle, all", s.get("unconditional")); row("SPY straddle, VIX3M > VIX at entry", s.get("contango")); row("SPY straddle, VIX3M <= VIX at entry", s.get("backwardation"))
            wf = s.get("stop_loss_walk_forward", {})
            for k, v in wf.get("results", {}).items():
                row(f"SPY straddle, {k}, in sample (to {wf['split']})", v["in_sample"]); row(f"SPY straddle, {k}, out of sample", v["out_of_sample"])
        row("SPY calendar (short front, long second, vega-neutral)", st.get("spy_calendar"))
        for ccy in ("btc", "eth"):
            row(f"{ccy.upper()} short 30-day straddle, all", st.get(f"{ccy}_straddle")); row(f"{ccy.upper()} straddle, iv60 > iv30 at entry", st.get(f"{ccy}_straddle_contango")); row(f"{ccy.upper()} straddle, iv60 <= iv30 at entry", st.get(f"{ccy}_straddle_backwardation")); row(f"{ccy.upper()} straddle, costless", st.get(f"{ccy}_straddle_costless"))
        if "spy_straddle" in st and "stop_loss_walk_forward" in st["spy_straddle"]:
            L.append(f"\nStop-loss chosen in sample: {st['spy_straddle']['stop_loss_walk_forward']['chosen']}.\n")
        for name in ("spy_straddle", "btc_straddle"):
            v = st.get(name, {}).get("unconditional", st.get(name)) if name == "spy_straddle" else st.get(name)
            if v and v.get("by_year"):
                L.append(f"{name} net by entry year: " + ", ".join(f"{y}: {f(x['net'] / (1 if name == 'spy_straddle' else 1), 1)} ({x['n']}, hit {f(x['hit'] * 100, 0)} %)" for y, x in v["by_year"].items()) + "\n")
    with open(os.path.join(RES, "summary.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))
    print("summary ->", os.path.join(RES, "summary.md"))


if __name__ == "__main__":
    main()
