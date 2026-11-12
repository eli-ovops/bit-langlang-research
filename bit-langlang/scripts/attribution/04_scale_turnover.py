"""04 规模与换手：逐年的保证金中位数、日均笔数、手续费/毛利比、每笔期望（USDT 与 R）。"""
import numpy as np
import pandas as pd

import common as C

p = C.load_positions()
p = p.sort_values("entry_time").reset_index(drop=True)

rows = []
for y, g in p.groupby("year"):
    gv = g[g["valid_size"]]
    gw = g.loc[g["pnl"] > 0, "pnl"].sum()
    days = g["day"].nunique()
    span_days = (g["entry_time"].max() - g["entry_time"].min()).days + 1
    bs_net = C.cluster_bootstrap_sum(g[g["valid_size"]], "net", "day")
    rows.append(
        dict(
            year=y,
            n=len(g),
            active_days=days,
            span_days=span_days,
            trades_per_active_day=len(g) / days,
            trades_per_calendar_day=len(g) / span_days,
            margin_median=gv["margin"].median(),
            margin_mean=gv["margin"].mean(),
            margin_p90=gv["margin"].quantile(0.90),
            notional_median=gv["notional"].median(),
            notional_mean=gv["notional"].mean(),
            leverage_median=g["leverage"].median(),
            hold_min_median=g["hold_min"].median(),
            gross_pnl=g["pnl"].sum(),
            fee=g["fee"].sum(),
            net=g["net"].sum(),
            gross_profit=gw,
            fee_over_gross_profit=-g["fee"].sum() / gw,
            fee_over_gross_pnl=-g["fee"].sum() / g["pnl"].sum(),
            win_rate=(g["pnl"] > 0).mean(),
            expectancy_usdt_net=bs_net["mean_point"],
            expectancy_usdt_ci_lo=bs_net["mean_ci_lo"],
            expectancy_usdt_ci_hi=bs_net["mean_ci_hi"],
            mean_R_gross=gv["R_gross"].mean(),
            median_R_gross=gv["R_gross"].median(),
            mean_R_net=gv["R_net"].mean(),
            median_R_net=gv["R_net"].median(),
            sum_R_gross=gv["R_gross"].sum(),
            sum_R_net=gv["R_net"].sum(),
        )
    )
yearly = pd.DataFrame(rows)
tot = dict(year="合计")
tot["n"] = len(p)
tot["active_days"] = p["day"].nunique()
tot["span_days"] = (p["entry_time"].max() - p["entry_time"].min()).days + 1
tot["trades_per_active_day"] = tot["n"] / tot["active_days"]
tot["trades_per_calendar_day"] = tot["n"] / tot["span_days"]
gv = p[p["valid_size"]]
tot["margin_median"] = gv["margin"].median()
tot["margin_mean"] = gv["margin"].mean()
tot["margin_p90"] = gv["margin"].quantile(0.90)
tot["notional_median"] = gv["notional"].median()
tot["notional_mean"] = gv["notional"].mean()
tot["leverage_median"] = p["leverage"].median()
tot["hold_min_median"] = p["hold_min"].median()
tot["gross_pnl"] = p["pnl"].sum()
tot["fee"] = p["fee"].sum()
tot["net"] = p["net"].sum()
tot["gross_profit"] = p.loc[p["pnl"] > 0, "pnl"].sum()
tot["fee_over_gross_profit"] = -p["fee"].sum() / tot["gross_profit"]
tot["fee_over_gross_pnl"] = -p["fee"].sum() / p["pnl"].sum()
tot["win_rate"] = (p["pnl"] > 0).mean()
bs = C.cluster_bootstrap_sum(gv, "net", "day")
tot["expectancy_usdt_net"] = bs["mean_point"]
tot["expectancy_usdt_ci_lo"] = bs["mean_ci_lo"]
tot["expectancy_usdt_ci_hi"] = bs["mean_ci_hi"]
tot["mean_R_gross"] = gv["R_gross"].mean()
tot["median_R_gross"] = gv["R_gross"].median()
tot["mean_R_net"] = gv["R_net"].mean()
tot["median_R_net"] = gv["R_net"].median()
tot["sum_R_gross"] = gv["R_gross"].sum()
tot["sum_R_net"] = gv["R_net"].sum()
yearly = pd.concat([yearly, pd.DataFrame([tot])], ignore_index=True)
C.save(yearly, "scale_turnover_yearly.csv")

# 月度换手
monthly = (
    p.groupby("month")
    .agg(n=("pnl", "size"), margin_median=("margin", "median"), net=("net", "sum"),
         gross_pnl=("pnl", "sum"), fee=("fee", "sum"), win_rate=("pnl", lambda s: (s > 0).mean()))
    .reset_index()
)
monthly["n"] = monthly["n"].astype(int)
C.save(monthly, "scale_turnover_monthly.csv")

# 规模 vs 每笔优势的逐年分离（关键表）
sep = yearly[["year", "n", "margin_median", "notional_median", "gross_pnl", "net", "sum_R_gross",
              "expectancy_usdt_net", "mean_R_gross"]].copy()
sep["pnl_if_equal_margin_1"] = sep["sum_R_gross"]  # 每笔保证金=1 时的 PnL 合计
sep["actual_over_equal"] = sep["gross_pnl"] / sep["sum_R_gross"]
C.save(sep, "scale_vs_edge_yearly.csv")

print(yearly.round(3).to_string(index=False))
print("\n=== monthly ===")
print(monthly.round(1).to_string(index=False))
