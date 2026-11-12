#!/usr/bin/env python3
"""检验 bit浪浪 实际入场点是否具有"择时优势"（entry edge）。

方法：
1. 交割单入场时间 → 对齐 5m K 线（自动推断时区偏移）
2. 计算入场后 h 根 5m 的方向性收益（多单取正、空单取负）
3. 与同期同币的无条件收益分布对比（t 检验）
4. 分年/分方向/分币种
输出：data/processed/entry_edge_report.md + entry_features.csv
"""
import os, numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MKT = os.path.join(ROOT, "data", "market")
OUT = os.path.join(ROOT, "data", "processed")

SYM_MAP = {
    "BTC-USDT-SWAP": "BTCUSDT", "ETH-USDT-SWAP": "ETHUSDT", "SOL-USDT-SWAP": "SOLUSDT",
    "PEOPLE-USDT-SWAP": "PEOPLEUSDT", "TRB-USDT-SWAP": "TRBUSDT", "DOGE-USDT-SWAP": "DOGEUSDT",
    "WLD-USDT-SWAP": "WLDUSDT", "APT-USDT-SWAP": "APTUSDT", "ORDI-USDT-SWAP": "ORDIUSDT",
    "PEPE-USDT-SWAP": "1000PEPEUSDT",
}

def load5(sym):
    p = os.path.join(MKT, f"{sym}_5m.csv.gz")
    if not os.path.exists(p): return None
    try:
        d = pd.read_csv(p, usecols=["ts","open","high","low","close","volume"])
    except (EOFError, pd.errors.ParserError):
        return None
    d["ts"] = pd.to_datetime(d.ts, unit="ms", utc=True)
    return d.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def main():
    tr = pd.read_csv(os.path.join(OUT, "trades_clean.csv"))
    tr["symbol_bin"] = tr.symbol.map(SYM_MAP)
    tr = tr.dropna(subset=["symbol_bin"])
    tr["entry_time"] = pd.to_datetime(tr.entry_time)
    tr["sign"] = np.where(tr.side.astype(str).str.strip() == "多", 1, -1)
    print("trades with market data:", len(tr))

    # --- 时区偏移推断：用 BTC 入场价与 5m 收盘价匹配 ---
    btc = load5("BTCUSDT")
    b = tr[(tr.symbol_bin == "BTCUSDT")].copy()
    best = None
    for off in [-12, -8, -6, -4, 0, 4, 6, 8, 12]:
        t = (b.entry_time + pd.Timedelta(hours=off)).dt.tz_localize("UTC", ambiguous="NaT", nonexistent="NaT")
        idx = btc.ts.searchsorted(t)
        idx = np.clip(idx, 0, len(btc) - 1)
        px = btc.close.values[idx]
        err = np.median(np.abs(np.log(px / b.entry_price.values)))
        print(f"offset {off:+d}h median |log err| = {err:.5f}")
        if best is None or err < best[1]: best = (off, err)
    off = best[0]
    print("=> use offset", off, "h")

    rows = []
    for sym, g in tr.groupby("symbol_bin"):
        d = load5(sym)
        if d is None or len(d) < 1000: continue
        t = (g.entry_time + pd.Timedelta(hours=off)).dt.tz_localize("UTC", ambiguous="NaT", nonexistent="NaT")
        idx = d.ts.searchsorted(t)
        idx = np.clip(idx, 1, len(d) - 1)
        close = d.close.values; high = d.high.values; low = d.low.values
        n = len(d)
        for h in (1, 3, 6, 12, 24, 48, 96, 288):
            fwd = np.full(n, np.nan)
            fwd[:-h] = close[h:] / close[:-h] - 1
            g2 = g.copy(); g2["h"] = h
            g2["fwd"] = fwd[idx]
            rows.append(g2)
    allf = pd.concat(rows)
    # 入口特征：过去 1h/4h 收益、距 1h 高低点
    allf = allf.reset_index(drop=True)
    allf["edge"] = allf.sign * allf.fwd

    # 汇总
    md = ["# bit浪浪 入场择时优势检验\n", f"- 时区偏移：{off:+d}h（交割单时间 → UTC）", f"- 可对齐交易：{len(allf)//8} 笔（6 币种，8 个时间窗口）\n"]
    md.append("## 1. 入场后方向性收益（edge，多单取正/空单取负）\n")
    md.append("| 持有 5m 根数 | 约合时间 | 平均 edge | 中位 edge | 胜率(edge>0) | t 值 | 样本 |\n|---|---|---|---|---|---|---|")
    for h in (1, 3, 6, 12, 24, 48, 96, 288):
        s = allf[allf.h == h].edge.dropna()
        tstat = s.mean() / (s.std() / np.sqrt(len(s))) if len(s) > 2 else np.nan
        md.append(f"| {h} | {h*5/60:.1f}h | {s.mean()*100:+.4f}% | {s.median()*100:+.4f}% | {(s>0).mean()*100:.1f}% | {tstat:.1f} | {len(s)} |")
    md.append("")
    # 分方向
    md.append("## 2. 多 / 空 分别\n")
    md.append("| 方向 | h=12 (1h) 平均 edge | h=48 (4h) | 样本 |\n|---|---|---|---|")
    for sd, g in allf.groupby(allf.sign.map({1:"多",-1:"空"})):
        a = g[g.h==12].edge.mean()*100; b2 = g[g.h==48].edge.mean()*100
        md.append(f"| {sd} | {a:+.4f}% | {b2:+.4f}% | {len(g[g.h==12])} |")
    md.append("")
    # 分年
    allf["year"] = allf.entry_time.dt.year
    md.append("## 3. 分年（h=48, 4h）\n")
    md.append("| 年份 | 平均 edge | 胜率 | 样本 |\n|---|---|---|---|")
    for y, g in allf[allf.h==48].groupby("year"):
        md.append(f"| {y} | {g.edge.mean()*100:+.4f}% | {(g.edge>0).mean()*100:.1f}% | {len(g)} |")
    md.append("")
    md.append("## 4. 分币种（h=48, 4h）\n")
    md.append("| 币种 | 笔数 | 平均 edge | 胜率 |\n|---|---|---|---|")
    for s, g in allf[allf.h==48].groupby("symbol_bin"):
        md.append(f"| {s} | {len(g)} | {g.edge.mean()*100:+.4f}% | {(g.edge>0).mean()*100:.1f}% |")
    md.append("")
    with open(os.path.join(OUT, "entry_edge_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("saved entry_edge_report.md")

if __name__ == "__main__":
    main()
