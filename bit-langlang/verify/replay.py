#!/usr/bin/env python3
"""历史回放：按纪律卡的条件统计"若严格按流程，历史上会有多少警报/信号"。
目的：评估 5m 手工执行的**频率与延迟可行性**；不是策略回测，不输出收益结论。
"""
import argparse, json, os
import numpy as np
import pandas as pd
from .common import MARKET, VERIFY

SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","PEOPLEUSDT","TRBUSDT","WLDUSDT","APTUSDT","ORDIUSDT","1000PEPEUSDT"]

def load5(sym):
    p = os.path.join(MARKET, f"{sym}_5m.csv.gz")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, usecols=["ts","open","high","low","close"])
    d["ts"] = pd.to_datetime(d.ts, unit="ms", utc=True)
    return d.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def regime():
    p = os.path.join(MARKET, "BTCUSDT_1d.csv.gz")
    d = pd.read_csv(p)
    d["ts"] = pd.to_datetime(d.ts, unit="ms", utc=True)
    d = d.sort_values("ts").reset_index(drop=True)
    e50 = d.close.ewm(span=50, adjust=False).mean()
    e200 = d.close.ewm(span=200, adjust=False).mean()
    on = (d.close > e50) & (e50 > e50.shift(5)) & (d.close > e200)
    out = pd.DataFrame({"day": d.ts.dt.floor("D"), "risk_on": on.shift(1).fillna(False).values})
    return out

def scan(sym, df, days):
    n = len(df)
    df["symbol"] = sym
    lo6 = df.low.rolling(6).min()
    low20 = df.low.shift(1).rolling(20).min()
    close = df.close; op = df.open; low = df.low
    cond = (low <= lo6 + 1e-12) & (close > op) & (close > close.shift(1)) & (low20.notna())
    cond &= (close >= low20 * 0.995) & (close <= low20 * 1.015)
    stop = low * (1 - 0.0015)
    stop_dist = (close - stop) / close
    cond &= (stop_dist >= 0.002) & (stop_dist <= 0.012)
    df = df.assign(stop=stop, stop_dist=stop_dist, cond=cond.fillna(False))
    df["day"] = df.ts.dt.floor("D")
    df = df.merge(days, on="day", how="left")
    df["cond"] = df.cond & df.risk_on.fillna(False)
    alerts = df[df.cond].copy()
    # 入场：下一根开盘；出场：先到 -1R 还是 +2R（96 根内）
    idx = np.where(df.cond.values)[0]
    res = []
    for i in idx[:3000]:
        if i + 1 >= n: continue
        entry = df.open.values[i+1]
        stp = df.stop.values[i]
        R = entry - stp
        if R <= 0: continue
        t1 = entry + 2*R
        hit = None; bars = 0
        for j in range(i+1, min(i+97, n)):
            bars = j - i
            if df.low.values[j] <= stp: hit = "stop"; break
            if df.high.values[j] >= t1: hit = "t1"; break
        res.append(dict(symbol=sym, ts=df.ts.values[i], day=str(df.day.values[i])[:10],
                        entry=entry, stop=stp, R=R, stop_dist=float(df.stop_dist.values[i]),
                        exit=hit or "none", bars=bars, bar_ret=float(close.values[i]/df.open.values[i]-1)))
    return alerts, pd.DataFrame(res)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-10-25")
    ap.add_argument("--max-alerts", type=int, default=20000)
    ap.add_argument("--top-n", type=int, default=3, help="每日按止损距离降序取前 N 个")
    ap.add_argument("--fee-bps", type=float, default=5.0)
    ap.add_argument("--slip-bps", type=float, default=5.0)
    a = ap.parse_args()
    days = regime()
    all_alert, all_res = [], []
    for s in SYMS:
        df = load5(s)
        if df is None: continue
        df = df[(df.ts >= a.start) & (df.ts <= a.end)].reset_index(drop=True)
        alerts, res = scan(s, df, days)
        all_alert.append(alerts[["ts","day","symbol","close","stop","stop_dist"]])
        all_res.append(res)
        print(f"{s}: alerts={len(alerts)}")
    A = pd.concat(all_alert); R = pd.concat(all_res)
    A.to_csv(os.path.join(VERIFY, "replay_alerts.csv"), index=False)
    R.to_csv(os.path.join(VERIFY, "replay_outcomes.csv"), index=False)
    per_day = A.groupby("day").size()
    summary = {
        "range": [a.start, a.end],
        "total_alerts": int(len(A)),
        "trading_days": int(per_day.shape[0]),
        "alerts_per_day": {"mean": round(float(per_day.mean()), 2), "p50": float(per_day.median()),
                           "p90": float(per_day.quantile(.9)), "max": int(per_day.max())},
        "alerts_per_symbol_day": round(len(A)/max(per_day.shape[0]*len(SYMS),1), 3),
        "stop_dist_pct": {"p10": round(float(A.stop_dist.quantile(.1))*100,2),
                          "p50": round(float(A.stop_dist.quantile(.5))*100,2),
                          "p90": round(float(A.stop_dist.quantile(.9))*100,2)},
        "outcome_counts": R.exit.value_counts().to_dict(),
        "bars_to_exit": {"p50": float(R.bars.median()), "p90": float(R.bars.quantile(.9))},
        "note": "仅频率/延迟可行性评估，不是收益回测；未计手续费/滑点",
    }
    # ---- 优先级过滤：每天按止损距离降序取 Top N（成本更低）----
    A2 = A.copy()
    A2["rank"] = A2.groupby("day")["stop_dist"].rank(ascending=False, method="first")
    sel = A2[A2["rank"] <= a.top_n].copy()
    R = R.assign(tskey=pd.to_datetime(R.ts, utc=True).astype("int64"))
    sel = sel.assign(tskey=pd.to_datetime(sel.ts, utc=True).astype("int64"))
    R2 = R.merge(sel[["symbol","tskey"]], on=["symbol","tskey"], how="inner")
    R2["gross_R"] = np.where(R2.exit == "t1", 2.0, np.where(R2.exit == "stop", -1.0, 0.0))
    fee_bps, slip_bps = a.fee_bps, a.slip_bps
    R2["cost_R"] = (2*(fee_bps+slip_bps)/10000) / R2.stop_dist
    R2["net_R"] = R2.gross_R - R2.cost_R
    sel_days = sel.groupby("day").size()
    filtered = {
        "top_n": a.top_n,
        "fee_bps": fee_bps, "slip_bps": slip_bps,
        "selected_alerts": int(len(sel)),
        "selected_per_day": {"mean": round(float(sel_days.mean()),2), "p50": float(sel_days.median()), "max": int(sel_days.max())},
        "selected_stop_dist_pct": {"p10": round(float(sel.stop_dist.quantile(.1))*100,2), "p50": round(float(sel.stop_dist.quantile(.5))*100,2), "p90": round(float(sel.stop_dist.quantile(.9))*100,2)},
        "outcome_counts": R2.exit.value_counts().to_dict(),
        "gross_R_mean": round(float(R2.gross_R.mean()),3),
        "cost_R_mean": round(float(R2.cost_R.mean()),3),
        "net_R_mean": round(float(R2.net_R.mean()),3),
        "net_R_after_trim5": round(float(R2.net_R.sort_values(ascending=False).iloc[5:].mean()),3),
        "note": "仅为流程可行性/成本敏感性，不是策略回测：未计资金费、未建模滑点对成交的影响",
    }
    summary["filtered_top_n"] = filtered
    json.dump(summary, open(os.path.join(VERIFY, "replay_summary.json"), "w"), ensure_ascii=False, indent=2)
    print(json.dumps(filtered, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
