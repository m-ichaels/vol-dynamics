"""What one end-of-day chain slice needs before it can be used: the implied forward and discount factor from put-call
parity across the strikes (Project H's regression with the SOFR prior), implied vols from mids on that forward, and
the ATM straddle."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .surface import forward_from_parity, implied_vol


def expiry_forward(g: pd.DataFrame, S: float, T: float, r_prior: float) -> tuple[float, float, str]:
    """g: one date's rows of one expiry with strike, cp, mid, spread.  Returns (F, df, how)."""
    c = g[g["cp"] > 0].set_index("strike")["mid"]; p = g[g["cp"] < 0].set_index("strike")["mid"]
    ks = c.index.intersection(p.index)
    ks = ks[(ks > 0.85 * S) & (ks < 1.15 * S)]
    if len(ks) < 2:
        return S * np.exp(r_prior * T), float(np.exp(-r_prior * T)), "spot"
    sp = g.set_index(["strike", "cp"])["spread"]
    spread = np.array([sp.get((k, 1.0), np.nan) + sp.get((k, -1.0), np.nan) for k in ks])
    F, df, how = forward_from_parity(ks.values, c.loc[ks].values, p.loc[ks].values, T, r_prior, np.where(np.isfinite(spread), spread, np.nanmedian(spread) if np.isfinite(spread).any() else 1.0))
    if not np.isfinite(F) or abs(F / S - 1) > 0.05:
        return S * np.exp(r_prior * T), float(np.exp(-r_prior * T)), "spot"
    return float(F), float(df), how


def with_vols(g: pd.DataFrame, F: float, df: float) -> pd.DataFrame:
    """implied vols from the mids on the parity forward (the vendor's `vol` column is kept as vol_vendor)"""
    g = g.copy()
    g["vol_vendor"] = g["vol"]
    g["iv"] = implied_vol(g["mid"].values, F, g["strike"].values, g["T"].values, g["cp"].values, df)
    return g


def atm_straddle(g: pd.DataFrame, F: float, df: float, S: float):
    """the strike nearest the forward with both legs quoted: mids, bids, asks, the two implied vols"""
    c = g[g["cp"] > 0].set_index("strike"); p = g[g["cp"] < 0].set_index("strike")
    ks = c.index.intersection(p.index)
    if len(ks) == 0:
        return None
    k = ks[np.argmin(np.abs(ks.values - F))]
    if abs(k / F - 1) > 0.04:
        return None
    rc, rp = c.loc[k], p.loc[k]
    if not (rc["bid"] > 0 and rp["bid"] > 0 and np.isfinite(rc["ask"]) and np.isfinite(rp["ask"])):
        return None
    T = float(g["T"].iloc[0])
    ivc = float(implied_vol(rc["mid"], F, k, T, 1.0, df)); ivp = float(implied_vol(rp["mid"], F, k, T, -1.0, df))
    if not (np.isfinite(ivc) and np.isfinite(ivp)):
        return None
    iv = 0.5 * (ivc + ivp)
    return {"K": float(k), "T": T, "F": F, "df": df, "iv": iv, "iv_c": ivc, "iv_p": ivp, "w": iv * iv * T, "mid": float(rc["mid"] + rp["mid"]), "bid": float(rc["bid"] + rp["bid"]), "ask": float(rc["ask"] + rp["ask"]),
            "spread": float(rc["spread"] + rp["spread"]), "legs": {1.0: rc, -1.0: rp}}
