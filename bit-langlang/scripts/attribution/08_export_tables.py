"""08 导出 docs 用的 markdown 表格与 summary.json（保证文档数字可复现）。"""
import json

import numpy as np
import pandas as pd

import common as C

OUT = C.OUT

PCT_COLS = {"win_rate", "fee_over_gross", "net_retained_pct", "pct_of_n", "funding_coverage_pct",
            "fee_over_gross_profit", "fee_over_gross_pnl"}
INT_COLS = {"n", "key", "year", "removed_top_k", "active_days", "n_days", "n_clusters", "rank",
            "span_days", "n_covered", "trades", "value_int"}
R_COLS = {"mean_R", "median_R", "mean_R_gross", "median_R_gross", "sum_R_gross", "sum_R_net",
          "R_lo", "R_hi", "R_median", "cluster_t", "expectancy_usdt", "expectancy_usdt_net",
          "trades_per_active_day", "trades_per_calendar_day"}


def fmt(col, v):
    if isinstance(v, str):
        return v
    if pd.isna(v):
        return ""
    if isinstance(v, (int, np.integer)) or col in INT_COLS:
        return f"{v:,.0f}"
    if isinstance(v, (float, np.floating)):
        if col in PCT_COLS:
            return f"{v:.1%}"
        if col in R_COLS:
            return f"{v:.3f}"
        return f"{v:,.2f}"
    return str(v)


def md_table(df: pd.DataFrame, cols, headers) -> str:
    assert len(cols) == len(headers), (len(cols), len(headers))
    head = "| " + " | ".join(headers) + " |\n|" + "|".join(["---"] * len(headers)) + "|\n"
    body = ""
    for _, r in df[cols].iterrows():
        body += "| " + " | ".join(fmt(c, r[c]) for c in cols) + " |\n"
    return head + body


parts = []

# 1. PnL 桥
df = pd.read_csv(OUT / "pnl_bridge_summary.csv")
parts.append("## 表 A PnL 桥（全样本 vs 10 币覆盖子样本）\n")
parts.append(md_table(df, ["item", "scope", "usdt", "note"], ["项目", "范围", "USDT", "说明"]))
parts.append("")

# 2. 逐年桥
df = pd.read_csv(OUT / "pnl_bridge_yearly.csv")
parts.append("## 表 B 逐年 PnL 桥\n")
parts.append(md_table(df, ["key", "n", "gross_pnl", "fee", "net_pre_funding", "funding_covered", "net_after_funding", "funding_coverage_pct"],
                      ["年份", "n", "毛价格盈亏", "手续费", "净(不含资金费)", "资金费", "净(含资金费)", "资金费覆盖率"]))
parts.append("")

# 3. 逐年规模
df = pd.read_csv(OUT / "scale_turnover_yearly.csv")
parts.append("## 表 C 规模与换手（逐年）\n")
parts.append(md_table(df, ["year", "n", "active_days", "trades_per_active_day", "margin_median", "notional_median", "leverage_median", "hold_min_median", "win_rate", "expectancy_usdt_net", "mean_R_gross", "median_R_gross", "fee_over_gross_profit"],
                      ["年份", "n", "活跃日", "日均笔数", "保证金中位", "名义中位", "杠杆中位", "持仓中位(分)", "胜率", "每笔期望净USDT", "均值R", "中位R", "费/毛利"]))
parts.append("")

# 4. 方向 / 币种 / 时长
for fname, title in [
    ("dim_side.csv", "表 D 方向归因"),
    ("dim_coin_group.csv", "表 E 币种分组归因"),
    ("dim_hold_bucket.csv", "表 F 持仓时长归因"),
]:
    df = pd.read_csv(OUT / fname)
    parts.append(f"## {title}\n")
    parts.append(md_table(df, ["group", "n", "gross_pnl", "fee", "funding", "net_after_funding", "win_rate", "mean_pnl", "median_pnl", "mean_R", "median_R", "sum_net", "sum_net_ci_lo", "sum_net_ci_hi"],
                          ["分组", "n", "毛盈亏", "手续费", "资金费", "净(含资金费)", "胜率", "均值PnL", "中位PnL", "均值R", "中位R", "净合计", "CI下限", "CI上限"]))
    parts.append("")

