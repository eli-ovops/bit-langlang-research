"""User-specified spot universe, exploratory and retrospective, never an order."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .cycle_space_research import spot_summary

COINS=('UNIUSDT','AAVEUSDT','LINKUSDT','ENAUSDT','LITUSDT')
SYMBOLS=COINS+('BTCUSDT','ETHUSDT')
DATA_START='2024-05-31'; START='2024-07-02'; END='2026-10-25'
URL='https://data-api.binance.vision/api/v3/klines'
DEFINITION=Path('docs/五币强弱与现货对照-研究定义-20261030.md')


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(frames,start=START,end=END,coins=COINS):
    """Monthly score is known 24h before the next-day open fill proxy."""
    begin=pd.Timestamp(start,tz='UTC');finish=pd.Timestamp(end,tz='UTC')
    index=frames[coins[0]].index
    if begin not in index or finish-pd.Timedelta(days=1) not in index:raise ValueError('window missing')
    for symbol in coins:
        if not frames[symbol].index.equals(index):raise ValueError('unaligned daily data')
    data=pd.DataFrame({symbol:frames[symbol].close for symbol in coins})
    cash=2000.;quantity=0.;held=None;orders=[];daily=[];picks=[]
    for day in index[(index>=begin)&(index<finish)]:
        loc=index.get_loc(day)
        if day.day==2:
            if loc<32:raise ValueError('insufficient history')
            ranks=(data.iloc[loc-2]/data.iloc[loc-32]-1).sort_values(ascending=False,kind='stable')
            ranked=sorted(((s,float(ranks[s])) for s in coins),key=lambda p:(-p[1],p[0]))
            choice=ranked[0][0]
            picks.append({'decision_time':(day-pd.Timedelta(days=1)).isoformat(),
                          'execution_time':day.isoformat(),'score_end_day':index[loc-2].date().isoformat(),
                          'score_start_day':index[loc-32].date().isoformat(),'ranks':ranked,'selected':choice})
            if held!=choice:
                if held is not None:
                    ref=float(frames[held].loc[day,'open']);fill=ref*(1-.0002)
                    proceeds=quantity*fill;fee=proceeds*.001;cash+=proceeds-fee
                    orders.append({'time':day.isoformat(),'symbol':held,'side':'SELL','ref_open':ref,
                                   'fill':fill,'qty':quantity,'fee':fee,'cash_after':cash})
                    quantity=0.
                ref=float(frames[choice].loc[day,'open']);fill=ref*(1+.0002)
                quantity=cash/(fill*(1+.001));fee=quantity*fill*.001
                cash-=quantity*fill+fee; held=choice
                if abs(cash)<1e-9:cash=0.
                orders.append({'time':day.isoformat(),'symbol':held,'side':'BUY','ref_open':ref,
                               'fill':fill,'qty':quantity,'fee':fee,'cash_after':cash})
        equity=cash+(quantity*float(frames[held].loc[day,'close']) if held else 0.)
        if not np.isfinite(equity) or equity<0:raise ValueError('invalid equity')
        daily.append({'date':day.date().isoformat(),'held':held,'cash':cash,'qty':quantity,'equity':equity})
    values=np.asarray([r['equity'] for r in daily]);peaks=np.maximum.accumulate(np.r_[2000.,values])[1:]
    end_mark=float(values[-1]); exit_est=end_mark*(1-.0002)*(1-.001) if held else end_mark
    years=(finish-begin).days/365.25
    return {'initial_usdt':2000.,'equity_mark_usdt':end_mark,'return_pct':(end_mark/2000-1)*100,
            'cagr_pct':((end_mark/2000)**(1/years)-1)*100,
            'mdd_daily_close_pct':float((values/peaks-1).min()*100),
            'estimated_exit_net_usdt':exit_est,'orders':orders,'picks':picks,'daily':daily}


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--end',default=END)
    p.add_argument('--without-lit',action='store_true');p.add_argument('--definition',default=str(DEFINITION));args=p.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    coins=tuple(s for s in COINS if not (args.without_lit and s=='LITUSDT'))
    symbols=coins+('BTCUSDT','ETHUSDT')
    start=int(pd.Timestamp(DATA_START,tz='UTC').timestamp()*1000);end=int(pd.Timestamp(args.end,tz='UTC').timestamp()*1000)
    expected=pd.date_range(DATA_START,pd.Timestamp(args.end)-pd.Timedelta(days=1),freq='D',tz='UTC')
    frames={};raw={};hashes={}
    for symbol in symbols:
        params={'symbol':symbol,'interval':'1d','startTime':start,'endTime':end-1,'limit':1000}
        r=requests.get(URL,params=params,timeout=30);r.raise_for_status()
        dest=out/f'{symbol}-response.json';dest.write_bytes(r.content);hashes[symbol]=digest(dest)
        (out/f'{symbol}-request.json').write_text(json.dumps({'url':URL,'params':params},indent=2)+'\n')
        rows=r.json();raw[symbol]=rows
        times=pd.to_datetime([x[0] for x in rows],unit='ms',utc=True)
        if not times.equals(expected):raise ValueError(f'{symbol}: daily time grid mismatch')
        if any(int(x[6])!=int(x[0])+86400000-1 for x in rows):raise ValueError('bad daily close time')
        values=np.asarray([[float(x[k]) for k in (1,2,3,4,5,7)] for x in rows])
        if (not np.isfinite(values).all() or (values[:,:4]<=0).any() or (values[:,4:]<0).any()
                or (values[:,2]>values[:,[0,1,3]].min(axis=1)).any()
                or (values[:,1]<values[:,[0,2,3]].max(axis=1)).any()):raise ValueError('bad spot OHLC')
        frames[symbol]=pd.DataFrame({'open':values[:,0],'close':values[:,3]},index=times)
    rotation=evaluate(frames,end=args.end,coins=coins)
    start_ms=int(pd.Timestamp(START,tz='UTC').timestamp()*1000)
    benchmarks={s:spot_summary([row for row in rows if row[0]>=start_ms],START,args.end) for s,rows in raw.items()}
    (out/'rotation-daily.json').write_text(json.dumps(rotation,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    summary={'status':'EXPLORATORY_NOT_VALIDATED','start':START,'end_exclusive':args.end,'coins':coins,
             'definition_sha256':digest(args.definition),'code_sha256':digest(__file__),
             'benchmark_code_sha256':digest(Path('verify/cycle_space_research.py')),
             'spot_response_sha256':hashes,'rotation':{k:v for k,v in rotation.items() if k not in ('orders','daily','picks')},
             'rotation_rebalances':len(rotation['picks']),'rotation_orders':len(rotation['orders']),
             'selected_counts':{s:sum(p['selected']==s for p in rotation['picks']) for s in coins},
             'benchmarks':benchmarks,
             'limitations':['User-chosen universe, retrospective and not full market.',
                '30-day return and monthly rotation are research assumptions, not verified trader rules.',
                'No stop, intraday entry or regime model; fills and costs assumed.',
                'Source authenticity, spread, taxes, actual venue and account are UNKNOWN.']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'rotation':summary['rotation'],'selected_counts':summary['selected_counts'],
                      'benchmarks':{s:round(x['equity_mark_usdt'],2) for s,x in benchmarks.items()}},ensure_ascii=False))


if __name__=='__main__':main()
