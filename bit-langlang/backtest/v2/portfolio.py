#!/usr/bin/env python3
"""组合层：并发上限 + 风险分档 + 权益曲线（含日终浮动盈亏 MTM）。

两套口径
--------
* 逐币：单币独立序列（无并发冲突），同一风险分档、按当前权益比例下注（可复利）；
  杠杆上限（BTC/ETH 10x、山寨 5x）会压缩名义仓位，实际风险可能低于目标值。
* 组合：全部币按入场时间排序，最多 3 笔并发；满仓时新信号跳过（记录 skipped）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def lever_cap(symbol: str, cfg: dict) -> float:
    p = cfg["PORTFOLIO"]
    return p["lev_major"] if symbol in ("BTCUSDT", "ETHUSDT") else p["lev_alt"]


def replay(trades: pd.DataFrame, risk: float, cfg: dict, equity0: float | None = None,
           max_concurrent: int | None = None, by_symbol: bool = False,
           use_leverage_cap: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """按入场时间顺序分配仓位，返回 (accepted trades, 已实现权益曲线, 跳过数)。"""
    p = cfg["PORTFOLIO"]
    equity0 = p["equity0"] if equity0 is None else equity0
    max_conc = p["max_concurrent"] if max_concurrent is None else max_concurrent
    if len(trades) == 0:
        empty = pd.DataFrame(columns=["ts", "equity"])
        return trades.copy(), empty, 0

    d = trades.sort_values(["entry_time", "symbol"]).reset_index(drop=True).copy()
    d["risk_scale"] = d.get("risk_scale", 1.0)
    if isinstance(d["risk_scale"], pd.Series):
        d["risk_scale"] = d["risk_scale"].fillna(1.0).astype(float)

    equity = float(equity0)
    open_pos: list[tuple[pd.Timestamp, float]] = []
    curve = [(pd.Timestamp(d["entry_time"].min()), equity)]
    acc_rows: list[dict] = []
    skipped = 0

    for idx, t in d.iterrows():
        # 先结算到期仓位（以已实现权益继续下注）
        still = []
        for et, pnl in open_pos:
            if et <= t["entry_time"]:
                equity += pnl
                curve.append((et, equity))
            else:
                still.append((et, pnl))
        open_pos = still
        if equity <= 0:
            break
        if (not by_symbol) and len(open_pos) >= max_conc:
            skipped += 1
            continue

        stop_pct = float(t["stop_pct"]) if "stop_pct" in d.columns and np.isfinite(t.get("stop_pct", np.nan)) else np.nan
        lev = lever_cap(t["symbol"], cfg) if use_leverage_cap else np.inf
        scale = float(t.get("risk_scale", 1.0))
        risk_amt = risk * equity * scale
        if np.isfinite(stop_pct) and stop_pct > 0:
            notional = risk_amt / stop_pct
            if notional > lev * equity:                 # 杠杆上限压缩仓位
                notional = lev * equity
            risk_eff = notional * stop_pct
        else:                                            # v1 口径：net_R 已含风险缩放
            notional = risk_amt
            risk_eff = risk_amt
        pnl = risk_eff * float(t["net_R"])
        open_pos.append((t["exit_time"], pnl))
        row = t.to_dict()
        row.update(dict(
            notional=notional, risk_eff=risk_eff, pnl=pnl, equity_at_entry=equity,
            equity_after=equity + pnl,
        ))
        acc_rows.append(row)

    for et, pnl in open_pos:
        equity += pnl
        curve.append((et, equity))

    acc = pd.DataFrame(acc_rows)
    cv = pd.DataFrame(curve, columns=["ts", "equity"]).sort_values("ts").reset_index(drop=True)
    return acc, cv, skipped


def mtm_curve(acc: pd.DataFrame, close_map: dict[str, pd.Series], cfg: dict,
              start: str, end: str, equity0: float | None = None) -> pd.DataFrame:
    """日终 MTM 权益：已实现 + 未平仓浮动（按当日日线收盘）。

    未平仓按 R 计价：T1 前 r=(px-entry)/R；T1 后 r=0.5×3R+0.5×(px-entry)/R；再扣已计提成本。
    日终点 = 当日 23:59 UTC；样本区间外的持仓不会被计入曲线。
    """
    p = cfg["PORTFOLIO"]
    equity0 = p["equity0"] if equity0 is None else equity0
    if len(acc) == 0:
        return pd.DataFrame(columns=["ts", "equity"])

    days = pd.date_range(pd.Timestamp(start).normalize(),
                         pd.Timestamp(end).normalize() + pd.Timedelta(days=1), freq="D")
    rows = []
    for day_end in days:
        cash = equity0 + acc.loc[acc["exit_time"] <= day_end, "pnl"].sum()
        unreal = 0.0
        op = acc[(acc["entry_time"] <= day_end) & (acc["exit_time"] > day_end)]
        for _, t in op.iterrows():
            ser = close_map.get(t["symbol"])
            if ser is None:
                continue
            avail = ser.index[ser.index <= day_end]
            if len(avail) == 0:
                px = t["entry"]
            else:
                px = float(ser.loc[avail[-1]])
            R = t["R"]
            frac = 0.5 if t["t1_hit"] else 1.0
            realized_t1 = (1 - frac) * 3.0 if t["t1_hit"] else 0.0
            r_mark = realized_t1 + frac * (px - t["entry"]) / R - t["cost_R"]
            unreal += t["notional"] * t["stop_pct"] * r_mark
        rows.append((pd.Timestamp(day_end) + pd.Timedelta(hours=23, minutes=59), cash + unreal))
    return pd.DataFrame(rows, columns=["ts", "equity"])
