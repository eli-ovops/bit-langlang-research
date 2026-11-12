#!/usr/bin/env python3
"""冒烟测试：合成 10 笔交易，验证 KPI/成本模型数值合理。"""
import os, tempfile
import pandas as pd
from .kpi import compute, load
from .cost_model import table
from .common import VERIFY

def synth():
    rows = []
    for i in range(10):
        entry = 100.0; stop = 99.0 if i % 2 == 0 else 101.0
        win = i < 4
        exit_ = (102.0 if i % 2 == 0 else 98.0) if win else (99.0 if i % 2 == 0 else 101.0)
        rows.append(dict(date=f"2026-01-{i+1:02d}", symbol="BTCUSDT",
                         side="long" if i % 2 == 0 else "short", plan_id=f"P{i}",
                         setup="box_pullback", entry=entry, stop=stop, t1=entry+2*(entry-stop),
                         exit=exit_, qty=1, notional=2000, margin=2000, fee=-1.0, slippage=-0.2,
                         risk_pct=1.0, hold_min=10, five_q_pass=1 if i != 9 else 0,
                         stop_placed=1 if i != 8 else 0, added=1 if i == 7 else 0,
                         reversed=1 if i == 6 else 0, plan_deviation=1 if i == 5 else 0,
                         review_class="体系内" if win else "纪律错", note=""))
    return pd.DataFrame(rows)

def main():
    d = synth()
    path = os.path.join(VERIFY, "smoke_trades.csv")
    d.to_csv(path, index=False)
    k = compute(load(path), risk_limit=1.5)
    assert k["trades"] == 10
    assert k["five_q_pass_rate"] == 90.0, k["five_q_pass_rate"]
    assert k["stop_placed_rate"] == 90.0
    assert k["added_count"] == 1 and k["reversed_count"] == 1
    assert 0 <= k["win_rate"] <= 100
    t = table()
    assert len(t) == 4 and t[0]["stop_pct"] == 0.2
    # 成本随止损距离单调下降
    c = [r["fee5_slip5"] for r in t]
    assert c[0] > c[1] > c[2] > c[3], c
    print("SMOKE OK")
    print({kk: k[kk] for kk in ("trades","five_q_pass_rate","stop_placed_rate","added_count","reversed_count","win_rate","avg_R","max_consec_loss")})
    print("cost rows:", t)

if __name__ == "__main__":
    main()
