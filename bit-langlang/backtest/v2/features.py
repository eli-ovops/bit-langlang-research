#!/usr/bin/env python3
"""特征层：日线（季节 + 结构）与 5m（ATR / 摆动低点）。

防未来函数约定
--------------
* 日线表按 UTC 自然日聚合；`day` 列 = 该日 00:00 UTC。
* 所有日线特征在加入 5m 前都 `.shift(1)`：`day=D` 行携带的是 D-1 收盘后才知道的信息。
* 季节布尔量先按 D-1 收盘计算，再 `.shift(1)`，等价于"D 日开盘时可见"。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def btc_regime(df1d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """BTC 日线"季节"代理：Spring/Summer 才允许开多。

    risk_on(D) = close(D-1) > EMA50(D-1) and EMA50(D-1) > EMA50(D-6) and close(D-1) > EMA200(D-1)
    该定义同时满足：一手问答"不做逆势/只看大级别"、规格 v0 §2.1 的 Spring+Summer 语义。
    """
    d = df1d.copy()
    d["day"] = d["ts"].dt.floor("D")
    d["ema_fast"] = ema(d["close"], cfg["ema_fast"])
    d["ema_slow"] = ema(d["close"], cfg["ema_slow"])
    d["ema_long"] = ema(d["close"], cfg["ema_long"])
    raw = (
        (d["close"] > d["ema_slow"])
        & (d["ema_slow"] > d["ema_slow"].shift(cfg["ema_slope_lb"]))
        & (d["close"] > d["ema_long"])
    )
    d["risk_on"] = raw.shift(1).fillna(False)
    # 归因用季节标签（同样只用 D-1 信息）
    state = np.where(
        d["close"] < d["ema_long"], "winter",
        np.where(raw, "spring_summer", "autumn"),
    )
    d["season"] = pd.Series(state, index=d.index).shift(1)
    return d[["day", "risk_on", "season"]]


def symbol_daily_uptrend(df1d: pd.DataFrame, n: int) -> pd.DataFrame:
    """标的自身日线趋势代理（可选结构过滤）：close(D-1) > EMA_n(D-1)。"""
    d = df1d.copy()
    d["day"] = d["ts"].dt.floor("D")
    e = ema(d["close"], n)
    d["sym_uptrend"] = (d["close"] > e).shift(1).fillna(False)
    return d[["day", "sym_uptrend"]]


def daily_structure(df1d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """日线支撑/阻力（全部 shift(1)）。

    sup_short / sup_long : 前 N 日最低（支撑 / 箱体下沿）
    res_short / res_mid / res_long : 前 N 日最高（阻力 / 前高 / 大级别前高）
    """
    d = df1d.copy()
    d["day"] = d["ts"].dt.floor("D")
    for name, n in (
        ("sup10", cfg["sup_short"]),
        ("sup20", cfg["sup_long"]),
    ):
        d[name] = d["low"].rolling(n, min_periods=n).min().shift(1)
    for name, n in (
        ("res20", cfg["res_short"]),
        ("res60", cfg["res_mid"]),
        ("res120", cfg["res_long"]),
    ):
        d[name] = d["high"].rolling(n, min_periods=n).max().shift(1)
    return d[["day", "sup10", "sup20", "res20", "res60", "res120"]]


def daily_features(df1d: pd.DataFrame, cfg_daily: dict) -> pd.DataFrame:
    d = daily_structure(df1d, cfg_daily)
    d = d.merge(symbol_daily_uptrend(df1d, cfg_daily["ema_symbol"]), on="day", how="left")
    return d


def intraday_features(d5: pd.DataFrame, cfg_entry: dict) -> pd.DataFrame:
    """5m 特征：真实波幅 ATR、前 24h 最低、前 20 根最高（追高过滤）、摆动低点。"""
    d = d5.copy()
    h, l, c = d["high"], d["low"], d["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(cfg_entry["atr_n"], min_periods=cfg_entry["atr_n"]).mean()
    d["sup24h"] = l.rolling(cfg_entry["sup_24h_bars"], min_periods=cfg_entry["sup_24h_bars"]).min().shift(1)
    d["hi20_prev"] = h.rolling(cfg_entry["chase_hi_lb"], min_periods=cfg_entry["chase_hi_lb"]).max().shift(1)
    d["swing_low"] = l.rolling(cfg_entry["swing_lb"], min_periods=cfg_entry["swing_lb"]).min()
    # 前一日最低（前 288 根全部走完，shift(288) 确保整日收盘后才可见）
    d["pdl"] = l.rolling(288, min_periods=288).min().shift(288)
    # 前 4h 摆动低（48 根，shift(1)）
    d["sup4h"] = l.rolling(48, min_periods=48).min().shift(1)
    return d
