#!/usr/bin/env python3
"""诊断：为什么 v2 的机械规则跑不出正期望（**只用于解释，不用于调参**）。

严格限制
--------
* 只用 IS（2022-05-24..2024-06-20）的信号集；
* 只对同一批入场做"如果换出场几何会怎样"的事后分解，**不据此修改交付配置**；
* 不碰 OOS。

输出：data/backtest_v2/diagnostics.json、tables/diagnostics_is.md
"""
from __future__ import annotations

import copy
import os

import numpy as np
import pandas as pd

from . import config, dataio, engine, features, metrics
from .utils import to_md

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "backtest_v2")
TAB = os.path.join(OUT, "tables")
COST_PCT = {"major": 0.0016, "alt": 0.0026}   # 0.05%×2 + 滑点×2


def build_cfg() -> dict:
    return dict(SPLIT=config.SPLIT, COST=config.COST, PORTFOLIO=config.PORTFOLIO,
                DAILY=dict(config.DAILY), ENTRY=dict(config.ENTRY),
                EXIT=dict(config.EXIT), BACKTEST=dict(config.BACKTEST))


def collect_entries(cfg: dict):
    raw = {s: dataio.load_symbol(s, cfg["COST"]["funding_clip"]) for s in dataio.SYMBOLS}
    regime = features.btc_regime(raw["BTCUSDT"]["d1"], cfg["DAILY"])
    frames, entries = {}, []
    for sym in dataio.SYMBOLS:
        sd = raw[sym]
        frame = engine.build_frame(sd, regime, cfg)
        frames[sym] = frame
        tr = engine.simulate_symbol(
            sym, frame, engine.FundingSeries(sd["funding"]), cfg,
            cfg["SPLIT"]["is_start"], cfg["SPLIT"]["is_end"],
            cfg["COST"]["slip_major"] if sym in dataio.MAJORS else cfg["COST"]["slip_alt"], "is")
        for t in tr:
            t["sym"] = sym
            entries.append(t)
    return frames, pd.DataFrame(entries)


def entry_path_stats(E: pd.DataFrame, frames: dict) -> dict:
    rows = []
    for _, t in E.iterrows():
        sym = t["sym"]
        f = frames[sym]
        i = int(t["bar_index"])
        entry = float(t["entry"])
        R = float(t["R"])
        h, l, c = f["high"].values, f["low"].values, f["close"].values
        cst = COST_PCT["major" if sym in dataio.MAJORS else "alt"]
        sp = float(t["stop_pct"])
        rec = dict(symbol=sym, setup=t["setup"], year=t["entry_time"].year,
                   stop_pct=sp, cost_R=cst / sp,
                   ret24h=(c[min(i + 287, len(c) - 1)] - entry) / entry,
                   ret72h=(c[min(i + 863, len(c) - 1)] - entry) / entry,
                   ret7d=(c[min(i + 2015, len(c) - 1)] - entry) / entry,
                   mfe24_R=(h[i:i + 288].max() - entry) / R,
                   mae24_R=(entry - l[i:i + 288].min()) / R,
                   mfe72_R=(h[i:i + 864].max() - entry) / R)
        rows.append(rec)
    P = pd.DataFrame(rows)

    def summ(x: pd.Series) -> dict:
        return dict(mean=round(float(x.mean()) * 100, 3), median=round(float(x.median()) * 100, 3),
                    positive_share=round(float((x > 0).mean()) * 100, 1))

    return dict(
        n=len(P),
        entry_drift_pct={k: summ(P[k]) for k in ("ret24h", "ret72h", "ret7d")},
        mfe_mae_R=dict(
            mfe24_median=round(float(P["mfe24_R"].median()), 2),
            mae24_median=round(float(P["mae24_R"].median()), 2),
            mfe72_median=round(float(P["mfe72_R"].median()), 2),
        ),
        stop_pct_median=round(float(P["stop_pct"].median()) * 100, 3),
        cost_R_mean=round(float(P["cost_R"].mean()), 3),
        by_setup={k: dict(n=int(len(g)), ret24h_mean_pct=round(float(g["ret24h"].mean()) * 100, 3),
                          ret72h_mean_pct=round(float(g["ret72h"].mean()) * 100, 3))
                  for k, g in P.groupby("setup")},
        by_year={str(k): dict(n=int(len(g)), ret24h_mean_pct=round(float(g["ret24h"].mean()) * 100, 3),
                              ret72h_mean_pct=round(float(g["ret72h"].mean()) * 100, 3))
                 for k, g in P.groupby("year")},
    )


