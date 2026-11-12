"""01 PnL 桥：毛价格盈亏 -> 手续费 -> 资金费 -> 净盈亏（逐年/逐月/逐币）。

输出 data/attribution/
  pnl_bridge_summary.csv
  pnl_bridge_yearly.csv
  pnl_bridge_monthly.csv
  pnl_bridge_coverage.csv
"""
import numpy as np
import pandas as pd

import common as C

p = C.load_positions()
p = C.attach_funding(p)
l = C.load_legs()

gross = p["pnl"].sum()
fee = p["fee"].sum()
net_pre = p["net"].sum()
cov = p[p["covered_mkt"]]
unc = p[~p["covered_mkt"]]
funding = cov["funding"].sum()
net_after = net_pre + funding

# ---- 汇总 ----------------------------------------------------------------
rows = [
    dict(item="毛价格盈亏 (Σpnl)", scope="全样本 4,651 仓位", usdt=gross, note="交割单 pnl 字段=价格方向性盈亏，不含手续费（已验证）"),
    dict(item="手续费", scope="全样本", usdt=fee, note="fee 为负=支出；占毛价格盈亏 %.1f%%" % (-fee / gross * 100)),
    dict(item="净盈亏(不含资金费)", scope="全样本", usdt=net_pre, note="= Σpnl + Σfee"),
    dict(item="资金费", scope="10 币覆盖 2,499 仓位", usdt=funding, note="估算：见 common.attach_funding；负=支付"),
    dict(item="净盈亏(含资金费)", scope="全样本（未覆盖资金费按 0）", usdt=net_after, note="未覆盖 30.3% 仓位的资金费未计"),
    dict(item="毛价格盈亏", scope="10 币覆盖子样本", usdt=cov["pnl"].sum(), note="占全样本毛盈亏 %.1f%%" % (cov["pnl"].sum() / gross * 100)),
    dict(item="手续费", scope="10 币覆盖子样本", usdt=cov["fee"].sum(), note=""),
    dict(item="资金费", scope="10 币覆盖子样本", usdt=funding, note=""),
    dict(item="净盈亏", scope="10 币覆盖子样本", usdt=cov["net"].sum() + funding, note="= 毛 + 手续费 + 资金费"),
]
summary = pd.DataFrame(rows)
C.save(summary, "pnl_bridge_summary.csv")

# ---- 逐年 ----------------------------------------------------------------
def bridge_table(df: pd.DataFrame, key: str) -> pd.DataFrame:
    recs = []
    for k, g in df.groupby(key, sort=True):
        gc = g[g["covered_mkt"]]
        recs.append(
            dict(
                key=k,
                n=len(g),
                n_covered=len(gc),
                gross_pnl=g["pnl"].sum(),
                fee=g["fee"].sum(),
                net_pre_funding=g["net"].sum(),
                funding_covered=gc["funding"].sum(),
                net_after_funding=g["net"].sum() + gc["funding"].sum(),
                funding_coverage_pct=gc["pnl"].sum() / g["pnl"].sum() if g["pnl"].sum() else np.nan,
                fee_over_gross=(-g["fee"].sum() / g["pnl"].sum()) if g["pnl"].sum() else np.nan,
            )
        )
    return pd.DataFrame(recs)


yearly = bridge_table(p, "year")
monthly = bridge_table(p, "month")
C.save(yearly, "pnl_bridge_yearly.csv")
C.save(monthly, "pnl_bridge_monthly.csv")

# ---- 逐币覆盖 ------------------------------------------------------------
coin = (
    p.groupby("base")
    .agg(n=("pnl", "size"), gross_pnl=("pnl", "sum"), fee=("fee", "sum"), net=("net", "sum"),
         covered=("covered_mkt", "first"))
    .reset_index()
)
fmap = cov.groupby("base")["funding"].sum().rename("funding")
coin = coin.merge(fmap, on="base", how="left")
coin["funding"] = coin["funding"].fillna(0.0)
coin["net_after_funding"] = coin["net"] + coin["funding"]
coin["pnl_share"] = coin["net"] / net_pre
coin = coin.sort_values("net", ascending=False)
C.save(coin, "pnl_bridge_coverage.csv")

# ---- 对账（腿 vs 仓位；剔除项披露）--------------------------------------
leg_pnl = l["pnl"].sum()
leg_fee = l["fee"].sum()
recon = pd.DataFrame(
    [
        dict(item="腿口径 4,798 腿 Σpnl", value=leg_pnl),
        dict(item="仓口径 4,651 仓位 Σpnl", value=gross),
        dict(item="差（多腿聚合本身不改变总和）", value=gross - leg_pnl),
        dict(item="腿 Σfee", value=leg_fee),
        dict(item="仓 Σfee", value=fee),
        dict(item="YFII 39 行若计入应加回的 pnl（审计值）", value=41_951_400.0),
        dict(item="BNT 缺平仓时间行剔除的 pnl（审计值）", value=14_300.0),
        dict(item="YFII 加回后的毛 PnL（仅披露，不进入主口径）", value=gross + 41_951_400.0),
    ]
)
C.save(recon, "pnl_bridge_reconciliation.csv")

print("\n=== bridge ===")
print(summary.to_string(index=False))
print("\n=== yearly ===")
print(yearly.to_string(index=False))
print("\n=== recon ===")
print(recon.to_string(index=False))
print("\nfunding events distribution:", cov["funding_n_events"].value_counts().head(8).to_dict())
print("funding / gross covered:", funding / cov["pnl"].sum())
print("funding positive positions:", (cov["funding"] > 0).mean(), "negative:", (cov["funding"] < 0).mean())
