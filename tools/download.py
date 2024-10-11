#!/usr/bin/env python3
"""Free data for the volatility-dynamics research.   python tools/download.py <what...> [--from 2016-01-01]

what: deribit   every BTC and ETH option trade since the first print (Nov 2016 / Mar 2019), month by month, in the same
                parquet layout as ProjectH; months ProjectH has already downloaded are copied from ../ProjectH
                                                                                     -> data/raw/deribit/trades_<CCY>_<YYYYMM>.parquet
      dvol      Deribit DVOL (30-day implied vol index) daily and hourly, BTC and ETH  -> data/raw/deribit/dvol_<CCY>.json
      candles   5-minute BTC-PERPETUAL and ETH-PERPETUAL candles from the history host  -> data/raw/deribit/candles_<CCY>_<YYYY>.parquet
      cboe      VIX, VIX9D, VIX3M, VIX6M, VIX1D, VVIX, SKEW, VXN, RVX, VXD, GVZ, OVX, VXTLT, VXEEM, VXAPL, VXAZN, VXGOG,
                VXIBM, VXGS daily histories                                             -> data/raw/cboe/<name>.csv
      vx        VX futures daily settlement files per contract, 2013 to 2027             -> data/raw/cboe/vx/VX_<expiry>.csv
      volhist   DoltHub post-no-preference/options volatility_history per symbol          -> data/raw/dolt/volhist_<SYM>.jsonl
      chains    DoltHub option_chain for SPY on every date the table has, and for the earnings names on the dates
                around each earnings date                                                -> data/raw/dolt/chains_<SYM>.jsonl
      earnings  DoltHub post-no-preference/earnings earnings_calendar per symbol           -> data/raw/dolt/earnings_<SYM>.jsonl
      prices    Yahoo daily bars for the underlyings                                     -> data/reference/prices.parquet
      rates     SOFR and EFFR from the New York Fed                                      -> data/reference/rates.csv
      all
Everything is incremental: a month, a file or a date already on disk is not fetched again."""
import csv
import datetime as dt
import glob
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw"); REF = os.path.join(ROOT, "data", "reference")
SIBLING_H = os.path.join(os.path.dirname(ROOT), "ProjectH", "data", "raw", "deribit")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
HIST = "https://history.deribit.com/api/v2/public"
LIVE = "https://www.deribit.com/api/v2/public"
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
CBOE_INDICES = ["VIX", "VIX9D", "VIX3M", "VIX6M", "VIX1D", "VVIX", "SKEW", "VXN", "RVX", "VXD", "GVZ", "OVX", "VXTLT", "VXEEM", "VXAPL", "VXAZN", "VXGOG", "VXIBM", "VXGS"]
FIRST_TRADE = {"BTC": dt.date(2016, 11, 1), "ETH": dt.date(2019, 3, 1)}
PERP_START = {"BTC": 2018, "ETH": 2019}
# the DoltHub universe: SPY and the sector ETF the table carries, the five names with a Cboe vol index, and liquid large caps with quarterly earnings
EARNINGS_NAMES = ["AAPL", "AMZN", "GOOGL", "IBM", "GS", "MSFT", "META", "NVDA", "TSLA", "NFLX", "AMD", "INTC", "JPM", "BAC", "WMT", "HD", "DIS", "BA", "XOM", "CVX", "PFE", "JNJ", "UNH", "KO", "PEP", "MCD", "NKE", "CRM", "ORCL", "CSCO", "ADBE", "QCOM", "COST", "V", "MA", "CAT", "GE", "T", "VZ", "SBUX", "LLY", "MRK", "ABBV", "PYPL", "AVGO", "TXN", "MU", "UBER", "SQ", "SHOP"]
VOLHIST_NAMES = ["SPY", "XLF"] + EARNINGS_NAMES
PRICE_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "GLD", "USO", "TLT", "EEM", "XLF", "^GSPC", "^NDX", "^RUT", "^DJI", "^VIX"] + EARNINGS_NAMES


def get(url, retries=4, timeout=90):
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            if e.code == 429:
                time.sleep(10 * (k + 1)); continue
            if k == retries - 1:
                return None
            time.sleep(2 * (k + 1))
        except Exception:  # noqa: BLE001
            if k == retries - 1:
                return None
            time.sleep(2 * (k + 1))