def exit_policy_whatif(E: pd.DataFrame, frames: dict) -> list[dict]:
    """同一批入场 → 不同出场几何的净期望（诊断，不是可交付策略）。"""
    arr = {s: {k: frames[s][k].values for k in ("open", "high", "low", "close")} for s in frames}
    rows = []

    def run(name, stop_pct=None, hold_h=None, t1_R=None, trail_lb=5, maxh=4032, target=None):
        res, t1s, holds = [], [], []
        for _, t in E.iterrows():
            sym = t["sym"]
            a = arr[sym]
            o, h, l, c = a["open"], a["high"], a["low"], a["close"]
            i = int(t["bar_index"])
            entry = float(t["entry"])
            sp = float(stop_pct) if stop_pct is not None else float(t["stop_pct"])
            R = entry * sp
            stop = entry - R
            cst = COST_PCT["major" if sym in dataio.MAJORS else "alt"]
            if hold_h is not None:
                j = min(i + hold_h * 12, len(c) - 1)
                hit = False
                for k in range(i, j + 1):
                    if l[k] <= stop:
                        hit = True
                        break
                gross = -1.0 if hit else (c[j] - entry) / R
                res.append(gross - cst / sp)
                continue
            if target == "resistance":
                t1 = float(t["resistance"])
            else:
                t1 = entry + t1_R * R
            t1_hit = False
            exit_px = None
            kk = i
            for k in range(i, min(i + maxh, len(c))):
                kk = k
                if l[k] <= stop:
                    exit_px = o[k] if o[k] < stop else stop
                    break
                if (not t1_hit) and h[k] >= t1:
                    t1_hit = True
                    stop = entry
                if t1_hit and k >= i + 1:
                    lo = l[max(0, k - trail_lb + 1): k + 1].min()
                    stop = max(stop, lo * (1 - 0.0015))
            if exit_px is None:
                exit_px = c[min(i + maxh, len(c) - 1)]
            if t1_hit:
                r_t1 = (t1 - entry) / R
                gross = 0.5 * r_t1 + 0.5 * (exit_px - entry) / R
            else:
                gross = (exit_px - entry) / R
            res.append(gross - cst / sp)
            t1s.append(t1_hit)
            holds.append((kk - i) / 12)
        r = np.array(res)
        w, ls = r[r > 0], r[r < 0]
        rows.append(dict(
            policy=name, n=len(r),
            win_rate=round(float((r > 0).mean()) * 100, 1),
            expectancy_R=round(float(r.mean()), 3),
            sum_R=round(float(r.sum()), 1),
            pf=round(float(w.sum() / abs(ls.sum())), 2) if len(ls) else None,
            t1_hit_rate=round(float(np.mean(t1s)) * 100, 1) if t1s else None,
            median_hold_h=round(float(np.median(holds)), 1) if holds else None,
        ))

    run("交付配置：5m结构止损 + T1@3R + 5m跟踪", t1_R=3.0, trail_lb=5)
    run("持有24h + 1R止损", stop_pct=0.008, hold_h=24)
    run("持有72h + 1R止损", stop_pct=0.008, hold_h=72)
    run("持有72h + 2%止损", stop_pct=0.02, hold_h=72)
    run("2%止损 + T1@3R + 5m跟踪", stop_pct=0.02, t1_R=3.0, trail_lb=5)
    run("2%止损 + T1@3R + 1h跟踪", stop_pct=0.02, t1_R=3.0, trail_lb=12)
    run("5m结构止损 + T1@日线阻力 + 跟踪", target="resistance", trail_lb=5)
    run("2%止损 + T1@日线阻力 + 1h跟踪", stop_pct=0.02, target="resistance", trail_lb=12)
    return rows


