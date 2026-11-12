"""04 — 统计汇总：捕获率、反事实出场/入场、波动-空间选择、alpha 分解。

口径：
  * 收益单位 = % 价格变动（1R = 1%），已扣该笔自己的实际手续费（fee/notional）。
  * 区间 = 按入场日（UTC）聚类的 bootstrap 95%CI（重采样日、按原始笔数加权，2000 次）；
    t = 聚类稳健 t（Liang-Zeger）。见 common.cluster_bootstrap_mean。
  * 去尾 = 剔除该指标自身最大的 5 笔。
  * 多重比较：所有检验都在 T19 登记，给 Bonferroni 阈值。
产物：data/entry_exit/tables/*.csv, summary.json, tables.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

TAB = C.OUT / "tables"
TAB.mkdir(parents=True, exist_ok=True)
for _old in TAB.glob("*.csv"):   # 保证重跑不残留旧表
    _old.unlink()

HORIZONS = ["5m", "30m", "1h", "4h", "24h", "72h"]
POST = ["5m", "30m", "1h", "4h", "24h"]
NBOOT = 2000
MD = []


# --------------------------------------------------------------------------- #
def stat(v, days, trim_top: int = 0) -> dict:
    v = np.asarray(v, dtype=float)
    days = np.asarray(days)
    ok = np.isfinite(v)
    v, days = v[ok], days[ok]
    if len(v) == 0:
        return dict(n=0)
    out = dict(n=int(len(v)), mean=float(v.mean()), median=float(np.median(v)),
               std=float(v.std(ddof=1)) if len(v) > 1 else np.nan,
               win_rate=float((v > 0).mean()), sum=float(v.sum()))
    g = C.cluster_bootstrap_mean(v, days, n_boot=NBOOT)
    out.update(ci_lo=g["ci_lo"], ci_hi=g["ci_hi"], t=g["t"], n_days=g["n_days"])
    if trim_top:
        keep = np.argsort(v)[:-trim_top] if trim_top < len(v) else np.array([], dtype=int)
        out["mean_trim5"] = float(v[keep].mean()) if len(keep) else np.nan
        out["sum_trim5"] = float(v[keep].sum()) if len(keep) else np.nan
    return out


def paired(a, b, days, trim_top: int = 0) -> dict:
    return stat(np.asarray(a) - np.asarray(b), days, trim_top=trim_top)


def pf(v) -> float:
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    gl = -v[v < 0].sum()
    return float(v[v > 0].sum() / gl) if gl > 0 else np.nan


def skew(v) -> float:
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    m, sd = v.mean(), v.std()
    return float(((v - m) ** 3).mean() / sd**3) if sd > 0 else np.nan


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if not np.isfinite(v) else floatfmt.format(v))
            else:
                cells.append("" if pd.isna(v) else str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def section(title: str, df: pd.DataFrame, note: str = "", fmt: str = "{:.3f}") -> None:
    MD.append(f"### {title}\n\n" + (note + "\n\n" if note else "") + md_table(df, fmt))


def stats_norm_ppf(p: float) -> float:
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    dd = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = np.sqrt(-2 * np.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((dd[0] * q + dd[1]) * q + dd[2]) * q + dd[3]) * q + 1)
    if p > phigh:
        q = np.sqrt(-2 * np.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((dd[0] * q + dd[1]) * q + dd[2]) * q + dd[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# --------------------------------------------------------------------------- #
def main() -> None:
    panel = pd.read_csv(C.OUT / "trades_panel.csv")
    align = json.load(open(C.OUT / "alignment.json"))
    d = panel[panel["path_ok"]].reset_index(drop=True)
    cf = pd.read_csv(C.OUT / "cf_exits.csv")
    rand = pd.read_csv(C.OUT / "random_entry.csv")
    feat = pd.read_csv(C.OUT / "entry_features.csv")
    assert len(d) == len(cf)

    days = d["entry_day"].values
    r_actual = d["r_net"].values
    sides = d["s"].values
    summary = {}

    # 随机入场：每笔 × 每规则 的均值
    rl = rand[rand["kind"] == "local"]
    rmat = rl.groupby(["trade_row", "rule"])["r_rand"].mean().unstack()
    rmat = rmat.reindex(np.arange(len(d)))
    rg = rand[rand["kind"] == "global"].groupby("trade_row")["r_rand"].mean().reindex(
        np.arange(len(d))).values
    rge = rand[rand["kind"] == "global_era"].groupby("trade_row")["r_rand"].mean().reindex(
        np.arange(len(d))).values
    loc_dur = rmat["duration"].values
    bclose = cf["r_bclose"].values

    RULES = [("实际出场", "r_actual", None)]
    RULES += [(f"固定持有 {h}", f"r_cf_{h}", f"cf_{h}") for h in HORIZONS]
    RULES += [("跟踪止损 1%", "r_trail_1", "trail_1"), ("跟踪止损 2%", "r_trail_2", "trail_2")]
    RULES += [("他的入场+持有到平仓 bar 收盘(B)", "r_bclose", "duration")]

    # ================================================================== #
    # T0 样本
    # ================================================================== #
    t0 = pd.DataFrame([
        dict(项="仓位总数(4651)", 值=align["positions_total"]),
        dict(项="10 币仓位", 值=align["positions_10coin"]),
        dict(项="10 币覆盖率", 值=round(align["coverage_10coin"], 4)),
        dict(项="可对齐到 5m", 值=align["aligned"]),
        dict(项="可对齐/全样本", 值=round(align["coverage_aligned"], 4)),
        dict(项="入场价落在入场 bar 内", 值=round(align["entry_in_bar_hit"], 4)),
        dict(项="进入路径分析 (path_ok)", 值=len(d)),
        dict(项="其中 0 持仓分钟", 值=int((d["hold_min"] == 0).sum())),
        dict(项="多 / 空", 值=str(d["side"].value_counts().to_dict())),
        dict(项="年份", 值=str(d["year"].value_counts().sort_index().to_dict())),
        dict(项="持仓 bar 中位 / P90", 值=f'{d["hold_bars"].median():.0f} / '
                                    f'{d["hold_bars"].quantile(0.9):.0f}'),
        dict(项="入场日数(聚类单位)", 值=int(d["entry_day"].nunique())),
    ])
    t0.to_csv(TAB / "T0_sample.csv", index=False)
    section("T0 样本与覆盖率", t0, fmt="{:.4f}")
    summary["sample"] = dict(n_path=len(d), coverage_10coin=align["coverage_10coin"],
                             coverage_aligned=align["coverage_aligned"],
                             zero_hold=int((d["hold_min"] == 0).sum()),
                             n_days=int(d["entry_day"].nunique()))

    # ================================================================== #
    # T1 MFE/MAE
    # ================================================================== #
    rows = []
    for h in HORIZONS:
        mfe, mae = d["mfe_" + h].values, d["mae_" + h].values
        rows.append(dict(持有=h,
                         MFE中位=np.nanmedian(mfe), MAE中位=np.nanmedian(mae),
                         MFE均值=np.nanmean(mfe), MAE均值=np.nanmean(mae),
                         MFE_p90=np.nanpercentile(mfe, 90), MAE_p10=np.nanpercentile(mae, 10),
                         MFE_MAE中位比=np.nanmedian(mfe) / abs(np.nanmedian(mae)),
                         机械持有收益=np.nanmean(cf["r_cf_" + h].values),
                         随机入场同规则=np.nanmean(rmat["cf_" + h].values)))
    t1 = pd.DataFrame(rows)
    t1.to_csv(TAB / "T1_mfe_mae.csv", index=False)
    section("T1 入场后 MFE/MAE（%，按方向归一；不含入场 bar 与平仓 bar 的极值）", t1)
    mfe_e = d["mfe_exit"].values
    mae_e = d["mae_exit"].values
    t1b = pd.DataFrame([
        dict(项="MFE 到实际平仓 中位", 值=np.nanmedian(mfe_e)),
        dict(项="MAE 到实际平仓 中位", 值=np.nanmedian(mae_e)),
        dict(项="实际净收益 中位", 值=np.median(r_actual)),
        dict(项="实际持有 bar 中位", 值=float(d["hold_bars"].median())),
    ])
    section("T1b 到实际平仓时刻的 MFE/MAE", t1b)

    # ================================================================== #
    # T2 捕获率 / 止损距离
    # ================================================================== #
    win = r_actual > 0
    cap = np.where((mfe_e > 0) & win, r_actual / np.where(mfe_e > 0, mfe_e, np.nan), np.nan)
    cap24 = np.where((d["mfe_24h"].values > 0) & win,
                     r_actual / np.where(d["mfe_24h"].values > 0, d["mfe_24h"].values, np.nan), np.nan)
    mfe_share = np.where(win & (d["mfe_24h"].values > 0),
                         mfe_e / np.where(d["mfe_24h"].values > 0, d["mfe_24h"].values, np.nan), np.nan)
    rows = [
        dict(组="盈利单", 指标="realized %", 值=np.nanmean(r_actual[win]),
             中位=np.nanmedian(r_actual[win]), n=int(win.sum())),
        dict(组="盈利单", 指标="MFE(到平仓) %", 值=np.nanmean(mfe_e[win]),
             中位=np.nanmedian(mfe_e[win]), n=int(win.sum())),
        dict(组="盈利单", 指标="捕获率 = realized/MFE(到平仓)", 值=np.nanmean(cap),
             中位=np.nanmedian(cap), n=int(np.isfinite(cap).sum())),
        dict(组="盈利单", 指标="捕获率 = realized/MFE24h", 值=np.nanmean(cap24),
             中位=np.nanmedian(cap24), n=int(np.isfinite(cap24).sum())),
        dict(组="盈利单", 指标="MFE(到平仓)/MFE24h", 值=np.nanmean(mfe_share),
             中位=np.nanmedian(mfe_share), n=int(np.isfinite(mfe_share).sum())),
        dict(组="亏损单", 指标="realized %", 值=np.nanmean(r_actual[~win]),
             中位=np.nanmedian(r_actual[~win]), n=int((~win).sum())),
        dict(组="亏损单", 指标="MAE(到平仓) %", 值=np.nanmean(mae_e[~win]),
             中位=np.nanmedian(mae_e[~win]), n=int((~win).sum())),
        dict(组="亏损单", 指标="MAE(到平仓)/|realized|（≈1 = 平在极值；|realized|≥0.1%）",
             值=np.nanmean(mae_e[~win][np.abs(r_actual[~win]) >= 0.1]
                          / r_actual[~win][np.abs(r_actual[~win]) >= 0.1]),
             中位=np.nanmedian(mae_e[~win][np.abs(r_actual[~win]) >= 0.1]
                              / r_actual[~win][np.abs(r_actual[~win]) >= 0.1]),
             n=int((np.abs(r_actual[~win]) >= 0.1).sum())),
        dict(组="亏损单", 指标="MFE24h(全窗) %", 值=np.nanmean(d["mfe_24h"].values[~win]),
             中位=np.nanmedian(d["mfe_24h"].values[~win]), n=int((~win).sum())),
        dict(组="亏损单", 指标="MAE24h(全窗) %", 值=np.nanmean(d["mae_24h"].values[~win]),
             中位=np.nanmedian(d["mae_24h"].values[~win]), n=int((~win).sum())),
    ]
    t2 = pd.DataFrame(rows)
    t2.to_csv(TAB / "T2_capture.csv", index=False)
    section("T2 捕获率与止损距离", t2)

    rows = []
    for h in HORIZONS:
        mfe = d["mfe_" + h].values
        mae = d["mae_" + h].values
        ok = (mfe > 1e-9) & (mae < -1e-9)
        lr = np.log(mfe[ok] / np.abs(mae[ok]))
        st = stat(lr, days[ok])
        rows.append(dict(持有=h, n=st["n"], log比均值=st["mean"],
                         比值=float(np.exp(st["mean"])),
                         CI=f'[{np.exp(st["ci_lo"]):.2f},{np.exp(st["ci_hi"]):.2f}]', t=st["t"],
                         MFE大于MAE占比=float((lr > 0).mean())))
    t2b = pd.DataFrame(rows)
    t2b.to_csv(TAB / "T2b_mfe_mae_asymmetry.csv", index=False)
    section("T2b 凸性检验：每笔的 log(MFE/|MAE|) 是否显著大于 0（>1 = 有利偏移系统性更大）", t2b,
            note="若比值显著 >1，说明同样持有期里有利波动比不利波动大，这是凸性/赔率的来源。")

    # ================================================================== #
    # T3 平仓后延续漂移
    # ================================================================== #
    rows = []
    for h in POST:
        v = d["post_exit_" + h].values
        sw = C.cluster_bootstrap_mean(v[win], days[win])
        sl = C.cluster_bootstrap_mean(v[~win], days[~win])
        rows.append(dict(窗口=h,
                         赢单均值=np.nanmean(v[win]), 赢单中位=np.nanmedian(v[win]),
                         赢单CI=f'[{sw["ci_lo"]:+.2f},{sw["ci_hi"]:+.2f}]', 赢单t=sw["t"],
                         亏单均值=np.nanmean(v[~win]), 亏单中位=np.nanmedian(v[~win]),
                         亏单CI=f'[{sl["ci_lo"]:+.2f},{sl["ci_hi"]:+.2f}]', 亏单t=sl["t"]))
    t3 = pd.DataFrame(rows)
    t3.to_csv(TAB / "T3_post_exit_drift.csv", index=False)
    section("T3 平仓后延续漂移（正 = 平仓后价格仍朝他的方向走）", t3,
            note="赢单为正 → 砍早了（没让利润奔跑）；亏单为负 → 平仓后继续逆向，止损有效。")
    summary["post_exit_drift"] = t3.to_dict(orient="records")

    # ================================================================== #
    # T4 反事实出场：他的入场 + 不同出场规则
    # ================================================================== #
    rows = []
    for name, col, rule in RULES:
        v = cf[col].values
        st = stat(v, days, trim_top=5)
        rows.append(dict(规则=name, n=st["n"], 均值=st["mean"], 中位=st["median"],
                         CI=f'[{st["ci_lo"]:+.2f},{st["ci_hi"]:+.2f}]', t=st["t"],
                         胜率=st["win_rate"], 总和=st["sum"], PF=pf(v), 去尾5均值=st["mean_trim5"]))
    t4 = pd.DataFrame(rows)
    t4.to_csv(TAB / "T4_exit_rules.csv", index=False)
    section("T4 反事实出场（同一入场点，净 %，1R=1%）", t4)
    summary["exit_rules"] = t4.to_dict(orient="records")

    # T5 原始配对差（他的入场内部比较）
    rows = []
    for name, col, rule in RULES[1:]:
        st = paired(cf[col].values, cf["r_actual"].values, days, trim_top=5)
        rows.append(dict(规则=name, 差=st["mean"], 中位=st["median"],
                         CI=f'[{st["ci_lo"]:+.2f},{st["ci_hi"]:+.2f}]', t=st["t"],
                         去尾5=st["mean_trim5"]))
    t5 = pd.DataFrame(rows)
    t5.to_csv(TAB / "T5_exit_vs_actual.csv", index=False)
    section("T5 机械出场 − 他实际出场（配对差，未扣β）", t5)

    # T6 β 调整后的出场优势（DiD）
    rows = []
    for name, col, rule in RULES[1:]:
        if rule is None:
            continue
        rand_rule = rmat[rule].values
        diff_raw = cf[col].values - r_actual
        diff_rand = rand_rule - loc_dur
        did = diff_raw - diff_rand
        st = stat(did, days, trim_top=5)
        st_raw = stat(diff_raw, days)
        rows.append(dict(规则=name, 未调整差=st_raw["mean"], t_未调整=st_raw["t"],
                         β调整后DiD=st["mean"], CI=f'[{st["ci_lo"]:+.2f},{st["ci_hi"]:+.2f}]',
                         t=st["t"], 去尾5=st["mean_trim5"]))
    t6 = pd.DataFrame(rows)
    t6.to_csv(TAB / "T6_exit_beta_adjusted.csv", index=False)
    section("T6 出场规则优势：DiD（机械出场−实际）−（随机入场同两规则之差）", t6,
            note="β 调整后仍为正，才说明该机械出场真的比他的出场好，而不是多吃了市场漂移。")
    summary["exit_beta_adjusted"] = t6.to_dict(orient="records")

    # ================================================================== #
    # T7 反事实入场：同规则下"他的入场 vs 随机入场"
    # ================================================================== #
    rows = []
    for name, col, rule in RULES:
        his = cf[col].values
        rnd = rmat[rule].values if rule else loc_dur
        st = paired(his, rnd, days, trim_top=5)
        rows.append(dict(出场规则=name, 他的入场=float(np.nanmean(his)),
                         随机入场=float(np.nanmean(rnd)), 入场alpha=st["mean"],
                         CI=f'[{st["ci_lo"]:+.2f},{st["ci_hi"]:+.2f}]', t=st["t"],
                         去尾5=st["mean_trim5"]))
    t7 = pd.DataFrame(rows)
    t7.to_csv(TAB / "T7_entry_alpha_by_rule.csv", index=False)
    section("T7 同一出场规则下：他的入场 − 同币±1天随机入场（=入场时点 alpha）", t7,
            note="若在长持有规则下 alpha 消失，说明长持有收益来自市场漂移而非入场选择。")
    summary["entry_alpha_by_rule"] = t7.to_dict(orient="records")

    # T8 收益水平对照
    rows = []
    for name, v in [("他的实际(A)", r_actual), ("他的入场+bar收盘(B)", bclose),
                    ("随机同币±1天·同时长(LOCAL)", loc_dur),
                    ("随机同期异币·同时长(ERA β)", rge),
                    ("随机全样本异币·同时长(ALL β)", rg)]:
        st = stat(v, days, trim_top=5)
        rows.append(dict(组合=name, 均值=st["mean"], 中位=st["median"],
                         CI=f'[{st["ci_lo"]:+.2f},{st["ci_hi"]:+.2f}]', t=st["t"],
                         胜率=st["win_rate"], 去尾5=st["mean_trim5"]))
    t8 = pd.DataFrame(rows)
    t8.to_csv(TAB / "T8_levels.csv", index=False)
    section("T8 收益水平（%, 净）", t8)

    # ================================================================== #
    # T9 alpha 分解
    # ================================================================== #
    bar_open = []
    for coin in C.COINS:
        op = C.load_market(coin, "5m")["open"].values
        ii = d.index[d["coin"] == coin].values
        if len(ii):
            bar_open.append(pd.Series(op[d.loc[ii, "i0"].values.astype(int)], index=ii))
    bar_open = pd.concat(bar_open).sort_index().values
    disp = 100.0 * sides * (d["P0"].values - bar_open) / d["P0"].values  # 入场前 bar 内同向位移
    hb = d["hold_bars"].values.astype(int)
    i0 = d["i0"].values.astype(int)
    close_all = []
    for coin in C.COINS:
        cl = C.load_market(coin, "5m")["close"].values
        ii = d.index[d["coin"] == coin].values
        if len(ii):
            tgt = np.minimum(i0[ii] + hb[ii], len(cl) - 1)
            close_all.append(pd.Series(cl[tgt], index=ii))
    close_all = pd.concat(close_all).sort_index().values
    bar_ret = 100.0 * sides * (close_all - bar_open) / bar_open

    comps = [
        ("① 市场β（同期、异币、同时长）", rge),
        ("② 币/日选择 alpha（LOCAL − ERAβ）", loc_dur - rge),
        ("③ 入场时点 alpha（B − LOCAL）", bclose - loc_dur),
        ("④ 出场管理 alpha（实际 − B）", r_actual - bclose),
    ]
    rows = []
    for name, v in comps:
        st = stat(v, days, trim_top=5)
        rows.append(dict(成分=name, 均值=st["mean"], 中位=st["median"],
                         CI=f'[{st["ci_lo"]:+.2f},{st["ci_hi"]:+.2f}]', t=st["t"],
                         去尾5=st["mean_trim5"], 占实际收益比=st["mean"] / float(r_actual.mean())))
    st_a = stat(r_actual, days, trim_top=5)
    rows.append(dict(成分="= 他的实际净收益", 均值=st_a["mean"], 中位=st_a["median"],
                     CI=f'[{st_a["ci_lo"]:+.2f},{st_a["ci_hi"]:+.2f}]', t=st_a["t"],
                     去尾5=st_a["mean_trim5"], 占实际收益比=1.0))
    t9 = pd.DataFrame(rows)
    t9.to_csv(TAB / "T9_decomposition.csv", index=False)
    section("T9 收益分解（均值口径，%, 净）", t9,
            note="四项相加 = 实际净收益。① β 是同期同币随机入场的被动漂移；② 是他挑币/挑日的贡献；"
                 "③ 是同币同日内的入场时点；④ 是他的出场价 vs 持有到平仓 bar 收盘。")
    summary["decomposition"] = t9.to_dict(orient="records")

    # T9b 入场时点的再分解（追涨证据）——全部净口径（扣同样的 cost）
    bar_ret_net = bar_ret - d["cost_pct"].values
    bar_sel = bar_ret_net - loc_dur
    entry_a = bclose - loc_dur
    disp = disp  # s*(P0-bar_open)/P0*100
    rows = [
        dict(项="入场前该 bar 内已发生的同向位移 disp（已在成交价里，不可捕获）",
             均值=float(np.nanmean(disp)), 中位=float(np.nanmedian(disp))),
        dict(项="所选 bar 持有期前瞻收益（净，相对同币±1天随机）",
             均值=float(np.nanmean(bar_sel)), 中位=float(np.nanmedian(bar_sel))),
        dict(项="净入场 alpha ③（实测，= B − LOCAL）",
             均值=float(np.nanmean(entry_a)), 中位=float(np.nanmedian(entry_a))),
        dict(项="残差（= ③ − (bar_sel − disp)，二阶项 + cost 口径差）",
             均值=float(np.nanmean(entry_a - (bar_sel - disp))),
             中位=float(np.nanmedian(entry_a - (bar_sel - disp)))),
    ]
    t9b = pd.DataFrame(rows)
    t9b.to_csv(TAB / "T9b_entry_anatomy.csv", index=False)
    section("T9b 入场时点的解剖：他买入时那根 bar 已经走了多少", t9b)

    # T9c 入场/出场价在各自 bar 内的相对位置（1 = 买在 bar 最高 / 卖在 bar 最低 = 追价）
    hi_e, lo_e, hi_x, lo_x = [], [], [], []
    for coin in C.COINS:
        m = C.load_market(coin, "5m")
        hh, ll = m["high"].values, m["low"].values
        ii = d.index[d["coin"] == coin].values
        if len(ii):
            a0 = i0[ii]
            xx = np.minimum(d.loc[ii, "ix"].values.astype(int), len(hh) - 1)
            hi_e.append(pd.Series(hh[a0], index=ii))
            lo_e.append(pd.Series(ll[a0], index=ii))
            hi_x.append(pd.Series(hh[xx], index=ii))
            lo_x.append(pd.Series(ll[xx], index=ii))
    hi_e = pd.concat(hi_e).sort_index().values
    lo_e = pd.concat(lo_e).sort_index().values
    hi_x = pd.concat(hi_x).sort_index().values
    lo_x = pd.concat(lo_x).sort_index().values
    rng_e = np.maximum(hi_e - lo_e, 1e-12)
    rng_x = np.maximum(hi_x - lo_x, 1e-12)
    entry_pct = np.clip((hi_e - d["P0"].values) / rng_e, 0, 1)   # 1 = 买在 bar 最低（对多有利）
    entry_pct = np.where(sides > 0, 1 - entry_pct, entry_pct)    # 统一为"1 = 对方向最有利"
    exit_pct = np.clip((hi_x - d["Px"].values) / rng_x, 0, 1)
    exit_pct = np.where(sides > 0, 1 - exit_pct, exit_pct)       # 1 = 平在 bar 最有利端
    rows = [dict(项="入场价在入场 bar 内的位置（1=最有利端/最低买）",
                 均值=float(np.nanmean(entry_pct)), 中位=float(np.nanmedian(entry_pct))),
            dict(项="出场价在平仓 bar 内的位置（1=最有利端/最高卖）",
                 均值=float(np.nanmean(exit_pct)), 中位=float(np.nanmedian(exit_pct))),
            dict(项="赢单的出场位置（中位）", 均值=float(np.nanmean(exit_pct[win])),
                 中位=float(np.nanmedian(exit_pct[win]))),
            dict(项="亏单的出场位置（中位）", 均值=float(np.nanmean(exit_pct[~win])),
                 中位=float(np.nanmedian(exit_pct[~win])))]
    t9c = pd.DataFrame(rows)
    t9c.to_csv(TAB / "T9c_bar_position.csv", index=False)
    section("T9c 成交价在 5m bar 内的相对位置（0=最不利端，1=最有利端，0.5=bar 内随机）", t9c)

    # ================================================================== #
    # T10 波动 / 空间选择
    # ================================================================== #
    act = feat[feat["kind"] == "actual"]
    rnd = feat[feat["kind"] == "random"]
    rows = []
    for col in ["fwd_vol_24h", "past_vol_24h", "entry_bar_range", "space_prior",
                "range20_pct", "range5_pct", "tightness_5_20"]:
        a = act[col].values
        b = rnd.groupby("trade_row")[col].mean().reindex(act["trade_row"].values).values
        st = paired(a, b, act["entry_day"].values)
        rows.append(dict(特征=col, 他中位=float(np.nanmedian(a)),
                         随机中位=float(np.nanmedian(b)),
                         差均值=st["mean"], CI=f'[{st["ci_lo"]:+.3f},{st["ci_hi"]:+.3f}]', t=st["t"]))
    t10 = pd.DataFrame(rows)
    t10.to_csv(TAB / "T10_selection.csv", index=False)
    section("T10 入场时点的波动/空间选择：他 vs 同币±1天随机时刻", t10, fmt="{:.4f}",
            note="fwd_vol_24h 用未来 24h 数据，只用于描述他在什么环境里下注，不是入场规则。")
    summary["selection"] = t10.to_dict(orient="records")

    def quartile_table(col, labels, title, fname, fmt="{:.3f}"):
        try:
            q = pd.qcut(d[col], 4, labels=labels, duplicates="drop")
        except ValueError:
            return
        rows = []
        for g, ii in d.groupby(q, observed=True).groups.items():
            ii = np.asarray(ii)
            ca = C.cluster_bootstrap_mean(r_actual[ii], days[ii])
            ce = C.cluster_bootstrap_mean((bclose - loc_dur)[ii], days[ii])
            rows.append(dict(分位=str(g), n=len(ii), 该组中位=float(np.nanmedian(d[col].values[ii])),
                             实际=np.nanmean(r_actual[ii]),
                             实际CI=f'[{ca["ci_lo"]:+.2f},{ca["ci_hi"]:+.2f}]',
                             随机同时长=np.nanmean(loc_dur[ii]),
                             入场alpha=np.nanmean((bclose - loc_dur)[ii]),
                             入场CI=f'[{ce["ci_lo"]:+.2f},{ce["ci_hi"]:+.2f}]',
                             MFE24中位=np.nanmedian(d["mfe_24h"].values[ii]),
                             MAE24中位=np.nanmedian(d["mae_24h"].values[ii]),
                             胜率=float((r_actual[ii] > 0).mean())))
        tab = pd.DataFrame(rows)
        tab.to_csv(TAB / fname, index=False)
        section(title, tab, fmt=fmt)

    quartile_table("fwd_vol_24h", ["Q1低", "Q2", "Q3", "Q4高"],
                   "T11 未来 24h 实现波动分位 × 收益/凸性", "T11_vol_quartile.csv")
    quartile_table("space_prior", ["Q1小", "Q2", "Q3", "Q4大"],
                   "T12 入场时到前高空间分位 × 收益", "T12_space_quartile.csv")
    quartile_table("tightness_5_20", ["Q1紧", "Q2", "Q3", "Q4松"],
                   "T12b 箱体紧致度(5日/20日振幅)分位 × 收益", "T12b_tightness_quartile.csv")

    # 凸性对照：他的实际 vs 随机同时长
    def convex(v):
        v = np.asarray(v, float)
        v = v[np.isfinite(v)]
        s = v.sum()
        return dict(均值=float(v.mean()), 中位=float(np.median(v)), 偏度=skew(v),
                    峰度=float(((v - v.mean()) ** 4).mean() / v.std() ** 4 - 3),
                    涨5pct概率=float((v > 5).mean()), 跌5pct概率=float((v < -5).mean()),
                    最大单笔=float(v.max()), 最小单笔=float(v.min()),
                    总和=float(s),
                    前1pct笔合计=float(np.sort(v)[-max(1, int(0.01 * len(v))):].sum()),
                    前5笔合计=float(np.sort(v)[-5:].sum()))
    t13 = pd.DataFrame({"他的实际": convex(r_actual),
                        "随机同币同时长": convex(loc_dur),
                        "随机全样本β": convex(rg)}).T.reset_index().rename(columns={"index": "组合"})
    t13.to_csv(TAB / "T13_convexity.csv", index=False)
    section("T13 凸性：收益分布对照", t13,
            note="前 5 笔合计 / 总和 的比值衡量利润集中度（他的实际 vs 随机基准）；偏度/涨5%概率衡量右尾。"
                 "注意随机基准的总和接近 0，所以合计比占比更稳")

    # ================================================================== #
    # T14 稳健性
    # ================================================================== #
    top5 = np.argsort(r_actual)[-5:]
    drop5 = np.ones(len(d), bool)
    drop5[top5] = False
    variants = {
        "全样本": np.ones(len(d), bool),
        "剔除 0 持仓分钟": d["hold_min"].values > 0,
        "剔除最大 5 笔(按实际收益)": drop5,
        "剔除 2022": d["year"].values != 2022,
        "仅 2023-2024": d["year"].values >= 2023,
        "剔除 BTC/ETH": ~d["coin"].isin(["BTC", "ETH"]).values,
        "仅 BTC/ETH": d["coin"].isin(["BTC", "ETH"]).values,
    }
    rows = []
    for name, mask in variants.items():
        ii = np.where(mask)[0]
        dd = days[ii]
        ci = C.cluster_bootstrap_mean(r_actual[ii], dd)
        rows.append(dict(变体=name, n=len(ii),
                         实际=float(np.nanmean(r_actual[ii])),
                         CI=f'[{ci["ci_lo"]:+.2f},{ci["ci_hi"]:+.2f}]',
                         β=float(np.nanmean(rge[ii])),
                         币日选择=float(np.nanmean((loc_dur - rge)[ii])),
                         入场=float(np.nanmean((bclose - loc_dur)[ii])),
                         出场=float(np.nanmean((r_actual - bclose)[ii]))))
    t14 = pd.DataFrame(rows)
    t14.to_csv(TAB / "T14_robustness.csv", index=False)
    section("T14 稳健性（去尾 / 子样本）", t14)

    # T14b 出场 alpha 是技能还是冲击成本？按名义额 / 持仓时长拆
    rows = []
    nt = d["notional"].values
    qn = pd.qcut(nt, 3, labels=["小额", "中额", "大额"], duplicates="drop")
    for g, ii in d.groupby(qn, observed=True).groups.items():
        ii = np.asarray(ii)
        rows.append(dict(维度="名义额三分位(2024 年后单笔可达数百万U)", 组=str(g), n=len(ii),
                         名义额中位=float(np.median(nt[ii])),
                         实际=float(np.mean(r_actual[ii])),
                         入场=float(np.mean((bclose - loc_dur)[ii])),
                         出场=float(np.mean((r_actual - bclose)[ii]))))
    hb = d["hold_bars"].values
    qh = pd.cut(hb, [-1, 0, 1, 5, 12, 10**9],
                labels=["0 bar", "1 bar", "2-5 bar", "6-12 bar", ">12 bar"])
    for g, ii in d.groupby(qh, observed=True).groups.items():
        ii = np.asarray(ii)
        rows.append(dict(维度="持仓 bar 分桶", 组=str(g), n=len(ii),
                         名义额中位=float(np.median(nt[ii])),
                         实际=float(np.mean(r_actual[ii])),
                         入场=float(np.mean((bclose - loc_dur)[ii])),
                         出场=float(np.mean((r_actual - bclose)[ii]))))
    t14b = pd.DataFrame(rows)
    t14b.to_csv(TAB / "T14b_exit_alpha_split.csv", index=False)
    section("T14b 出场 alpha 按名义额/持仓拆（若随名义额上升 → 可能是他自己砸盘/拉盘的冲击，而非纯技能）", t14b)

    # T14c 按他的实际持有时长分桶（利润集中度 / 凸性来源）
    hb_ = d["hold_bars"].values
    qb = pd.cut(hb_, [-1, 0, 1, 5, 12, 48, 10**9],
                labels=["0 bar", "1 bar", "2-5 bar", "6-12 bar", "13-48 bar", ">48 bar"])
    rows = []
    for g, ii in d.groupby(qb, observed=True).groups.items():
        ii = np.asarray(ii)
        se = stat(r_actual[ii], days[ii])
        rows.append(dict(持有桶=str(g), n=len(ii),
                         总和=float(r_actual[ii].sum()),
                         实际=float(r_actual[ii].mean()),
                         实际CI=f'[{se["ci_lo"]:+.2f},{se["ci_hi"]:+.2f}]',
                         随机同时长=float(np.nanmean(loc_dur[ii])),
                         入场alpha=float(np.nanmean((bclose - loc_dur)[ii])),
                         出场alpha=float(np.nanmean((r_actual - bclose)[ii])),
                         胜率=float((r_actual[ii] > 0).mean()),
                         占比=float(r_actual[ii].sum() / r_actual.sum())))
    t14c = pd.DataFrame(rows)
    t14c.to_csv(TAB / "T14c_by_hold_bucket.csv", index=False)
    section("T14c 按实际持有时长分桶：利润集中度", t14c,
            note="注意：持有时长是内生变量（他因为单子走对了才拿得久），所以本表的入场alpha 不能当入场技能读，"
                 "只能说明他砍掉的和留下的分别是什么。干净口径见 T7（固定机械出场）。")

    # ================================================================== #
    # T15 分币 / 分年 / 分方向
    # ================================================================== #
    rows = []
    for coin, ii in d.groupby("coin").groups.items():
        ii = np.asarray(ii)
        if len(ii) < 20:
            continue
        rows.append(dict(组=coin, n=len(ii), 实际=float(np.nanmean(r_actual[ii])),
                         β=float(np.nanmean(rge[ii])),
                         币日选择=float(np.nanmean((loc_dur - rge)[ii])),
                         入场=float(np.nanmean((bclose - loc_dur)[ii])),
                         出场=float(np.nanmean((r_actual - bclose)[ii])),
                         MFE24中位=float(np.nanmedian(d["mfe_24h"].values[ii])),
                         MAE24中位=float(np.nanmedian(d["mae_24h"].values[ii]))))
    t15 = pd.DataFrame(rows).sort_values("n", ascending=False)
    t15.to_csv(TAB / "T15_by_coin.csv", index=False)
    section("T15 分币分解（%）", t15)

    rows = []
    for yy, ii in d.groupby("year").groups.items():
        ii = np.asarray(ii)
        rows.append(dict(年=int(yy), n=len(ii), 实际=float(np.nanmean(r_actual[ii])),
                         β=float(np.nanmean(rge[ii])),
                         币日选择=float(np.nanmean((loc_dur - rge)[ii])),
                         入场=float(np.nanmean((bclose - loc_dur)[ii])),
                         出场=float(np.nanmean((r_actual - bclose)[ii])),
                         胜率=float((r_actual[ii] > 0).mean())))
    t16 = pd.DataFrame(rows)
    t16.to_csv(TAB / "T16_by_year.csv", index=False)
    section("T16 分年分解（%）", t16)

    rows = []
    for sd, ii in d.groupby("side").groups.items():
        ii = np.asarray(ii)
        rows.append(dict(方向=sd, n=len(ii), 实际=float(np.nanmean(r_actual[ii])),
                         β=float(np.nanmean(rge[ii])),
                         币日选择=float(np.nanmean((loc_dur - rge)[ii])),
                         入场=float(np.nanmean((bclose - loc_dur)[ii])),
                         出场=float(np.nanmean((r_actual - bclose)[ii]))))
    t17 = pd.DataFrame(rows)
    t17.to_csv(TAB / "T17_by_side.csv", index=False)
    section("T17 分方向分解（%）", t17)

    # 跟踪止损触发结构
    rows = []
    for pct in (1, 2):
        hit = cf[f"trail_{pct}_hit"].values
        rows.append(dict(规则=f"trail{pct}%", 触发率=float(hit.mean()),
                         未触发率=float(1 - hit.mean()),
                         持有bar中位=float(np.nanmedian(cf[f"trail_{pct}_bars"].values)),
                         持有bar_P90=float(np.nanpercentile(cf[f"trail_{pct}_bars"].values, 90))))
    t18 = pd.DataFrame(rows)
    t18.to_csv(TAB / "T18_trail_trigger.csv", index=False)
    section("T18 跟踪止损的触发结构（最长 72h）", t18)

    # ================================================================== #
    # T19 多重比较登记
    # ================================================================== #
    tests = []
    for name, col, rule in RULES[1:]:
        st = stat(cf[col].values - cf["r_actual"].values, days)
        if np.isfinite(st["t"]):
            tests.append((f"出场[{name}] − 实际", st["t"]))
        if rule:
            did = (cf[col].values - r_actual) - (rmat[rule].values - loc_dur)
            st = stat(did, days)
            if np.isfinite(st["t"]):
                tests.append((f"出场[{name}] DiD", st["t"]))
    for name, col, rule in RULES:
        rnd = rmat[rule].values if rule else loc_dur
        st = stat(cf[col].values - rnd, days)
        if np.isfinite(st["t"]):
            tests.append((f"入场alpha[{name}]", st["t"]))
    for _, r in t10.iterrows():
        if np.isfinite(r["t"]):
            tests.append((f"选择[{r['特征']}]", r["t"]))
    for name, v in comps:
        st = stat(v, days)
        if np.isfinite(st["t"]):
            tests.append((f"分解[{name}]", st["t"]))
    tests_df = pd.DataFrame(tests, columns=["检验", "聚类t"])
    tests_df["|t|"] = tests_df["聚类t"].abs()
    tests_df = tests_df.sort_values("|t|", ascending=False).reset_index(drop=True)
    m = len(tests_df)
    tests_df["Bonferroni阈值"] = abs(stats_norm_ppf(1 - 0.025 / m))
    tests_df["过Bonferroni"] = tests_df["|t|"] > tests_df["Bonferroni阈值"]
    tests_df.to_csv(TAB / "T19_multiplicity.csv", index=False)
    section(f"T19 多重比较登记（{m} 个检验；Bonferroni 5% 双侧 |t| 阈值 "
            f"{abs(stats_norm_ppf(1 - 0.025 / m)):.2f}）", tests_df)
    summary["multiplicity_m"] = m
    summary["multiplicity"] = tests_df.to_dict(orient="records")

    # ---- 写文件 ----
    with open(C.OUT / "summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=float)
    (C.OUT / "tables.md").write_text("\n\n".join(MD), encoding="utf-8")
    print(f"wrote {len(list(TAB.glob('*.csv')))} tables + summary.json")
    print("\nT4 出场：")
    print(t4[["规则", "均值", "CI", "t", "去尾5均值"]].to_string(index=False))
    print("\nT6 β调整：")
    print(t6[["规则", "未调整差", "t_未调整", "β调整后DiD", "CI", "t"]].to_string(index=False))
    print("\nT7 入场 alpha：")
    print(t7[["出场规则", "他的入场", "随机入场", "入场alpha", "CI", "t"]].to_string(index=False))
    print("\nT9 分解：")
    print(t9[["成分", "均值", "CI", "t", "去尾5"]].to_string(index=False))
    print("\nT10 选择：")
    print(t10[["特征", "他中位", "随机中位", "差均值", "CI", "t"]].to_string(index=False))


if __name__ == "__main__":
    main()
