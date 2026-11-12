#!/usr/bin/env python3
"""前瞻扫描：用冻结参数扫描最新数据，输出当前候选/观察列表（BTC/ETH only）。
用法：python3 -m verify.forward_scan [--days 5] [--json]
数据需使用有效的只读行情快照；旧下载器会保留未收盘尾根，不可直接用于前瞻。
"""
import argparse, hashlib, json, os
from pathlib import Path
import numpy as np
import pandas as pd
from .common import MARKET, VERIFY

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "frozen_config.json")))
SYMS = CFG["universe"]

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def stop_for_entry(entry_price):
    """Unrounded theoretical stop; exchange tick size and triggering are unknown."""
    return float(entry_price) * (1 - CFG["stop_pct"]) if entry_price is not None else None

def signal_records(data, hit, cutoff):
    """Complete candidate list for the available window, not live execution."""
    return [{"ts":str(data.ts.iloc[i]), "historical_only":True,
             "entry_next_open":float(data.open.iloc[i+1]) if i+1<len(data) else None,
             "reference_stop_on_open":stop_for_entry(data.open.iloc[i+1]) if i+1<len(data) else None}
            for i in np.flatnonzero(hit) if data.ts.iloc[i]>=cutoff]

def read_raw_candles(symbol, market_dir=MARKET):
    path = os.path.join(market_dir, f'{symbol}_5m.csv.gz')
    if not os.path.exists(path): return None
    data = pd.read_csv(path, usecols=['ts','open','high','low','close'])
    data['ts'] = pd.to_datetime(data.ts, unit='ms', utc=True, errors='coerce')
    return data

def closed_snapshot(data, now, max_age_minutes=15, minimum_bars=0):
    """Return completed candles and an explicit freshness assessment."""
    if data is None or data.empty:
        return None, {'status':'INVALID', 'reason':'行情缺失'}
    ts = data.ts
    if ts.isna().any() or not ts.is_monotonic_increasing or ts.duplicated().any():
        return None, {'status':'INVALID', 'reason':'时间戳缺失、重复或乱序'}
    if (ts.astype('int64') % 300_000_000_000 != 0).any():
        return None, {'status':'INVALID', 'reason':'K 线未按 5 分钟 UTC 网格对齐'}
    if all(c in data.columns for c in ('open','high','low','close')):
        v = data[['open','high','low','close']].apply(pd.to_numeric, errors='coerce')
        if not np.isfinite(v.to_numpy()).all() or (v <= 0).any().any() or (v.low > v[['open','close','high']].min(axis=1)).any() or (v.high < v[['open','close','low']].max(axis=1)).any():
            return None, {'status':'INVALID', 'reason':'OHLC 价格缺失或高低关系错误'}
    if (ts.diff().dropna() != pd.Timedelta(minutes=5)).any():
        return None, {'status':'INVALID', 'reason':'5 分钟行情存在缺口'}
    closed = data.loc[ts + pd.Timedelta(minutes=5) <= now].copy()
    if closed.empty:
        return None, {'status':'INVALID', 'reason':'没有已收盘 K 线'}
    if len(closed)<minimum_bars:
        return None, {'status':'INVALID', 'reason':'日线指标预热数据少于 205 天'}
    age = (now - (closed.ts.iloc[-1] + pd.Timedelta(minutes=5))).total_seconds() / 60
    if age > max_age_minutes:
        return closed, {'status':'STALE', 'last_closed':str(closed.ts.iloc[-1]), 'age_minutes':round(age,2)}
    return closed, {'status':'FRESH', 'last_closed':str(closed.ts.iloc[-1]), 'age_minutes':round(age,2)}

