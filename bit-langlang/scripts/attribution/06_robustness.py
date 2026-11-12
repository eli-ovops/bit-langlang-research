"""06 稳健性：关键结论的按日聚类 bootstrap CI、多重比较、口径/剔除项敏感性。"""
import numpy as np
import pandas as pd

import common as C

p = C.attach_funding(C.load_positions())
pv = p[p["valid_size"]].copy()

# ---- 1. 关键结论 CI（按入场日整群 bootstrap，2000 次）---------------------
key = []


def add(name, df, col="net", note="", n_days=None):
    bs = C.cluster_bootstrap_sum(df, col, "day")
    t = C.tstat_cluster(df, col, "day")
    key.append(dict(conclusion=name, n=bs["n"], n_days=bs["n_clusters"], sum_point=bs["point"],
                    sum_ci_lo=bs["ci_lo"], sum_ci_hi=bs["ci_hi"],
                    mean_point=bs["mean_point"], mean_ci_lo=bs["mean_ci_lo"], mean_ci_hi=bs["mean_ci_hi"],
                    cluster_t=t["t"], note=note))


add("全样本净盈亏 (pnl+fee)", p, "net", "总收益是否显著>0")
add("全样本毛价格盈亏", p, "pnl", "")
add("每笔期望净收益", p, "net", "均值口径")
add("多头净盈亏", p[p["side"] == "多"], "net", "")
add("空头净盈亏", p[p["side"] == "空"], "net", "")
add("剔除 2024 后净盈亏", p[p["year"] != 2024], "net", "")
add("2024 净盈亏", p[p["year"] == 2024], "net", "")
# 去尾：删掉净收益最大的 20 笔
trim20 = p.sort_values("net", ascending=False).iloc[20:]
add("去掉最大 20 笔后净盈亏", trim20, "net", "尾部依赖度")
trim1 = p.sort_values("net", ascending=False).iloc[1:]
add("去掉最大 1 笔后净盈亏", trim1, "net", "")
# 持仓时长桶
for b in ["<5m", "5-30m", "30m-4h", "4h-24h", ">24h"]:
    add(f"持仓 {b} 净盈亏", p[p["hold_bucket"] == b], "net", "")
# 保证金十分位 top/bottom
add("保证金 D10 净盈亏", p[(p["valid_size"]) & (p["margin"] >= p[p["valid_size"]]["margin"].quantile(0.9))], "net", "")
add("保证金 D1 净盈亏", p[(p["valid_size"]) & (p["margin"] <= p[p["valid_size"]]["margin"].quantile(0.1))], "net", "")
# 等规模
add("等规模 R 合计(每笔保证金=1)", pv, "R_gross", "R 口径的总和")
keydf = pd.DataFrame(key)
C.save(keydf, "key_conclusions_ci.csv")

# ---- 2. 多重比较：本文件考察的独立分组检验数 -----------------------------
n_tests = 8 + 5 + 2 + 3 + 4  # 方向2/币种3/时长5/十分位10/年份3/反事实若干，粗略下界
from statistics import NormalDist

z = NormalDist().inv_cdf(1 - 0.05 / n_tests / 2)
mc = pd.DataFrame([
    dict(item="按入场日聚类的独立检验数（保守下界）", value=n_tests),
    dict(item="Bonferroni 0.05 阈值 (per-test p)", value=0.05 / n_tests),
    dict(item="对应双侧 |t| 阈值 (正态近似)", value=z),
])
C.save(mc, "multiple_comparison.csv")

# ---- 3. 资金费估算口径敏感性 --------------------------------------------
p_const = C.load_positions()
p_const = C.attach_funding(p_const)  # 插值口径
fund_interp = p_const[p_const["covered_mkt"]]["funding"].sum()


def funding_const_notional(p0: pd.DataFrame) -> float:
    tot = 0.0
    for mkt, grp in p0[p0["covered_mkt"]].groupby("mkt"):
        f = pd.read_csv(__import__("gzip").open(C.MKT / f"{mkt}_funding.csv.gz", "rt"))
        f["utc"] = pd.to_datetime(f["ts"], unit="ms")
        f = f.sort_values("utc").reset_index(drop=True)
        fts = f["utc"].values
        rates = f["funding_rate"].values
        for _, row in grp.iterrows():
            lo = np.searchsorted(fts, np.datetime64(row["entry_utc"]), side="right")
            hi = np.searchsorted(fts, np.datetime64(row["exit_utc"]), side="right")
            if hi > lo:
                tot += -row["side_sign"] * rates[lo:hi].sum() * row["notional"]
    return tot


fund_const = funding_const_notional(p_const)
# R 口径敏感性：pnl/margin vs 行内 ret 字段
pv2 = pv.copy()
pv2["R_ret"] = np.where(pv2["notional"] > 0, pv2["ret"] * pv2["leverage"], np.nan)
rr = pv2[["R_gross", "R_ret"]].corr().iloc[0, 1]
sens = pd.DataFrame([
    dict(check="资金费：5m 价格插值名义", value=fund_interp, note="主口径"),
    dict(check="资金费：固定入场名义", value=fund_const, note="敏感性；差异越小越稳"),
    dict(check="两种资金费口径差异", value=fund_const - fund_interp, note=""),
    dict(check="资金费占毛价格盈亏", value=fund_interp / p["pnl"].sum(), note="10 币子样本"),
    dict(check="R 定义：pnl/margin 与 ret*leverage 相关系数", value=rr, note="ret 字段不可靠，仅作校验"),
    dict(check="R 定义差异均值 (R_gross - ret*lev)", value=(pv2["R_gross"] - pv2["R_ret"]).mean(), note=""),
    dict(check="零名义 6 行手续费合计", value=p.loc[~p["valid_size"], "fee"].sum(), note="已计入 PnL 桥，R 口径剔除"),
    dict(check="负持仓 6 行净收益（仓口径；腿口径 7 行）", value=p.loc[p["hold_min"] < 0, "net"].sum(), note="保留打标；时长桶因 hold_min<0 归入 NaN，已单列"),
    dict(check="YFII 39 行若计入将增加的 pnl（审计值）", value=41_951_400.0, note="未计入，单列披露"),
    dict(check="YFII 计入后总毛盈亏倍数", value=(p["pnl"].sum() + 41_951_400.0) / p["pnl"].sum(), note=""),
])
C.save(sens, "robustness_sensitivity.csv")

# ---- 4. 尾部交易明细（前 30 笔净收益）------------------------------------
top = p.sort_values("net", ascending=False).head(30)[
    ["symbol", "side", "entry_time", "hold_min", "hold_bucket", "margin", "notional", "leverage",
     "pnl", "fee", "net", "R_gross", "win", "year"]
].reset_index(drop=True)
top.insert(0, "rank", np.arange(1, len(top) + 1))
C.save(top, "top_trades.csv")

# 前 20 笔的分年/时长集中度
t20 = p.sort_values("net", ascending=False).head(20)
print("top20 by year:", t20["year"].value_counts().to_dict())
print("top20 by hold bucket:", t20["hold_bucket"].astype(str).value_counts().to_dict())
print("top20 by side:", t20["side"].value_counts().to_dict())
print("top20 sum:", t20["net"].sum(), "of total", p["net"].sum())

print("\n=== key conclusions ===")
print(keydf.round(2).to_string(index=False))
print("\n=== multiple comparison ==="); print(mc.to_string(index=False))
print("\n=== sensitivity ==="); print(sens.round(4).to_string(index=False))
