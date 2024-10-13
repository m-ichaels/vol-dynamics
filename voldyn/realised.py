"""Realised-variance estimators and the jump test.

Daily estimators from OHLC (all in daily variance units, annualise with 252 for equities, 365 for crypto):

    close-to-close    r_t^2,  r_t = ln(C_t / C_{t-1})
    Parkinson         (ln H/L)^2 / (4 ln 2)
    Garman-Klass      0.5 (ln H/L)^2 - (2 ln 2 - 1) (ln C/O)^2
    Rogers-Satchell   ln(H/C) ln(H/O) + ln(L/C) ln(L/O)
    Yang-Zhang        sigma_o^2 + k sigma_c^2 + (1-k) sigma_rs^2 over a window, k = 0.34 / (1.34 + (n+1)/(n-1))

Intraday, from 5-minute closes (crypto trades 24/7, so one day is 288 bars):

    RV      sum r_i^2                                  bipower variation   BV = (pi/2) sum |r_i| |r_{i-1}|
    the Barndorff-Nielsen-Shephard (2006) ratio test for jumps on day t:
        z = (RV - BV) / RV  /  sqrt( (pi^2/4 + pi - 5) * (1/n) * max(1, TQ / BV^2) ),  TQ the tripower quarticity;
    z > 1.96 flags a jump day and the jump variation is max(RV - BV, 0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

LN2 = np.log(2.0)
MU1 = np.sqrt(2.0 / np.pi)                       # E|Z|
MU43 = 2 ** (2 / 3) * 0.9027452929509336 / np.sqrt(np.pi)   # E|Z|^{4/3} = 2^{2/3} Gamma(7/6) / Gamma(1/2)


def daily_estimators(o: pd.DataFrame) -> pd.DataFrame:
    """o: columns open, high, low, close (adjusted consistently).  Returns daily variance estimates per day."""
    O, H, L, C = (np.log(o[c].astype(float)) for c in ("open", "high", "low", "close"))
    Cp = C.shift(1)
    out = pd.DataFrame(index=o.index)
    out["cc"] = (C - Cp) ** 2
    out["park"] = (H - L) ** 2 / (4 * LN2)
    out["gk"] = 0.5 * (H - L) ** 2 - (2 * LN2 - 1) * (C - O) ** 2
    out["rs"] = (H - C) * (H - O) + (L - C) * (L - O)
    out["overnight"] = (O - Cp) ** 2
    out["ret"] = C - Cp
    return out


def yang_zhang(o: pd.DataFrame, window: int = 21) -> pd.Series:
    O, H, L, C = (np.log(o[c].astype(float)) for c in ("open", "high", "low", "close"))
    Cp = C.shift(1)
    on = O - Cp; oc = C - O
    rs = (H - C) * (H - O) + (L - C) * (L - O)
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    so2 = on.rolling(window).var(); sc2 = oc.rolling(window).var(); srs = rs.rolling(window).mean()
    return so2 + k * sc2 + (1 - k) * srs


def rolling_realised(daily_var: pd.Series, window: int, ann: int) -> pd.Series:
    """annualised realised vol over a trailing window of daily variances"""
    return np.sqrt(daily_var.rolling(window).mean() * ann)


def forward_realised(daily_var: pd.Series, window: int, ann: int) -> pd.Series:
    """annualised realised vol over the NEXT `window` days (aligned to the day the forecast is made, exclusive)"""
    fwd = daily_var[::-1].rolling(window).mean()[::-1].shift(-1)
    return np.sqrt(fwd * ann)


def intraday_measures(closes: pd.Series, bars_per_day: int | None = None, tz_day: str = "D") -> pd.DataFrame:
    """closes: intraday close series with a DatetimeIndex.  Returns per-day RV, BV, TQ, n, the BNS z statistic, the
    jump indicator and the jump variation, in daily variance units (per-bar returns summed over the day)."""
    r = np.log(closes.astype(float)).diff().dropna()
    day = r.index.floor(tz_day)
    df = pd.DataFrame({"r": r.values, "day": day})
    df["r_lag"] = df.groupby("day")["r"].shift(1); df["r_lag2"] = df.groupby("day")["r"].shift(2)
    df["ar"] = df["r"].abs(); df["ar1"] = df["r_lag"].abs(); df["ar2"] = df["r_lag2"].abs()
    g = df.groupby("day")
    rv = g["r"].apply(lambda x: float(np.sum(x ** 2)))
    bv = g.apply(lambda x: float(np.nansum(x["ar"] * x["ar1"])) / MU1 ** 2, include_groups=False)
    tq = g.apply(lambda x: float(np.nansum((x["ar"] * x["ar1"] * x["ar2"]) ** (4 / 3))), include_groups=False)
    n = g.size()
    tq = tq * n / MU43 ** 3
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (rv - bv) / rv
        denom = np.sqrt((np.pi ** 2 / 4 + np.pi - 5) / n * np.maximum(1.0, tq / bv ** 2))
        z = ratio / denom
    out = pd.DataFrame({"rv": rv, "bv": bv, "tq": tq, "n": n, "z_bns": z})
    out["jump"] = out["z_bns"] > 1.96
    out["jv"] = np.where(out["jump"], np.maximum(out["rv"] - out["bv"], 0.0), 0.0)
    out["cv"] = out["rv"] - out["jv"]
    if bars_per_day:
        out = out[out["n"] >= 0.8 * bars_per_day]
    return out
