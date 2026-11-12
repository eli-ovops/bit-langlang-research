#!/usr/bin/env python3
"""从 Binance USDT-M 永续拉取 K 线与资金费率（断点续传）。

用法:
  python3 scripts/02_download_market.py --symbols BTC ETH SOL PEPE PEOPLE WLD APT --intervals 5m 1h 4h 1d
输出:
  data/market/<SYMBOL>USDT_<interval>.csv.gz   (ts, open, high, low, close, volume, turnover)
  data/market/<SYMBOL>USDT_funding.csv.gz      (ts, funding_rate)
"""
import argparse, gzip, json, os, sys, time
import pandas as pd
import requests

BASE = "https://fapi.binance.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "market")
os.makedirs(OUT, exist_ok=True)
START_MS = int(pd.Timestamp("2022-01-01", tz="UTC").timestamp() * 1000)

SPECIAL = {"PEPE": "1000PEPE", "SHIB": "1000SHIB", "BONK": "1000BONK", "FLOKI": "1000FLOKI"}

def to_symbol(base):
    return SPECIAL.get(base.upper(), base.upper()) + "USDT"

S = requests.Session()
S.headers.update({"User-Agent": "bitlanglang-research/1.0"})

def get(path, params, tries=5):
    for i in range(tries):
        try:
            r = S.get(BASE + path, params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                time.sleep(wait + 2); continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")

def onboard_map():
    info = get("/fapi/v1/exchangeInfo", {})
    return {s["symbol"]: s.get("onboardDate", 0) for s in info["symbols"]}

def last_ts(path):
    if not os.path.exists(path): return None
    try:
        with gzip.open(path, "rt") as f:
            last = None
            for line in f:
                last = line
        if last is None or last.startswith("ts,"): return None
        return int(last.split(",")[0])
    except Exception:
        return None

def download_klines(symbol, interval, start_ms, end_ms):
    path = os.path.join(OUT, f"{symbol}_{interval}.csv.gz")
    last = last_ts(path)
    if last:
        start_ms = max(start_ms, last + 1)
    if start_ms >= end_ms:
        print(f"[skip] {symbol} {interval} up to date"); return

    mode = "at" if last else "wt"
    n = 0
    with gzip.open(path, mode, newline="") as f:
        if mode == "wt":
            f.write("ts,open,high,low,close,volume,turnover\n")
        cur = start_ms
        while cur < end_ms:
            batch = get("/fapi/v1/klines", {"symbol": symbol, "interval": interval,
                                            "startTime": cur, "limit": 1000})
            if not batch:
                break
            rows = []
            for k in batch:
                rows.append(f"{k[0]},{k[1]},{k[2]},{k[3]},{k[4]},{k[5]},{k[7]}\n")
            f.write("".join(rows)); f.flush()
            n += len(rows)
            cur = batch[-1][0] + 1
            if len(batch) < 1000:
                break
            time.sleep(0.05)
    print(f"[ok] {symbol} {interval}: +{n} bars")

def download_funding(symbol, start_ms, end_ms):
    path = os.path.join(OUT, f"{symbol}_funding.csv.gz")
    last = last_ts(path)
    if last: start_ms = max(start_ms, last + 1)
    if start_ms >= end_ms:
        print(f"[skip] {symbol} funding up to date"); return
    mode = "at" if last else "wt"
    n = 0
    with gzip.open(path, mode, newline="") as f:
        if mode == "wt":
            f.write("ts,funding_rate\n")
        cur = start_ms
        while cur < end_ms:
            batch = get("/fapi/v1/fundingRate", {"symbol": symbol, "startTime": cur, "limit": 1000})
            if not batch: break
            rows = [f"{int(x['fundingTime'])},{x['fundingRate']}\n" for x in batch]
            f.write("".join(rows)); f.flush()
            n += len(rows)
            cur = int(batch[-1]["fundingTime"]) + 1
            if len(batch) < 1000: break
            time.sleep(0.05)
    print(f"[ok] {symbol} funding: +{n}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL", "PEPE", "PEOPLE", "WLD", "APT"])
    ap.add_argument("--intervals", nargs="+", default=["5m", "1h", "4h", "1d"])
    ap.add_argument("--skip-funding", action="store_true")
    a = ap.parse_args()
    end_ms = int(time.time() * 1000)
    onb = onboard_map()
    for base in a.symbols:
        sym = to_symbol(base)
        if sym not in onb:
            print(f"[warn] {sym} not listed on Binance futures; skip"); continue
        start = max(START_MS, int(onb[sym]) if onb.get(sym) else START_MS)
        print(f"=== {sym} start={pd.to_datetime(start, unit='ms', utc=True)}")
        for iv in a.intervals:
            download_klines(sym, iv, start, end_ms)
        if not a.skip_funding:
            download_funding(sym, start, end_ms)

if __name__ == "__main__":
    main()
