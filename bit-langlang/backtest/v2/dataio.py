#!/usr/bin/env python3
"""数据 IO：5m / 1d K 线 + 资金费。只读 data/market，不写任何行情文件。"""
from __future__ import annotations

import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MARKET = os.path.join(ROOT, "data", "market")

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "PEOPLEUSDT",
    "TRBUSDT", "WLDUSDT", "APTUSDT", "ORDIUSDT", "1000PEPEUSDT",
]

MAJORS = {"BTCUSDT", "ETHUSDT"}


def load_ohlcv(symbol: str, interval: str) -> pd.DataFrame | None:
    path = os.path.join(MARKET, f"{symbol}_{interval}.csv.gz")
    if not os.path.exists(path):
        return None
    d = pd.read_csv(path, usecols=["ts", "open", "high", "low", "close", "volume"])
    # 统一为 naive UTC（报告中所有时间均为 UTC）
    d["ts"] = pd.to_datetime(d["ts"], unit="ms", utc=True).dt.tz_localize(None)
    d = d.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return d


def load_funding(symbol: str, clip: float) -> pd.DataFrame:
    """返回 ts / funding_rate；单次费率截断到 ±clip，防止异常值主导成本。"""
    path = os.path.join(MARKET, f"{symbol}_funding.csv.gz")
    if not os.path.exists(path):
        return pd.DataFrame(columns=["ts", "funding_rate"])
    d = pd.read_csv(path)
    d = d[["ts", "funding_rate"]].dropna()
    d["ts"] = pd.to_datetime(d["ts"], unit="ms", utc=True).dt.tz_localize(None)
    d = d.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    d["funding_rate"] = d["funding_rate"].clip(-clip, clip)
    return d


def load_symbol(symbol: str, clip: float) -> dict:
    return {
        "symbol": symbol,
        "d5": load_ohlcv(symbol, "5m"),
        "d1": load_ohlcv(symbol, "1d"),
        "funding": load_funding(symbol, clip),
    }
