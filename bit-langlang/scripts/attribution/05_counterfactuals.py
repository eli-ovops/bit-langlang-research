"""05 反事实（纯算术重算，不重跑策略）。

统一口径：净盈亏 = Σ(pnl + fee) + Σ资金费（资金费仅在 10 币覆盖子样本可算，未覆盖按 0）。
C0  基线净盈亏（含可算资金费）
C1  零手续费
C2  零资金费
C3  零手续费 + 零资金费
C4  只做多 / C5 只做空
C6  剔除 2024 / C6b 只保留 2024
C7  等规模：每笔保证金=1，PnL = ΣR_gross / ΣR_net（分离规模增长与每笔优势）
C8  固定风险 1%/笔复利（用 R 按平仓时间顺序；近似，见 note）
C9  规模冻结在 2022 / 2023 中位保证金
"""
import numpy as np
import pandas as pd

import common as C

p = C.attach_funding(C.load_positions()).sort_values("exit_time").reset_index(drop=True)
pv = p[p["valid_size"]].copy()


def nf(df):
    """净盈亏（含可算资金费）。"""
    return df["net"].sum() + df[df["covered_mkt"]]["funding"].sum()


base = nf(p)
base_ex_fund = p["net"].sum()
gross = p["pnl"].sum()
fee = p["fee"].sum()
funding = p[p["covered_mkt"]]["funding"].sum()

rows = []


def add(name, value, n, note, ci=None):
    rows.append(dict(scenario=name, value=value, n=n, delta_vs_base=value - base,
                     ci_lo=ci[0] if ci else np.nan, ci_hi=ci[1] if ci else np.nan, note=note))


add("C0 基线净盈亏（含可算资金费）", base, len(p), "= Σ(pnl+fee)+Σfunding；未覆盖 2,152 仓位的资金费按 0")
add("C0b 基线（不含资金费）", base_ex_fund, len(p), "= Σ(pnl+fee)")
add("C1 零手续费（资金费保留）", gross + funding, len(p), "手续费全部返还的反事实")
add("C2 零资金费", base_ex_fund, len(p), "去掉全部资金费支出")
add("C3 零手续费+零资金费", gross, len(p), "= Σpnl，纯方向性、零摩擦")

long = p[p["side"] == "多"]
short = p[p["side"] == "空"]
bsl = C.cluster_bootstrap_sum(long, "net", "day")
bss = C.cluster_bootstrap_sum(short, "net", "day")
add("C4 只做多", nf(long), len(long), "多单净盈亏（含多单资金费）", (bsl["ci_lo"], bsl["ci_hi"]))
add("C5 只做空", nf(short), len(short), "空单净盈亏", (bss["ci_lo"], bss["ci_hi"]))

no24 = p[p["year"] != 2024]
y24 = p[p["year"] == 2024]
bsn = C.cluster_bootstrap_sum(no24, "net", "day")
bsy = C.cluster_bootstrap_sum(y24, "net", "day")
add("C6 剔除 2024（2022-05~2023-12）", nf(no24), len(no24), "只保留 2022-05~2023-12", (bsn["ci_lo"], bsn["ci_hi"]))
add("C6b 只保留 2024（1-6 月）", nf(y24), len(y24), "", (bsy["ci_lo"], bsy["ci_hi"]))

add("C7 等规模：ΣR_gross（每笔保证金=1）", pv["R_gross"].sum(), len(pv),
    "Σ(pnl/margin)；1 单位 = 1U 保证金，可与实际 PnL 对比看规模贡献")
add("C7b 等规模：ΣR_net（每笔保证金=1）", pv["R_net"].sum(), len(pv), "Σ((pnl+fee)/margin)")
add("C7c 等规模多头 ΣR_gross", pv[pv["side"] == "多"]["R_gross"].sum(), (pv["side"] == "多").sum(), "")
add("C7d 等规模空头 ΣR_gross", pv[pv["side"] == "空"]["R_gross"].sum(), (pv["side"] == "空").sum(), "")
add("C7e 等规模·剔除 2024 ΣR_gross", pv[pv["year"] != 2024]["R_gross"].sum(), (pv["year"] != 2024).sum(), "")
add("C7f 等规模·仅 2024 ΣR_gross", pv[pv["year"] == 2024]["R_gross"].sum(), (pv["year"] == 2024).sum(), "")

