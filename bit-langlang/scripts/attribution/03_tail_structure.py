"""03 尾部结构：去尾、集中度、分布不对称度。

口径：单笔净收益 net = pnl + fee（不含资金费，资金费只在 10 币子样本可算且量级 <3%）。
去尾 = 直接删除该仓位（连同其手续费），这是"没有这笔交易"的反事实。
"""
import numpy as np
import pandas as pd

import common as C

p = C.load_positions()
p = p.sort_values("net", ascending=False).reset_index(drop=True)
n_all = len(p)
total_net = p["net"].sum()
total_gross = p["pnl"].sum()

# ---- 1. 去尾 -------------------------------------------------------------
recs = []
for k in [0, 1, 3, 5, 10, 20, 50, 100]:
    if k == 0:
        sub = p
    else:
        sub = p.iloc[k:]
    bs = C.cluster_bootstrap_sum(sub, "net", "day")
    recs.append(
        dict(
            removed_top_k=k,
            n=len(sub),
            net=sub["net"].sum(),
            net_retained_pct=sub["net"].sum() / total_net,
            net_ci_lo=bs["ci_lo"],
            net_ci_hi=bs["ci_hi"],
            gross_pnl=sub["pnl"].sum(),
            fee=sub["fee"].sum(),
            mean_net=sub["net"].mean(),
        )
    )
tails = pd.DataFrame(recs)
C.save(tails, "tail_trim.csv")

# ---- 2. 集中度 -----------------------------------------------------------
pos = p[p["net"] > 0].reset_index(drop=True)
conc = []
cum = 0.0
for i, v in enumerate(p["net"].values, start=1):
    cum += v
    conc.append((i, cum))
conc = pd.DataFrame(conc, columns=["rank", "cum_net"])
targets = [0.5, 0.8, 0.9, 1.0]
rows = []
for t in targets:
    hit = conc[conc["cum_net"] >= t * total_net]
    rows.append(dict(metric=f"净收益达到总量 {t:.0%} 所需 top 交易数", value=int(hit["rank"].iloc[0]) if len(hit) else None,
                     pct_of_n=(int(hit["rank"].iloc[0]) / n_all) if len(hit) else None))
# top k% 贡献
for q in [0.01, 0.05, 0.10]:
    k = max(1, int(round(n_all * q)))
    rows.append(dict(metric=f"Top {q:.0%} (n={k}) 的净收益合计占比", value=float(p["net"].head(k).sum() / total_net), pct_of_n=q))
rows.append(dict(metric="最大单笔净收益", value=float(p["net"].iloc[0]), pct_of_n=float(p["net"].iloc[0] / total_net)))
rows.append(dict(metric="最大单笔净收益占毛价格盈亏", value=float(p["net"].iloc[0]), pct_of_n=float(p["net"].iloc[0] / total_gross)))
rows.append(dict(metric="最大单笔毛盈亏", value=float(p["pnl"].max()), pct_of_n=float(p["pnl"].max() / total_gross)))
rows.append(dict(metric="前 10 笔净收益合计", value=float(p["net"].head(10).sum()), pct_of_n=float(p["net"].head(10).sum() / total_net)))
rows.append(dict(metric="前 20 笔净收益合计", value=float(p["net"].head(20).sum()), pct_of_n=float(p["net"].head(20).sum() / total_net)))
conc = pd.concat([pd.DataFrame(rows), conc.tail(0)], ignore_index=True)
C.save(conc, "tail_concentration.csv")

# ---- 3. 分布不对称 -------------------------------------------------------
net = p["net"]
gross_wins = p.loc[p["pnl"] > 0, "pnl"].sum()
gross_losses = -p.loc[p["pnl"] < 0, "pnl"].sum()
base = pd.DataFrame(
    [
        dict(metric="n", value=n_all),
        dict(metric="总净收益", value=total_net),
        dict(metric="均值 net/笔", value=net.mean()),
        dict(metric="中位 net/笔", value=net.median()),
        dict(metric="均值/中位比", value=net.mean() / net.median() if net.median() else np.nan),
        dict(metric="胜率(pnl>0)", value=(p["pnl"] > 0).mean()),
        dict(metric="平均盈利", value=p.loc[p["pnl"] > 0, "pnl"].mean()),
        dict(metric="平均亏损", value=p.loc[p["pnl"] < 0, "pnl"].mean()),
        dict(metric="盈亏比 avgWin/|avgLoss|", value=abs(p.loc[p["pnl"] > 0, "pnl"].mean() / p.loc[p["pnl"] < 0, "pnl"].mean())),
        dict(metric="PF 毛利/毛损", value=gross_wins / gross_losses),
        dict(metric="净收益偏度 skew", value=net.skew()),
        dict(metric="净收益峰度 kurtosis", value=net.kurt()),
        dict(metric="R_gross 偏度", value=p["R_gross"].skew()),
        dict(metric="净收益 5%/25%/50%/75%/95% 分位",
             value=float(0)),  # placeholder, see next
        dict(metric="q05", value=net.quantile(0.05)),
        dict(metric="q25", value=net.quantile(0.25)),
        dict(metric="q50", value=net.quantile(0.50)),
        dict(metric="q75", value=net.quantile(0.75)),
        dict(metric="q95", value=net.quantile(0.95)),
        dict(metric="盈利交易合计(毛)", value=gross_wins),
        dict(metric="亏损交易合计(毛)", value=-gross_losses),
        dict(metric="最大 20 笔盈利合计", value=p["net"].head(20).sum()),
        dict(metric="最差 20 笔亏损合计", value=p["net"].tail(20).sum()),
    ]
)
base = base[base["metric"] != "净收益 5%/25%/50%/75%/95% 分位"]
# 单笔净收益的聚类 bootstrap：均值 CI + 总量 CI
bs_all = C.cluster_bootstrap_sum(p, "net", "day")
base.loc[len(base)] = dict(metric="总量 net CI95 lo", value=bs_all["ci_lo"])
base.loc[len(base)] = dict(metric="总量 net CI95 hi", value=bs_all["ci_hi"])
base.loc[len(base)] = dict(metric="均值 net CI95 lo", value=bs_all["mean_ci_lo"])
base.loc[len(base)] = dict(metric="均值 net CI95 hi", value=bs_all["mean_ci_hi"])
C.save(base, "tail_distribution.csv")

# ---- 4. 尾部 vs 中位：按净收益分层的贡献 ---------------------------------
p["sign"] = np.sign(p["net"])
layer = p.groupby("sign").agg(n=("net", "size"), net=("net", "sum"), mean=("net", "mean"), median=("net", "median")).reset_index()
C.save(layer, "tail_sign_layer.csv")

# ---- 5. 尾部与持仓时长的交叉（关键：大钱在哪）---------------------------
crosstab = (
    p.groupby("hold_bucket", observed=True)
    .agg(n=("net", "size"), net=("net", "sum"), top20_net=("net", lambda s: s.nlargest(20).sum()))
    .reset_index()
)
crosstab["net_share"] = crosstab["net"] / total_net
C.save(crosstab, "tail_hold_crosstab.csv")

print("=== trim ==="); print(tails.round(1).to_string(index=False))
print("\n=== concentration ==="); print(conc.to_string(index=False))
print("\n=== distribution ==="); print(base.round(4).to_string(index=False))
print("\n=== hold crosstab ==="); print(crosstab.round(3).to_string(index=False))
