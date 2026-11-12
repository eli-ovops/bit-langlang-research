#!/usr/bin/env python3
"""从 vendor/BitLanglangReview 的 Excel 交割单提取干净 CSV + 基础统计。

输出：
  data/processed/trades_clean.csv      4810 条清洗后成交（基础字段 + 派生字段）
  data/processed/trades_labeled.csv    带"周期/开仓位置/复盘细节"标注的子集
  data/processed/coin_stats.csv        分币种统计
  data/processed/monthly.csv           月度统计
  data/processed/DATASET_REPORT.md     数据体检报告
"""
import os
import json
import pandas as pd
import numpy as np
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(ROOT, "vendor", "BitLanglangReview", "1_2022.5~2024.6浪浪交易交割单数据3 (1).xlsx")
OUT = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT, exist_ok=True)

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

# ---------- 1. 清洗后成交 ----------
ws = wb["时间排列+去除金额错误单子"]
rows = list(ws.iter_rows(values_only=True))
hdr = rows[1]
data = [r for r in rows[2:] if r[3] and r[0] is not None]
df = pd.DataFrame(data).iloc[:, :17].copy()
df.columns = ["id", "entry_time", "exit_time", "symbol", "side", "leverage", "margin",
              "entry_price", "exit_price", "ret", "pnl", "turnover", "qty", "notional",
              "fee", "note", "month"]
