#!/usr/bin/env python3
"""季节切换版：BTC 强(risk_on)只做多 TPH；BTC 弱(risk_off)只做空 TPH；其余空仓。
同一行为：0.4% 止损 + 持有 72h + 不加仓。"""
import json, os
import numpy as np
import pandas as pd
from .prove_method import load5, SYMS, sim_exit, stats
from .common import VERIFY

def regime():
    b = load5("BTCUSDT")
    d = b.set_index(b.ts.dt.floor("D")).close.resample("D").last().reset_index()
    d.columns = ["day", "close"]
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["ema200"] = d.close.ewm(span=200, adjust=False).mean()
    on = (d.close > d.ema50) & (d.ema50 > d.ema50.shift(5)) & (d.close > d.ema200)
    off = (d.close < d.ema50) & (d.ema50 < d.ema50.shift(5)) & (d.close < d.ema200)
    d["on"] = on.shift(1).fillna(False).values
    d["off"] = off.shift(1).fillna(False).values
    d["day"] = pd.to_datetime(d["day"]).dt.tz_localize(None)
    return d.set_index("day")[["on", "off"]], d.set_index("day")["close"]

def signals(sym, rmap, start, end):
    d = load5(sym); d = d[(d.ts >= start) & (d.ts <= end)].reset_index(drop=True)
    if len(d) < 1000: return []
    day = d.ts.dt.floor("D")
    r = rmap.reindex(day.values)
    dly = pd.DataFrame({"day": day.values, "close": d.close.values}).groupby("day").close.last().reset_index()
    dly["hi20"] = dly.close.rolling(20).max(); dly["lo20"] = dly.close.rolling(20).min()
    btc_close = rmap  # placeholder
    rs7 = dly.close.pct_change(7)
    # 相对 BTC 强度需要 BTC 日线
    return d, dly, day, r

def main():
    rmap, btc_close = regime()
    btc_ret = btc_close.pct_change(7)
    out = []
    for sym in SYMS:
        d0 = load5(sym); d0 = d0[(d0.ts >= "2022-05-01") & (d0.ts <= "2026-10-25")].reset_index(drop=True)
        if len(d0) < 1000: continue
        day = d0.ts.dt.floor("D")
        r = rmap.reindex(day.values).values
        dly = pd.DataFrame({"day": day.values, "close": d0.close.values}).groupby("day").close.last().reset_index()
        dly["hi20"] = dly.close.rolling(20).max(); dly["lo20"] = dly.close.rolling(20).min()
        rs7 = dly.close.pct_change(7) - btc_ret.reindex(dly.day).values
        dly["rs7"] = rs7.values
        dly["dist_hi"] = (dly.hi20 - dly.close) / dly.close
        dly["dist_lo"] = (dly.close - dly.lo20) / dly.close
        ok = dly.set_index("day")[["rs7", "dist_hi", "dist_lo"]].shift(1)
        feats = ok.reindex(day.values).values
        rs, dh, dl = feats[:, 0], feats[:, 1], feats[:, 2]
        hi20 = d0.high.rolling(20).max(); lo20 = d0.low.rolling(20).min(); prev = d0.close.shift(1)
        long_cond = (r[:, 0]) & (rs > 0) & (dh < 0.03) & (d0.low <= lo20 * 1.001) & (d0.close > prev)
        short_cond = (r[:, 1]) & (rs < 0) & (dl < 0.03) & (d0.high >= hi20 * 0.999) & (d0.close < prev)
        for i in np.where(long_cond.fillna(False).values)[0]:
            if i + 2 < len(d0): out.append(dict(dir=1, ts=d0.ts.values[i], R=sim_exit(d0.open.values, d0.high.values, d0.low.values, d0.close.values, int(i), 1, trail_trigger=None, max_bars=864)))
        for i in np.where(short_cond.fillna(False).values)[0]:
            if i + 2 < len(d0): out.append(dict(dir=-1, ts=d0.ts.values[i], R=sim_exit(d0.open.values, d0.high.values, d0.low.values, d0.close.values, int(i), -1, trail_trigger=None, max_bars=864)))
    df = pd.DataFrame(out); df["year"] = pd.to_datetime(df.ts).dt.year
    res = {"overall": {f"{bps}bp": stats(df.R.values, bps) for bps in (5.7, 10, 20)},
           "by_dir": {int(k): {f"{bps}bp": stats(g.R.values, bps) for bps in (10,)} for k, g in df.groupby("dir")},
           "by_year": {int(y): {f"{bps}bp": stats(g.R.values, bps) for bps in (10,)} for y, g in df.groupby("year")}}
    json.dump(res, open(os.path.join(VERIFY, "prove_regime.json"), "w"), ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
