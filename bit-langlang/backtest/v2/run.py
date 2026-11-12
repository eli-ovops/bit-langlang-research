#!/usr/bin/env python3
"""v2 回测入口：IS / OOS × 两档风险（1.5% / 3.3% 权益）× 逐币 + 组合。

复现方式
--------
    # 1) 样本内（结构选择 / bug 修复只能在这一段做）
    python3 -m backtest.v2.run --split is

    # 2) 样本外（只跑一次；必须显式 --allow-oos 确认）
    python3 -m backtest.v2.run --split oos --allow-oos

    # 3) 两段一起（报告用；OOS 仍只跑这一次）
    python3 -m backtest.v2.run --split all --allow-oos

    # 归因 / 诊断（各自只读 trades CSV 或只用 IS 入场集）
    python3 -m backtest.v2.analyze
    python3 -m backtest.v2.diagnostics

输出目录：data/backtest_v2/
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from . import config, dataio, engine, features, metrics, portfolio
from .utils import to_md

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "backtest_v2")
TAB = os.path.join(OUT, "tables")
V1_TRADES = os.path.join(ROOT, "data", "backtest", "trades_all.csv")


# ---------------------------------------------------------------------------
def build_cfg(require_symbol_uptrend: bool | None = None) -> dict:
    cfg = dict(SPLIT=config.SPLIT, COST=config.COST, PORTFOLIO=config.PORTFOLIO,
               DAILY=dict(config.DAILY), ENTRY=dict(config.ENTRY),
               EXIT=dict(config.EXIT), BACKTEST=dict(config.BACKTEST))
    if require_symbol_uptrend is not None:
        cfg["DAILY"]["require_symbol_daily_uptrend"] = bool(require_symbol_uptrend)
    return cfg


def build_btc_regime(cfg: dict) -> pd.DataFrame:
    btc1d = dataio.load_ohlcv("BTCUSDT", "1d")
    return features.btc_regime(btc1d, cfg["DAILY"])


def generate_trades(cfg: dict, split: str, regime: pd.DataFrame) -> pd.DataFrame:
    if split == "is":
        start, end = cfg["SPLIT"]["is_start"], cfg["SPLIT"]["is_end"]
    else:
        start, end = cfg["SPLIT"]["oos_start"], cfg["SPLIT"]["oos_end"]
    rows = []
    for sym in dataio.SYMBOLS:
        sd = dataio.load_symbol(sym, cfg["COST"]["funding_clip"])
        if sd["d5"] is None or sd["d1"] is None:
            print(f"  [skip] {sym} 缺少数据")
            continue
        frame = engine.build_frame(sd, regime, cfg)
        fund = engine.FundingSeries(sd["funding"])
        slip = cfg["COST"]["slip_major"] if sym in dataio.MAJORS else cfg["COST"]["slip_alt"]
        tr = engine.simulate_symbol(sym, frame, fund, cfg, start, end, slip, split)
        for t in tr:
            t["symbol"] = sym
        rows.extend(tr)
        d = pd.DataFrame(tr)
        if len(d):
            print(f"  {sym:13s} {len(d):4d} 笔 | 胜率 {(d.net_R>0).mean()*100:5.1f}% | ΣR {d.net_R.sum():8.1f}")
        else:
            print(f"  {sym:13s}    0 笔")
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["t1_time"] = pd.to_datetime(df["t1_time"])
    return df.sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def attach_btc_context(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """BTC 日线诊断字段（仅归因，不参与信号）。"""
    if len(trades) == 0:
        return trades
    b = dataio.load_ohlcv("BTCUSDT", "1d")
    b["day"] = b["ts"].dt.floor("D")
    b["btc_ret20"] = b["close"].pct_change(20).shift(1)
    b["btc_vol20"] = b["close"].pct_change().rolling(20).std().shift(1)
    b["btc_dd120"] = (b["close"] / b["close"].rolling(120, min_periods=20).max() - 1).shift(1)
    b["btc_above_ema50"] = (b["close"].shift(1) > features.ema(b["close"], 50).shift(1)).astype(int)
    sub = b[["day", "btc_ret20", "btc_vol20", "btc_dd120", "btc_above_ema50"]]
    t = trades.copy()
    t["day"] = t["entry_time"].dt.floor("D")
    t = t.merge(sub, on="day", how="left").drop(columns=["day"])
    return t


def load_close_map() -> dict[str, pd.Series]:
    m = {}
    for sym in dataio.SYMBOLS:
        d = dataio.load_ohlcv(sym, "1d")
        if d is None:
            continue
        m[sym] = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"]))
    return m


# ---------------------------------------------------------------------------
def v1_baseline(cfg: dict) -> dict:
    """v1 逐笔结果（data/backtest/trades_all.csv，只读）→ IS/OOS 指标。"""
    if not os.path.exists(V1_TRADES):
        return {}
    d = pd.read_csv(V1_TRADES, parse_dates=["entry_time", "exit_time"])
    d["hold_hours"] = (d["exit_time"] - d["entry_time"]).dt.total_seconds() / 3600.0
    d["risk_scale"] = d.get("risk_scale", pd.Series(1.0, index=d.index)).fillna(1.0)
    d["exit_reason"] = d["reason"]
    d["setup"] = np.where(d["s1"], "v1_s1", np.where(d["s2"], "v1_s2", "v1_s3"))
    d["t1_hit"] = d["t1_hit"].astype(bool)
    d["gross_R"] = d["gross_R"].astype(float)
    d["cost_R"] = d["cost_R"].astype(float)
    d["cost_fee_slip_R"] = d["cost_R"]
    d["cost_funding_R"] = d["funding"]
    out = {}
    for split, (s, e) in {
        "is": (cfg["SPLIT"]["is_start"], cfg["SPLIT"]["is_end"]),
        "oos": (cfg["SPLIT"]["oos_start"], cfg["SPLIT"]["oos_end"]),
    }.items():
        sub = d[(d["entry_time"] >= s) & (d["entry_time"] <= pd.Timestamp(e) + pd.Timedelta(days=1))].copy()
        acc, cv, _ = portfolio.replay(sub, 0.015, cfg)
        st = metrics.full_stats(sub, cv, None)
        st["accepted_n"] = int(len(acc))
        st["symbol_breakdown"] = {k: int(v) for k, v in sub["symbol"].value_counts().items()}
        out[split] = st
    return out


def benchmark_buy_hold(cfg: dict, split: str) -> dict:
    s = cfg["SPLIT"][f"{split}_start"]
    e = cfg["SPLIT"][f"{split}_end"]
    b = dataio.load_ohlcv("BTCUSDT", "1d")
    b = b[(b["ts"] >= s) & (b["ts"] <= e)]
    if len(b) < 2:
        return {}
    return dict(btc_buy_hold_pct=round(float((b["close"].iloc[-1] / b["open"].iloc[0] - 1) * 100), 1),
                btc_maxdd_pct=round(float((b["close"] / b["close"].cummax() - 1).min() * 100), 1))


# ---------------------------------------------------------------------------
NUMERIC_COLS = ["symbol", "n", "win_rate", "payoff", "pf", "expectancy_R", "sum_R",
                "avg_win_R", "avg_loss_R", "t1_rate", "median_R", "max_R", "min_R",
                "max_consec_loss", "hold_median_h", "hold_p25_h", "hold_p75_h", "hold_p90_h",
                "hold_lt24h_share", "hold_24_72h_share", "hold_gt72h_share",
                "cost_R_total", "cost_funding_R_total", "cost_share_of_gross_profit",
                "tail5_sum_R", "tail5_pf", "tail5_positive", "tail10_sum_R", "tail10_pf",
                "tail10_positive", "realized_ret_pct", "realized_mdd_pct", "realized_final_equity",
                "mtm_ret_pct", "mtm_mdd_pct", "mtm_final_equity", "realized_longest_underwater_days",
                "skipped_by_concurrency", "signals_total", "accepted_n", "net_R_per_month",
                "cum_R", "mdd_R"]


def summarise_split(trades: pd.DataFrame, cfg: dict, split: str, close_map: dict,
                    v1: dict | None) -> dict:
    out = {"split": split, "tiers": {}}
    for tier, risk in cfg["PORTFOLIO"]["risk_tiers"].items():
        res = {"risk_pct": risk * 100, "symbols": {}, "portfolio": {}}
        rows = []
        for sym, g in trades.groupby("symbol"):
            acc, cv, _ = portfolio.replay(g, risk, cfg, by_symbol=True)
            m = portfolio.mtm_curve(acc, {sym: close_map[sym]}, cfg,
                                    cfg["SPLIT"][f"{split}_start"], cfg["SPLIT"][f"{split}_end"])
            st = metrics.full_stats(acc if len(acc) else g, cv, m)
            st["symbol"] = sym
            res["symbols"][sym] = st
            rows.append({k: st.get(k) for k in NUMERIC_COLS})
        sym_df = pd.DataFrame(rows)
        if len(sym_df):
            sym_df = sym_df[[c for c in NUMERIC_COLS if c in sym_df.columns]]
            sym_df.to_csv(os.path.join(OUT, f"summary_symbols_{split}_{tier}.csv"), index=False)
        # 组合
        acc, cv, skipped = portfolio.replay(trades, risk, cfg)
        m = portfolio.mtm_curve(acc, close_map, cfg,
                                cfg["SPLIT"][f"{split}_start"], cfg["SPLIT"][f"{split}_end"])
        st = metrics.full_stats(acc, cv, m)
        st["skipped_by_concurrency"] = int(skipped)
        st["signals_total"] = int(len(trades))
        st["accepted_n"] = int(len(acc))
        st["gates"] = metrics.gate_check(st, v1, split=split)
        res["portfolio"] = st
        acc.to_csv(os.path.join(OUT, f"portfolio_trades_{split}_{tier}.csv"), index=False)
        if len(m):
            m.to_csv(os.path.join(OUT, f"equity_mtm_{split}_{tier}.csv"), index=False)
        if len(acc):
            mm = acc.copy()
            mm["month"] = mm["entry_time"].dt.to_period("M").astype(str)
            mm.groupby("month").agg(n=("net_R", "size"), net_R=("net_R", "sum"),
                                    pnl=("pnl", "sum")).to_csv(
                os.path.join(OUT, f"monthly_{split}_{tier}.csv"))
        out["tiers"][tier] = res
    out["benchmark"] = benchmark_buy_hold(cfg, split)
    return out


# ---------------------------------------------------------------------------
def markdown_tables(all_summary: dict, cfg: dict, v1: dict):
    os.makedirs(TAB, exist_ok=True)
    lines = []
    for split in all_summary["splits"]:
        sp = all_summary["splits"][split]
        if "tiers" not in sp:
            continue
        lines.append(f"\n## {split.upper()} 组合（最多 3 笔并发，初始 2000U）\n")
        rows = []
        for tier, tr in sp["tiers"].items():
            p = tr["portfolio"]
            rows.append(dict(
                risk=f"{tr['risk_pct']:.1f}%",
                signals=p.get("signals_total"), trades=p.get("n"),
                win_rate=f"{p.get('win_rate', 0)*100:.1f}%",
                payoff=round(p.get("payoff") or 0, 2),
                pf=round(p.get("pf") or 0, 2),
                expectancy_R=round(p.get("expectancy_R") or 0, 3),
                sum_R=round(p.get("sum_R") or 0, 1),
                MDD_MTM=f"{p.get('mtm_mdd_pct') or 0:.1f}%",
                max_consec_loss=p.get("max_consec_loss"),
                median_hold_h=p.get("hold_median_h"),
                final_equity=round(p.get("mtm_final_equity") or 0, 0),
                tail5_R=p.get("tail5_sum_R"), tail10_R=p.get("tail10_sum_R"),
                cost_share=f"{(p.get('cost_share_of_gross_profit') or 0)*100:.0f}%",
                skipped=p.get("skipped_by_concurrency"),
            ))
        lines.append(to_md(pd.DataFrame(rows)))
        # 逐币 1.5%
        for tier in sp["tiers"]:
            tr = sp["tiers"][tier]
            rows = []
            for sym, s in tr["symbols"].items():
                rows.append(dict(symbol=sym, n=s.get("n"),
                                 win_rate=f"{(s.get('win_rate') or 0)*100:.1f}%",
                                 payoff=round(s.get("payoff") or 0, 2),
                                 pf=round(s.get("pf") or 0, 2),
                                 exp_R=round(s.get("expectancy_R") or 0, 3),
                                 sum_R=round(s.get("sum_R") or 0, 1),
                                 MDD=f"{s.get('mtm_mdd_pct') or 0:.1f}%",
                                 maxLL=s.get("max_consec_loss"),
                                 hold_h=s.get("hold_median_h"),
                                 cost_R=round(s.get("cost_R_total") or 0, 1)))
            lines.append(f"\n### {split.upper()} 逐币 @ risk {tr['risk_pct']:.1f}%\n")
            lines.append(to_md(pd.DataFrame(rows)))
    with open(os.path.join(TAB, "summary.md"), "w") as fh:
        fh.write("# 汇总表（自动生成）\n" + "\n".join(lines))

    # v1 vs v2
    rows = []
    for split in ("is", "oos"):
        if split not in all_summary["splits"]:
            continue
        sp = all_summary["splits"][split]
        if "tiers" not in sp:
            continue
        v2 = sp["tiers"]["r15"]["portfolio"]
        rows.append(dict(split=split.upper(), version="v1",
                         n=v1.get(split, {}).get("n"),
                         win_rate=f"{(v1.get(split, {}).get('win_rate') or 0)*100:.1f}%",
                         payoff=round(v1.get(split, {}).get("payoff") or 0, 2),
                         pf=round(v1.get(split, {}).get("pf") or 0, 2),
                         exp_R=round(v1.get(split, {}).get("expectancy_R") or 0, 3),
                         sum_R=round(v1.get(split, {}).get("sum_R") or 0, 1),
                         MDD_realized=f"{(v1.get(split, {}).get('realized_mdd_pct') or 0):.1f}%"))
        rows.append(dict(split=split.upper(), version="v2(1.5%)", n=v2.get("n"),
                         win_rate=f"{(v2.get('win_rate') or 0)*100:.1f}%",
                         payoff=round(v2.get("payoff") or 0, 2),
                         pf=round(v2.get("pf") or 0, 2),
                         exp_R=round(v2.get("expectancy_R") or 0, 3),
                         sum_R=round(v2.get("sum_R") or 0, 1),
                         MDD_realized=f"{(v2.get('mtm_mdd_pct') or 0):.1f}%"))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(OUT, "v1_vs_v2.csv"), index=False)
    with open(os.path.join(TAB, "v1_vs_v2.md"), "w") as fh:
        fh.write("# v1 vs v2\n\n" + to_md(t))


# ---------------------------------------------------------------------------
def plot_figures(cfg: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # pragma: no cover
        print(f"[warn] matplotlib 不可用，跳过画图: {e}")
        return
    figdir = os.path.join(OUT, "figs")
    os.makedirs(figdir, exist_ok=True)
    tiers = {"r15": "1.5%", "r33": "3.3%"}
    for split in ("is", "oos"):
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                 gridspec_kw=dict(height_ratios=[2, 1]))
        any_curve = False
        for tier, color in (("r15", "tab:blue"), ("r33", "tab:orange")):
            path = os.path.join(OUT, f"equity_mtm_{split}_{tier}.csv")
            if not os.path.exists(path):
                continue
            d = pd.read_csv(path, parse_dates=["ts"]).set_index("ts")
            eq = d["equity"]
            axes[0].plot(eq.index, eq.values, color=color, label=f"risk {tiers[tier]}")
            dd = (eq / eq.cummax() - 1) * 100
            axes[1].fill_between(dd.index, dd.values, 0, color=color, alpha=0.3)
            any_curve = True
        if any_curve:
            axes[0].axhline(cfg["PORTFOLIO"]["equity0"], color="grey", lw=0.8, ls="--")
            axes[0].set_title(f"bitlanglang v2 portfolio equity ({split.upper()}, 2000U, max 3 concurrent)")
            axes[0].set_ylabel("Equity (USDT)")
            axes[0].legend()
            axes[1].set_ylabel("Drawdown %")
            axes[1].set_xlabel("UTC")
            fig.tight_layout()
            fig.savefig(os.path.join(figdir, f"equity_dd_{split}.png"), dpi=130)
            plt.close(fig)
    frames = []
    for split in ("is", "oos"):
        p = os.path.join(OUT, f"trades_{split}.csv")
        if os.path.exists(p):
            d = pd.read_csv(p, parse_dates=["entry_time", "exit_time"])
            d["split"] = split
            frames.append(d)
    if not frames:
        return
    tr = pd.concat(frames)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    axes[0].hist(tr["net_R"].clip(-2, 12), bins=60, color="tab:blue")
    axes[0].set_title("net R distribution (clipped -2..12)")
    axes[0].set_xlabel("net_R")
    axes[1].hist(tr["hold_hours"].clip(0, 14 * 24), bins=60, color="tab:green")
    axes[1].set_title("holding time in hours (clipped 14d)")
    axes[1].set_xlabel("hours")
    axes[2].scatter(tr["stop_pct"] * 100, tr["net_R"].clip(-2, 12), s=8, alpha=0.4)
    axes[2].set_title("stop distance (%) vs net_R")
    axes[2].set_xlabel("stop %")
    fig.tight_layout()
    fig.savefig(os.path.join(figdir, "r_hold_stop.png"), dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["is", "oos", "all"], default="is")
    ap.add_argument("--allow-oos", action="store_true",
                    help="显式允许运行样本外（OOS 只应跑一次）")
    ap.add_argument("--require-symbol-uptrend", choices=["on", "off"], default=None,
                    help="仅 IS 用的结构选择项（二选一，非网格）；OOS 禁止修改")
    a = ap.parse_args(argv)

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TAB, exist_ok=True)
    cfg = build_cfg(None if a.require_symbol_uptrend is None
                    else a.require_symbol_uptrend == "on")
    if a.require_symbol_uptrend is not None and a.split != "is":
        raise SystemExit("结构选择只允许在 IS 上做；OOS 必须使用冻结参数。")
    if a.split in ("oos", "all") and not a.allow_oos:
        raise SystemExit("OOS 只允许跑一次：如确认这是唯一一次（或报告复现），请加 --allow-oos")

    splits = ["is", "oos"] if a.split == "all" else [a.split]
    regime = build_btc_regime(cfg)
    close_map = load_close_map()
    v1 = v1_baseline(cfg)

    all_summary = {
        "config": {"split": cfg["SPLIT"], "cost": cfg["COST"],
                   "portfolio": cfg["PORTFOLIO"], "daily": cfg["DAILY"],
                   "entry": cfg["ENTRY"], "exit": cfg["EXIT"]},
        "v1_baseline": v1, "splits": {},
    }
    for split in splits:
        print(f"\n=== {split.upper()} 信号生成 ===")
        trades = generate_trades(cfg, split, regime)
        if len(trades) == 0:
            print("  无信号")
            all_summary["splits"][split] = {"split": split, "trades": 0}
            continue
        trades = attach_btc_context(trades, cfg)
        trades.to_csv(os.path.join(OUT, f"trades_{split}.csv"), index=False)
        print(f"  合计信号 {len(trades)} 笔，ΣR {trades.net_R.sum():.1f}")
        all_summary["splits"][split] = summarise_split(
            trades, cfg, split, close_map, v1.get(split))

    metrics.dump_json(os.path.join(OUT, "summary.json"), all_summary)
    markdown_tables(all_summary, cfg, v1)
    plot_figures(cfg)
    print(f"\n已写入 {os.path.relpath(OUT, ROOT)}/summary.json")
    return all_summary


if __name__ == "__main__":
    main()
