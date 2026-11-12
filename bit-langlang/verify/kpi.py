#!/usr/bin/env python3
"""行为 KPI + 交易指标。输入 trades CSV，输出 markdown/JSON。"""
import argparse, json, os
import numpy as np
import pandas as pd
from .common import VERIFY, ACCOUNT, RISK_PCT, num, yn

def load(path):
    d = pd.read_csv(path)
    for c in ["entry","stop","t1","exit","qty","notional","margin","fee","slippage","risk_pct","hold_min"]:
        if c in d: d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ["five_q_pass","stop_placed","added","reversed","plan_deviation"]:
        if c in d: d[c] = d[c].apply(yn)
    return d

def compute(d, risk_limit=1.5):
    out = {}
    n = len(d)
    out["trades"] = n
    if n == 0: return out
    side = d.side.astype(str).str.lower()
    is_long = side.str.startswith("l") | side.eq("多")
    # 方向/R
    d = d.copy()
    d["dir"] = np.where(is_long, 1, -1)
    d["R"] = (d.exit - d.entry) * d.dir / (d.entry - d.stop).abs()
    out.update({
        "five_q_pass_rate": round(d.five_q_pass.mean()*100, 1),
        "stop_placed_rate": round(d.stop_placed.mean()*100, 1),
        "risk_compliant_rate": round((d.risk_pct <= risk_limit).mean()*100, 1),
        "added_count": int(d.added.sum()),
        "reversed_count": int(d.reversed.sum()),
        "plan_deviation_rate": round(d.plan_deviation.mean()*100, 1),
        "win_rate": round((d.R > 0).mean()*100, 1),
        "avg_R": round(d.R.mean(), 3),
        "pf": round(d.loc[d.R>0,"R"].sum() / abs(d.loc[d.R<0,"R"].sum()), 2) if (d.R<0).any() else None,
        "median_hold_min": round(d.hold_min.median(), 1) if d.hold_min.notna().any() else None,
        "fee_over_gross_pct": round(-d.fee.sum() / max(d.R[d.R>0].sum(), 1e-9) * 100, 1) if "fee" in d else None,
    })
    # 连亏
    streak = mx = 0
    for r in d.R:
        if r < 0: streak += 1; mx = max(mx, streak)
        else: streak = 0
    out["max_consec_loss"] = mx
    # 复盘分类
    if "review_class" in d:
        out["review_class"] = d.review_class.fillna("未分类").value_counts().to_dict()
    # 按 setup/币种
    for key in ("setup","symbol","side"):
        if key in d:
            g = d.groupby(key).agg(n=("R","size"), win=("R",lambda x:(x>0).mean()*100), avg_R=("R","mean")).round(2)
            out[f"by_{key}"] = g.reset_index().to_dict("records")
    # 回撤（按 R 序列、固定风险）
    risk_amt = ACCOUNT * RISK_PCT
    eq = ACCOUNT + (d.R.fillna(0) * risk_amt).cumsum()
    peak = np.maximum.accumulate(eq)
    out["mdd_fixed_pct"] = round(float((eq/peak-1).min()*100), 2)
    return out

def to_md(k):
    lines = ["# 行为 KPI 报告", ""]
    lines.append("## 行为遵守")
    for key, label in [("trades","笔数"),("five_q_pass_rate","五问完成率%"),("stop_placed_rate","开仓即挂止损%"),
                       ("risk_compliant_rate","风险合规%"),("added_count","加仓次数"),("reversed_count","反手次数"),
                       ("plan_deviation_rate","计划外交易%"),("max_consec_loss","最大连亏")]:
        if key in k: lines.append(f"- {label}: {k[key]}")
    if "review_class" in k:
        lines.append("- 复盘分类: " + ", ".join(f"{a}={b}" for a,b in k["review_class"].items()))
    lines.append("\n## 交易指标")
    for key, label in [("win_rate","胜率%"),("avg_R","期望R"),("pf","PF"),("median_hold_min","持仓中位(分)"),
                       ("mdd_fixed_pct","固定风险MDD%"),("fee_over_gross_pct","费/毛利%")]:
        if key in k: lines.append(f"- {label}: {k[key]}")
    for key in ("by_setup","by_symbol","by_side"):
        if key in k:
            lines.append(f"\n## {key}")
            lines.append("| group | n | win% | avgR |")
            lines.append("|---|---|---|---|")
            for r in k[key]:
                lines.append(f"| {r[key.split('_')[1]]} | {r['n']} | {r['win']} | {r['avg_R']} |")
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(VERIFY, "trades.csv"))
    ap.add_argument("--risk-limit", type=float, default=1.5)
    ap.add_argument("--out", default=os.path.join(VERIFY, "kpi_report.md"))
    a = ap.parse_args()
    if not os.path.exists(a.file):
        raise SystemExit(f"no file: {a.file}")
    d = load(a.file)
    k = compute(d, a.risk_limit)
    md = to_md(k)
    open(a.out, "w", encoding="utf-8").write(md)
    json.dump(k, open(os.path.join(VERIFY, "kpi.json"), "w"), ensure_ascii=False, indent=2)
    print(md)

if __name__ == "__main__":
    main()
