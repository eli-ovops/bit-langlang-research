#!/usr/bin/env python3
"""指标层：逐币/组合统计、权益曲线指标、去尾检验、成本占比、G1/G2 判定。"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b not in (0, 0.0) and np.isfinite(b) else float("nan")


def trade_stats(df: pd.DataFrame) -> dict:
    """纯逐笔统计（以 R 为单位，与风险分档无关）。"""
    n = len(df)
    if n == 0:
        return dict(n=0, win_rate=None, avg_win_R=None, avg_loss_R=None, payoff=None,
                    pf=None, expectancy_R=None, sum_R=None, gross_profit_R=None,
                    gross_loss_R=None, cost_R_total=None, cost_share_of_gross_profit=None,
                    funding_R_total=None, t1_rate=None, median_R=None, max_R=None, min_R=None,
                    tail5_sum_R=None, tail5_pf=None, tail5_positive=None,
                    tail10_sum_R=None, tail10_pf=None, tail10_positive=None)
    net = df["net_R"].values.astype(float)
    wins = net[net > 0]
    losses = net[net < 0]
    gp = float(wins.sum())
    gl = float(-losses.sum())
    pf = _safe_div(gp, gl)
    avg_w = float(wins.mean()) if len(wins) else float("nan")
    avg_l = float(losses.mean()) if len(losses) else float("nan")
    cost = df["cost_R"].sum() if "cost_R" in df.columns else float("nan")
    fund = df["cost_funding_R"].sum() if "cost_funding_R" in df.columns else float("nan")

    def tail(k: int) -> dict:
        if n <= k:
            return dict(sum_R=None, pf=None, positive=None)
        sub = df.drop(df["net_R"].nlargest(k).index)
        s = sub["net_R"].values.astype(float)
        w = s[s > 0].sum()
        l = -s[s < 0].sum()
        return dict(sum_R=float(s.sum()), pf=_safe_div(w, l), positive=bool(s.sum() > 0))

    out = dict(
        n=int(n),
        win_rate=float(len(wins) / n),
        avg_win_R=avg_w,
        avg_loss_R=avg_l,
        payoff=_safe_div(avg_w, abs(avg_l)),
        pf=pf,
        expectancy_R=float(net.mean()),
        sum_R=float(net.sum()),
        gross_profit_R=gp,
        gross_loss_R=gl,
        cost_R_total=float(cost),
        cost_funding_R_total=float(fund),
        cost_share_of_gross_profit=_safe_div(cost, gp),
        t1_rate=float(df["t1_hit"].mean()) if "t1_hit" in df.columns else None,
        median_R=float(np.median(net)),
        max_R=float(net.max()),
        min_R=float(net.min()),
        hold_median_h=float(df["hold_hours"].median()) if "hold_hours" in df.columns else None,
        hold_p25_h=float(df["hold_hours"].quantile(0.25)) if "hold_hours" in df.columns else None,
        hold_p75_h=float(df["hold_hours"].quantile(0.75)) if "hold_hours" in df.columns else None,
        hold_p90_h=float(df["hold_hours"].quantile(0.90)) if "hold_hours" in df.columns else None,
        hold_lt24h_share=float((df["hold_hours"] < 24).mean()) if "hold_hours" in df.columns else None,
        hold_24_72h_share=float(df["hold_hours"].between(24, 72).mean()) if "hold_hours" in df.columns else None,
        hold_gt72h_share=float((df["hold_hours"] > 72).mean()) if "hold_hours" in df.columns else None,
    )
    out.update({f"tail5_{k}": v for k, v in tail(5).items()})
    out.update({f"tail10_{k}": v for k, v in tail(10).items()})
    return out


def equity_stats(curve: pd.DataFrame) -> dict:
    if curve is None or len(curve) == 0:
        return dict(ret_pct=None, mdd_pct=None, longest_underwater_days=None,
                    final_equity=None, max_consec_loss=None)
    eq = curve["equity"].values.astype(float)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min()) if len(dd) else 0.0
    under = eq < peak - 1e-9
    max_days = 0
    start_i = None
    for i, u in enumerate(under):
        if u and start_i is None:
            start_i = i
        elif (not u) and start_i is not None:
            max_days = max(max_days, (curve["ts"].iloc[i] - curve["ts"].iloc[start_i]).days)
            start_i = None
    if start_i is not None:
        max_days = max(max_days, (curve["ts"].iloc[-1] - curve["ts"].iloc[start_i]).days)
    return dict(
        ret_pct=float((eq[-1] / eq[0] - 1.0) * 100.0),
        mdd_pct=float(mdd * 100.0),
        longest_underwater_days=int(max_days),
        final_equity=float(eq[-1]),
    )


def max_consec_losses(net_R: pd.Series) -> int:
    streak = mx = 0
    for r in net_R.values:
        if r < 0:
            streak += 1
            mx = max(mx, streak)
        else:
            streak = 0
    return int(mx)


def cum_r_stats(trades: pd.DataFrame) -> dict:
    """与仓位大小无关的累计 R 回撤。"""
    if len(trades) == 0:
        return dict(cum_R=0.0, mdd_R=0.0, mdd_R_end_R=None)
    t = trades.sort_values("exit_time")
    cum = t["net_R"].cumsum().values
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = cum - peak
    return dict(cum_R=float(cum[-1]), mdd_R=float(dd.min()),
                mdd_R_end_R=float(cum[int(np.argmin(dd))]))


def full_stats(trades: pd.DataFrame, curve: pd.DataFrame | None = None,
               mtm: pd.DataFrame | None = None) -> dict:
    s = trade_stats(trades)
    s.update(cum_r_stats(trades))
    s["max_consec_loss"] = max_consec_losses(trades["net_R"]) if len(trades) else None
    if len(trades):
        s["first_entry"] = str(trades["entry_time"].min())
        s["last_exit"] = str(trades["exit_time"].max())
        s["net_R_per_month"] = float(trades["net_R"].sum() / max(1.0, (
            (trades["entry_time"].max() - trades["entry_time"].min()).days / 30.44)))
        s["exit_reason_breakdown"] = {k: int(v) for k, v in trades["exit_reason"].value_counts().items()}
        if "setup" in trades.columns:
            s["setup_breakdown"] = {k: int(v) for k, v in trades["setup"].value_counts().items()}
        if "season" in trades.columns:
            s["season_breakdown"] = {k: int(v) for k, v in trades["season"].value_counts().items()}
        s["symbol_breakdown"] = {k: int(v) for k, v in trades["symbol"].value_counts().items()}
    # 权益口径
    for tag, cv in (("realized", curve), ("mtm", mtm)):
        if cv is None or len(cv) == 0:
            continue
        es = equity_stats(cv)
        for k, v in es.items():
            s[f"{tag}_{k}"] = v
    return s


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o)
    return o


def dump_json(path: str, obj):
    with open(path, "w") as fh:
        json.dump(_jsonable(obj), fh, ensure_ascii=False, indent=2)


def gate_check(s: dict, v1: dict | None = None, split: str = "is") -> dict:
    """按 docs/风险审查框架.md 的 G1/G2/G3/G4 明确判定。"""
    g = {}
    if s.get("n", 0) > 0 and split == "is":
        g["G1_win_rate_32_48"] = "PASS" if 0.32 <= s["win_rate"] <= 0.48 else "FAIL"
        g["G1_payoff_ge_2.2"] = "PASS" if (s["payoff"] or 0) >= 2.2 else "FAIL"
        g["G1_pf_ge_1.5"] = "PASS" if (s["pf"] or 0) >= 1.5 else "FAIL"
        # 成交笔数：以 v1 同期笔数为量级基准（±30%）
        if v1 and v1.get("n"):
            g["G1_trade_count_vs_v1"] = f"{s['n']} vs {v1['n']} ({s['n']/v1['n']:.2f}x)"
        else:
            g["G1_trade_count_vs_v1"] = "n/a"
        g["G1_overall"] = "PASS" if all(g[k] == "PASS" for k in
                                        ("G1_win_rate_32_48", "G1_payoff_ge_2.2", "G1_pf_ge_1.5")) else "FAIL"
    if s.get("n", 0) > 0 and split == "oos":
        g["G2_pf_ge_1.1"] = "PASS" if (s["pf"] or 0) >= 1.1 else "FAIL"
        mdd = s.get("mtm_mdd_pct", s.get("realized_mdd_pct"))
        g["G2_mdd_le_25"] = "PASS" if (mdd is not None and abs(mdd) <= 25) else "FAIL"
        g["G2_no_blowup"] = "PASS" if (s.get("mtm_final_equity") or 0) > 0 else "FAIL"
        g["G2_overall"] = "PASS" if all(g[k] == "PASS" for k in
                                        ("G2_pf_ge_1.1", "G2_mdd_le_25", "G2_no_blowup")) else "FAIL"
    if s.get("n", 0) > 0:
        g["G3_tail5_positive"] = "PASS" if s.get("tail5_positive") else "FAIL"
        g["G3_tail10_positive"] = "PASS" if s.get("tail10_positive") else "FAIL"
        mdd = s.get("mtm_mdd_pct", s.get("realized_mdd_pct"))
        g["G4_mdd_le_25"] = "PASS" if (mdd is not None and abs(mdd) <= 25) else "FAIL"
    return g