# 5. 保证金十分位
df = pd.read_csv(OUT / "dim_margin_decile.csv")
parts.append("## 表 G 保证金十分位\n")
parts.append(md_table(df, ["group", "n", "margin_median", "notional_median", "gross_pnl", "win_rate", "mean_R", "sum_net", "sum_net_ci_lo", "sum_net_ci_hi", "expectancy_usdt"],
                      ["十分位", "n", "保证金中位", "名义中位", "毛盈亏", "胜率", "均值R", "净合计", "CI下限", "CI上限", "每笔期望"]))
parts.append("")

# 6. R 十分位
df = pd.read_csv(OUT / "dim_R_decile.csv")
parts.append("## 表 H R 十分位（R=pnl/margin）\n")
parts.append(md_table(df, ["group", "n", "R_lo", "R_hi", "R_median", "gross_pnl", "win_rate", "mean_pnl", "sum_net"],
                      ["R 十分位", "n", "R下限", "R上限", "R中位", "毛盈亏", "胜率", "均值PnL", "净合计"]))
parts.append("")

# 7. 尾部
df = pd.read_csv(OUT / "tail_trim.csv")
parts.append("## 表 I 去尾后的净收益\n")
parts.append(md_table(df, ["removed_top_k", "n", "net", "net_retained_pct", "net_ci_lo", "net_ci_hi", "gross_pnl", "fee", "mean_net"],
                      ["去掉最大 k 笔", "剩余 n", "净收益", "保留比例", "CI下限", "CI上限", "毛盈亏", "手续费", "每笔均值"]))
parts.append("")

df = pd.read_csv(OUT / "tail_concentration.csv")
parts.append("## 表 J 集中度\n")
parts.append(md_table(df, ["metric", "value", "pct_of_n"], ["指标", "值", "占 n/比例"]))
parts.append("")

# 8. 反事实
df = pd.read_csv(OUT / "counterfactuals.csv")
parts.append("## 表 K 反事实\n")
parts.append(md_table(df, ["scenario", "value", "n", "delta_vs_base", "ci_lo", "ci_hi"],
                      ["情景", "结果", "n", "相对基线变化", "CI下限", "CI上限"]))
parts.append("")

# 9. 关键结论 CI
df = pd.read_csv(OUT / "key_conclusions_ci.csv")
parts.append("## 表 L 关键结论与置信区间（按入场日整群 bootstrap）\n")
parts.append(md_table(df, ["conclusion", "n", "n_days", "sum_point", "sum_ci_lo", "sum_ci_hi", "mean_point", "mean_ci_lo", "mean_ci_hi", "cluster_t"],
                      ["结论", "n", "聚类日数", "合计", "CI下限", "CI上限", "均值", "均值CI下限", "均值CI上限", "聚类t"]))
parts.append("")

# 10. 等规模逐年
df = pd.read_csv(OUT / "counterfactual_equal_size_yearly.csv")
parts.append("## 表 M 等规模（保证金=1）逐年\n")
parts.append(md_table(df, ["year", "n", "sum_R_gross", "sum_R_net", "mean_R_gross", "median_R_gross", "actual_gross_pnl", "implied_avg_margin"],
                      ["年份", "n", "ΣR_gross", "ΣR_net", "均值R", "中位R", "实际毛PnL", "隐含平均保证金"]))
parts.append("")

# 11. 稳健性
df = pd.read_csv(OUT / "robustness_sensitivity.csv")
parts.append("## 表 N 口径敏感性\n")
parts.append(md_table(df, ["check", "value", "note"], ["检查项", "值", "说明"]))
parts.append("")

text = "# 归因表（自动生成，勿手改）\n\n> 由 `scripts/attribution/08_export_tables.py` 生成；数字与 `data/attribution/*.csv` 一致。\n\n" + "\n".join(parts)
(OUT / "tables_for_doc.md").write_text(text, encoding="utf-8")

summary = {}
for name in ["pnl_bridge_summary", "counterfactuals", "tail_concentration", "key_conclusions_ci",
             "counterfactual_equal_size_yearly", "scale_turnover_yearly"]:
    summary[name] = pd.read_csv(OUT / f"{name}.csv").to_dict(orient="records")
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
print("saved", OUT / "tables_for_doc.md", len(text), "chars")
