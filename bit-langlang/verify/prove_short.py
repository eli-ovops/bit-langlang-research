#!/usr/bin/env python3
"""TPH 镜像：只做空。同一行为（0.4% 快止损 + 持有 24/72h + 不加仓）。
测试三个时段：2022 熊 / 2023-2024H1 牛 / 2024-07~2026-10 后段；
并测他的真实空单入场。
"""
import json, os
import numpy as np
import pandas as pd
from .prove_method import load5, SYMS, MAP, sim_exit, stats
from .common import VERIFY

def entries_short(d, btc_d, start, end, max_n=None):
    d = d[(d.ts >= start) & (d.ts <= end)].reset_index(drop=True)
    if len(d) < 1000: return None
    day = d.ts.dt.floor("D")
    dly = pd.DataFrame({"day": day.values, "close": d.close.values}).groupby("day").close.last().reset_index()
    dly["lo20"] = dly.close.rolling(20).min()
    rs7 = dly.close.pct_change(7) - btc_d.pct_change(7).reindex(dly.day).values
    dly["rs7"] = rs7.values
    dly["dist_lo"] = (dly.close - dly.lo20) / dly.close   # 距 20 日低点 <3% → 弱势、接近破位
    ok = dly.set_index("day")[["rs7", "dist_lo"]].shift(1)
    feats = ok.reindex(day.values).values
    rs, dl = feats[:, 0], feats[:, 1]
    hi20 = d.high.rolling(20).max(); prev = d.close.shift(1)
    cond = (rs < 0) & (dl < 0.03) & (d.high >= hi20 * 0.999) & (d.close < prev)
    idx = np.where(cond.fillna(False).values)[0]
    if max_n: idx = idx[:max_n]
    return d, idx

def run_period(d, idx, dirn=-1):
    out = []
    for i in idx:
        if i + 2 >= len(d): continue
        for name, kw in (("hold24h", dict(trail_trigger=None, max_bars=288)),
                         ("hold72h", dict(trail_trigger=None, max_bars=864)),
                         ("trail1", dict(trail_trigger=1.0, max_bars=864))):
            out.append((name, sim_exit(d.open.values, d.high.values, d.low.values, d.close.values, int(i), dirn, **kw)))
    df = pd.DataFrame(out, columns=["variant", "gross_R"])
    return df

def main():
    btc = load5("BTCUSDT"); btc_d = btc.set_index(btc.ts.dt.floor("D")).close.resample("D").last()
    btc_d.index = pd.to_datetime(btc_d.index).tz_localize(None)
    periods = {"2022_bear": ("2022-05-01", "2022-12-31"),
               "2023_2024H1_bull": ("2023-01-01", "2024-06-30"),
               "2024H2_2026_post": ("2024-07-01", "2026-10-25")}
    res = {}
    for pname, (s0, s1) in periods.items():
        rows = []
        for sym in SYMS:
            d = load5(sym)
            if d is None: continue
            e = entries_short(d, btc_d, s0, s1)
            if e is None: continue
            d2, idx = e
            rows.append(run_period(d2, idx))
        if not rows:
            continue
        df = pd.concat(rows)
        res[pname] = {}
        for v in ("hold24h", "hold72h", "trail1"):
            Rs = df[df.variant == v].gross_R.values
            res[pname][v] = {f"{bps}bp": stats(Rs, bps) for bps in (5.7, 10, 20)}
    # 他的真实空单
    pos = pd.read_csv("data/processed/v2/trades_positions.csv", parse_dates=["entry_time", "exit_time"])
    pos["sym"] = pos.symbol.map(MAP); pos = pos[(pos.side == "空")].dropna(subset=["sym"]).copy()
    rows = []
    for sym, g in pos.groupby("sym"):
        d = load5(sym)
        if d is None: continue
        idx = np.clip(np.searchsorted(d.ts, (g.entry_time - pd.Timedelta(hours=8)).dt.tz_localize("UTC")), 0, len(d) - 2)
        for i in idx:
            if i + 2 >= len(d): continue
            for name, kw in (("hold24h", dict(trail_trigger=None, max_bars=288)),
                             ("hold72h", dict(trail_trigger=None, max_bars=864))):
                rows.append((name, sim_exit(d.open.values, d.high.values, d.low.values, d.close.values, int(i), -1, **kw)))
    dfh = pd.DataFrame(rows, columns=["variant", "gross_R"])
    res["his_short_entries"] = {v: {f"{bps}bp": stats(dfh[dfh.variant == v].gross_R.values, bps) for bps in (5.7, 10, 20)}
                                for v in ("hold24h", "hold72h")}
    json.dump(res, open(os.path.join(VERIFY, "prove_short.json"), "w"), ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
