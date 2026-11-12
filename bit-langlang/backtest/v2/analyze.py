#!/usr/bin/env python3
"""归因分析：从 data/backtest_v2/trades_{split}.csv 生成表格（用于报告 §失效场景）。

只读 trades CSV，不改策略、不改参数。输出 data/backtest_v2/analysis_{split}.csv 与
data/backtest_v2/tables/*.md。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .utils import to_md

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "backtest_v2")
TAB = os.path.join(OUT, "tables")


def _agg(g: pd.DataFrame) -> pd.Series:
    net = g["net_R"]
    w = net[net > 0]
    l = net[net < 0]
    return pd.Series(dict(
        n=len(g),
        win_rate=round((net > 0).mean() * 100, 1),
        expectancy_R=round(net.mean(), 3),
        sum_R=round(net.sum(), 1),
        pf=round(w.sum() / abs(l.sum()), 2) if len(l) and l.sum() != 0 else np.nan,
        avg_win_R=round(w.mean(), 2) if len(w) else np.nan,
        avg_loss_R=round(l.mean(), 2) if len(l) else np.nan,
        t1_rate=round(g["t1_hit"].mean() * 100, 1),
        median_hold_h=round(g["hold_hours"].median(), 1),
        median_stop_pct=round(g["stop_pct"].median() * 100, 2),
        cost_R=round(g["cost_R"].mean(), 3),
    ))


def _bucket(df: pd.DataFrame, col: str, bins: int = 3) -> pd.DataFrame:
    x = df[col].dropna()
    if len(x) < 30:
        return pd.DataFrame()
    qs = np.quantile(x, np.linspace(0, 1, bins + 1))
    qs = np.unique(qs)
    if len(qs) < 3:
        return pd.DataFrame()
    labels = [f"{qs[i]:.3f}~{qs[i+1]:.3f}" for i in range(len(qs) - 1)]
    df = df.copy()
    df["_bucket"] = pd.cut(df[col], bins=qs, labels=labels, include_lowest=True)
    return df.groupby("_bucket", observed=True).apply(_agg).reset_index().rename(columns={"_bucket": col})


def main():
    os.makedirs(TAB, exist_ok=True)
    for split in ("is", "oos"):
        path = os.path.join(OUT, f"trades_{split}.csv")
        if not os.path.exists(path):
            print(f"[skip] 缺少 {path}")
            continue
        d = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
        d["year"] = d["entry_time"].dt.year
        d["month"] = d["entry_time"].dt.to_period("M").astype(str)
        tables = {}
        tables["per_symbol"] = d.groupby("symbol").apply(_agg).reset_index()
        tables["per_year"] = d.groupby("year").apply(_agg).reset_index()
        tables["per_setup"] = d.groupby("setup").apply(_agg).reset_index()
        tables["per_season"] = d.groupby("season").apply(_agg).reset_index()
        tables["per_exit_reason"] = d.groupby("exit_reason").apply(_agg).reset_index()
        tables["per_month"] = d.groupby("month").apply(_agg).reset_index()
        if "btc_ret20" in d.columns:
            tables["by_btc_ret20"] = _bucket(d, "btc_ret20")
            tables["by_btc_vol20"] = _bucket(d, "btc_vol20")
            tables["by_btc_dd120"] = _bucket(d, "btc_dd120")
        # 成本分解
        cost = pd.DataFrame([dict(
            split=split,
            n=len(d),
            fee_slip_R=round(d["cost_fee_slip_R"].sum(), 1),
            funding_R=round(d["cost_funding_R"].sum(), 1),
            cost_R=round(d["cost_R"].sum(), 1),
            gross_profit_R=round(d.loc[d["gross_R"] > 0, "gross_R"].sum(), 1),
            gross_R=round(d["gross_R"].sum(), 1),
            net_R=round(d["net_R"].sum(), 1),
            cost_over_gross_profit=round(d["cost_R"].sum() / d.loc[d["gross_R"] > 0, "gross_R"].sum(), 3),
        )])
        tables["cost_decomposition"] = cost
        for name, t in tables.items():
            if len(t):
                t.to_csv(os.path.join(OUT, f"analysis_{split}_{name}.csv"), index=False)
        # markdown
        lines = [f"# {split.upper()} 归因分析（自动生成）\n"]
        for name, t in tables.items():
            if not len(t):
                continue
            lines.append(f"\n## {name}\n")
            lines.append(to_md(t))
            lines.append("")
        with open(os.path.join(TAB, f"analysis_{split}.md"), "w") as fh:
            fh.write("\n".join(lines))
        print(f"[ok] {split}: {len(d)} 笔 → {os.path.relpath(TAB, ROOT)}/analysis_{split}.md")


if __name__ == "__main__":
    main()
