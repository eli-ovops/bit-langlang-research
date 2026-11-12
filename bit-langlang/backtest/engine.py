#!/usr/bin/env python3
"""bit浪浪 风格策略 —— 规则引擎 + 逐笔模拟（v1）

规则来源：docs/策略规格-v0.md
- 只做多；BTC 日线季节过滤（close>EMA50 且 EMA50 上行）
- 日线箱体突破回踩（S1）/ 二波回踩（S2）作为 setup
- 5m 拐点扳机入场（低点后不破 + 阳线收盘破前高）
- 止损 5m 拐点下方；T1=3R 减半推保本；T2=日线前高，否则 6R；时间止损 8h
- 单笔风险按账户 %，杠杆上限（BTC/ETH 10x，山寨 5x），不复利加仓

输出：data/backtest/trades_<symbol>.csv（含 gross_R / cost_R / net_R）
"""
import os, sys, glob, json
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MKT = os.path.join(ROOT, "data", "market")
OUT = os.path.join(ROOT, "data", "backtest")
os.makedirs(OUT, exist_ok=True)

# ---------------- 参数 ----------------
P = dict(
    box_days=20, box_amp_max=0.30,        # S1 箱体
    s1_valid_days=5, s1_zone=(0.99, 1.03),
    s2_box_days=8, s2_box_amp_max=0.20, s2_drawdown_min=0.12, s2_zone_frac=0.33,
    swing_lookback=5, buf_pct=0.0015, atr_buf_mult=0.3,
    max_stop_pct=0.02, rr_to_target_min=3.0, t1_R=2.0, t2_R_fallback=5.0,
    min_space_pct=0.05, time_stop_bars=4032,
    fee=0.0005, slip_btc=0.0003, slip_alt=0.0008,
    max_hold_bars=2016,  # 7 天兜底
)

def load(sym, interval):
    p = os.path.join(MKT, f"{sym}_{interval}.csv.gz")
    if not os.path.exists(p): return None
    try:
        d = pd.read_csv(p)
    except (EOFError, pd.errors.ParserError) as e:
        print(f"[warn] {p} not ready: {e}"); return None
    d["ts"] = pd.to_datetime(d.ts, unit="ms", utc=True)
    d = d.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return d

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def prepare_daily(df5, df1d):
    d = df1d.copy()
    d["ema50"] = ema(d.close, 50)
    d["ema200"] = ema(d.close, 200)
    d["risk_on"] = ((d.close > d.ema50) & (d.ema50 > d.ema50.shift(5)) &
                    (d.close > d.ema200)).shift(1).fillna(False)
    # 前 20 日箱体（不含当日）
    d["box_high"] = d.high.shift(1).rolling(P["box_days"]).max()
    d["box_low"] = d.low.shift(1).rolling(P["box_days"]).min()
    d["box_amp"] = (d.box_high - d.box_low) / d.box_low
    d["res20"] = d.high.shift(1).rolling(20).max()
    d["res120"] = d.high.shift(1).rolling(120).max()
    d["ema20"] = ema(d.close, 20)
    # S1: 昨日收盘突破箱顶，且箱体足够窄；之后 5 天内回踩到箱顶附近
    d["s1_break"] = (d.close.shift(1) > d.box_high) & (d.box_amp <= P["box_amp_max"])
    d["s1_flag"] = False
    # S2: 20 日急涨后回撤 >=12%，形成 >=8 日窄箱体，价格位于箱体下 1/3
    h20 = d.high.rolling(20).max(); l20 = d.low.rolling(20).min()
    d["drawdown_from_20h"] = 1 - d.close / h20
    bh = d.high.shift(1).rolling(P["s2_box_days"]).max()
    bl = d.low.shift(1).rolling(P["s2_box_days"]).min()
    d["s2_amp"] = (bh - bl) / bl
    d["s2_flag"] = (((h20 >= 1.20 * l20) & (d.drawdown_from_20h >= P["s2_drawdown_min"]) &
                    (d.s2_amp <= P["s2_box_amp_max"]) &
                    (d.close <= bl + P["s2_zone_frac"] * (bh - bl))).shift(1).fillna(False))
    # S3: 上升趋势中的第一次小分歧（回撤 2%-8%，距高点 <=12 天）
    h20b = d.high.rolling(20).max()
    l20b = d.low.rolling(20).min()
    pull = (h20b - d.close) / h20b
    # 距 20 日最高点过去的天数
    hi_idx = pd.Series(np.arange(len(d))).where(d.high == h20b).ffill()
    days_since = pd.Series(np.arange(len(d))) - hi_idx
    d["s3_flag"] = (((h20b >= 1.15 * l20b) & pull.between(0.02, 0.08) &
                    (days_since <= 12) & (d.close > d.ema20)).shift(1).fillna(False))
    # S1 有效窗口：突破日后 1..5 天
    s1 = np.zeros(len(d), dtype=bool)
    idx = np.where(d.s1_break.values)[0]
    for i in idx:
        lo, hi = i + 1, min(i + 1 + P["s1_valid_days"], len(d))
        s1[lo:hi] = True
    d["s1_active"] = s1
    d["s3_flag"] = d["s3_flag"].fillna(False)
    cols = ["ts", "risk_on", "box_high", "box_low", "res20", "res120", "s1_active", "s2_flag", "s3_flag", "close"]
    dd = d[cols].copy()
    dd["day"] = dd.ts.dt.floor("D")
    return dd

