#!/usr/bin/env python3
"""组合层模拟 + 风险闸门评估（与具体策略解耦）。

输入：trades CSV（需含 entry_time, exit_time, net_R, symbol；可选 risk_scale）
输出：组合权益曲线、风险指标、G1-G10 可判定项。

用法：
  python3 backtest/portfolio_gates.py data/backtest/trades_all.csv --risk 0.015
"""
import argparse, json, os
import numpy as np
import pandas as pd

def load_trades(path):
    d = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
    if "net_R" not in d.columns:
        raise SystemExit("需要 net_R 列")
    if "risk_scale" not in d.columns:
        d["risk_scale"] = 1.0
    d["risk_scale"] = d["risk_scale"].fillna(1.0).clip(0, 1)
    return d.sort_values("entry_time").reset_index(drop=True)

def simulate(d, risk=0.015, initial=2000.0, max_concurrent=3):
    """按入场时间顺序分配风险；退出时结算；并发上限。"""
    equity = initial
    open_pos = []   # (exit_time, pnl)
    curve = [(d.entry_time.min(), equity)]
    realized = []
    skipped = 0
    for _, t in d.iterrows():
        # 结算已到期
        still = []
        for et, pnl in open_pos:
            if et <= t.entry_time:
                equity += pnl
                realized.append((et, equity))
                curve.append((et, equity))
            else:
                still.append((et, pnl))
        open_pos = still
        if len(open_pos) >= max_concurrent:
            skipped += 1
            continue
        r = float(t.net_R)
        scale = float(t.get("risk_scale", 1.0))
        pnl = r * risk * equity * scale
        open_pos.append((t.exit_time, pnl))
        if equity <= 0:
            break
    for et, pnl in open_pos:
        equity += pnl
        curve.append((et, equity))
    c = pd.DataFrame(curve, columns=["ts", "equity"]).sort_values("ts").reset_index(drop=True)
    return c, equity, skipped

def segment_metrics(trades, risk):
    out = {}
    for name, lo, hi in [("IS", "2000-01-01", "2024-07-01"), ("OOS", "2024-07-01", "2100-01-01")]:
        d = trades[(trades.entry_time >= lo) & (trades.entry_time < hi)]
        if not len(d):
            continue
        w = d.net_R[d.net_R > 0]; l = d.net_R[d.net_R < 0]
        pf = w.sum() / abs(l.sum()) if len(l) and l.sum() != 0 else float("inf")
        out[name] = dict(trades=len(d), win_rate=round(float((d.net_R > 0).mean() * 100), 2),
                         pf=round(float(pf), 3), sum_R=round(float(d.net_R.sum()), 2))
    return out

def metrics(curve, initial, trades, risk):
    eq = curve.equity.values
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    mdd = float(dd.min()) if len(dd) else 0.0
    # 最长水下时间（天）
    under = eq < peak - 1e-9
    max_days, start = 0, None
    for i, u in enumerate(under):
        if u and start is None: start = i
        if not u and start is not None:
            max_days = max(max_days, (curve.ts.iloc[i] - curve.ts.iloc[start]).days); start = None
    if start is not None:
        max_days = max(max_days, (curve.ts.iloc[-1] - curve.ts.iloc[start]).days)
    # 连亏（按单笔）
    streak = mx = 0
    for r in trades.net_R.values:
        if r < 0: streak += 1; mx = max(mx, streak)
        else: streak = 0
    wins = trades.net_R[trades.net_R > 0]; losses = trades.net_R[trades.net_R < 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    # 去尾
    def tail(n):
        idx = trades.net_R.nlargest(n).index
        return trades.drop(idx).net_R.sum()
    return dict(
        final=float(eq[-1]), ret_pct=float((eq[-1] / initial - 1) * 100),
        mdd_pct=float(mdd * 100), longest_underwater_days=int(max_days),
        trades=int(len(trades)), win_rate=float((trades.net_R > 0).mean() * 100),
        pf=float(pf), avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        max_consec_loss=int(mx), risk=risk,
        sum_R=float(trades.net_R.sum()),
        tail_remove_5=float(tail(5)), tail_remove_10=float(tail(10)),
    )

def gates(m, curve):
    """按 docs/风险审查框架.md 可判定的 Gate 给结论。"""
    g = {}
    seg = m.get("by_segment", {})
    is_ = seg.get("IS"); oos = seg.get("OOS")
    g["G1_可复现(IS)"] = ("PASS" if is_ and is_["pf"] >= 1.5 else "FAIL") if is_ else "未测"
    g["G2_样本外"] = ("PASS" if oos and oos["pf"] >= 1.1 and abs(m["mdd_pct"]) <= 25 else "FAIL") if oos else "未测"
    g["G3_去尾"] = "PASS" if m["tail_remove_5"] > 0 and m["tail_remove_10"] > 0 else "FAIL"
    g["G4_连亏压力"] = "PASS" if abs(m["mdd_pct"]) <= 25 else "FAIL"
    g["G5_参数稳健"] = "未测"
    g["G6_成本敏感"] = "未测"
    g["G7_单币依赖"] = "未测"
    g["G8_极端行情"] = "未测"
    g["G9_容量"] = "未测"
    g["G10_运营"] = "未测"
    return g

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trades")
    ap.add_argument("--risk", type=float, default=0.015)
    ap.add_argument("--initial", type=float, default=2000)
    ap.add_argument("--max-concurrent", type=int, default=3)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()
    d = load_trades(a.trades)
    c, eq, skipped = simulate(d, a.risk, a.initial, a.max_concurrent)
    m = metrics(c, a.initial, d, a.risk)
    m["skipped_by_concurrency"] = skipped
    m["by_segment"] = segment_metrics(d, a.risk)
    out = dict(metrics=m, gates=gates(m, c))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if a.json_out:
        os.makedirs(os.path.dirname(a.json_out), exist_ok=True)
        json.dump(out, open(a.json_out, "w"), ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
