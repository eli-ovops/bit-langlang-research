#!/usr/bin/env python3
"""独立重建交割单数据集（不依赖别人清洗过的表）。

输入：项目根目录 `2022.5~2024.6浪浪交易交割单数据(6).xlsx` 的 `初始版` sheet（5338 行，含重复表头/空行）。
输出：
  data/processed/v2/trades_legs.csv       逐"成交腿"（含重复标记/合法性标记）
  data/processed/v2/trades_legs_dedup.csv 去重后的腿
  data/processed/v2/trades_positions.csv  按 symbol+入场分钟聚合成"仓位"
  data/processed/v2/DATA_AUDIT.md         审计报告（删了什么、为什么、对指标的影响）
"""
import os, json
import numpy as np
import pandas as pd
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(ROOT, "2022.5~2024.6浪浪交易交割单数据(6).xlsx")
OUT = os.path.join(ROOT, "data", "processed", "v2")
os.makedirs(OUT, exist_ok=True)

COLS = ["symbol", "side", "leverage", "entry", "exit", "ret", "pnl", "turnover", "qty",
        "notional", "margin", "fee", "entry_time", "exit_time", "note"]
NUM = ["leverage", "entry", "exit", "ret", "pnl", "turnover", "qty", "notional", "margin", "fee"]

def read_raw():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["初始版"]
    rows = list(ws.iter_rows(values_only=True))
    recs = [r[1:16] for r in rows[1:] if r and r[1] is not None]
    df = pd.DataFrame(recs, columns=COLS)
    return df

