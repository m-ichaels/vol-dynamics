"""Crypto implied and realised volatility from the Deribit history.

Implied: every option trade carries the exchange's implied vol at the print.  Per UTC day and expiry, the ATM vol is the
vega-weighted median IV of prints within |ln(K/S)| < 0.10 (S the index at the print); constant-maturity vols at 7, 30,
60 and 90 days come from linear interpolation of total variance across the two neighbouring expiries.  The 30-day series
is checked against Deribit's own DVOL index where the two overlap (2021 on).

Realised: 5-minute perpetual candles (BTC from Aug 2018, ETH from 2019) give RV, bipower variation and the BNS jump
test per UTC day; before the perpetual existed the daily index price at 00:00 UTC (from the prints) gives close-to-close.

Calendar effects, 24/7 market: realised variance by hour of week (UTC) and around the 00:00 / 08:00 / 16:00 UTC funding
timestamps of the perpetual; weekend realised vol against weekday; whether the implied term structure prices the weekend
(the 7-day vol on Fridays against Mondays)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data, realised
from .surface import greeks

TENORS = {7: 7 / 365, 30: 30 / 365, 60: 60 / 365, 90: 90 / 365}


def atm_by_expiry(trades: pd.DataFrame, band: float = 0.10, min_prints: int = 3) -> pd.DataFrame:
    """per (day, expiry): vega-weighted median IV of near-the-money prints, the number of prints and the mean index"""
    t = trades[(trades["iv"] > 1) & (trades["iv"] < 500) & (trades["index_price"] > 0) & (trades["T"] > 1 / 365)].copy()
    t["k"] = np.log(t["strike"] / t["index_price"])
    t = t[t["k"].abs() < band]
    t["day"] = pd.to_datetime(t["timestamp"], unit="ms", utc=True).dt.tz_convert(None).dt.normalize()
    t["sig"] = t["iv"] / 100.0
    t["vega"] = greeks(t["index_price"].values, t["strike"].values, t["T"].values, t["sig"].values)["vega"] * t["amount"].clip(lower=0.01)
    rows = []
    for (d, e), g in t.groupby(["day", "expiry_ms"]):
        if len(g) < min_prints:
            continue
        w = g["vega"].values; s = g["sig"].values; o = np.argsort(s); cw = np.cumsum(w[o]) / w.sum()
        med = float(s[o][np.searchsorted(cw, 0.5)])
        rows.append({"day": d, "expiry_ms": e, "T": float((e - pd.Timestamp(d).value // 10 ** 6 - 12 * 3600e3) / (365 * 86400e3)), "atm": med, "n": int(len(g)), "index": float(g["index_price"].mean())})
    return pd.DataFrame(rows)


def constant_maturity(atm: pd.DataFrame, tenors: dict = TENORS) -> pd.DataFrame:
    """interpolate total variance across expiries to constant maturities per day (flat outside the range)"""
    out = []
    for d, g in atm.groupby("day"):
        g = g[g["T"] > 0.5 / 365].sort_values("T")
        if len(g) < 2:
            continue
        T = g["T"].values; w = (g["atm"].values ** 2) * T
        row = {"day": d, "index": float(g["index"].mean()), "n_expiries": int(len(g))}
        for name, tau in tenors.items():
            if tau <= T[0]:
                row[f"iv{name}"] = float(np.sqrt(w[0] / T[0]))
            elif tau >= T[-1]:
                row[f"iv{name}"] = float(np.sqrt(w[-1] / T[-1]))
            else:
                j = int(np.searchsorted(T, tau)); lam = (tau - T[j - 1]) / (T[j] - T[j - 1])
                row[f"iv{name}"] = float(np.sqrt(((1 - lam) * w[j - 1] + lam * w[j]) / tau))
        out.append(row)
    return pd.DataFrame(out).set_index("day").sort_index()


def implied_from_trades(currency: str, chunk_months: int = 6) -> pd.DataFrame:
    """the constant-maturity implied term structure for the whole history, built month-chunk by month-chunk"""
    months = sorted(m for m in (f[-14:-8] for f in data.trade_files(currency)))
    parts = []
    for i in range(0, len(months), chunk_months):
        tr = data.load_trades(currency, months[i:i + chunk_months], ["timestamp", "instrument_name", "iv", "index_price", "amount", "price", "mark_price", "block_trade_id"])
        if tr.empty:
            continue
        tr = data.add_instrument_columns(tr)
        parts.append(atm_by_expiry(tr))
    atm = pd.concat(parts, ignore_index=True)
    return constant_maturity(atm), atm


def daily_index(currency: str) -> pd.Series:
    """the index at 00:00 UTC from the perpetual candles where they exist, else the first print of the day"""
    try:
        c = data.load_candles(currency)
        s = c["close"].resample("1D").last().dropna()
    except Exception:  # noqa: BLE001
        s = pd.Series(dtype=float)
    return s


def realised_daily(currency: str) -> pd.DataFrame:
    """per UTC day: RV, BV, jumps from the 5-minute candles (288 bars a day); plus close-to-close"""
    c = data.load_candles(currency)
    m = realised.intraday_measures(c["close"], bars_per_day=288)
    d = c["close"].resample("1D").last().dropna()
    m["cc"] = (np.log(d).diff() ** 2).reindex(m.index)
    m["ret"] = np.log(d).diff().reindex(m.index)
    return m


def compare_with_dvol(cm: pd.DataFrame, dvol: pd.Series) -> dict:
    j = pd.DataFrame({"trades": cm["iv30"] * 100, "dvol": dvol}).dropna()
    if len(j) < 100:
        return {"n": int(len(j))}
    d = j["trades"] - j["dvol"]
    return {"n": int(len(j)), "corr": float(j["trades"].corr(j["dvol"])), "mean_diff_pts": float(d.mean()), "mad_pts": float(d.abs().mean()), "corr_changes": float(j["trades"].diff().corr(j["dvol"].diff()))}


def calendar_effects(currency: str) -> dict:
    """realised variance by hour of week and around funding timestamps; weekend against weekday; the implied weekend"""
    c = data.load_candles(currency)
    r = np.log(c["close"]).diff().dropna()
    r2 = r ** 2
    idx = r2.index
    how = pd.Series(r2.values, index=idx).groupby([idx.dayofweek, idx.hour]).mean()
    hour_mat = how.unstack().reindex(range(7)) * 288 * 365            # annualised variance by (day, hour)
    weekday = r2[idx.dayofweek < 5]; weekend = r2[idx.dayofweek >= 5]
    # funding: Deribit perpetual funding is continuous but the 8-hour marks at 00/08/16 UTC are where the perps settle funding
    minute = idx.hour * 60 + idx.minute
    near = np.isin(idx.hour, [0, 8, 16]) & (idx.minute < 30)
    out = {"n_bars": int(len(r2)), "ann_vol_weekday": float(np.sqrt(weekday.mean() * 288 * 365)), "ann_vol_weekend": float(np.sqrt(weekend.mean() * 288 * 365)),
           "weekend_to_weekday_var_ratio": float(weekend.mean() / weekday.mean()),
           "ann_vol_funding_half_hours": float(np.sqrt(r2[near].mean() * 288 * 365)), "ann_vol_other_hours": float(np.sqrt(r2[~near].mean() * 288 * 365)),
           "var_ratio_funding_to_other": float(r2[near].mean() / r2[~near].mean()),
           "by_hour_utc": {int(h): float(np.sqrt(g.mean() * 288 * 365)) for h, g in r2.groupby(idx.hour)},
           "by_dayofweek": {int(d): float(np.sqrt(g.mean() * 288 * 365)) for d, g in r2.groupby(idx.dayofweek)}}
    # by year, the weekend ratio
    out["weekend_ratio_by_year"] = {int(y): float(g[g.index.dayofweek >= 5].mean() / g[g.index.dayofweek < 5].mean()) for y, g in r2.groupby(idx.year)}
    out["hour_of_week_ann_vol"] = np.sqrt(hour_mat).round(3).values.tolist()
    return out


def implied_weekend(cm: pd.DataFrame) -> dict:
    """does the 7-day implied fall into the weekend?  Friday against Monday 7-day vol, paired by week"""
    s = cm["iv7"].dropna()
    fri = s[s.index.dayofweek == 4]; mon = s[s.index.dayofweek == 0]
    f = fri.copy(); f.index = f.index + pd.Timedelta(days=3)
    j = pd.DataFrame({"fri": f, "mon": mon}).dropna()
    d = (j["fri"] - j["mon"]) * 100
    return {"n_weeks": int(len(j)), "fri_minus_mon_7d_vol_pts": float(d.mean()), "se": float(d.std() / np.sqrt(len(d))), "share_fri_lower": float((d < 0).mean())}