m22 = p[p["year"] == 2022]["margin"].median()
m23 = p[p["year"] == 2023]["margin"].median()
add("C9 规模冻结在 2022 中位保证金", pv["R_gross"].sum() * m22, len(pv),
    f"每笔保证金固定 {m22:,.0f}U，ΣR_gross×{m22:,.0f}")
add("C9b 规模冻结在 2023 中位保证金", pv["R_gross"].sum() * m23, len(pv),
    f"每笔保证金固定 {m23:,.0f}U")

# ---- 固定风险 1% 复利 ----------------------------------------------------
def compound(df: pd.DataFrame, rcol: str, risk: float = 0.01) -> pd.DataFrame:
    d = df.dropna(subset=[rcol]).sort_values("exit_time").copy()
    r = d[rcol].values
    eqv = np.empty(len(d) + 1)
    eqv[0] = 1.0
    for i in range(len(d)):
        eqv[i + 1] = eqv[i] * (1.0 + risk * r[i])
    d["equity"] = eqv[1:]
    peak = np.maximum.accumulate(eqv)
    d["drawdown"] = (eqv / peak - 1.0)[1:]
    return d


res = []
curves = {}
for label, rcol in [("R_net", "R_net"), ("R_gross", "R_gross")]:
    d = compound(pv, rcol)
    curves[label] = d[["exit_time", "equity", "drawdown", rcol]].rename(columns={rcol: "R"})
    res.append(dict(scenario=f"C8 固定风险 1%/笔复利 [{label}]", value=float(d["equity"].iloc[-1]),
                    n=len(d), delta_vs_base=np.nan, ci_lo=np.nan, ci_hi=np.nan,
                    note=f"终值={d['equity'].iloc[-1]:.3f}x；最大回撤={d['drawdown'].min():.2%}；按平仓时间顺序；"
                         f"以 margin 收益近似 R（无止损口径），见局限"))

cf = pd.DataFrame(rows + res)
C.save(cf, "counterfactuals.csv")
C.save(curves["R_net"], "counterfactual_equity_net.csv")

# ---- 等规模逐年 ----------------------------------------------------------
eq = pv.groupby("year").agg(n=("R_gross", "size"), sum_R_gross=("R_gross", "sum"), sum_R_net=("R_net", "sum"),
                            mean_R_gross=("R_gross", "mean"), median_R_gross=("R_gross", "median"),
                            actual_gross_pnl=("pnl", "sum")).reset_index()
eq.loc[len(eq)] = dict(year="合计", n=len(pv), sum_R_gross=pv["R_gross"].sum(), sum_R_net=pv["R_net"].sum(),
                       mean_R_gross=pv["R_gross"].mean(), median_R_gross=pv["R_gross"].median(),
                       actual_gross_pnl=pv["pnl"].sum())
eq["implied_avg_margin"] = eq["actual_gross_pnl"] / eq["sum_R_gross"]
C.save(eq, "counterfactual_equal_size_yearly.csv")

# ---- 分年复利 ------------------------------------------------------------
seg = []
for y, g in pv.groupby("year"):
    d = compound(g, "R_net")
    seg.append(dict(year=y, n=len(d), equity_end=float(d["equity"].iloc[-1]), max_dd=float(d["drawdown"].min())))
seg = pd.DataFrame(seg)
C.save(seg, "counterfactual_compounding_by_year.csv")

print("=== counterfactuals ===")
print(cf[["scenario", "value", "n", "delta_vs_base", "ci_lo", "ci_hi"]].round(1).to_string(index=False))
print("\n=== equal size by year ==="); print(eq.round(3).to_string(index=False))
print("\n=== compounding by year ==="); print(seg.round(3).to_string(index=False))
print("\n=== compound summary ==="); print(pd.DataFrame(res)[["scenario", "note"]].to_string(index=False))
print("\nimplied avg margin = Σpnl/ΣR =", pv["pnl"].sum() / pv["R_gross"].sum())
print("base incl funding:", base, " funding:", funding)
