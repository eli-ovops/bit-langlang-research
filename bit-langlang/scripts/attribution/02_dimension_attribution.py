"""02 维度归因：方向 / 币种分组 / 持仓时长 / 保证金十分位 / R 十分位。

每个分组给出：n、毛盈亏、净盈亏(不含资金费)、资金费(覆盖子样本)、净盈亏(含资金费)、
胜率、均值/中位 PnL、均值/中位 R、每笔期望、按入场日聚类的 bootstrap 95% CI。
"""
import numpy as np
import pandas as pd

import common as C

p = C.load_positions()
p = C.attach_funding(p)
p = p[p["valid_size"]].copy()  # 6 行零名义的 AIDOGE 无 R 可算；费用已在 bridge 计入
print(f"有效仓位（margin>0）: {len(p)}")

COLS = [
    "group", "n", "gross_pnl", "fee", "funding", "net_after_funding", "win_rate",
    "mean_pnl", "median_pnl", "mean_R", "median_R", "expectancy_usdt",
    "sum_net", "sum_net_ci_lo", "sum_net_ci_hi", "mean_net", "mean_net_ci_lo", "mean_net_ci_hi",
    "n_days",
]


def agg_group(df: pd.DataFrame, label: str) -> dict:
    cov = df[df["covered_mkt"]]
    bs = C.cluster_bootstrap_sum(df, "net", "day")
    return dict(
        group=str(label),
        n=len(df),
        gross_pnl=df["pnl"].sum(),
        fee=df["fee"].sum(),
        funding=cov["funding"].sum(),
        net_after_funding=df["net"].sum() + cov["funding"].sum(),
        win_rate=(df["pnl"] > 0).mean(),
        mean_pnl=df["pnl"].mean(),
        median_pnl=df["pnl"].median(),
        mean_R=df["R_gross"].mean(),
        median_R=df["R_gross"].median(),
        expectancy_usdt=df["net"].mean(),
        sum_net=bs["point"],
        sum_net_ci_lo=bs["ci_lo"],
        sum_net_ci_hi=bs["ci_hi"],
        mean_net=bs["mean_point"],
        mean_net_ci_lo=bs["mean_ci_lo"],
        mean_net_ci_hi=bs["mean_ci_hi"],
        n_days=df["day"].nunique(),
    )


def by(df: pd.DataFrame, key: str, order=None) -> pd.DataFrame:
    recs = [agg_group(g, k) for k, g in df.groupby(key, observed=True, sort=True)]
    t = pd.DataFrame(recs)
    if order is not None:
        t["__o"] = t["group"].map({str(o): i for i, o in enumerate(order)})
        t = t.sort_values("__o").drop(columns="__o")
    return t[COLS]


# ---- 1. 方向 -------------------------------------------------------------
side = by(p, "side", order=["多", "空"])
side.loc[len(side)] = agg_group(p, "合计") | {"group": "合计"}
C.save(side, "dim_side.csv")

# ---- 2. 币种分组 ---------------------------------------------------------
cg = by(p, "coin_group", order=["BTC", "ETH", "山寨"])
cg.loc[len(cg)] = agg_group(p, "合计") | {"group": "合计"}
C.save(cg, "dim_coin_group.csv")

# Top10（按笔数）
vc = p["base"].value_counts().sort_values(ascending=False, kind="mergesort")
topn = vc.head(10).index.tolist()  # 第 10/11 名笔数相同，按字母序稳定排序
p["coin_top10_by_n"] = np.where(p["base"].isin(topn), p["base"], "其他")
t10 = by(p, "coin_top10_by_n")
C.save(t10, "dim_coin_top10_by_n.csv")
print("\nTop10 by n:", topn)

# 逐币（全 129）
coin = by(p, "base")
coin = coin.sort_values("gross_pnl", ascending=False).reset_index(drop=True)
C.save(coin, "dim_coin_all.csv")

# ---- 3. 持仓时长桶 -------------------------------------------------------
hold = by(p, "hold_bucket", order=C.HOLD_LABELS)
C.save(hold, "dim_hold_bucket.csv")

# ---- 4. 保证金十分位 -----------------------------------------------------
p["margin_dec"] = pd.qcut(p["margin"], 10, labels=[f"D{i}" for i in range(1, 11)])
md = by(p, "margin_dec", order=[f"D{i}" for i in range(1, 11)])
md.insert(1, "margin_lo", md["group"].map(p.groupby("margin_dec", observed=True)["margin"].min()))
md.insert(2, "margin_hi", md["group"].map(p.groupby("margin_dec", observed=True)["margin"].max()))
md.insert(3, "margin_median", md["group"].map(p.groupby("margin_dec", observed=True)["margin"].median()))
md.insert(4, "notional_median", md["group"].map(p.groupby("margin_dec", observed=True)["notional"].median()))
C.save(md, "dim_margin_decile.csv")

# ---- 5. R 十分位（R_gross = pnl/margin）----------------------------------
p["R_dec"] = pd.qcut(p["R_gross"], 10, labels=[f"Q{i}" for i in range(1, 11)])
rd = by(p, "R_dec", order=[f"Q{i}" for i in range(1, 11)])
rd.insert(1, "R_lo", rd["group"].map(p.groupby("R_dec", observed=True)["R_gross"].min()))
rd.insert(2, "R_hi", rd["group"].map(p.groupby("R_dec", observed=True)["R_gross"].max()))
rd.insert(3, "R_median", rd["group"].map(p.groupby("R_dec", observed=True)["R_gross"].median()))
C.save(rd, "dim_R_decile.csv")

print("\n=== side ==="); print(side.round(2).to_string(index=False))
print("\n=== coin_group ==="); print(cg.round(2).to_string(index=False))
print("\n=== hold ==="); print(hold.round(2).to_string(index=False))
print("\n=== margin decile ===")
print(md[["group", "n", "margin_median", "notional_median", "gross_pnl", "mean_R", "win_rate", "mean_net"]].round(3).to_string(index=False))
print("\n=== R decile ===")
print(rd[["group", "n", "R_median", "gross_pnl", "win_rate", "mean_pnl"]].round(3).to_string(index=False))
print("\n=== coin top10 by pnl ===")
print(coin.head(12)[["group", "n", "gross_pnl", "fee", "mean_R", "win_rate"]].round(2).to_string(index=False))
