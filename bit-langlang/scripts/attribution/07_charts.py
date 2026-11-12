"""07 图表（可选）：把 data/attribution 里的结果画成 PNG。"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import common as C

plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang HK", "Heiti TC", "Hiragino Sans GB"]
plt.rcParams["axes.unicode_minus"] = False

FIG = C.OUT / "figures"
FIG.mkdir(exist_ok=True)

p = C.attach_funding(C.load_positions()).sort_values("exit_time").reset_index(drop=True)
p["cum_net"] = p["net"].cumsum()

# 1. 累计净收益（实际） vs 固定 1% 风险复利（等规模）
eq = pd.read_csv(C.OUT / "counterfactual_equity_net.csv", parse_dates=["exit_time"])
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.plot(p["exit_time"], p["cum_net"] / 1e6, lw=1.2, label="实际累计净收益 (百万U)")
ax.set_ylabel("累计净收益 (百万 USDT)")
ax2 = ax.twinx()
ax2.plot(eq["exit_time"], eq["equity"], color="tab:orange", lw=1.2,
         label="1% 风险/笔 复利 (保证金=风险, 倍数)")
ax2.set_ylabel("复利倍数 (R_net, 1%/笔)")
ax.axvline(pd.Timestamp("2024-01-01"), color="gray", ls="--", lw=0.8)
ax.set_title("实际累计收益 vs 等规模复利：规模放大贡献了绝大部分")
lines = ax.get_lines()[:1] + ax2.get_lines()[:1]
ax.legend(lines, [l.get_label() for l in lines], loc="upper left", fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "fig1_equity_vs_compound.png", dpi=130)
plt.close(fig)

# 2. 月度净收益
m = pd.read_csv(C.OUT / "scale_turnover_monthly.csv")
fig, ax = plt.subplots(figsize=(9, 3.6))
cols = ["tab:gray" if str(x)[:4] != "2024" else "tab:red" for x in m["month"]]
ax.bar(m["month"], m["net"] / 1e3, color=cols)
ax.set_title("月度净收益 (千 USDT)；红色=2024")
ax.set_ylabel("千 USDT")
ax.tick_params(axis="x", rotation=90, labelsize=7)
fig.tight_layout()
fig.savefig(FIG / "fig2_monthly_net.png", dpi=130)
plt.close(fig)

# 3. 持仓时长分桶 net + CI
h = pd.read_csv(C.OUT / "dim_hold_bucket.csv")
fig, ax = plt.subplots(figsize=(7, 3.6))
x = np.arange(len(h))
ax.bar(x, h["sum_net"] / 1e3, color="tab:blue")
ax.errorbar(x, h["sum_net"] / 1e3,
            yerr=[(h["sum_net"] - h["sum_net_ci_lo"]) / 1e3, (h["sum_net_ci_hi"] - h["sum_net"]) / 1e3],
            fmt="none", ecolor="k", capsize=4, lw=1)
ax.set_xticks(x, h["group"])
ax.axhline(0, color="k", lw=0.6)
ax.set_title("净收益按持仓时长桶（按日聚类 bootstrap 95%CI）")
ax.set_ylabel("千 USDT")
fig.tight_layout()
fig.savefig(FIG / "fig3_hold_bucket.png", dpi=130)
plt.close(fig)

# 4. 单笔净收益分布（对称对数）+ 尾部贡献曲线
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
net = p["net"].values
bins = np.concatenate([-np.logspace(6, 0, 40), [0], np.logspace(0, 6, 40)])
a1.hist(np.clip(net, -1e6, 1e6), bins=bins, color="tab:purple")
a1.set_xscale("symlog", linthresh=1)
a1.set_title("单笔净收益分布 (symlog)")
a1.set_xlabel("net USDT")
a1.set_ylabel("笔数")
ranked = np.sort(net)[::-1]
cum = np.cumsum(ranked)
a2.plot(np.arange(1, len(cum) + 1), cum / cum[-1], lw=1.5)
a2.axhline(0.5, color="gray", ls="--", lw=0.8)
a2.axhline(0.8, color="gray", ls=":", lw=0.8)
a2.set_xlim(0, 200)
a2.set_title("按排名累计净收益占比 (前 200 笔)")
a2.set_xlabel("排名")
a2.set_ylabel("累计占比")
fig.tight_layout()
fig.savefig(FIG / "fig4_distribution_tail.png", dpi=130)
plt.close(fig)

# 5. 规模 vs 每笔优势（双面板，避免 symlog 误导）
se = pd.read_csv(C.OUT / "counterfactual_equal_size_yearly.csv")
se = se[se["year"] != "合计"].copy()
_st = pd.read_csv(C.OUT / "scale_turnover_yearly.csv")
se["margin_median"] = se["year"].astype(str).map(
    _st.set_index(_st["year"].astype(str))["margin_median"].to_dict())
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
xx = np.arange(len(se))
a1.bar(xx, se["actual_gross_pnl"] / 1e6, color="tab:blue")
a1.set_xticks(xx, se["year"])
a1.set_title("实际毛 PnL (百万 U)")
a1.set_ylabel("百万 USDT")
for i, v in enumerate(se["actual_gross_pnl"] / 1e6):
    a1.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
a2.bar(xx - 0.18, se["sum_R_gross"], 0.36, color="tab:orange", label="等规模 ΣR_gross")
a2.bar(xx + 0.18, se["sum_R_net"], 0.36, color="tab:purple", label="等规模 ΣR_net")
a2.set_xticks(xx, se["year"])
a2.set_title("每笔优势（ΣR，保证金=1）")
a2.set_ylabel("ΣR")
a2.legend(fontsize=8)
ax3 = a2.twinx()
ax3.plot(xx, se["margin_median"] / 1e3, "o-", color="tab:green", label="保证金中位(千U)")
ax3.set_ylabel("保证金中位数 (千 U)")
ax3.legend(fontsize=8, loc="upper left")
fig.suptitle("逐年：规模（保证金）暴涨 59×，每笔优势（ΣR）没有变强", fontsize=11)
fig.tight_layout()
fig.savefig(FIG / "fig5_scale_vs_edge.png", dpi=130)
plt.close(fig)

print("figures ->", FIG)
for f in sorted(FIG.iterdir()):
    print(" ", f.name, f.stat().st_size)
