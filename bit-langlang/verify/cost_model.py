#!/usr/bin/env python3
"""成本模型：给定费率/滑点/止损距离，算每笔盈亏平衡所需毛优势。"""
import argparse, json, os
from .common import ACCOUNT, RISK_PCT, VERIFY

def table(fees_bps=(2,5,10), slips_bps=(0,5,10), stops_pct=(0.2,0.5,1.0,2.0), risk_pct=RISK_PCT):
    out = []
    for s in stops_pct:
        row = {"stop_pct": s}
        for f in fees_bps:
            for sl in slips_bps:
                rt = 2*(f+sl)  # 双边 bps
                cost_R = (rt/10000) / (s/100)   # 成本占 R 的比例
                row[f"fee{f}_slip{sl}"] = round(cost_R, 4)
        out.append(row)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--account", type=float, default=ACCOUNT)
    ap.add_argument("--risk", type=float, default=RISK_PCT)
    a = ap.parse_args()
    rows = table()
    if a.json:
        print(json.dumps({"account": a.account, "risk_pct": a.risk, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print(f"账户 {a.account:.0f}U，单笔风险 {a.risk*100:.1f}% = {a.account*a.risk:.1f}U")
        print("每笔盈亏平衡所需的毛优势（R）；>1 表示成本已超过止损，不可交易\n")
        cols = [k for k in rows[0] if k != "stop_pct"]
        print("stop% | " + " | ".join(cols))
        for r in rows:
            print(f"{r['stop_pct']:.1f}  | " + " | ".join(f"{r[c]:.3f}" for c in cols))
    os.makedirs(VERIFY, exist_ok=True)
    with open(os.path.join(VERIFY, "cost_table.json"), "w") as f:
        json.dump({"account": a.account, "risk_pct": a.risk, "rows": rows}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