def build_snapshot(market_dir, days, now):
    """Calculate one historical-as-of snapshot; caller owns clock authenticity."""
    if days <= 0: raise ValueError('days 必须为正整数')
    now = pd.to_datetime(now, utc=True, errors='raise')
    if pd.isna(now): raise ValueError('扫描时间无效')
    from .tph_frozen_audit import signals
    btc, btc_status = closed_snapshot(read_raw_candles("BTCUSDT",market_dir), now, minimum_bars=205*288)
    out = {"generated_at": str(now), "config": CFG["name"],
           "config_sha256": hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest(),
           "validation_status": "INVALID", "validation_reason": "BTC相对自身强度恒为零；成本与端到端验证尚未完成。", "symbols": {}}
    out['btc_data_status'] = btc_status
    for sym in SYMS:
        d, state = closed_snapshot(read_raw_candles(sym,market_dir), now, minimum_bars=205*288)
        if btc is None or d is None:
            out['symbols'][sym] = {'data_status':state, 'watch':False, 'signals_recent':[]}
            continue
        d = d.reset_index(drop=True)
        if not d.ts.equals(btc.ts.reset_index(drop=True)):
            state = {**state, 'status':'INVALID', 'reason':'币种与 BTC 的完整已收盘时间网格不一致'}
            out['symbols'][sym] = {'data_status':state, 'watch':False, 'signals_recent':[],
                                   'candidate_count':0,
                                   'data_sha256':hashlib.sha256((Path(market_dir)/f'{sym}_5m.csv.gz').read_bytes()).hexdigest()}
            continue
        hit, features, ema20 = signals(btc, d)
        # The final daily bucket can still be forming; never present its EMA
        # as a completed daily indicator. A 23:55 candle closes at midnight.
        last_day=d.ts.iloc[-1].floor('D')
        completed_day=last_day if d.ts.iloc[-1].hour==23 and d.ts.iloc[-1].minute==55 else last_day-pd.Timedelta(days=1)
        completed_ema=ema20.get(completed_day, np.nan)
        cutoff = d.ts.max() - pd.Timedelta(days=days)
        rs, dh, on = features.rs7.iloc[-1], features.dist_hi.iloc[-1], features.risk_on.iloc[-1]
        candidates = signal_records(d,hit,cutoff) if state['status']=='FRESH' and btc_status['status']=='FRESH' else []
        out["symbols"][sym] = {
            "data_status": state,
            "data_sha256":hashlib.sha256((Path(market_dir)/f'{sym}_5m.csv.gz').read_bytes()).hexdigest(),
            "candidate_window_start":str(cutoff), "candidate_count":len(candidates),
            "candidate_coverage":"available snapshot only; historical diagnostic, not proof of prospective capture",
            "last_price": float(d.close.iloc[-1]), "last_ts": str(d.ts.iloc[-1]),
            "risk_on": bool(on) if pd.notna(on) else None,
            "rs7": round(float(rs), 4) if pd.notna(rs) else None,
            "dist_hi": round(float(dh), 4) if pd.notna(dh) else None,
            "ema20_daily": round(float(completed_ema), 2) if pd.notna(completed_ema) else None,
            "ema20_daily_completed_day_utc": str(completed_day.date()) if pd.notna(completed_ema) else None,
            "signals_recent": candidates,
            "watch": bool(state['status'] == 'FRESH' and btc_status['status'] == 'FRESH' and pd.notna(rs) and pd.notna(dh) and on == True and rs > 0 and dh < .03),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--market-dir", default=MARKET, help="可选行情快照目录")
    ap.add_argument("--out", help="可选的新文件路径；已存在则拒绝覆盖")
    a = ap.parse_args()
    if a.days <= 0: ap.error('--days 必须为正整数')
    out=build_snapshot(a.market_dir,a.days,pd.Timestamp.now(tz="UTC"))
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"VALIDATION {out['validation_status']}: {out['validation_reason']}")
        for sym, v in out["symbols"].items():
            print(f"[{sym}] data={v['data_status']['status']} price={v.get('last_price')} risk_on={v.get('risk_on')} rs7={v.get('rs7')} dist_hi={v.get('dist_hi')} watch={v['watch']} signals_recent={len(v['signals_recent'])}")
            for s in v["signals_recent"]:
                print("   signal:", s)
    if a.out:
        with open(a.out, 'x', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
