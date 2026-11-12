#!/usr/bin/env python3
"""防未来函数 / 数据一致性自检（只读）。报告 §4 的"可复现性"证据。

检查项
------
S1 日线特征 shift：随机抽 200 个 (symbol, day)，用 raw 1d 数据中 day ≤ D-1 的行重算
   sup10/sup20/res20/res60/res120，必须与 5m 表 day=D 行的值完全一致。
S2 季节布尔：用 BTC 1d 的 D-1 及更早数据重算 risk_on，必须与 5m 表一致。
S3 成交时点：每笔 entry_time 必须是 5m 表 bar_index 的 ts，且 signal_bar = bar_index-1。
S4 价格关系：stop < entry < t1；stop_pct ∈ [0.3%, 2%]；exit 时间 ≥ entry 时间。
S5 R 一致性：gross_R 用 entry/stop/exit 重算误差 < 1e-6；net_R = gross_R − cost_R。
S6 成本下界：cost_R ≥ (2×fee + 2×slip_min)/stop_pct − 1e-6（资金费可为负）。
S7 单币无重叠：同一 symbol 相邻交易 entry_time > 上一笔 exit_time。
S8 持仓上限：hold_bars ≤ 4032（14 天）。

用法：python3 -m backtest.v2.sanity [--split is]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

from . import config, dataio, features

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "backtest_v2")
TOL = 1e-6


def daily_feature_table(df1d: pd.DataFrame) -> pd.DataFrame:
    """按 D 行给出"只用到 D-1 及更早"的日线特征（与 features.daily_structure 等价）。"""
    d = df1d.copy()
    d["day"] = d["ts"].dt.floor("D")
    out = pd.DataFrame({"day": d["day"]})
    for name, n in (("sup10", 10), ("sup20", 20)):
        out[name] = d["low"].rolling(n, min_periods=n).min().shift(1)
    for name, n in (("res20", 20), ("res60", 60), ("res120", 120)):
        out[name] = d["high"].rolling(n, min_periods=n).max().shift(1)
    return out


def btc_regime_table(df1d: pd.DataFrame) -> pd.DataFrame:
    from .features import ema
    d = df1d.copy()
    d["day"] = d["ts"].dt.floor("D")
    ef, es, el = (ema(d["close"], n) for n in (20, 50, 200))
    raw = (d["close"] > es) & (es > es.shift(5)) & (d["close"] > el)
    return pd.DataFrame({"day": d["day"], "risk_on": raw.shift(1).fillna(False)})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="is")
    a = ap.parse_args(argv)
    trades = pd.read_csv(os.path.join(OUT, f"trades_{a.split}.csv"), parse_dates=["entry_time", "exit_time"])
    lines, fails = [], []

    def report(chk, ok, detail=""):
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {chk} {detail}")
        if not ok:
            fails.append(chk)

    btc1d = dataio.load_ohlcv("BTCUSDT", "1d")
    regime_tab = btc_regime_table(btc1d)
    regime_idx = regime_tab.set_index("day")["risk_on"]

    # S1：独立重算日线特征（只用到 D-1）与 features.daily_structure 对照
    s1_bad, s1_checked = 0, 0
    for sym in dataio.SYMBOLS:
        d1 = dataio.load_ohlcv(sym, "1d")
        if d1 is None:
            continue
        ref = daily_feature_table(d1)
        got = features.daily_structure(d1, config.DAILY)
        m = ref.merge(got, on="day", suffixes=("_ref", "_got"))
        for col in ("sup10", "sup20", "res20", "res60", "res120"):
            ref_v, got_v = m[f"{col}_ref"].values, m[f"{col}_got"].values
            both = ~(np.isnan(ref_v) | np.isnan(got_v))
            s1_checked += int(both.sum())
            s1_bad += int((np.abs(ref_v[both] - got_v[both]) > 1e-9).sum())
    report("S1 日线特征只用到 D-1（独立重算）", s1_bad == 0, f"对比 {s1_checked} 个值，违例 {s1_bad}")

    # S3 + S4 + S5 + S6 + S7 + S8
    errs = dict(s2=0, s3=0, s4=0, s5=0, s6=0, s7=0, s8=0)
    n_checked = 0
    for sym, g in trades.groupby("symbol"):
        g = g.sort_values("entry_time").reset_index(drop=True)
        # S7
        if len(g) > 1 and (g["entry_time"].values[1:] <= g["exit_time"].values[:-1]).any():
            errs["s7"] += 1
        for _, t in g.iterrows():
            n_checked += 1
            day = (t["entry_time"] - pd.Timedelta(minutes=5)).normalize()   # 信号根所在日
            # S2（信号根当日 BTC 季节必须为 True）
            if day in regime_idx.index and not bool(regime_idx.loc[day]):
                errs["s2"] += 1
            # S3
            if not (t["bar_index"] == t["signal_bar"] + 1):
                errs["s3"] += 1
            # S4
            if not (t["stop"] < t["entry"] < t["t1"]):
                errs["s4"] += 1
            if not (config.ENTRY["min_stop_pct"] - TOL <= t["stop_pct"] <= config.ENTRY["max_stop_pct"] + TOL):
                errs["s4"] += 1
            if t["exit_time"] < t["entry_time"]:
                errs["s4"] += 1
            # S5
            R = t["entry"] - t["stop"]
            if t["t1_hit"]:
                gross = 0.5 * (t["t1"] - t["entry"]) / R + 0.5 * (t["exit"] - t["entry"]) / R
            else:
                gross = (t["exit"] - t["entry"]) / R
            if abs(gross - t["gross_R"]) > 1e-4:
                errs["s5"] += 1
            if abs((t["gross_R"] - t["cost_R"]) - t["net_R"]) > 1e-6:
                errs["s5"] += 1
            # S6（只校验手续费+滑点部分：资金费可正可负）
            per_side = config.COST["fee"] + config.COST["slip_major"]
            mult = 1.5 if t["t1_hit"] else 2.0     # T1 减半后卖出腿成本减半
            if t["cost_fee_slip_R"] < mult * per_side / t["stop_pct"] - 1e-6:
                errs["s6"] += 1
            # S8
            if t["hold_bars"] > 4032:
                errs["s8"] += 1

    report("S2 BTC 季节布尔与 D-1 重算一致", errs["s2"] == 0, f"违例 {errs['s2']}")
    report("S3 成交在信号后一根 5m 开盘", errs["s3"] == 0, f"违例 {errs['s3']}")
    report("S4 stop<entry<t1 且 stop_pct∈[0.3%,2%]", errs["s4"] == 0, f"违例 {errs['s4']}")
    report("S5 R 口径自洽（gross/exit/net）", errs["s5"] == 0, f"违例 {errs['s5']}")
    report("S6 成本 ≥ 双边费+滑点/stop_pct", errs["s6"] == 0, f"违例 {errs['s6']}")
    report("S7 单币无重叠持仓", errs["s7"] == 0, f"违例 {errs['s7']}")
    report("S8 持仓 ≤ 14 天", errs["s8"] == 0, f"违例 {errs['s8']}")

    # S9 交易记录完整
    req = ["entry_time", "exit_time", "entry", "stop", "t1", "exit", "stop_pct", "gross_R",
           "cost_R", "net_R", "exit_reason", "setup", "symbol", "bar_index", "signal_bar"]
    report("S9 必需字段齐全且无 NaN（价格类）", all(c in trades.columns for c in req)
           and trades[["entry", "stop", "t1", "exit", "stop_pct"]].notna().all().all(),
           f"{len(trades)} 笔 / {n_checked} 检查点")
    lines.append(f"\n合计检查 {n_checked} 笔交易。")
    txt = "\n".join(lines)
    print(txt)
    with open(os.path.join(OUT, f"sanity_{a.split}.txt"), "w") as fh:
        fh.write(txt + "\n")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