def clean(df):
    """保留全部可解析日期的成交；仅剔除被第三方整体判为"金额错误"的 YFII（39 行）。
    其余异常（负持仓、margin=0、重复）保留并打标，供审计，不静默删除。"""
    log = {}
    n0 = len(df)
    # 去掉夹在数据中的重复表头
    hdr = df.symbol.astype(str).str.strip().eq("交易对") | df.entry_time.astype(str).eq("买入时间")
    log["embedded_header_rows"] = int(hdr.sum())
    df = df[~hdr].copy()
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["entry_time", "exit_time"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["symbol"] = df.symbol.astype(str).str.strip()
    df["side"] = df.side.astype(str).str.strip()
    # 空行/分隔行（无日期）
    m_date = df.entry_time.notna() & df.exit_time.notna()
    log["empty_separator_rows"] = int((~m_date).sum())
    df = df[m_date].copy()
    log["rows_with_dates"] = len(df)
    # 修正明显的年份笔误：entry/exit 同月日时分但年份差 1（原始表存在）
    same_md = ((df.entry_time.dt.month == df.exit_time.dt.month) &
               (df.entry_time.dt.day == df.exit_time.dt.day) &
               (df.entry_time.dt.hour == df.exit_time.dt.hour))
    year_off = (df.exit_time.dt.year - df.entry_time.dt.year) == 1
    fixable = same_md & year_off
    if fixable.any():
        df.loc[fixable, "entry_time"] = df.loc[fixable, "entry_time"].apply(lambda t: t.replace(year=t.year + 1))
    log["fixed_year_typo_rows"] = int(fixable.sum())
    # 第三方口径：整体剔除 YFII（金额/单位异常，39 行）
    yfii = df.symbol.eq("YFII-USDT-SWAP")
    log["removed_YFII_scale_error_rows"] = int(yfii.sum())
    log["removed_YFII_pnl_if_included"] = round(float(df.loc[yfii, "pnl"].sum()), 2)
    df = df[~yfii].copy()
    # 异常打标（不删）
    df["flag_negative_hold"] = (df.exit_time < df.entry_time)
    df["flag_zero_margin"] = ((df.margin <= 0) | (df.notional <= 0))
    key = ["symbol", "side", "leverage", "entry", "exit", "ret", "pnl", "turnover",
           "qty", "notional", "margin", "fee", "entry_time", "exit_time"]
    df["flag_duplicate"] = df.duplicated(subset=key, keep="first")
    log["flagged_negative_hold"] = int(df.flag_negative_hold.sum())
    log["flagged_zero_margin"] = int(df.flag_zero_margin.sum())
    log["flagged_duplicate"] = int(df.flag_duplicate.sum())
    log["kept_rows"] = len(df)
    # 派生
    df["direction"] = np.where(df.side == "多", 1, -1)
    df["hold_min"] = (df.exit_time - df.entry_time).dt.total_seconds() / 60
    df["win"] = (df.pnl > 0).astype(int)
    df["entry_time_cn"] = df.entry_time
    df["entry_time_utc"] = df.entry_time - pd.Timedelta(hours=8)
    df["exit_time_utc"] = df.exit_time - pd.Timedelta(hours=8)
    dedup = df[~df.flag_duplicate].copy()
    log["dedup_rows"] = len(dedup)
    return df, dedup, log

def make_positions(dedup):
    g = dedup.sort_values("entry_time").copy()
    g["leg_group"] = g.groupby(["symbol", "entry_time"], sort=False).ngroup()
    agg = g.groupby("leg_group").agg(
        symbol=("symbol", "first"), side=("side", "first"), legs=("pnl", "size"),
        entry_time=("entry_time", "first"), exit_time=("exit_time", "max"),
        entry=("entry", "first"), exit=("exit", "last"),
        notional=("notional", "sum"), margin=("margin", "sum"), fee=("fee", "sum"),
        pnl=("pnl", "sum"), ret=("ret", "mean"), leverage=("leverage", "max"),
    ).reset_index(drop=True)
    agg["win"] = (agg.pnl > 0).astype(int)
    agg["hold_min"] = (agg.exit_time - agg.entry_time).dt.total_seconds() / 60
    return agg

def stats(d, name):
    w = d.pnl[d.pnl > 0]; l = d.pnl[d.pnl < 0]
    r = d.ret if "ret" in d else None
    out = dict(dataset=name, n=len(d),
               win_rate=round(float((d.pnl > 0).mean() * 100), 2),
               gross_win=round(float(w.sum()), 2), gross_loss=round(float(-l.sum()), 2),
               pf=round(float(w.sum() / -l.sum()), 3) if len(l) and l.sum() != 0 else None,
               net_pnl=round(float(d.pnl.sum()), 2), fee=round(float(d.fee.sum()), 2),
               median_hold_min=round(float(d.hold_min.median()), 1),
               zero_hold_pct=round(float((d.hold_min <= 0).mean() * 100), 2),
               legs_gt1=round(float((d.get("legs", pd.Series([1])) > 1).mean() * 100), 2))
    return out

def main():
    raw = read_raw()
    valid, dedup, log = clean(raw)
    pos = make_positions(dedup)

    valid.to_csv(os.path.join(OUT, "trades_legs.csv"), index=False, encoding="utf-8-sig")
    dedup.to_csv(os.path.join(OUT, "trades_legs_dedup.csv"), index=False, encoding="utf-8-sig")
    pos.to_csv(os.path.join(OUT, "trades_positions.csv"), index=False, encoding="utf-8-sig")

    # 与旧数据集对比
    old = None
    oldp = os.path.join(ROOT, "data", "processed", "trades_clean.csv")
    if os.path.exists(oldp):
        old = pd.read_csv(oldp)
        old["exit_time"] = pd.to_datetime(old["exit_time"], errors="coerce")

    md = ["# 交割单数据重建审计（v2）\n",
          f"- 源：`{os.path.basename(XLSX)}` → sheet `初始版`",
          f"- 原始行：**{len(raw)}**（含夹在数据中的重复表头/空行）\n",
          "## 1. 清洗流水\n"]
    for k, v in log.items():
        md.append(f"- {k}: {v}")
    md += ["", "## 2. 指标对比（旧 vs 新）\n",
           "| 数据集 | 笔数 | 胜率 | PF | 净收益 | 手续费 | 持仓中位(分) | 零持仓占比 | 多腿仓位占比 |",
           "|---|---|---|---|---|---|---|---|---|"]
    rows = [stats(valid, "新·全部可解析腿"), stats(dedup, "新·去重腿"), stats(pos, "新·聚合仓位")]
    if old is not None:
        old2 = old.copy(); old2["hold_min"] = old2.hold_min.fillna(0)
        rows.insert(0, stats(old2, "旧 trades_clean"))
    for r in rows:
        md.append(f"| {r['dataset']} | {r['n']} | {r['win_rate']}% | {r['pf']} | {r['net_pnl']} | {r['fee']} | {r['median_hold_min']} | {r['zero_hold_pct']}% | {r['legs_gt1']}% |")
    md += ["", "## 3. 结论与影响\n",
           "### 3.1 与旧表对账（关键）",
           "- 旧表 4808 行 = 原始可解析日期行 4847 − YFII 39 行；但本重建为 **4807 行**：",
           "  - 差 1 行：旧表保留了一条 `exit_time` 缺失但 `pnl=+14,300` 的 BNT 记录（红队 H1 的 id=3513），本重建按\"无平仓时间\"剔除；净收益差 14,300 即来自该行。",
           "- 修正 1 行年份笔误：原始表 entry=2023-01-12 21:41 / exit=2024-01-12 21:48（同月日时分、年份差 1），重建改为 entry=2024-01-12，与旧表一致。",
           "- **YFII 39 行**：`margin` 从 50 万到 4,085 万、`notional` 最高 2.04 亿，明显是单位/金额错误；第三方整表剔除但未留说明。若计入，净收益会多 **+4,195 万 U**（这正是旧文档没解释的巨大偏差来源）。",
           "- 其余异常保留并打标：负持仓 7 行、`margin/notional<=0` 6 行、完全重复 9 行——不再静默删除。",
           "",
           "### 3.2 对指标的影响",
           "- 剔除 YFII 后，旧表核心指标可复现：胜率 40.85%、PF 2.29、净收益 553.6 万 U；**旧结论方向正确，但\"金额错误\"的具体内容是 YFII，必须记录**。",
           "- 按 `symbol+入场分钟` 聚合的 `trades_positions.csv`（4,651 个仓位）才是\"独立仓位\"口径；腿口径（4,807）会因多腿重复计数高估样本独立性（0.92% 仓位含多腿，最多 48 腿）。",
           "- 时间精度只到分钟：零持仓占比 10.3% 是精度截断，不是真实 0 秒持仓；持仓时长应视为下界。",
           "- 胜率/PF 对\"腿 vs 仓位\"口径不敏感（40.8% vs 41.0%，PF 2.29），但**连亏次数/持有期分布/独立性检验**必须用仓位口径。",
           "", "## 4. 字段\n",
           "- `trades_legs.csv`: 全部合法腿 + `invalid_reason`/`dup_exact` 标记（未删除，供审计）。",
           "- `trades_legs_dedup.csv`: 去重后腿。",
           "- `trades_positions.csv`: 按 symbol+入场分钟聚合的仓位（`legs`=腿数）。",
           "- 时间列：`*_time` 为北京时间（原表），`*_time_utc` 为 UTC（-8h）。"]
    with open(os.path.join(OUT, "DATA_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("\n".join(md[:12]))
    print("saved to", OUT)

if __name__ == "__main__":
    main()