def entry_mode_comparison(cfg: dict) -> list[dict]:
    """两种"入场读取"在 IS 上的对照（只用于说明规则自洽性，不用于调参）。"""
    raw = {s: dataio.load_symbol(s, cfg["COST"]["funding_clip"]) for s in dataio.SYMBOLS}
    regime = features.btc_regime(raw["BTCUSDT"]["d1"], cfg["DAILY"])
    rows = []
    for mode, note in (("above_support", "交付读取：支撑上方 0.4~1.85% 预判承接，止损 1~2%"),
                       ("at_support", "字面读取：跌到支撑处承接，止损 0.6~1%")):
        c = copy.deepcopy(cfg)
        c["ENTRY"]["entry_mode"] = mode
        allt = []
        for sym in dataio.SYMBOLS:
            sd = raw[sym]
            frame = engine.build_frame(sd, regime, c)
            tr = engine.simulate_symbol(
                sym, frame, engine.FundingSeries(sd["funding"]), c,
                c["SPLIT"]["is_start"], c["SPLIT"]["is_end"],
                c["COST"]["slip_major"] if sym in dataio.MAJORS else c["COST"]["slip_alt"], "is")
            allt.extend(tr)
        d = pd.DataFrame(allt)
        w, ls = d.net_R[d.net_R > 0], d.net_R[d.net_R < 0]
        rows.append(dict(
            mode=mode, note=note, n=len(d),
            win_rate=round(float((d.net_R > 0).mean()) * 100, 1),
            payoff=round(float(w.mean() / abs(ls.mean())), 2),
            pf=round(float(w.sum() / abs(ls.sum())), 2),
            expectancy_R=round(float(d.net_R.mean()), 3),
            sum_R=round(float(d.net_R.sum()), 1),
            gross_R=round(float(d.gross_R.mean()), 3),
            cost_R=round(float(d.cost_R.mean()), 3),
            median_stop_pct=round(float(d.stop_pct.median()) * 100, 2),
            median_hold_h=round(float(d.hold_hours.median()), 1),
            t1_rate=round(float(d.t1_hit.mean()) * 100, 1),
        ))
    return rows


def main():
    os.makedirs(TAB, exist_ok=True)
    cfg = build_cfg()
    print("生成 IS 入场集（只用于诊断）...")
    frames, E = collect_entries(cfg)
    print(f"  {len(E)} 笔")
    diag = dict(
        note="IS-only 诊断；不用于调参，不接触 OOS",
        entry_mode_comparison=entry_mode_comparison(cfg),
        entry_path=entry_path_stats(E, frames),
        exit_policy_whatif=exit_policy_whatif(E, frames),
        cost_context=dict(
            fee_per_side=cfg["COST"]["fee"],
            slip_major=cfg["COST"]["slip_major"],
            slip_alt=cfg["COST"]["slip_alt"],
            cost_pct_roundtrip_major=COST_PCT["major"],
            cost_pct_roundtrip_alt=COST_PCT["alt"],
        ),
    )
    metrics.dump_json(os.path.join(OUT, "diagnostics.json"), diag)

    # markdown
    lines = ["# 诊断（IS only，自动生成）\n",
             "> 仅用于解释失效原因，**不是可交付策略**，不据此调参。\n",
             "\n## 0. 两种入场读取的对照（IS）\n"]
    lines.append(to_md(pd.DataFrame(diag["entry_mode_comparison"])))
    lines.append("\n## 1. 入场后的路径统计\n")
    ep = diag["entry_path"]
    lines.append(f"- 入场样本：{ep['n']} 笔；止损距离中位 {ep['stop_pct_median']}%；"
                 f"单笔成本 {ep['cost_R_mean']}R\n")
    lines.append("\n| 持有期 | 均值 | 中位 | 为正占比 |\n|---|---|---|---|")
    for k, v in ep["entry_drift_pct"].items():
        lines.append(f"| {k} | {v['mean']}% | {v['median']}% | {v['positive_share']}% |")
    lines.append(f"\n- MFE24 中位 {ep['mfe_mae_R']['mfe24_median']}R / MAE24 中位 "
                 f"{ep['mfe_mae_R']['mae24_median']}R / MFE72 中位 {ep['mfe_mae_R']['mfe72_median']}R\n")
    lines.append("\n## 2. 同一批入场、不同出场几何（诊断，非交付）\n")
    t = pd.DataFrame(diag["exit_policy_whatif"])
    lines.append(to_md(t))
    lines.append("\n## 3. 成本口径\n")
    lines.append(f"- 单边手续费 {cfg['COST']['fee']*100:.2f}%，滑点 BTC/ETH "
                 f"{cfg['COST']['slip_major']*100:.2f}%、山寨 {cfg['COST']['slip_alt']*100:.2f}%\n"
                 f"- 往返成本：主流 {COST_PCT['major']*100:.2f}%、山寨 {COST_PCT['alt']*100:.2f}%\n")
    with open(os.path.join(TAB, "diagnostics_is.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("[ok] diagnostics.json / tables/diagnostics_is.md")


if __name__ == "__main__":
    main()