def jget(url, **kw):
    raw = get(url, **kw)
    return json.loads(raw) if raw else None


def log(msg):
    print(msg, flush=True)


# ---- Deribit ------------------------------------------------------------------------------------------------------------------
TRADE_COLS = ["timestamp", "trade_id", "trade_seq", "instrument_name", "price", "mark_price", "iv", "index_price", "direction", "amount", "contracts", "tick_direction", "block_trade_id", "liquidation"]


def write_trades(rows, p):
    import pyarrow as pa
    import pyarrow.parquet as pq
    seen = set(); uniq = []
    for r in rows:
        if r[1] in seen:
            continue
        seen.add(r[1]); uniq.append(r)
    c = list(zip(*uniq))
    table = pa.table({"timestamp": pa.array(c[0], pa.int64()), "trade_id": pa.array([str(v) for v in c[1]]), "trade_seq": pa.array(c[2], pa.int64()), "instrument_name": pa.array(c[3]), "price": pa.array(c[4], pa.float64()), "mark_price": pa.array(c[5], pa.float64()), "iv": pa.array(c[6], pa.float64()), "index_price": pa.array(c[7], pa.float64()), "direction": pa.array(c[8]), "amount": pa.array(c[9], pa.float64()), "contracts": pa.array([float(v) if v is not None else None for v in c[10]], pa.float64()), "tick_direction": pa.array(c[11], pa.int64()), "block_trade_id": pa.array([str(v) if v is not None else None for v in c[12]]), "liquidation": pa.array([str(v) if v is not None else None for v in c[13]])})
    pq.write_table(table, p, compression="zstd")


def deribit_trades(currency, start=None, end=None):
    """all option trades by month, paginated by time; a month ProjectH already holds is copied instead of fetched"""
    out_dir = os.path.join(RAW, "deribit"); os.makedirs(out_dir, exist_ok=True)
    start = start or FIRST_TRADE[currency]; end = end or dt.date.today()
    y, m = start.year, start.month
    while dt.date(y, m, 1) <= end:
        p = os.path.join(out_dir, f"trades_{currency}_{y}{m:02d}.parquet")
        m_end = dt.date(y + (m == 12), m % 12 + 1, 1); complete = m_end <= end
        if os.path.exists(p) and complete:
            y, m = (y + 1, 1) if m == 12 else (y, m + 1); continue
        sib = os.path.join(SIBLING_H, os.path.basename(p))
        if complete and os.path.exists(sib):
            shutil.copy2(sib, p); log(f"  trades {currency} {y}-{m:02d}: copied from ProjectH"); y, m = (y + 1, 1) if m == 12 else (y, m + 1); continue
        t0 = int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        t1 = int(dt.datetime(m_end.year, m_end.month, m_end.day, tzinfo=dt.timezone.utc).timestamp() * 1000) - 1
        rows = []; cur = t0; calls = 0; t_start = time.time()
        while True:
            u = f"{HIST}/get_last_trades_by_currency_and_time?currency={currency}&kind=option&start_timestamp={cur}&end_timestamp={t1}&count=1000&sorting=asc"
            d = jget(u); calls += 1
            if not d or "result" not in d:
                time.sleep(5); d = jget(u)
                if not d or "result" not in d:
                    log(f"  giving up at {cur}"); break
            tr = d["result"]["trades"]
            if not tr:
                break
            for x in tr:
                rows.append(tuple(x.get(c) for c in TRADE_COLS))
            last = tr[-1]["timestamp"]
            if not d["result"].get("has_more") or last >= t1:
                break
            cur = last + 1 if last > cur else cur + 1
            time.sleep(0.05)
        if rows:
            write_trades(rows, p)
        log(f"  trades {currency} {y}-{m:02d}: {len(rows)} rows, {calls} calls, {time.time() - t_start:.0f}s")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def dvol(currency):
    os.makedirs(os.path.join(RAW, "deribit"), exist_ok=True); out = {}
    for res in ("1D", "3600"):
        rows = {}; t0 = int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); cur_end = int(time.time() * 1000)
        while cur_end > t0:
            d = jget(f"{LIVE}/get_volatility_index_data?currency={currency}&start_timestamp={t0}&end_timestamp={cur_end}&resolution={res}")
            data = (d or {}).get("result", {}).get("data", [])
            if not data:
                break
            for r in data:
                rows[r[0]] = r
            oldest = min(r[0] for r in data)
            if oldest <= t0 or len(data) < 2:
                break
            cur_end = oldest - 1; time.sleep(0.1)
        out[res] = [rows[k] for k in sorted(rows)]
    p = os.path.join(RAW, "deribit", f"dvol_{currency}.json"); json.dump(out, open(p, "w"))
    log(f"dvol {currency}: {len(out.get('1D', []))} days, {len(out.get('3600', []))} hours")


