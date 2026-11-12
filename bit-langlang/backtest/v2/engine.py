#!/usr/bin/env python3
"""v2 引擎：逐 5m bar 扫描信号 → 逐笔模拟（只做多）。

规则（与 docs/策略规格-v0.md + 一手问答校准对齐）
------------------------------------------------
入场（预判式承接 + 假突破反转，不追突破）：
  1) BTC 日线季节 risk_on（shift(1) 后可见）；
  2) 标的自身日线在 EMA50 上方（IS 结构选择项，见 config.DAILY）；
  3) 价格回到支撑区域：最近 4 根 5m 触及 {前 10 日低, 前 20 日低, 前 24h 低} 之一，
     且当前收盘距该支撑 ≤2.5%；最近 4 根不得深度跌穿支撑 >0.8%（收盘口径）；
  4) 出现下列任一"止跌反转"：
     A 假突破收回：最近 4 根内最低价刺破支撑 ≥0.2%，本根收盘重新站回支撑上方且为阳线；
     B 承接止跌：未刺破支撑，本根为阳线、收盘高于前收、收盘位于当根上半区；
  5) 不追突破：本根收盘不创前 20 根 5m 新高，且前 6 根累计涨幅 <2%；
  6) 空间：到最近日线阻力（前 20/60/120 日最高中最近的、且在价格上方者）≥5%，
     无阻力（新高区）按名义 15% 空间处理；
  7) 止损：前 5 根 5m 最低价下方 max(0.15%, 0.3×ATR14)，止损距离 ∈ [0.3%, 2%]；
  8) 下一根 5m 开盘市价成交。

出场：
  * T1 = 3R 卖出 50%，剩余止损推至成本保本价；
  * T1 后每根 bar 用 5m 摆动低点（前 5 根最低）− buffer 跟踪，只上移不下移；
  * 最长持有 14 天（4032 根 5m），无 8h 时间止损；
  * 保守撮合：同一根 bar 先判止损、再判 T1。

成本：每边 taker 0.05%；滑点 BTC/ETH 0.03%、山寨 0.08%（计入 R）；
      资金费按持仓期逐次累计（T1 后名义减半），单次 |rate|>0.3% 截断。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import features


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
class FundingSeries:
    """资金费累计和（按时间窗口求和）。"""

    def __init__(self, df: pd.DataFrame):
        if df is None or len(df) == 0:
            self.ts = np.array([], dtype="datetime64[ns]").astype("int64")
            self.cum = np.array([0.0])
            return
        ts = pd.to_datetime(df["ts"]).values.astype("datetime64[ns]").astype("int64")
        self.ts = ts
        self.cum = np.concatenate([[0.0], np.cumsum(df["funding_rate"].values.astype(float))])

    def sum_between(self, t0, t1) -> float:
        if len(self.ts) == 0 or not np.isfinite(self.cum[-1]):
            return 0.0
        a = int(np.searchsorted(self.ts, np.datetime64(t0, "ns").astype("int64"), side="right"))
        b = int(np.searchsorted(self.ts, np.datetime64(t1, "ns").astype("int64"), side="right"))
        if b <= a:
            return 0.0
        return float(self.cum[b] - self.cum[a])


def build_frame(sym_data: dict, regime: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """5m 主表：并入 5m 特征 + 自身日线结构 + BTC 季节。"""
    d5 = features.intraday_features(sym_data["d5"], cfg["ENTRY"])
    d1 = features.daily_features(sym_data["d1"], cfg["DAILY"])
    daily = d1.merge(regime, on="day", how="left")
    d5["day"] = d5["ts"].dt.floor("D")
    m = d5.merge(daily, on="day", how="left")
    return m


def _nearest_resistance(entry_ref: float, res20, res60, res120) -> float:
    cands = [r for r in (res20, res60, res120) if np.isfinite(r) and r > entry_ref * 1.001]
    if not cands:
        return entry_ref * 1.15   # 新高区：无上方阻力，按名义 15% 空间
    return float(min(cands))


# ---------------------------------------------------------------------------
# 信号 + 逐笔模拟
# ---------------------------------------------------------------------------
def simulate_symbol(
    sym: str,
    frame: pd.DataFrame,
    funding: FundingSeries,
    cfg: dict,
    start: str,
    end: str,
    slip: float,
    split_label: str,
) -> list[dict]:
    e = cfg["ENTRY"]
    x = cfg["EXIT"]
    cst = cfg["COST"]
    fee = cst["fee"]

    d = frame
    o = d["open"].values.astype(float)
    h = d["high"].values.astype(float)
    l = d["low"].values.astype(float)
    c = d["close"].values.astype(float)
    atr = d["atr"].values.astype(float)
    swing_low = d["swing_low"].values.astype(float)
    hi20 = d["hi20_prev"].values.astype(float)
    sup24h = d["sup24h"].values.astype(float)
    pdl = d["pdl"].values.astype(float)
    sup4h = d["sup4h"].values.astype(float)
    sup10 = d["sup10"].values.astype(float)
    sup20 = d["sup20"].values.astype(float)
    res20 = d["res20"].values.astype(float)
    res60 = d["res60"].values.astype(float)
    res120 = d["res120"].values.astype(float)
    risk_on = d["risk_on"].fillna(False).values.astype(bool)
    season = d["season"].fillna("unknown").values
    sym_uptrend = d["sym_uptrend"].fillna(False).values.astype(bool)
    ts = d["ts"].values

    n = len(d)
    ts64 = ts.astype("datetime64[ns]").astype("int64")
    t_start_i = int(np.datetime64(pd.Timestamp(start), "ns").astype("int64"))
    t_end_i = int((np.datetime64(pd.Timestamp(end), "ns") + np.timedelta64(24 * 3600 - 1, "s")).astype("int64"))

    win = e["touch_bars"]
    swing_lb = e["swing_lb"]
    be_cost = fee + slip
    be_stop_off = x["breakeven_cost_mult"] * be_cost

    trades: list[dict] = []
    i = cfg["BACKTEST"]["warmup_bars"]
    last = n - 2
    while i < last:
        # 便宜的过滤先做
        if not risk_on[i]:
            i += 1
            continue
        if ts64[i] < t_start_i or ts64[i] > t_end_i:
            i += 1
            continue
        if cfg["DAILY"]["require_symbol_daily_uptrend"] and not sym_uptrend[i]:
            i += 1
            continue
        if not np.isfinite(c[i]) or c[i] <= 0:
            i += 1
            continue
        ci = c[i]

        # ---- 3) 支撑区域 ----
        lo_w = np.inf
        for k in range(i - win + 1, i + 1):
            if l[k] < lo_w:
                lo_w = l[k]
        _src = e["support_sources"]
        cands = []
        for key in _src:
            v = {"sup10": sup10, "sup20": sup20, "sup24h": sup24h,
                 "pdl": pdl, "sup4h": sup4h}[key][i]
            cands.append(v if np.isfinite(v) else np.nan)
        mode = e.get("entry_mode", "at_support")
        if mode == "above_support":
            # 预判式承接：价格仍在支撑上方 0.4%~1.85%（止损 = 支撑下方 → 风险 1%~2%）
            dmin, dmax = e["support_dist_min"], e["support_dist_max"]
            valid = [v for v in cands
                     if np.isfinite(v) and dmin <= (ci - v) / v <= dmax]
            if not valid:
                i += 1
                continue
            L = float(max(valid))                    # 最近的、仍在价格下方的支撑
            # 必须已经"回落接近"支撑：最近 4 根最低价进入支撑上方 3% 内
            if lo_w > L * (1 + dmax + 0.010):
                i += 1
                continue
            dist_ok = True
        else:
            # 在支撑处/轻微跌穿后承接
            valid = [v for v in cands
                     if np.isfinite(v) and v <= ci * 1.005 and (ci - v) / v <= e["support_tol"]]
            if not valid:
                i += 1
                continue
            L = float(max(valid))
            if lo_w > L * (1 + e["touch_tol"]):      # 最近 4 根必须触及支撑区域
                i += 1
                continue
            if ci < L * (1 - 0.008):                 # 不得深度跌穿（不接已破位的刀）
                i += 1
                continue
            dist_ok = True

        # ---- 4) 止跌反转 ----
        pierce = lo_w < L * (1 - e["pierce_min"])
        bull = (ci > o[i]) and (ci > c[i - 1])
        rng = h[i] - l[i]
        close_hi = rng <= 0 or (ci - l[i]) >= e["close_lo_frac"] * rng
        setup = None
        if pierce and ci > L and bull:
            setup = "false_break_reclaim"
        elif (not pierce) and bull and close_hi and ci <= L * (1.5 * e["touch_tol"] + 1 + 0.02):
            setup = "support_hold_reversal"
        if setup is None or not dist_ok:
            i += 1
            continue

        # ---- 5) 不追突破 ----
        if np.isfinite(hi20[i]) and ci > hi20[i] * 0.999:
            i += 1
            continue
        if i >= e["chase_cum_bars"] and np.isfinite(c[i - e["chase_cum_bars"]]) and c[i - e["chase_cum_bars"]] > 0:
            if ci / c[i - e["chase_cum_bars"]] - 1 >= e["chase_cum_max"]:
                i += 1
                continue

        # ---- 7) 止损 ----
        entry_raw = o[i + 1]
        if not np.isfinite(entry_raw) or entry_raw <= 0:
            i += 1
            continue
        # 止损锚 = 5m 摆动低点；above_support 模式下同时不高于支撑 L（取更深者）
        structure_low = swing_low[i]
        if mode == "above_support" and np.isfinite(L):
            structure_low = min(structure_low, L)
        if not np.isfinite(structure_low) or not np.isfinite(atr[i]):
            i += 1
            continue
        stop = structure_low - max(e["buf_pct"] * entry_raw, e["atr_buf"] * atr[i])
        # 诊断开关：固定止损宽度（不用于正式配置，仅用于证明"止损宽度是绑定约束"）
        if e.get("fixed_stop_pct") is not None:
            stop = min(stop, entry_raw * (1 - e["fixed_stop_pct"]))
        if stop >= entry_raw:
            i += 1
            continue
        stop_pct = (entry_raw - stop) / entry_raw
        if not (e["min_stop_pct"] <= stop_pct <= e["max_stop_pct"]):
            i += 1
            continue

        # ---- 6) 空间过滤 ----
        res = _nearest_resistance(ci, res20[i], res60[i], res120[i])
        if res <= entry_raw:            # 跳空后已触及阻力
            i += 1
            continue
        space_pct = (res - entry_raw) / entry_raw
        if space_pct < e["min_space_pct"]:
            i += 1
            continue

        R = entry_raw - stop
        t1 = entry_raw + x["t1_R"] * R
        be_stop = entry_raw * (1 + be_stop_off)

        # ---- 逐 bar 撮合 ----
        j = i + 1
        t1_hit = False
        t1_time = None
        exit_px = None
        exit_bar = None
        reason = None
        trail_stop = stop
        while j < n and (j - i) <= x["max_hold_bars"]:
            # 保守：先判止损
            if l[j] <= trail_stop:
                px = o[j] if o[j] < trail_stop else trail_stop
                exit_px = px * (1 - slip)
                exit_bar = j
                reason = "stop" if not t1_hit else "trail"
                break
            if (not t1_hit) and h[j] >= t1:
                t1_hit = True
                t1_time = ts[j]
                trail_stop = max(trail_stop, be_stop)
            if (t1_hit or x.get("trail_from_entry", False)) and j > i + 1:
                lo_trail = l[j - x["trail_lb"] + 1: j + 1].min()
                cand = lo_trail - max(e["buf_pct"] * c[j], e["atr_buf"] * atr[j])
                if np.isfinite(cand) and cand > trail_stop:
                    trail_stop = cand
            j += 1
        if exit_px is None:
            exit_bar = min(j, n - 1)
            exit_px = c[exit_bar] * (1 - slip)
            reason = "maxhold"

        # ---- R 与成本 ----
        if t1_hit:
            gross_R = (x["t1_frac"] * (x["t1_R"]) +
                       (1 - x["t1_frac"]) * ((exit_px - entry_raw) / R))
        else:
            gross_R = (exit_px - entry_raw) / R

        cost_pct = fee                                        # 入场 fee
        cost_pct += slip                                      # 入场滑点
        if t1_hit:
            cost_pct += x["t1_frac"] * fee                    # T1 限价卖出 fee
            cost_pct += (1 - x["t1_frac"]) * (fee + slip)     # 剩余市价卖出
            f1 = funding.sum_between(ts[i + 1], t1_time)
            f2 = funding.sum_between(t1_time, ts[exit_bar])
            fund_pct = f1 + 0.5 * f2
        else:
            cost_pct += fee + slip                            # 全量市价卖出
            fund_pct = funding.sum_between(ts[i + 1], ts[exit_bar])
        cost_pct += fund_pct        # 多单：正费率付费、负费率返利（signed，已截断异常值）
        cost_R = cost_pct / stop_pct
        net_R = gross_R - cost_R

        trades.append(dict(
            split=split_label,
            symbol=sym,
            setup=setup,
            entry_time=pd.Timestamp(ts[i + 1]),
            exit_time=pd.Timestamp(ts[exit_bar]),
            hold_hours=(ts64[exit_bar] - ts64[i + 1]) / 3.6e12,
            entry=entry_raw,
            stop=stop,
            t1=t1,
            t1_hit=bool(t1_hit),
            t1_time=pd.Timestamp(t1_time) if t1_hit else pd.NaT,
            exit=exit_px,
            exit_reason=reason,
            stop_pct=stop_pct,
            R=R,
            atr_pct=atr[i] / entry_raw,
            support=L,
            support_dist_pct=(ci - L) / L,
            resistance=res,
            space_pct=space_pct,
            season=str(season[i]),
            gross_R=gross_R,
            cost_fee_slip_R=(cost_pct - fund_pct) / stop_pct,
            cost_funding_R=fund_pct / stop_pct,
            cost_R=cost_R,
            net_R=net_R,
            hold_bars=int(exit_bar - i),
            signal_bar=int(i),
            bar_index=int(i + 1),
        ))
        i = exit_bar + 1

    return trades