for c in ["leverage", "margin", "entry_price", "exit_price", "ret", "pnl", "turnover", "qty", "notional", "fee"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["entry_time"] = pd.to_datetime(df["entry_time"], errors="coerce")
df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")
df["hold_min"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60
df["side"] = df["side"].astype(str).str.strip()
df["symbol"] = df["symbol"].astype(str).str.strip()
df["base"] = df["symbol"].str.replace("-USDT-SWAP", "", regex=False)
df["win"] = (df["pnl"] > 0).astype(int)
df["amp_pct"] = (df["ret"] / df["leverage"]) * 100  # 收益率/杠杆 = 实际振幅
df = df.sort_values("entry_time").reset_index(drop=True)
df.to_csv(os.path.join(OUT, "trades_clean.csv"), index=False, encoding="utf-8-sig")

# ---------- 2. 带标注的子集（5%波动以上单子） ----------
ws2 = wb["5%波动以上单子"]
r2 = list(ws2.iter_rows(values_only=True))
d2 = [r for r in r2[2:] if r and r[0] is not None]
lab = pd.DataFrame([r[:26] for r in d2])
lab.columns = ["id", "symbol", "side", "leverage", "entry_price", "exit_price", "ret", "pnl",
               "turnover", "qty", "notional", "margin", "fee", "entry_time", "exit_time",
               "note", "month", "btc_cycle", "btc_cycle_anchor", "alt_cycle", "est_ret",
               "pred_entry_type", "actual_entry_type", "review_note", "op_detail", "hold_min"]
for c in ["leverage", "entry_price", "exit_price", "ret", "pnl", "est_ret"]:
    lab[c] = pd.to_numeric(lab[c], errors="coerce")
lab["entry_time"] = pd.to_datetime(lab["entry_time"], errors="coerce")
lab["exit_time"] = pd.to_datetime(lab["exit_time"], errors="coerce")
lab["hold_min"] = pd.to_numeric(lab["hold_min"], errors="coerce")
lab.to_csv(os.path.join(OUT, "trades_labeled.csv"), index=False, encoding="utf-8-sig")

# ---------- 3. 分币种 ----------
ws3 = wb["不同币做的收益率"]
r3 = list(ws3.iter_rows(values_only=True))
coin = pd.DataFrame([r for r in r3[1:] if r[0]], columns=["base", "count", "share", "ret_sum", "ret_per_trade"])
coin["count"] = pd.to_numeric(coin["count"], errors="coerce")
coin["ret_sum"] = pd.to_numeric(coin["ret_sum"], errors="coerce")
coin = coin.sort_values("count", ascending=False)
coin.to_csv(os.path.join(OUT, "coin_stats.csv"), index=False, encoding="utf-8-sig")

# ---------- 4. 月度 ----------
df["ym"] = df["entry_time"].dt.to_period("M").astype(str)
monthly = df.groupby("ym").agg(
    trades=("id", "count"),
    long=("side", lambda s: (s == "多").sum()),
    short=("side", lambda s: (s == "空").sum()),
    pnl=("pnl", "sum"),
    win_rate=("win", "mean"),
    avg_lev=("leverage", "mean"),
    med_hold_min=("hold_min", "median"),
).reset_index()
monthly.to_csv(os.path.join(OUT, "monthly.csv"), index=False, encoding="utf-8-sig")

# ---------- 5. 体检报告 ----------
def q(s, p):
    return float(np.nanpercentile(s, p)) if len(s) else float("nan")

long_df = df[df.side == "多"]
short_df = df[df.side == "空"]
wins = df[df.pnl > 0]["pnl"]
losses = df[df.pnl < 0]["pnl"]
gross_win, gross_loss = wins.sum(), -losses.sum()

top = df.nlargest(15, "pnl")[["entry_time", "base", "side", "leverage", "ret", "pnl", "hold_min"]]
worst = df.nsmallest(10, "pnl")[["entry_time", "base", "side", "leverage", "ret", "pnl", "hold_min"]]
tail_rows = []
for k in (1, 3, 5, 10, 20):
    s = df.drop(df.nlargest(k, "pnl").index)["pnl"].sum()
    tail_rows.append((k, s))

entry_counts = lab["pred_entry_type"].value_counts().head(10)
actual_counts = lab["actual_entry_type"].value_counts().head(10)

md = []
md.append("# 交割单数据体检报告\n")
md.append(f"- 源文件：`{os.path.basename(XLSX)}`（{os.path.getsize(XLSX)/1e6:.1f} MB）")
md.append(f"- 清洗后成交：**{len(df)} 笔**，{df.entry_time.min()} → {df.entry_time.max()}")
md.append(f"- 覆盖币种：**{df.base.nunique()} 个**；有标注的子集：{len(lab)} 笔\n")
md.append("## 1. 总览\n")
md.append("| 指标 | 值 |\n|---|---|")
md.append(f"| 总收益（USDT，按单笔收益累加） | {df.pnl.sum():,.0f} |")
md.append(f"| 胜率（pnl>0） | {df.win.mean()*100:.1f}% |")
md.append(f"| 平均盈利 / 平均亏损 | {wins.mean():,.0f} / {losses.mean():,.0f} |")
md.append(f"| 盈亏比（avgWin/|avgLoss|） | {wins.mean()/abs(losses.mean()):.2f} |")
md.append(f"| Profit Factor | {gross_win/gross_loss:.2f} |")
md.append(f"| 手续费合计 | {df.fee.sum():,.0f} |")
md.append(f"| 单笔收益中位数 | {df.pnl.median():,.0f} |")
md.append(f"| 收益 P5 / P25 / P75 / P95 | {q(df.pnl,5):,.0f} / {q(df.pnl,25):,.0f} / {q(df.pnl,75):,.0f} / {q(df.pnl,95):,.0f} |")
md.append(f"| 单笔收益率 P5 / P95 | {q(df.ret,5)*100:.1f}% / {q(df.ret,95)*100:.1f}% |")
md.append(f"| 杠杆：中位数 / P95 | {df.leverage.median():.0f}x / {q(df.leverage,95):.0f}x |")
md.append(f"| 持仓时间中位数 | {df.hold_min.median():.0f} 分钟 |")
md.append(f"| 持仓 <10 分钟占比 | {(df.hold_min<10).mean()*100:.1f}% |")
md.append(f"| 持仓 >24h 占比 | {(df.hold_min>1440).mean()*100:.2f}% |\n")
md.append("### 多空拆分\n")
md.append("| | 笔数 | 占比 | 收益 | 胜率 | 平均持仓(分) |\n|---|---|---|---|---|---|")
for name, d in (("多", long_df), ("空", short_df)):
    md.append(f"| {name} | {len(d)} | {len(d)/len(df)*100:.1f}% | {d.pnl.sum():,.0f} | {d.win.mean()*100:.1f}% | {d.hold_min.median():.0f} |")
md.append("")
md.append("## 2. 去尾检验（幂律依赖度）\n")
md.append("| 剔除最大 N 笔后总收益 | 值 |\n|---|---|")
for k, s in tail_rows:
    md.append(f"| N={k} | {s:,.0f} |")
md.append("")
md.append("## 3. 最大盈利 / 最大亏损\n")
md.append("Top 15 盈利：\n\n```\n" + top.to_string(index=False) + "\n```\n")
md.append("Top 10 亏损：\n\n```\n" + worst.to_string(index=False) + "\n```\n")
md.append("## 4. 币种分布 Top 20（按笔数）\n")
md.append("```\n" + coin.head(20).to_string(index=False) + "\n```\n")
md.append("按累计收益排序 Top 15：\n\n```\n" + coin.sort_values("ret_sum", ascending=False).head(15).to_string(index=False) + "\n```\n")
md.append("## 5. 月度\n")
md.append("```\n" + monthly.to_string(index=False) + "\n```\n")
md.append("## 6. 人工标注：开仓位置类型分布（预测）\n")
md.append("```\n" + entry_counts.to_string() + "\n```\n")
md.append("实际归类：\n\n```\n" + actual_counts.to_string() + "\n```\n")
md.append("## 7. 复盘文本样例（有标注的 5 笔）\n")
for _, r in lab[lab.review_note.notna()].head(5).iterrows():
    md.append(f"- **{r.symbol} {r.side}** {r.entry_time}：{r.review_note}")
md.append("")

with open(os.path.join(OUT, "DATASET_REPORT.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md))

print(f"OK: {len(df)} trades, {df.base.nunique()} symbols, labeled={len(lab)}")
print(f"pnl={df.pnl.sum():,.0f} win={df.win.mean()*100:.1f}% PF={gross_win/gross_loss:.2f}")
print("files:", os.listdir(OUT))
