"""Exploratory OHLC proxies, never a trading system or prospective record."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .execution_delay_diagnostic import delay_one_bar, candidates_with_entry_in_window
from .forward_scan import closed_snapshot, read_raw_candles
from .tph_ledger import replay

START, SPLIT, END = '2024-07-01', '2025-10-01', '2026-10-25'
DEFINITION = Path('docs/周期空间情绪裸K-现货对照-研究定义-20261030.md')
MARKET = Path('data/market')
SPOT_URL = 'https://data-api.binance.vision/api/v3/klines'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def features(btc, eth):
    def daily(d):
        return d.set_index('ts').resample('1D').agg({'high':'max','low':'min','close':'last'})
    bd, ed = daily(btc), daily(eth)
    prior_high = ed.high.rolling(20, min_periods=20).max()
    ctx = pd.DataFrame({'cycle':bd.close > bd.close.shift(20),
                        'emotion':ed.close.pct_change(7) > bd.close.pct_change(7),
                        'space':(ed.close < prior_high) & (ed.close >= prior_high*.85)})
    ctx = ctx.shift(1).reindex(eth.ts.dt.floor('D')).reset_index(drop=True)
    prev_low = eth.low.shift(1).rolling(20, min_periods=20).min()
    trigger = (eth.low < prev_low) & (eth.close > prev_low)
    hit = (ctx.cycle.eq(True) & ctx.emotion.eq(True) & ctx.space.eq(True) & trigger).to_numpy()
    exit_floor = ed.low.shift(1).rolling(10, min_periods=10).min()
    return hit, eth.low.to_numpy(), exit_floor


def delayed(hit, levels):
    stops = np.full(len(levels), np.nan)
    stops[1:] = np.asarray(levels)[:-1]
    return delay_one_bar(hit), stops


def spot_summary(rows, start, end):
    first, last = pd.Timestamp(start, tz='UTC'), pd.Timestamp(end, tz='UTC')
    expected = pd.date_range(first, last-pd.Timedelta(days=1), freq='D')
    ts = pd.to_datetime([r[0] for r in rows], unit='ms', utc=True)
    if not ts.equals(expected):
        raise ValueError('spot daily timestamps incomplete or unordered')
    a = np.asarray([[float(v) for v in r[1:5]] for r in rows])
    if (not np.isfinite(a).all() or (a <= 0).any() or (a[:,2]>np.min(a[:,[0,1,3]],axis=1)).any()
            or (a[:,1]<np.max(a[:,[0,2,3]],axis=1)).any()):
        raise ValueError('spot OHLC invalid')
    qty = 2000/(a[0,0]*(1+.0002)*(1+.001))
    curve = qty*a[:,3]
    # Starting cash is the initial peak even when entry costs make day one negative.
    peaks = np.maximum.accumulate(np.r_[2000.,curve])[1:]
    mark = float(curve[-1]); sold = mark*(1-.0002)*(1-.001)
    years = (last-first).days/365.25
    return {'initial_usdt':2000,'quantity':float(qty),'entry_open':float(a[0,0]),'last_close':float(a[-1,3]),
            'equity_mark_usdt':mark,'return_mark_pct':(mark/2000-1)*100,
            'cagr_mark_pct':((mark/2000)**(1/years)-1)*100,
            'mdd_daily_close_pct':float((curve/peaks-1).min()*100),
            'estimated_exit_net_usdt':float(sold),'spot_fee_per_side_assumed':.001,'slippage_per_side_assumed':.0002}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True);args=parser.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    bars={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        frame,state=closed_snapshot(read_raw_candles(symbol,MARKET),pd.Timestamp(END,tz='UTC'),minimum_bars=205*288)
        if frame is None or state['status']!='FRESH' or frame.ts.iloc[-1]!=pd.Timestamp(END,tz='UTC')-pd.Timedelta(minutes=5):
            raise ValueError('invalid futures data')
        bars[symbol]=frame.reset_index(drop=True)
    if not bars['BTCUSDT'].ts.equals(bars['ETHUSDT'].ts):raise ValueError('futures grids differ')
    if bars['ETHUSDT'].ts.iloc[0]>pd.Timestamp(START,tz='UTC')-pd.Timedelta(days=205):raise ValueError('insufficient warmup')
    funding=pd.read_csv(MARKET/'ETHUSDT_funding.csv.gz',usecols=['ts','funding_rate'])
    if funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing or not np.isfinite(funding.to_numpy(dtype=float)).all():
        raise ValueError('funding invalid')
    inputs={str(p):sha(p) for p in (MARKET/'BTCUSDT_5m.csv.gz',MARKET/'ETHUSDT_5m.csv.gz',MARKET/'ETHUSDT_funding.csv.gz')}
    spot={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        params={'symbol':symbol,'interval':'1d','startTime':int(pd.Timestamp(START,tz='UTC').timestamp()*1000),
                'endTime':int(pd.Timestamp(END,tz='UTC').timestamp()*1000)-1,'limit':1000}
        response=requests.get(SPOT_URL,params=params,timeout=30);response.raise_for_status()
        (out/f'{symbol}-spot-response.json').write_bytes(response.content)
        (out/f'{symbol}-spot-request.json').write_text(json.dumps({'url':SPOT_URL,'params':params},indent=2)+'\n')
        spot[symbol]=response.json()
        spot_summary(spot[symbol],START,END)
    eth=bars['ETHUSDT'];hit,stops,exit_floor=features(bars['BTCUSDT'],eth)
    reports={}
    for label,start,end in [('full',START,END),('early',START,SPLIT),('late',SPLIT,END)]:
        eligible=hit & (eth.ts>=pd.Timestamp(start,tz='UTC')).to_numpy()
        delayed_hit,delayed_stop=delayed(eligible,stops)
        metrics,closed,opened=replay(eth,delayed_hit,exit_floor,funding,start,end,slip=.0002,
                                      risk_basis='initial',structural_stop=delayed_stop,delayed_stop=True)
        n=candidates_with_entry_in_window(eth,delayed_hit,start,end)
        if n!=len(closed)+len(opened)+metrics['skipped'] or abs(metrics['ledger_reconciliation_error'])>1e-7:
            raise ValueError('candidate or ledger reconciliation failed')
        if metrics['skipped']!=sum(metrics[k] for k in ('skipped_invalid_stop','skipped_capacity','skipped_cash')):
            raise ValueError('skip reconciliation failed')
        for x in closed+opened:
            if x['qty']*x['entry']>750+1e-7 or x['qty']*(x['entry']-x['stop'])>3+1e-7:
                raise ValueError('position limit exceeded')
        for x in closed:
            if abs(x['net_pnl']-(x['gross_pnl']-x['entry_fee']-x['exit_fee']-x['funding_paid']))>1e-8:
                raise ValueError('cost mismatch')
        start_ms=int(pd.Timestamp(start,tz='UTC').timestamp()*1000);end_ms=int(pd.Timestamp(end,tz='UTC').timestamp()*1000)
        comparisons={symbol:spot_summary([r for r in rows if start_ms<=r[0]<end_ms],start,end) for symbol,rows in spot.items()}
        reports[label]={'start':start,'end_exclusive':end,'candidates':n,'futures':metrics,
                        'closed_wins':int(sum(x['net_pnl']>0 for x in closed)),
                        'futures_fees':sum(x['entry_fee']+x['exit_fee'] for x in closed)+sum(x['entry_fee'] for x in opened),
                        'futures_funding':sum(x['funding_paid'] for x in closed+opened),'spot':comparisons}
        pd.DataFrame(closed).to_csv(out/f'{label}-closed.csv',index=False)
        pd.DataFrame(opened).to_csv(out/f'{label}-open.csv',index=False)
        print(label,n,round(metrics['equity_end'],2),flush=True)
    if any(sha(p)!=digest for p,digest in inputs.items()):raise ValueError('input changed')
    report={'status':'EXPLORATORY_NOT_VALIDATED','definition_sha256':sha(DEFINITION),'inputs_sha256':inputs,
            'code_sha256':{str(p):sha(p) for p in (Path(__file__),Path('verify/tph_ledger.py'),Path('verify/execution_delay_diagnostic.py'))},
            'spot_response_sha256':{s:sha(out/f'{s}-spot-response.json') for s in spot},'windows':reports,
            'limitations':['Repeatedly studied historical data, not independent OOS.',
                'OHLC proxies, not trader rules or real emotion/market breadth.',
                'Spot daily-close and futures 5m-close drawdowns have different frequency.',
                'Execution, exchange-specific funding and liquidation unverified.']}
    (out/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


if __name__=='__main__':main()
