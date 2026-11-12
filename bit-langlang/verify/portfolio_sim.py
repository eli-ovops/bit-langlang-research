#!/usr/bin/env python3
"""组合层模拟：TPH v2 多头（趋势出场）+ 并发上限 + 保证金约束 + 资金费 + 复利。
输出：年化、最大回撤、月度、被跳过信号数等。
"""
import json, os
import numpy as np
import pandas as pd
from .common import MARKET, VERIFY
from .prove_method import load5, SYMS

LEV = 5.0
STOP = 0.004

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def build_trades(start="2022-05-01", end="2026-10-25"):
    btc = load5("BTCUSDT")
    bc = btc.set_index(btc.ts.dt.floor("D")).close.resample("D").last(); bc.index = pd.to_datetime(bc.index).tz_localize(None)
    btc_ret7 = bc.pct_change(7)
    e50b = bc.ewm(span=50).mean(); e200b = bc.ewm(span=200).mean()
    btc_on = ((bc > e50b) & (e50b > e50b.shift(5)) & (bc > e200b)).shift(1).fillna(False)
    trades = []
    for sym in SYMS:
        d = load5(sym); d = d[(d.ts >= start) & (d.ts <= end)].reset_index(drop=True)
        fund_p = os.path.join(MARKET, f"{sym}_funding.csv.gz")
        fund = pd.read_csv(fund_p) if os.path.exists(fund_p) else None
        if fund is not None:
            fund["t"] = pd.to_datetime(fund.ts, unit="ms", utc=True)
            fund = fund.set_index("t").funding_rate
            fund.index = pd.to_datetime(fund.index).tz_convert("UTC").tz_localize(None)
        if len(d) < 1000: continue
        day = d.ts.dt.floor("D")
        dly = pd.DataFrame({"day": day.values, "close": d.close.values, "high": d.high.values, "low": d.low.values}).groupby("day").agg({"close":"last","high":"max","low":"min"}).reset_index()
        dly["hi20"] = dly.high.rolling(20).max(); dly["lo20"] = dly.low.rolling(20).min()
        dly["ema20"] = ema(dly.close, 20); dly["ema50"] = ema(dly.close, 50)
        tr_ = pd.concat([dly.high - dly.low, (dly.high - dly.close.shift()).abs(), (dly.low - dly.close.shift()).abs()], axis=1).max(axis=1)
        dly["atr_pct"] = tr_.rolling(14).mean() / dly.close
        dly["btc_on"] = btc_on.reindex(dly.day).fillna(False).values
        dly["rs7"] = dly.close.pct_change(7) - btc_ret7.reindex(dly.day).values
        dly["dist_hi"] = (dly.hi20 - dly.close) / dly.close
        m = dly.set_index("day").shift(1)
        f = m.reindex(day.values)
        rs, dh = f["rs7"].values, f["dist_hi"].values
        atrp, bon = f["atr_pct"].values, f["btc_on"].values
        coin_ok = f["close"].values > f["ema50"].values
        hi20 = d.high.rolling(20).max(); lo20 = d.low.rolling(20).min(); prev = d.close.shift(1)
        sig = (rs > 0) & (dh < 0.03) & coin_ok & (d.low <= lo20 * 1.001) & (d.close > prev)
        idx = np.where(sig.fillna(False).values)[0]
        o, h, l, c = d.open.values, d.high.values, d.low.values, d.close.values
        days = day.values
        ema20 = dly.set_index("day").ema20
        for i in idx:
            if i + 2 >= len(d): continue
            entry = o[i+1]; stop = entry * (1 - STOP); R = entry - stop
            j = i + 1; exit_px = None; exit_ts = None
            while j < len(d) and (pd.Timestamp(days[j]) - pd.Timestamp(days[i])).days <= 30:
                if l[j] <= stop:
                    exit_px = min(o[j], stop); exit_ts = d.ts.values[j]; break
                if j == len(d) - 1 or days[j+1] != days[j]:
                    e = ema20.get(pd.Timestamp(days[j]))
                    if e is not None and not np.isnan(e) and c[j] < e:
                        exit_px = c[j]; exit_ts = d.ts.values[j]; break
                j += 1
            if exit_px is None:
                j = min(j, len(d)-1); exit_px = c[j]; exit_ts = d.ts.values[j]
            gross_R = (exit_px - entry) / R
            # 资金费（多单正费率付费）
            fr = 0.0
            if fund is not None:
                t0 = pd.Timestamp(d.ts.values[i+1]); t1 = pd.Timestamp(exit_ts)
                fr = float(fund[(fund.index >= t0) & (fund.index <= t1)].sum())
            cost_R = (10/10000) / STOP + fr / STOP   # 10bp 往返 + 资金费
            trades.append(dict(symbol=sym, entry_ts=d.ts.values[i+1], exit_ts=exit_ts,
                               entry=entry, stop=stop, exit=exit_px, R=R,
                               gross_R=gross_R, cost_R=cost_R, net_R=gross_R-cost_R,
                               rs7=float(rs[i]), dist_hi=float(dh[i]), atr_pct=float(atrp[i]) if atrp[i]==atrp[i] else np.nan,
                               btc_on=bool(bon[i]), day=str(pd.Timestamp(days[i]).date())))
    return pd.DataFrame(trades).sort_values("entry_ts").reset_index(drop=True)

