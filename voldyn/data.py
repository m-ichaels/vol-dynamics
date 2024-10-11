"""Loaders for everything tools/download.py fetches, and the DuckDB database of views for the post-trade SQL.

Underlying map: each implied-vol series (a Cboe index or Deribit DVOL) is paired with the price series whose realised
variance it prices.  The Cboe indices are model-free 30-day implied vols of the index options; the ETF is the tradable
proxy and the index itself the realised-variance leg where one exists."""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re

import duckdb
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw"); REF = os.path.join(ROOT, "data", "reference"); DER = os.path.join(ROOT, "data", "derived"); RES = os.path.join(ROOT, "results")
DB_PATH = os.path.join(DER, "voldyn.duckdb")

# implied-vol index -> (realised-variance underlying, tradable proxy, asset class, label)
IV_MAP = {
    "VIX": ("^GSPC", "SPY", "equity index", "S&P 500"),
    "VXN": ("^NDX", "QQQ", "equity index", "Nasdaq-100"),
    "RVX": ("^RUT", "IWM", "equity index", "Russell 2000"),
    "VXD": ("^DJI", "DIA", "equity index", "Dow Jones"),
    "VXEEM": ("EEM", "EEM", "equity index", "EM equities (EEM)"),
    "VXTLT": ("TLT", "TLT", "rates", "20y+ Treasuries (TLT)"),
    "GVZ": ("GLD", "GLD", "commodity", "gold (GLD)"),
    "OVX": ("USO", "USO", "commodity", "crude oil (USO)"),
    "VXAPL": ("AAPL", "AAPL", "single name", "Apple"),
    "VXAZN": ("AMZN", "AMZN", "single name", "Amazon"),
    "VXGOG": ("GOOGL", "GOOGL", "single name", "Alphabet"),
    "VXIBM": ("IBM", "IBM", "single name", "IBM"),
    "VXGS": ("GS", "GS", "single name", "Goldman Sachs"),
    "DVOL_BTC": ("BTC", "BTC", "crypto", "Bitcoin (30d ATM from prints)"),
    "DVOL_ETH": ("ETH", "ETH", "crypto", "Ether (30d ATM from prints)"),
    "DVOLX_BTC": ("BTC", "BTC", "crypto", "Bitcoin (DVOL index, 2021+)"),
    "DVOLX_ETH": ("ETH", "ETH", "crypto", "Ether (DVOL index, 2021+)"),
}
TERM = ["VIX1D", "VIX9D", "VIX", "VIX3M", "VIX6M"]
TERM_DAYS = {"VIX1D": 1, "VIX9D": 9, "VIX": 30, "VIX3M": 93, "VIX6M": 184}
MONTHS = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
NAME_RE = re.compile(r"^([A-Z]+)-(\d{1,2})([A-Z]{3})(\d{2})-(\d+(?:d\d+)?)-([CP])$")
EXPIRY_HOUR_UTC = 8


def sql_path(p: str) -> str:
    return p.replace(os.sep, "/").replace("'", "''")


