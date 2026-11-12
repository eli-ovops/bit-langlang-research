#!/usr/bin/env python3
"""闸门判定（G1–G4 + G7 备注）——从已保存的结果重算，**不重跑策略、不重跑 OOS**。

用法：python3 -m backtest.v2.gates
输出：data/backtest_v2/gates.json、tables/gates.md，并把 summary.json 里的 gates 字段
      按本文件的口径覆盖（纯后处理，不改变任何回测数字）。
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .utils import to_md

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "backtest_v2")
TAB = os.path.join(OUT, "tables")


def stats_from_csv(path: str) -> dict:
    d = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
    net = d["net_R"].values.astype(float)
    w, l = net[net > 0], net[net < 0]
    cum = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    streak = mx = 0
    for r in net:
        if r < 0:
            streak += 1
            mx = max(mx, streak)
        else:
            streak = 0

    def tail_pf(k):
        if len(net) <= k:
            return None
        s = net[np.argsort(-net)[k:]]
        ww, ll = s[s > 0].sum(), -s[s < 0].sum()
        return float(ww / ll) if ll > 0 else None

    return dict(
        n=int(len(net)), win_rate=float((net > 0).mean()),
        payoff=float(w.mean() / abs(l.mean())) if len(w) and len(l) else None,
        pf=float(w.sum() / abs(l.sum())) if len(l) else None,
        expectancy_R=float(net.mean()), sum_R=float(net.sum()),
        mdd_R=float((cum - peak).min()), max_consec_loss=int(mx),
        tail5_pf=tail_pf(5), tail10_pf=tail_pf(10),
        tail5_sum_R=float(np.sort(net)[:-5].sum()) if len(net) > 5 else None,
        tail10_sum_R=float(np.sort(net)[:-10].sum()) if len(net) > 10 else None,
    )


def main():
    summary = json.load(open(os.path.join(OUT, "summary.json")))
    v1 = summary.get("v1_baseline", {})
    rows = []
    gates = {"definitions": {}, "splits": {}}
    for split in ("is", "oos"):
        tier_res = {}
        for tier in ("r15", "r33"):
            eq_path = os.path.join(OUT, f"equity_mtm_{split}_{tier}.csv")
            pt_path = os.path.join(OUT, f"portfolio_trades_{split}_{tier}.csv")
            if not os.path.exists(pt_path):
                continue
            s = stats_from_csv(pt_path)
            eq = pd.read_csv(eq_path) if os.path.exists(eq_path) else None
            if eq is not None and len(eq):
                e = eq["equity"].values
                s["mtm_mdd_pct"] = float((e / np.maximum.accumulate(e) - 1).min() * 100)
                s["mtm_final_equity"] = float(e[-1])
                s["mtm_ret_pct"] = float((e[-1] / e[0] - 1) * 100)
            tier_res[tier] = s
        gates["splits"][split] = {}
        if not tier_res:
            continue
        p = tier_res["r15"]
        v1s = v1.get(split, {})
        g = {}
        if split == "is":
            g["G1_win_rate_32_48"] = "PASS" if 0.32 <= p["win_rate"] <= 0.48 else "FAIL"
            g["G1_payoff_ge_2.2"] = "PASS" if (p["payoff"] or 0) >= 2.2 else "FAIL"
            g["G1_pf_ge_1.5"] = "PASS" if (p["pf"] or 0) >= 1.5 else "FAIL"
            if v1s.get("n"):
                ratio = p["n"] / v1s["n"]
                g["G1_trade_count_vs_v1"] = f"{ratio:.2f}x（{p['n']} vs v1 {v1s['n']}）" + \
                                            (" PASS" if 0.7 <= ratio <= 1.3 else " FAIL")
            g["G1_overall"] = "PASS" if all(
                g[k] == "PASS" for k in ("G1_win_rate_32_48", "G1_payoff_ge_2.2", "G1_pf_ge_1.5")) else "FAIL"
        else:
            g["G2_pf_ge_1.1"] = "PASS" if (p["pf"] or 0) >= 1.1 else "FAIL"
            g["G2_mdd_le_25"] = "PASS" if p.get("mtm_mdd_pct", -100) >= -25 else "FAIL"
            no_blow = (p.get("mtm_final_equity") or 0) >= 0.5 * 2000 and p.get("mtm_mdd_pct", -100) > -90
            g["G2_no_blowup"] = "PASS" if no_blow else "FAIL"
            g["G2_overall"] = "PASS" if all(
                g[k] == "PASS" for k in ("G2_pf_ge_1.1", "G2_mdd_le_25", "G2_no_blowup")) else "FAIL"
        # G3 去尾
        g["G3_tail5_pf_ge_1.2"] = "PASS" if (p.get("tail5_pf") or 0) >= 1.2 else "FAIL"
        g["G3_tail10_pf_ge_1.2"] = "PASS" if (p.get("tail10_pf") or 0) >= 1.2 else "FAIL"
        g["G3_tail5_sum_positive"] = "PASS" if (p.get("tail5_sum_R") or -1) > 0 else "FAIL"
        g["G3_overall"] = "PASS" if all(g[k].startswith("PASS") for k in
                                        ("G3_tail5_pf_ge_1.2", "G3_tail10_pf_ge_1.2")) else "FAIL"
        # G4 回撤/连亏
        g["G4_mdd_le_25"] = "PASS" if p.get("mtm_mdd_pct", -100) >= -25 else "FAIL"
        g["G4_max_consec_loss"] = p["max_consec_loss"]
        # G7 单币依赖（备注：每个币都亏）
        g["G7_note"] = "见 analysis per_symbol：没有任何一个币为正"
        gates["splits"][split] = g
        for tier, st in tier_res.items():
            rows.append(dict(split=split.upper(), tier=tier, n=st["n"],
                             win_rate=f"{st['win_rate']*100:.1f}%",
                             payoff=round(st["payoff"] or 0, 2), pf=round(st["pf"] or 0, 2),
                             exp_R=round(st["expectancy_R"], 3), sum_R=round(st["sum_R"], 1),
                             mdd_R=round(st["mdd_R"], 1),
                             mtm_mdd=f"{st.get('mtm_mdd_pct', 0):.1f}%",
                             max_consec_loss=st["max_consec_loss"],
                             tail5_pf=round(st.get("tail5_pf") or 0, 2),
                             tail10_pf=round(st.get("tail10_pf") or 0, 2)))

    gates["definitions"] = dict(
        G1="IS：胜率 32–48% / 盈亏比≥2.2 / PF≥1.5 / 笔数与 v1 同量级（±30%）",
        G2="OOS：PF≥1.1 / MTM MDD≤25% / 未爆仓（终值≥50% 初始、MDD>-90%）",
        G3="去尾：剔除最大 5/10 笔后 PF≥1.2",
        G4="1.5% 风险下 MDD≤25%",
    )
    # 覆盖 summary.json 的 gates（纯后处理）
    for split, g in gates["splits"].items():
        if split in summary.get("splits", {}):
            summary["splits"][split]["gates_recomputed"] = g
    with open(os.path.join(OUT, "summary.json"), "w") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "gates.json"), "w") as fh:
        json.dump(gates, fh, ensure_ascii=False, indent=2)

    lines = ["# 闸门判定（由已保存结果重算，未重跑策略）\n",
             "\n## 定义\n"] + [f"- **{k}**：{v}" for k, v in gates["definitions"].items()]
    lines.append("\n## 结果\n")
    lines.append(to_md(pd.DataFrame(rows)))
    for split, g in gates["splits"].items():
        lines.append(f"\n### {split.upper()}\n")
        lines.append(to_md(pd.DataFrame([dict(gate=k, result=v) for k, v in g.items()])))
    with open(os.path.join(TAB, "gates.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