def candles(currency, resolution=5):
    """5-minute perpetual candles, one parquet per year; the current year is refreshed each call"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    os.makedirs(os.path.join(RAW, "deribit"), exist_ok=True); today = dt.date.today()
    for year in range(PERP_START[currency], today.year + 1):
        p = os.path.join(RAW, "deribit", f"candles_{currency}_{year}.parquet")
        if os.path.exists(p) and year < today.year:
            continue
        rows = []; d0 = dt.date(year, 1, 1); t_start = time.time()
        while d0.year == year and d0 <= today:
            d1 = min(d0 + dt.timedelta(days=10), dt.date(year + 1, 1, 1))
            a = int(dt.datetime(d0.year, d0.month, d0.day, tzinfo=dt.timezone.utc).timestamp() * 1000); b = int(dt.datetime(d1.year, d1.month, d1.day, tzinfo=dt.timezone.utc).timestamp() * 1000) - 1
            d = jget(f"{HIST}/get_tradingview_chart_data?instrument_name={currency}-PERPETUAL&start_timestamp={a}&end_timestamp={b}&resolution={resolution}")
            r = (d or {}).get("result", {})
            if r.get("status") == "ok" and r.get("ticks"):
                rows += list(zip(r["ticks"], r["open"], r["high"], r["low"], r["close"], r["volume"]))
            d0 = d1; time.sleep(0.05)
        if rows:
            c = list(zip(*rows))
            pq.write_table(pa.table({"ts": pa.array(c[0], pa.int64()), "open": pa.array(c[1], pa.float64()), "high": pa.array(c[2], pa.float64()), "low": pa.array(c[3], pa.float64()), "close": pa.array(c[4], pa.float64()), "volume": pa.array(c[5], pa.float64())}), p, compression="zstd")
        log(f"  candles {currency} {year}: {len(rows)} bars, {time.time() - t_start:.0f}s")


# ---- Cboe --------------------------------------------------------------------------------------------------------------------------
def cboe():
    os.makedirs(os.path.join(RAW, "cboe"), exist_ok=True)
    for name in CBOE_INDICES:
        raw = get(f"{CBOE}/{name}_History.csv", timeout=60)
        if raw:
            open(os.path.join(RAW, "cboe", f"{name}.csv"), "wb").write(raw); log(f"  cboe {name}: {len(raw.splitlines())} lines")
        else:
            log(f"  cboe {name}: not available")


def third_friday(year, month):
    d = dt.date(year, month, 15)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def vx_expiries(y0=2013, y1=2027):
    """VX final settlement: the Wednesday 30 days before the third Friday of the following month (Cboe rule); a holiday
    on that Friday moves the settlement to the Tuesday, which the fallback in vx() catches"""
    out = []
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            out.append(third_friday(ny, nm) - dt.timedelta(days=30))
    return out


def vx():
    d_out = os.path.join(RAW, "cboe", "vx"); os.makedirs(d_out, exist_ok=True); n = 0; today = dt.date.today()
    for e in vx_expiries():
        p = os.path.join(d_out, f"VX_{e.isoformat()}.csv")
        if os.path.exists(p) and e < today - dt.timedelta(days=3):
            continue
        for cand in (e, e - dt.timedelta(days=1), e + dt.timedelta(days=1)):
            raw = get(f"https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{cand.isoformat()}.csv", retries=1, timeout=30)
            if raw and raw.startswith(b"Trade Date"):
                open(os.path.join(d_out, f"VX_{cand.isoformat()}.csv"), "wb").write(raw); n += 1; break
        time.sleep(0.1)
    log(f"vx: {n} contract files fetched, {len(glob.glob(os.path.join(d_out, '*.csv')))} on disk")


# ---- DoltHub -------------------------------------------------------------------------------------------------------------------------
def dolt_query(db, sql, timeout=180):
    u = f"https://www.dolthub.com/api/v1alpha1/post-no-preference/{db}/master?q=" + urllib.parse.quote(sql)
    d = jget(u, timeout=timeout)
    if not d or d.get("query_execution_status") not in ("Success", "RowLimit"):
        return None
    return d.get("rows", [])


def dolt_all(db, table, where, page=1000, tries=4):
    """page through the 1000-row API cap by keyset on the date column (OFFSET queries hit the server's deadline);
    each page is retried, with a pause, when the server times out"""
    rows = []; last = None
    while True:
        cond = where + (f" AND date > '{last}'" if last else "")
        r = None
        for k in range(tries):
            r = dolt_query(db, f"SELECT * FROM {table} WHERE {cond} ORDER BY date LIMIT {page}", timeout=120)
            if r is not None:
                break
            time.sleep(5 * (k + 1))
        if r is None:
            return None if not rows else rows
        rows += r
        if len(r) < page:
            return rows
        last = r[-1]["date"]; time.sleep(0.3)


def write_jsonl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def read_jsonl(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def volhist(symbols=VOLHIST_NAMES):
    os.makedirs(os.path.join(RAW, "dolt"), exist_ok=True)
    for s in symbols:
        p = os.path.join(RAW, "dolt", f"volhist_{s}.jsonl")
        have = read_jsonl(p)
        if have and max(r["date"] for r in have) >= (dt.date.today() - dt.timedelta(days=3)).isoformat():
            continue
        rows = dolt_all("options", "volatility_history", f"act_symbol='{s}'")
        if rows is not None:
            write_jsonl(p, rows); log(f"  volhist {s}: {len(rows)} rows")
        else:
            log(f"  volhist {s}: failed")
        time.sleep(0.2)


def earnings(symbols=EARNINGS_NAMES):
    os.makedirs(os.path.join(RAW, "dolt"), exist_ok=True)
    for s in symbols:
        p = os.path.join(RAW, "dolt", f"earnings_{s}.jsonl")
        if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < 7 * 86400:
            continue
        rows = dolt_all("earnings", "earnings_calendar", f"act_symbol='{s}'")
        if rows is not None:
            write_jsonl(p, rows); log(f"  earnings {s}: {len(rows)} rows")
        else:
            log(f"  earnings {s}: failed")
        time.sleep(0.2)


def chain_dates_for(symbol):
    """the dates the option_chain table plausibly has for the symbol: the volatility_history dates"""
    return sorted({r["date"] for r in read_jsonl(os.path.join(RAW, "dolt", f"volhist_{symbol}.jsonl"))})


def chains(symbols=None, window=(-6, 3)):
    """SPY on every candidate date; earnings names on candidate dates within `window` business days of an earnings date"""
    os.makedirs(os.path.join(RAW, "dolt"), exist_ok=True)
    symbols = symbols or (["SPY"] + EARNINGS_NAMES)
    for s in symbols:
        p = os.path.join(RAW, "dolt", f"chains_{s}.jsonl")
        have = {r["date"] for r in read_jsonl(p)}
        tried_p = p + ".tried"; tried = set(open(tried_p).read().split()) if os.path.exists(tried_p) else set()
        cands = chain_dates_for(s)
        if s != "SPY":
            ev = [dt.date.fromisoformat(r["date"]) for r in read_jsonl(os.path.join(RAW, "dolt", f"earnings_{s}.jsonl"))]
            keep = set()
            for e in ev:
                for k in range(window[0], window[1] + 1):
                    keep.add((e + dt.timedelta(days=k)).isoformat())
                    keep.add((e + dt.timedelta(days=k - 2)).isoformat())     # weekends: the table's early dates are Saturdays
            cands = [d for d in cands if d in keep]
        todo = [d for d in cands if d not in have and d not in tried]
        n = 0; t0 = time.time()
        with open(p, "a", encoding="utf-8") as f, open(tried_p, "a") as ft:
            for d in todo:
                rows = dolt_query("options", f"SELECT * FROM option_chain WHERE act_symbol='{s}' AND date='{d}'", timeout=60)
                if rows:
                    for r in rows:
                        f.write(json.dumps(r) + "\n")
                    n += len(rows); f.flush()
                if rows is not None:
                    ft.write(d + "\n"); ft.flush()
                time.sleep(0.15)
        log(f"  chains {s}: {len(todo)} dates queried, +{n} rows ({time.time() - t0:.0f}s)")


# ---- Yahoo and the New York Fed -------------------------------------------------------------------------------------------------------
def prices(symbols=PRICE_SYMBOLS):
    import pyarrow as pa
    import pyarrow.parquet as pq
    os.makedirs(REF, exist_ok=True); bars = []; divs = []
    for sym in symbols:
        raw = get(f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=20y&interval=1d&events=div,splits", timeout=60)
        if not raw:
            log(f"  no data {sym}"); continue
        try:
            r = json.loads(raw)["chart"]["result"][0]
        except Exception:  # noqa: BLE001
            log(f"  bad data {sym}"); continue
        ts = r.get("timestamp") or []; q = r["indicators"]["quote"][0]; adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose", [None] * len(ts))
        for i, t in enumerate(ts):
            if q["close"][i] is None:
                continue
            bars.append((sym, dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), q["open"][i] or q["close"][i], q["high"][i] or q["close"][i], q["low"][i] or q["close"][i], q["close"][i], (adj[i] if i < len(adj) and adj[i] is not None else q["close"][i]), q["volume"][i] or 0))
        for t, e in (r.get("events", {}).get("dividends") or {}).items():
            divs.append((sym, dt.datetime.fromtimestamp(int(e.get("date", t)), dt.timezone.utc).date().isoformat(), e["amount"]))
        time.sleep(0.3)
    c = list(zip(*bars))
    pq.write_table(pa.table({"symbol": c[0], "date": c[1], "open": pa.array(c[2], pa.float64()), "high": pa.array(c[3], pa.float64()), "low": pa.array(c[4], pa.float64()), "close": pa.array(c[5], pa.float64()), "adjclose": pa.array(c[6], pa.float64()), "volume": pa.array(c[7], pa.float64())}), os.path.join(REF, "prices.parquet"), compression="zstd")
    with open(os.path.join(REF, "dividends.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["symbol", "ex_date", "amount"]); w.writerows(sorted(divs))
    log(f"prices: {len(bars)} bars, {len(divs)} dividends, {len(set(c[0]))} symbols")


def rates():
    os.makedirs(REF, exist_ok=True); rows = {}
    for name, url in (("SOFR", "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate=2018-04-01&endDate=2030-12-31"), ("EFFR", "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2016-01-01&endDate=2030-12-31")):
        d = jget(url, timeout=60)
        for r in (d or {}).get("refRates", []):
            rows.setdefault(r["effectiveDate"], {})[name] = float(r["percentRate"])
    with open(os.path.join(REF, "rates.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["date", "SOFR", "EFFR"])
        for d in sorted(rows):
            w.writerow([d, rows[d].get("SOFR", ""), rows[d].get("EFFR", "")])
    log(f"rates: {len(rows)} days")


if __name__ == "__main__":
    a = sys.argv[1:]; what = [x for x in a if not x.startswith("--")]
    start = dt.date.fromisoformat(a[a.index("--from") + 1]) if "--from" in a else None
    ccys = [a[a.index("--currency") + 1]] if "--currency" in a else ["BTC", "ETH"]
    if "deribit" in what or "all" in what:
        for c in ccys:
            deribit_trades(c, start)
    if "dvol" in what or "all" in what:
        for c in ccys:
            dvol(c)
    if "candles" in what or "all" in what:
        for c in ccys:
            candles(c)
    if "cboe" in what or "all" in what:
        cboe()
    if "vx" in what or "all" in what:
        vx()
    if "volhist" in what or "all" in what:
        volhist()
    if "earnings" in what or "all" in what:
        earnings()
    if "chains" in what or "all" in what:
        chains()
    if "prices" in what or "all" in what:
        prices()
    if "rates" in what or "all" in what:
        rates()
    log("done")