def simulate_symbol(sym, df5, daily, start=None, end=None, funding=None, verbose=False):
    """在 5m 上逐 bar 找信号，模拟单笔交易，返回 R 倍数与成本。"""
    if df5 is None or daily is None or len(df5) < 500: return []
    d5 = df5.copy()
    d5["day"] = d5.ts.dt.floor("D")
    d5 = d5.merge(daily, on="day", how="left", suffixes=("", "_d"))
    d5 = d5.dropna(subset=["risk_on"]).reset_index(drop=True)
    if start is not None: d5 = d5[d5.ts >= start]
    if end is not None: d5 = d5[d5.ts <= end]
    if len(d5) < 200: return []
    d5 = d5.reset_index(drop=True)

    o = d5.open.values; h = d5.high.values; l = d5.low.values; c = d5.close.values
    risk_on = d5.risk_on.values.astype(bool)
    s1 = d5.s1_active.values.astype(bool)
    s2 = d5.s2_flag.values.astype(bool)
    s3 = d5.s3_flag.values.astype(bool)
    box_high = d5.box_high.values
    res20 = d5.res20.values
    res120 = d5.res120.values
    ts = d5.ts.values

    n = len(d5)
    # ATR14 on 5m
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    atr = pd.Series(tr).rolling(14).mean().values
    # 摆动低点：最近 5 根最小值
    swing_low = pd.Series(l).rolling(P["swing_lookback"]).min().values


    trades = []
    i = 20
    is_btc = sym.startswith("BTC") or sym.startswith("ETH")
    slip = P["slip_btc"] if is_btc else P["slip_alt"]
    lev_cap = 10.0 if is_btc else 5.0

    while i < n - 2:
        if not risk_on[i] or not (s1[i] or s2[i] or s3[i]):
            i += 1; continue
        L = swing_low[i - 1] if not np.isnan(swing_low[i - 1]) else np.nan
        if np.isnan(L) or np.isnan(atr[i - 1]):
            i += 1; continue
        # 扳机：最近 3 根不破 L + 当前收盘破前一根高点 + 仍在 setup 区域
        prev_high = h[i - 1]
        if not (l[i - 1] > L and l[i - 2] > L and l[i - 3] >= L * 0.9999):
            i += 1; continue
        if not (c[i] > prev_high):
            i += 1; continue
        # setup 区域过滤
        if s1[i]:
            if np.isnan(box_high[i]) or not (box_high[i] * P["s1_zone"][0] <= c[i] <= box_high[i] * P["s1_zone"][1]):
                i += 1; continue
        if s1[i] and s2[i]:
            pass
        raw_entry = o[i + 1]
        if raw_entry <= 0:
            i += 1; continue
        entry = raw_entry * (1 + slip)
        stop = L - max(P["buf_pct"] * entry, P["atr_buf_mult"] * atr[i - 1])
        if stop >= entry: i += 1; continue
        stop_pct = (entry - stop) / entry
        if stop_pct > P["max_stop_pct"] or stop_pct <= 0:
            i += 1; continue
        R = entry - stop
        # 目标：日线前高（须高于 entry）否则 6R
        res = res120[i]
        if np.isnan(res) or res <= entry:
            tgt = entry * (1 + P["min_space_pct"])
        else:
            tgt = res
        t1 = entry + P["t1_R"] * R
        if (tgt - entry) / entry < P["min_space_pct"]:
            i += 1; continue
        if (tgt - entry) / R < P["rr_to_target_min"]:
            i += 1; continue
        # 杠杆上限：notional <= equity*lev 由组合层保证；此处只记录 stop_pct
        notional_per_risk = 1.0 / stop_pct  # notional = risk * 此值

        # 逐 bar 走
        t1_hit = False
        exit_price = None; exit_bar = None; reason = None
        j = i + 1
        while j < n and (j - i) <= P["max_hold_bars"]:
            if l[j] <= stop:  # 先判止损（保守）
                px = min(o[j], stop) if o[j] < stop else stop
                exit_price = px * (1 - slip); exit_bar = j; reason = "stop"; break
            if (not t1_hit) and h[j] >= t1:
                t1_hit = True; stop = entry  # 保本
            if t1_hit:
                trail = min(l[max(0, j - 19):j + 1]) - P["buf_pct"] * c[j]
                stop = max(stop, trail)
            if t1_hit and h[j] >= tgt:
                exit_price = tgt; exit_bar = j; reason = "t2"; break
            if (j - i) >= P["time_stop_bars"]:
                exit_price = c[j] * (1 - slip); exit_bar = j; reason = "time"; break
            j += 1
        if exit_price is None:
            exit_bar = min(j, n - 1); exit_price = c[exit_bar] * (1 - slip); reason = "maxhold"

        if not t1_hit:
            gross_R = (exit_price - entry) / R
        else:
            # 一半在 T1 平（无滑点，限价），一半按退出价
            gross_R = 0.5 * (t1 - entry) / R + 0.5 * (exit_price - entry) / R

        cost_R = P["fee"] * 2 / stop_pct
        fund = 0.0
        if funding is not None and len(funding):
            t0 = pd.Timestamp(ts[i + 1]); t1ms = pd.Timestamp(ts[exit_bar])
            fund = funding.loc[(funding.index >= t0) & (funding.index <= t1ms), "funding_rate"].sum()
            cost_R += max(fund, -0.002) / stop_pct  # 多单正费率付费；负费率返利封顶
        net_R = gross_R - cost_R
        risk_frac = 0.015
        scale = min(1.0, lev_cap * stop_pct / risk_frac)

        trades.append(dict(
            symbol=sym, entry_time=pd.Timestamp(ts[i + 1]), exit_time=pd.Timestamp(ts[exit_bar]),
            entry=entry, stop=stop, t1=t1, tgt=tgt, exit=exit_price, stop_pct=stop_pct,
            hold_bars=exit_bar - i, reason=reason, t1_hit=t1_hit,
            gross_R=gross_R, cost_R=cost_R, net_R=net_R, funding=fund, risk_scale=scale,
            s1=bool(s1[i]), s2=bool(s2[i]), s3=bool(s3[i]), entry_close=c[i], box_high=box_high[i], res20=res20[i], res120=res120[i],
        ))
        i = exit_bar + 1
    return trades