def simulate(tr, risk=0.01, max_conc=3, initial=2000.0, lev=LEV):
    equity = initial; used_margin = 0.0; open_pos = []; taken = skipped_margin = skipped_conc = 0
    curve = [(tr.entry_ts.min(), equity)]; monthly = {}
    for _, t in tr.iterrows():
        # release exits
        still = []
        for (exit_ts, pnl, margin) in sorted(open_pos, key=lambda pos: pos[0]):
            if exit_ts <= t.entry_ts:
                equity += pnl; used_margin -= margin
                curve.append((exit_ts, equity))
            else:
                still.append((exit_ts, pnl, margin))
        open_pos = still
        if len(open_pos) >= max_conc:
            skipped_conc += 1; continue
        risk_amt = equity * risk
        notional = risk_amt / STOP
        margin = notional / lev
        avail = equity - used_margin
        if margin > avail:
            if avail <= 0:
                skipped_margin += 1; continue
            margin = avail; notional = margin * lev; risk_amt = notional * STOP
        pnl = t.net_R * risk_amt
        open_pos.append((t.exit_ts, pnl, margin)); used_margin += margin
        taken += 1
    for (exit_ts, pnl, margin) in sorted(open_pos, key=lambda pos: pos[0]):
        equity += pnl; used_margin -= margin; curve.append((exit_ts, equity))
    c = pd.DataFrame(curve, columns=["ts","equity"]).sort_values("ts")
    ts = pd.to_datetime(c.ts); eq = c["equity"].values
    peak = np.maximum.accumulate(eq); dd = eq/peak - 1
    # monthly
    m = pd.Series(eq, index=ts).resample("ME").last().pct_change(fill_method=None).dropna()
    years = (ts.iloc[-1] - ts.iloc[0]).days / 365.25
    cagr = (eq[-1]/initial)**(1/years) - 1 if years > 0 and eq[-1] > 0 else -1
    ret = eq[-1]/initial - 1
    sharpe = (m.mean()/m.std()*np.sqrt(12)) if len(m) > 2 and m.std() > 0 else None
    return dict(final=round(float(eq[-1]),2), ret_pct=round(float(ret*100),1), cagr_pct=round(float(cagr*100),1),
                mdd_pct=round(float(dd.min()*100),1), sharpe=round(float(sharpe),2) if sharpe else None,
                years=round(years,2), trades_taken=taken, skipped_concurrency=skipped_conc,
                skipped_margin=skipped_margin, monthly=monthly,
                yearly={int(y): round(float(g.iloc[-1]/g.iloc[0]-1)*100,1) for y,g in pd.Series(eq,index=ts).groupby(pd.Series(eq,index=ts).index.year)},
                mdd_series=dd)

def main():
    tr = build_trades()
    tr.to_csv(os.path.join(VERIFY, "portfolio_trades.csv"), index=False)
    print("trades built:", len(tr), "avg net_R", round(tr.net_R.mean(),3))
    res = {}
    for risk in (0.0005, 0.001, 0.002, 0.005, 0.01):
        for conc in (1, 3, 5, 10):
            r = simulate(tr, risk=risk, max_conc=conc)
            r["monthly"] = None; r["mdd_series"] = None
            res[f"risk{risk*100:.1f}_conc{conc}"] = r
            print(f"risk={risk*100:.1f}% conc={conc}: final={r['final']:,.0f} ret={r['ret_pct']}% cagr={r['cagr_pct']}% mdd={r['mdd_pct']}% sharpe={r['sharpe']} taken={r['trades_taken']} skipC={r['skipped_concurrency']} skipM={r['skipped_margin']}")
    json.dump(res, open(os.path.join(VERIFY, "portfolio_results.json"), "w"), ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
