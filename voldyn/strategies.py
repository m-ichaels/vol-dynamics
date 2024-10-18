"""Systematic volatility strategies with real bid-ask, daily delta hedging at a stated cost, a scenario margin and
walk-forward rules.

The engine holds option legs against a daily underlying path.  Each day the book is marked with Black-Scholes at the
leg's marking vol (the entry implied vol, replaced by the market's vol whenever a chain quotes the leg again), the hedge
is reset to the book's delta, and at expiry every leg settles at intrinsic on the real close.  Daily P&L is therefore

    dP = (option mark change) + hedge * dS - costs,

which for a short delta-hedged straddle is the textbook  0.5 Gamma S^2 (sigma_imp^2 - sigma_real^2) dt  plus vega P&L
when the mark vol changes.  The decomposition reported is option P&L, hedge P&L, spread cost and hedge cost, and they
sum to the net.

Margin (SPAN-style): the worst loss of the book over a grid of spot moves (+-15 % in 3 % steps) crossed with relative vol
moves (+-30 %), plus a minimum of 10 % of the short option notional; return is quoted per unit of the average margin.

Programs:
  spy_straddle      short the front ATM straddle on the first chain date with 20-45 days to expiry, hold to expiry,
                    delta-hedge daily; variants: unconditional, only when VIX3M > VIX (contango), with a stop-loss (a
                    multiple of the premium received) chosen on the first half of the sample and applied to the second
  spy_calendar      short the front ATM straddle, long the second at equal vega, hold to the front expiry
  btc_straddle      the same on Deribit BTC options: 30-day ATM straddle from the print-implied term structure, hedged
                    in the perpetual, settled on the index
Costs: half the quoted spread on each option leg at entry (and at exit when closed before expiry); SPY hedges at 1 bp
of notional each way; BTC options at a stated half-spread in vol points, perpetual hedges at 5 bp each way."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import chains, data
from .surface import black, greeks, implied_vol

SPY_HEDGE_BP = 1.0
BTC_HEDGE_BP = 5.0
BTC_HALF_SPREAD_VOL = 0.015     # 1.5 vol points each side for an ATM BTC option on Deribit (screen spreads run 1-3 points)
GRID_SPOT = np.arange(-0.15, 0.151, 0.03)
GRID_VOL = np.array([0.7, 0.85, 1.0, 1.15, 1.3])
MIN_MARGIN_FRAC = 0.10


@dataclass
class Leg:
    K: float
    cp: float
    expiry: pd.Timestamp
    qty: float                # +1 long one unit of the underlying's option, -1 short
    entry_px: float
    mark_vol: float
    label: str = ""
    carry: float = 0.0        # ln(F/S) / T at entry: rate minus dividend yield, from put-call parity
    r: float = 0.0            # discount rate
    mid_px: float | None = None   # the quoted mid at entry; the spread cost is |entry - mid| (defaults to the model price)


@dataclass
class Trade:
    name: str
    entry: pd.Timestamp
    legs: list
    spot0: float
    exit_rule: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def leg_price(lg, S, d):
    """discounted Black price and spot Greeks of one leg: F = S e^{carry T}, df = e^{-r T}"""
    T = max((lg.expiry - d).days, 0) / 365.0
    if T <= 0:
        return max(lg.cp * (S - lg.K), 0.0), (1.0 if lg.cp * (S - lg.K) > 0 else 0.0) * lg.cp, 0.0, 0.0
    F = S * np.exp(lg.carry * T); df = np.exp(-lg.r * T)
    px = df * float(black(F, lg.K, T, lg.mark_vol, lg.cp)); g = greeks(F, lg.K, T, lg.mark_vol, lg.cp)
    dFdS = np.exp(lg.carry * T)
    return px, df * float(g["delta"]) * dFdS, df * float(g["vega"]), df * float(g["gamma"]) * dFdS ** 2


def book_value(legs, S, d):
    v = 0.0; delta = 0.0; vega = 0.0; gamma = 0.0
    for lg in legs:
        px, dl, vg, gm = leg_price(lg, S, d)
        v += lg.qty * px; delta += lg.qty * dl; vega += lg.qty * vg; gamma += lg.qty * gm
    return v, delta, vega, gamma


def scenario_margin(legs, S, d):
    base, *_ = book_value(legs, S, d)
    worst = 0.0
    for ds in GRID_SPOT:
        for dv in GRID_VOL:
            scen = [Leg(l.K, l.cp, l.expiry, l.qty, l.entry_px, l.mark_vol * dv, l.label, l.carry, l.r) for l in legs]
            v, *_ = book_value(scen, S * (1 + ds), d)
            worst = max(worst, base - v)
    short_notional = sum(abs(l.qty) * S for l in legs if l.qty < 0)
    return max(worst, MIN_MARGIN_FRAC * short_notional)


def simulate(trade: Trade, path: pd.Series, hedge_bp: float, marks: dict | None = None, stop_loss_frac: float | None = None) -> Trade:
    """path: daily closes from the entry date to at least the last expiry.  marks: {date: {label: vol}} to refresh
    marking vols from later chains.  Returns the trade with a daily ledger and a summary."""
    legs = trade.legs; last_exp = max(l.expiry for l in legs)
    days = path.loc[trade.entry:last_exp].index
    S0 = float(path.loc[trade.entry]); v0, d0, vega0, gamma0 = book_value(legs, S0, trade.entry)
    entry_cash = -sum(l.qty * l.entry_px for l in legs)             # premium received (short) or paid
    spread_cost = sum(abs(l.qty) * abs(l.entry_px - (l.mid_px if l.mid_px is not None else leg_price(l, S0, trade.entry)[0])) for l in legs)
    hedge = -d0; hedge_cost = abs(hedge) * S0 * hedge_bp * 1e-4
    margin0 = scenario_margin(legs, S0, trade.entry)
    prev_v, prev_S = v0, S0; cum = 0.0; peak = 0.0; rows = []; stopped = False
    for i, d in enumerate(days):
        S = float(path.loc[d])
        if marks and d in marks:
            for l in legs:
                if l.label in marks[d] and np.isfinite(marks[d][l.label]) and (l.expiry - d).days > 1:
                    l.mark_vol = float(marks[d][l.label])
        v, delta, vega, gamma = book_value(legs, S, d)
        opt_pnl = v - prev_v if i > 0 else 0.0
        hedge_pnl = hedge * (S - prev_S) if i > 0 else 0.0
        cost = 0.0
        if i == 0:
            cost = spread_cost + hedge_cost
        new_hedge = -delta if d < last_exp else 0.0
        if i > 0:
            cost += abs(new_hedge - hedge) * S * hedge_bp * 1e-4
        net = opt_pnl + hedge_pnl - cost
        cum += net; peak = max(peak, cum)
        margin = scenario_margin(legs, S, d) if d < last_exp else 0.0
        rows.append({"date": d, "S": S, "book": v, "delta": delta, "vega": vega, "gamma": gamma, "hedge": new_hedge, "opt_pnl": opt_pnl, "hedge_pnl": hedge_pnl, "cost": cost, "net": net, "cum": cum, "margin": margin})
        if stop_loss_frac is not None and cum < -stop_loss_frac * abs(entry_cash) and d < last_exp:      # stop at a multiple of the premium received
            # close at the mark, pay the spread again (at the entry spread's vol-equivalent) and the hedge out
            close_cost = spread_cost + abs(new_hedge) * S * hedge_bp * 1e-4
            rows[-1]["cost"] += close_cost; rows[-1]["net"] -= close_cost; cum -= close_cost; rows[-1]["cum"] = cum
            stopped = True; break
        hedge = new_hedge; prev_v, prev_S = v, S
    led = pd.DataFrame(rows).set_index("date")
    trade.rows = led
    trade.summary = {"name": trade.name, "entry": trade.entry, "exit": led.index[-1], "days": int(len(led)), "spot0": S0, "premium": float(entry_cash), "margin0": float(margin0), "avg_margin": float(led["margin"].replace(0, np.nan).mean()),
                     "opt_pnl": float(led["opt_pnl"].sum()), "hedge_pnl": float(led["hedge_pnl"].sum()), "cost": float(led["cost"].sum()), "net": float(led["net"].sum()), "gross": float(led["opt_pnl"].sum() + led["hedge_pnl"].sum()),
                     "max_dd": float((led["cum"].cummax() - led["cum"]).max()), "stopped": stopped, "vega0": float(vega0), "hedge_turnover": float(led["hedge"].diff().abs().sum() * S0 + abs(d0) * S0)}
    return trade


# ---- programs -------------------------------------------------------------------------------------------------------------------------
def spy_entries(chains: pd.DataFrame, px: pd.DataFrame, min_days=20, max_days=45) -> list:
    """one entry per front expiry: the first chain date at which the front expiry has 20-45 days left"""
    out = []; used = set()
    for cd, day in chains.groupby("date"):
        spot_row = px.loc[:cd]
        if spot_row.empty:
            continue
        spot = float(spot_row["close"].iloc[-1]); sd = spot_row.index[-1]
        exps = sorted(day["expiration"].unique())
        cands = [e for e in exps if min_days <= (e - sd).days <= max_days]
        if not cands:
            continue
        e = cands[0]
        if e in used:
            continue
        used.add(e); out.append((sd, cd, e, spot))
    return out


def atm_legs(day: pd.DataFrame, spot: float, expiry: pd.Timestamp, sign: float, label: str, r_prior: float = 0.0):
    """the ATM straddle legs of one expiry: forward and discount from parity, entry at the bid (short) or ask (long),
    marking vol from the mid on that forward"""
    g = day[day["expiration"] == expiry]
    T = max((expiry - day["date"].iloc[0]).days, 1) / 365.0
    F, df, _ = chains.expiry_forward(g, spot, T, r_prior)
    st = chains.atm_straddle(g, F, df, spot)
    if st is None:
        return None
    carry = float(np.log(F / spot) / T); r = float(-np.log(df) / T)
    legs = []
    for cp in (1.0, -1.0):
        row = st["legs"][cp]
        px_entry = float(row["bid"] if sign < 0 else row["ask"])
        legs.append(Leg(st["K"], cp, expiry, sign, px_entry, st["iv_c"] if cp > 0 else st["iv_p"], f"{label}_{'C' if cp > 0 else 'P'}", carry, r, float(row["mid"])))
    return legs


def chain_marks(ch: pd.DataFrame, legs: list, px: pd.DataFrame, r_prior: float = 0.0) -> dict:
    """later chain quotes of the same legs -> marking vols by date and label (from the mid on that day's parity forward)"""
    out = {}
    exp = legs[0].expiry                      # the chain expiration (called before the settlement date replaces it)
    sub = ch[(ch["expiration"] == exp)]
    for d, g in sub.groupby("date"):
        spot = px["close"].loc[:d]
        if spot.empty:
            continue
        S = float(spot.iloc[-1]); T = max((exp - d).days, 1) / 365.0
        if T < 2 / 365:
            continue
        F, df, _ = chains.expiry_forward(g, S, T, r_prior)
        for l in legs:
            row = g[(g["strike"] == l.K) & (g["cp"] == l.cp)]
            if len(row) and row["mid"].iloc[0] > 0:
                v = float(implied_vol(row["mid"].iloc[0], F, l.K, T, l.cp, df))
                if np.isfinite(v) and 0.02 < v < 3:
                    out.setdefault(d, {})[l.label] = v
    return out


def run_spy_straddles(ch: pd.DataFrame, px: pd.DataFrame, cboe: pd.DataFrame, stop_loss_frac=None, condition: str = "all", rates: pd.Series | None = None, hedge_bp: float = SPY_HEDGE_BP) -> list:
    trades = []
    slope = (cboe["VIX3M"] - cboe["VIX"]) if "VIX3M" in cboe else None
    for sd, cd, e, spot in spy_entries(ch, px):
        if condition == "contango" and (slope is None or sd not in slope.index or not slope.loc[sd] > 0):
            continue
        if condition == "backwardation" and (slope is None or sd not in slope.index or not slope.loc[sd] <= 0):
            continue
        r0 = float(rates.loc[:sd].iloc[-1]) if rates is not None and len(rates.loc[:sd]) else 0.0
        day = ch[ch["date"] == cd]
        legs = atm_legs(day, spot, e, -1.0, "front", r0)
        if legs is None:
            continue
        marks = chain_marks(ch, legs, px, r0)
        # settle at the close of the expiry day (or the last close before it)
        path = px["close"].loc[sd:e]
        if len(path) < 5:
            continue
        legs = [Leg(l.K, l.cp, path.index[-1], l.qty, l.entry_px, l.mark_vol, l.label, l.carry, l.r, l.mid_px) for l in legs]
        tr = Trade(f"spy_straddle_{condition}", sd, legs, spot)
        trades.append(simulate(tr, path, hedge_bp, marks, stop_loss_frac))
    return trades


def run_spy_calendars(ch: pd.DataFrame, px: pd.DataFrame, rates: pd.Series | None = None) -> list:
    trades = []
    for sd, cd, e, spot in spy_entries(ch, px):
        day = ch[ch["date"] == cd]
        exps = sorted(x for x in day["expiration"].unique() if x > e)
        if not exps:
            continue
        e2 = exps[0]
        if (e2 - e).days < 14 or (e2 - e).days > 60:
            continue
        r0 = float(rates.loc[:sd].iloc[-1]) if rates is not None and len(rates.loc[:sd]) else 0.0
        front = atm_legs(day, spot, e, -1.0, "front", r0); back = atm_legs(day, spot, e2, +1.0, "back", r0)
        if front is None or back is None:
            continue
        v1 = sum(leg_price(l, spot, sd)[2] for l in front); v2 = sum(leg_price(l, spot, sd)[2] for l in back)
        ratio = v1 / v2 if v2 > 0 else 1.0
        for l in back:
            l.qty = ratio
        marks = chain_marks(ch, front, px, r0)
        for d, m in chain_marks(ch, back, px, r0).items():
            marks.setdefault(d, {}).update(m)
        path = px["close"].loc[sd:e]
        if len(path) < 5:
            continue
        legs = [Leg(l.K, l.cp, path.index[-1] if l.label.startswith("front") else l.expiry, l.qty, l.entry_px, l.mark_vol, l.label, l.carry, l.r, l.mid_px) for l in front + back]
        tr = Trade("spy_calendar", sd, legs, spot)
        # the back legs are closed at the front expiry at their mark; closing pays half their quoted spread again
        tr = simulate(tr, path, SPY_HEDGE_BP, marks)
        back_spread = sum(abs(l.qty) * 0.5 * float(day[(day["expiration"] == e2) & (day["strike"] == l.K) & (day["cp"] == l.cp)]["spread"].iloc[0]) for l in back)
        tr.rows.iloc[-1, tr.rows.columns.get_loc("cost")] += back_spread; tr.rows.iloc[-1, tr.rows.columns.get_loc("net")] -= back_spread
        tr.summary["cost"] += back_spread; tr.summary["net"] -= back_spread
        trades.append(tr)
    return trades


def run_btc_straddles(cm: pd.DataFrame, index: pd.Series, half_spread_vol: float = BTC_HALF_SPREAD_VOL, hold_days: int = 30) -> list:
    """one 30-day ATM straddle every 30 days: entry vol = iv30 + half spread (sold at the bid), marked at the current
    constant-maturity vol of the remaining tenor (interpolated from iv7/iv30), settled on the index after 30 days"""
    trades = []
    days = cm.index; i = 0
    while i < len(days):
        d0 = days[i]; end = d0 + pd.Timedelta(days=hold_days)
        if end > index.index[-1]:
            break
        S0 = float(index.get(d0, np.nan)); iv = float(cm.loc[d0, "iv30"])
        if not (np.isfinite(S0) and np.isfinite(iv)):
            i += 1; continue
        T = hold_days / 365.0
        legs = [Leg(S0, cp, end, -1.0, float(black(S0, S0, T, iv - half_spread_vol, cp)), iv, f"btc_{'C' if cp > 0 else 'P'}") for cp in (1.0, -1.0)]
        # marks: the constant-maturity vol for the remaining life, from iv7 and iv30
        marks = {}
        for d in cm.loc[d0:end].index:
            rem = (end - d).days / 365.0
            if rem <= 0:
                continue
            a, b = cm.loc[d, "iv7"], cm.loc[d, "iv30"]
            if not (np.isfinite(a) and np.isfinite(b)):
                continue
            lam = np.clip((rem - 7 / 365) / (23 / 365), 0, 1)
            w = (1 - lam) * a * a * 7 / 365 + lam * b * b * 30 / 365
            tau = (1 - lam) * 7 / 365 + lam * 30 / 365
            v = float(np.sqrt(w / tau))
            marks[d] = {"btc_C": v, "btc_P": v}
        path = index.loc[d0:end]
        tr = Trade("btc_straddle", d0, legs, S0)
        trades.append(simulate(tr, path, BTC_HEDGE_BP, marks))
        i = int(np.searchsorted(days, end + pd.Timedelta(days=1)))
    return trades


# ---- reporting ------------------------------------------------------------------------------------------------------------------------
def program_summary(trades: list, ann_days: int = 365) -> dict:
    if not trades:
        return {"n": 0}
    s = pd.DataFrame([t.summary for t in trades]).sort_values("entry")
    led = pd.concat([t.rows.assign(trade=t.name + "_" + str(t.entry.date())) for t in trades])
    daily = led.groupby(level=0)[["opt_pnl", "hedge_pnl", "cost", "net"]].sum(); margin_d = led.groupby(level=0)["margin"].sum()
    yrs = (s["exit"].max() - s["entry"].min()).days / 365.25
    avg_margin = float(margin_d[margin_d > 0].mean())
    cum = daily["net"].cumsum(); dd = float((cum.cummax() - cum).max())
    out = {"n_trades": int(len(s)), "years": round(yrs, 2), "first": str(s["entry"].min().date()), "last": str(s["exit"].max().date()),
           "gross_per_trade": float(s["gross"].mean()), "net_per_trade": float(s["net"].mean()), "cost_per_trade": float(s["cost"].mean()), "premium_per_trade": float(s["premium"].mean()),
           "net_per_trade_pct_spot": float((s["net"] / s["spot0"]).mean() * 100), "gross_per_trade_pct_spot": float((s["gross"] / s["spot0"]).mean() * 100), "cost_per_trade_pct_spot": float((s["cost"] / s["spot0"]).mean() * 100),
           "hit_rate": float((s["net"] > 0).mean()), "worst_trade_pct_spot": float((s["net"] / s["spot0"]).min() * 100), "stopped_share": float(s["stopped"].mean()),
           "opt_pnl_share": float(s["opt_pnl"].sum() / max(abs(s["gross"].sum()), 1e-9)), "hedge_pnl_share": float(s["hedge_pnl"].sum() / max(abs(s["gross"].sum()), 1e-9)),
           "avg_margin": avg_margin, "net_per_year": float(daily["net"].sum() / yrs), "gross_per_year": float((daily["opt_pnl"] + daily["hedge_pnl"]).sum() / yrs), "cost_per_year": float(daily["cost"].sum() / yrs),
           "return_on_margin_pct": float(daily["net"].sum() / yrs / avg_margin * 100) if avg_margin > 0 else np.nan, "max_drawdown_pct_margin": float(dd / avg_margin * 100) if avg_margin > 0 else np.nan,
           "daily_sharpe": float(daily["net"].mean() / daily["net"].std() * np.sqrt(ann_days)) if daily["net"].std() > 0 else np.nan,
           "by_year": {int(y): {"net": float(g["net"].sum()), "n": int(len(g)), "hit": float((g["net"] > 0).mean())} for y, g in s.groupby(s["entry"].dt.year)},
           "hedge_turnover_per_trade_x_spot": float((s["hedge_turnover"] / s["spot0"]).mean())}
    return out


def choose_stop(trades_by_stop: dict, split_date: pd.Timestamp) -> dict:
    """pick the stop-loss on trades entered before split_date by net per unit margin; report the rest out of sample"""
    res = {}
    for k, trs in trades_by_stop.items():
        a = [t for t in trs if t.entry < split_date]; b = [t for t in trs if t.entry >= split_date]
        res[k] = {"in_sample": program_summary(a), "out_of_sample": program_summary(b)}
    best = max(res, key=lambda k: res[k]["in_sample"].get("return_on_margin_pct", -1e9) if res[k]["in_sample"].get("n_trades", 0) > 5 else -1e9)
    return {"chosen": best, "split": str(split_date.date()), "results": res}