def main():
    syms = sys.argv[1:] or ["BTCUSDT","ETHUSDT","SOLUSDT","PEOPLEUSDT","TRBUSDT","DOGEUSDT","WLDUSDT","APTUSDT","ORDIUSDT","1000PEPEUSDT"]
    btc = load("BTCUSDT", "1d")
    daily_btc = prepare_daily(load("BTCUSDT","5m"), btc)
    # 全局季节过滤用 BTC 的 risk_on，映射到每个 symbol 的日线表
    regime = daily_btc.set_index("day")[["risk_on"]]
    all_trades = []
    for sym in syms:
        f5 = load(sym, "5m"); f1d = load(sym, "1d")
        if f5 is None or f1d is None:
            print(f"[skip] {sym}"); continue
        dly = prepare_daily(f5, f1d)
        dly = dly.drop(columns=["risk_on"]).merge(regime.reset_index(), on="day", how="left")
        fund_df = load(sym, "funding")
        if fund_df is not None:
            fund_df = fund_df.set_index("ts")
            fund_df.index = pd.to_datetime(fund_df.index).tz_convert("UTC").tz_localize(None)
        tr = simulate_symbol(sym, f5, dly, funding=fund_df)
        df = pd.DataFrame(tr)
        if len(df):
            df.to_csv(os.path.join(OUT, f"trades_{sym}.csv"), index=False)
        all_trades.append(df)
        print(f"{sym}: {len(df)} trades | win {(df.net_R>0).mean()*100 if len(df) else 0:.1f}% | sumR {df.net_R.sum() if len(df) else 0:.1f}")
    pd.concat(all_trades).to_csv(os.path.join(OUT, "trades_all.csv"), index=False)
    print("saved", os.path.join(OUT, "trades_all.csv"))

if __name__ == "__main__":
    main()