# ---- Cboe -----------------------------------------------------------------------------------------------------------------------
def load_cboe(name: str) -> pd.Series:
    """daily close of a Cboe index (per cent vol points), indexed by date"""
    p = os.path.join(RAW, "cboe", f"{name}.csv")
    df = pd.read_csv(p)
    df.columns = [c.strip().upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"])
    col = "CLOSE" if "CLOSE" in df.columns else df.columns[-1]
    s = pd.to_numeric(df[col], errors="coerce")
    return pd.Series(s.values, index=df["DATE"], name=name).dropna().sort_index()


def load_cboe_all(names=None) -> pd.DataFrame:
    names = names or [os.path.basename(p)[:-4] for p in glob.glob(os.path.join(RAW, "cboe", "*.csv"))]
    return pd.concat([load_cboe(n) for n in names], axis=1).sort_index()


def load_vx() -> pd.DataFrame:
    """every VX contract's daily settlement rows: date, expiry, settle, close, volume, open_interest"""
    rows = []
    for p in sorted(glob.glob(os.path.join(RAW, "cboe", "vx", "VX_*.csv"))):
        exp = pd.Timestamp(os.path.basename(p)[3:13])
        df = pd.read_csv(p)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df.rename(columns={"trade_date": "date"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce"); df["expiry"] = exp
        for c in ("open", "high", "low", "close", "settle", "total_volume", "open_interest"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        rows.append(df[["date", "expiry", "open", "high", "low", "close", "settle", "total_volume", "open_interest"]])
    vx = pd.concat(rows, ignore_index=True).dropna(subset=["date"])
    vx = vx[(vx["settle"] > 0) & (vx["date"] <= vx["expiry"])]
    return vx.sort_values(["date", "expiry"]).reset_index(drop=True)


# ---- prices and rates --------------------------------------------------------------------------------------------------------------
def load_prices() -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(REF, "prices.parquet")); df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def price_panel(field: str = "adjclose") -> pd.DataFrame:
    p = load_prices()
    return p.pivot(index="date", columns="symbol", values=field).sort_index()


def ohlc(symbol: str) -> pd.DataFrame:
    p = load_prices(); g = p[p["symbol"] == symbol].set_index("date")[["open", "high", "low", "close", "adjclose", "volume"]]
    # Yahoo's adjusted close carries the dividends; scale OHLC by adj/close so that estimators see a consistent path
    f = g["adjclose"] / g["close"]
    out = pd.DataFrame({c: g[c] * f for c in ("open", "high", "low", "close")}); out["volume"] = g["volume"]
    return out[(out > 0).all(axis=1) | (out["volume"] >= 0)].dropna()


def load_rates() -> pd.Series:
    r = pd.read_csv(os.path.join(REF, "rates.csv")); r["date"] = pd.to_datetime(r["date"])
    s = r.set_index("date")["SOFR"].astype(float)
    e = r.set_index("date")["EFFR"].astype(float)
    return (s.fillna(e) / 100.0).sort_index()


def load_dividends() -> pd.DataFrame:
    d = pd.read_csv(os.path.join(REF, "dividends.csv")); d["ex_date"] = pd.to_datetime(d["ex_date"]); return d


# ---- Deribit ---------------------------------------------------------------------------------------------------------------------
def parse_instrument(name: str):
    m = NAME_RE.match(name)
    if not m:
        return None
    cur, d, mon, y, k, cp = m.groups()
    exp = dt.datetime(2000 + int(y), MONTHS[mon], int(d), EXPIRY_HOUR_UTC, tzinfo=dt.timezone.utc)
    return cur, exp, float(k.replace("d", ".")), 1.0 if cp == "C" else -1.0


def trade_files(currency: str) -> list:
    return sorted(glob.glob(os.path.join(RAW, "deribit", f"trades_{currency}_*.parquet")))


def load_trades(currency: str, months: list | None = None, columns: list | None = None) -> pd.DataFrame:
    files = trade_files(currency)
    if months:
        files = [f for f in files if any(f.endswith(f"_{m}.parquet") for m in months)]
    if not files:
        return pd.DataFrame()
    con = duckdb.connect()
    cols = "*" if not columns else ", ".join(columns)
    df = con.execute(f"select {cols} from read_parquet([{', '.join(chr(39) + sql_path(f) + chr(39) for f in files)}], union_by_name=true) order by timestamp").df(); con.close()
    return df


def add_instrument_columns(df: pd.DataFrame, col: str = "instrument_name") -> pd.DataFrame:
    names = df[col].unique(); parsed = {n: parse_instrument(n) for n in names}
    df = df.copy()
    df["expiry_ms"] = df[col].map(lambda n: int(parsed[n][1].timestamp() * 1000) if parsed[n] else 0)
    df["strike"] = df[col].map(lambda n: parsed[n][2] if parsed[n] else np.nan)
    df["cp"] = df[col].map(lambda n: parsed[n][3] if parsed[n] else np.nan)
    df["T"] = (df["expiry_ms"] - df["timestamp"]) / (365.0 * 86400e3)
    return df


def load_dvol(currency: str, resolution: str = "1D") -> pd.Series:
    d = json.load(open(os.path.join(RAW, "deribit", f"dvol_{currency}.json"), encoding="utf-8"))
    df = pd.DataFrame(d[resolution], columns=["ts", "open", "high", "low", "close"])
    idx = pd.DatetimeIndex(pd.to_datetime(df["ts"], unit="ms", utc=True)).tz_convert(None)
    s = pd.Series(df["close"].values, index=idx, name=f"DVOL_{currency}")
    if resolution == "1D":
        s.index = s.index.normalize()
    return s.sort_index()


def load_candles(currency: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(RAW, "deribit", f"candles_{currency}_*.parquet")))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert(None)
    return df.drop_duplicates("ts").sort_values("ts").set_index("time")[["open", "high", "low", "close", "volume"]]


def crypto_daily(currency: str) -> pd.DataFrame:
    """daily OHLC of the perpetual at 00:00 UTC from the 5-minute candles"""
    c = load_candles(currency)
    d = c.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return d


# ---- DoltHub -----------------------------------------------------------------------------------------------------------------------
def read_jsonl(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_volhist(symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(read_jsonl(os.path.join(RAW, "dolt", f"volhist_{symbol}.jsonl")))
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for c in df.columns:
        if c.startswith(("hv_", "iv_")) and not c.endswith("_date"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def load_chains(symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(read_jsonl(os.path.join(RAW, "dolt", f"chains_{symbol}.jsonl")))
    if df.empty:
        return df
    for c in ("strike", "bid", "ask", "vol", "delta", "gamma", "theta", "vega", "rho"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]); df["expiration"] = pd.to_datetime(df["expiration"])
    df["cp"] = np.where(df["call_put"].str.lower().str.startswith("c"), 1.0, -1.0)
    df["T"] = ((df["expiration"] - df["date"]).dt.days + 0.5) / 365.0
    df["mid"] = 0.5 * (df["bid"] + df["ask"]); df["spread"] = df["ask"] - df["bid"]
    return df.drop_duplicates(["date", "expiration", "strike", "cp"]).sort_values(["date", "expiration", "strike"]).reset_index(drop=True)


def load_earnings(symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(read_jsonl(os.path.join(RAW, "dolt", f"earnings_{symbol}.jsonl")))
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["after_close"] = df["when"].fillna("").str.lower().str.contains("after")
    df["before_open"] = df["when"].fillna("").str.lower().str.contains("before")
    return df.sort_values("date").reset_index(drop=True)


def chain_symbols() -> list:
    return sorted(os.path.basename(p)[7:-6] for p in glob.glob(os.path.join(RAW, "dolt", "chains_*.jsonl")))


def load_fomc() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(REF, "fomc.csv")); df["date"] = pd.to_datetime(df["decision_date"]); return df


# ---- DuckDB -----------------------------------------------------------------------------------------------------------------------
def connect(path: str = DB_PATH):
    os.makedirs(DER, exist_ok=True); con = duckdb.connect(path)
    def view(name, pattern):
        files = sorted(glob.glob(pattern))
        if files:
            con.execute(f"create or replace view {name} as select * from read_parquet([{', '.join(chr(39) + sql_path(f) + chr(39) for f in files)}], union_by_name=true)")
    view("deribit_trades", os.path.join(RAW, "deribit", "trades_*.parquet"))
    view("candles", os.path.join(RAW, "deribit", "candles_*.parquet"))
    for t in ("realised", "implied", "premia_daily", "strategy_trades", "strategy_daily", "events_earnings", "vx_curve"):
        view(t, os.path.join(DER, f"{t}.parquet"))
    return con
