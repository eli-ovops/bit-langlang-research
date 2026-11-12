"""09 市场背景（只做归因对照，不构造策略）：月度 PnL 与 BTC 月度涨跌的关系。

用途：检验"他的钱=牛市 β"这一假设能解释多少。
"""
import gzip

import numpy as np
import pandas as pd

import common as C

p = C.attach_funding(C.load_positions())

btc = pd.read_csv(gzip.open(C.MKT / "BTCUSDT_1d.csv.gz", "rt"), usecols=["ts", "close"])
btc["date"] = pd.to_datetime(btc["ts"], unit="ms")
btc = btc.sort_values("date").set_index("date")
bm = btc["close"].resample("ME").last().pct_change().dropna()
bm.index = bm.index.to_period("M").astype(str)
bm = bm.rename("btc_ret")

m = p.groupby("month").agg(n=("pnl", "size"), net=("net", "sum"), gross=("pnl", "sum"),
                           long_net=("net", lambda s: np.nan)).reset_index()
long = p[p["side"] == "多"].groupby("month")["net"].sum().rename("long_net")
short = p[p["side"] == "空"].groupby("month")["net"].sum().rename("short_net")
ctx = m.drop(columns="long_net").set_index("month").join(long).join(short).join(bm, how="left").reset_index()
ctx["long_share"] = ctx["long_net"] / ctx["net"]
C.save(ctx, "market_context_monthly.csv")

d = ctx.dropna(subset=["btc_ret"])
corr = d["net"].corr(d["btc_ret"])
# OLS: net = a + b*btc_ret
b, a = np.polyfit(d["btc_ret"], d["net"], 1)
resid = d["net"] - (a + b * d["btc_ret"])
r2 = 1 - resid.var() / d["net"].var()
# 仅用月度涨跌符号的简单分组
up = d[d["btc_ret"] > 0]["net"]
dn = d[d["btc_ret"] <= 0]["net"]

year_btc = btc["close"].resample("YE").last().pct_change()
year_btc.index = year_btc.index.year
yr = p.groupby("year").agg(n=("pnl", "size"), gross=("pnl", "sum"), net=("net", "sum")).reset_index()
yr["btc_ret"] = yr["year"].map(year_btc)
C.save(yr, "market_context_yearly.csv")

summary = pd.DataFrame([
    dict(item="月度 net 与 BTC 月度收益 相关系数", value=corr, note=f"n={len(d)} 个月（2022-05~2024-06）"),
    dict(item="回归斜率 (月度 net 每 +100% BTC)", value=b, note="美元/月"),
    dict(item="回归 R²", value=r2, note="β/牛市能解释的月度 PnL 方差比例"),
    dict(item="BTC 上涨月中 月度 net 均值", value=up.mean(), note=f"n={len(up)}"),
    dict(item="BTC 下跌月中 月度 net 均值", value=dn.mean(), note=f"n={len(dn)}"),
    dict(item="2023 BTC 全年涨幅", value=float(year_btc.get(2023, np.nan)), note="牛市但规模小"),
    dict(item="2024 H1 BTC 涨幅", value=float(btc["close"].loc["2023-12-31"] and
                                             btc["close"].loc["2024-06-30"] / btc["close"].loc["2023-12-31"] - 1), note=""),
    dict(item="2022-05-31~2022-12-31 BTC 涨幅", value=float(btc["close"].loc["2022-12-31"] / btc["close"].loc["2022-05-31"] - 1), note=""),
])
C.save(summary, "market_context_summary.csv")
print(summary.to_string(index=False))
print("\n", ctx.round(3).tail(14).to_string(index=False))
