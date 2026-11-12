"""Post-selection counterfactual; does not change frozen signals."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .tph_frozen_audit import signals
from .tph_ledger import replay

ROOT=Path(__file__).resolve().parent.parent
DEFINITION=ROOT/'docs/周期近似-动态对照-事后探索定义-20261030.md'
START='2024-07-01';END='2026-10-25'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_checked(symbol):
    d=pd.read_csv(Path(MARKET)/(symbol+'_5m.csv.gz'),usecols=['ts','open','high','low','close'])
    d['ts']=pd.to_datetime(d.ts,unit='ms',utc=True,errors='raise')
    if (d.ts.duplicated().any() or not d.ts.is_monotonic_increasing or
            not d.ts.diff().dropna().eq(pd.Timedelta(minutes=5)).all() or
            not d.ts.dt.floor('5min').eq(d.ts).all() or
            not np.isfinite(d[['open','high','low','close']].to_numpy()).all() or
            (d[['open','high','low','close']]<=0).any().any() or
            (d.low>d[['open','close','high']].min(axis=1)).any() or
            (d.high<d[['open','close','low']].max(axis=1)).any()):
        raise ValueError('原始行情时间或 OHLC 无效')
    return d


def allowed_by_prior_day(candles):
    ts=candles.ts
    if ts.duplicated().any() or not ts.is_monotonic_increasing:raise ValueError('行情时标重复或逆序')
    daily=candles.groupby(ts.dt.floor('D')).agg(count=('ts','size'),first=('ts','first'),last=('ts','last'),close=('close','last'))
    valid=(daily['count'].eq(288)&daily['first'].eq(daily.index)&
           daily['last'].eq(daily.index+pd.Timedelta(hours=23,minutes=55)))
    closes=daily.close.where(valid).reindex(pd.date_range(daily.index.min(),daily.index.max(),freq='D',tz='UTC'))
    prior=(ts+pd.Timedelta(minutes=5)).dt.floor('D')-pd.Timedelta(days=1)
    a=closes.reindex(prior).to_numpy();b=closes.reindex(prior-pd.Timedelta(days=20)).to_numpy()
    ret=a/b-1
    return np.isfinite(ret)&(ret<.2),ret


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True);args=parser.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    btc=load_checked('BTCUSDT');eth=load_checked('ETHUSDT');fund=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    if (fund.ts.duplicated().any() or not fund.ts.is_monotonic_increasing or
            not np.isfinite(fund[['ts','funding_rate']].to_numpy(dtype=float)).all()):
        raise ValueError('资金费数据无效或逆序')
    end=pd.Timestamp(END,tz='UTC');btc=btc[btc.ts<end].reset_index(drop=True);eth=eth[eth.ts<end].reset_index(drop=True)
    hit,_,ema=signals(btc,eth);allowed,ret=allowed_by_prior_day(eth)
    start=pd.Timestamp(START,tz='UTC');entry_time=eth.ts+pd.Timedelta(minutes=5)
    window=(entry_time>=start)&(entry_time<end);selected=hit&window.to_numpy()
    dropped=pd.DataFrame({'signal_time':eth.ts[selected&~allowed].astype(str),
                          'prior_20d_return':ret[selected&~allowed]})
    dropped.to_csv(out/'filtered_candidates.csv',index=False)
    results={};ledgers={}
    for name,mask in [('baseline',hit),('filtered',hit&allowed)]:
        result,closed,opened=replay(eth,mask,ema,fund,START,END,fee=.0005,slip=.0002)
        results[name]=result;ledgers[name]=(closed,opened)
        pd.DataFrame(closed).to_csv(out/(name+'_closed.csv'),index=False)
        pd.DataFrame(opened).to_csv(out/(name+'_open.csv'),index=False)
        if abs(result['ledger_reconciliation_error'])>1e-7:raise ValueError('账本权益对账失败')
    if int(selected.sum())!=int((selected&allowed).sum())+len(dropped):raise ValueError('候选数量对账失败')
    summary={'status':'POST_SELECTION_EXPLORATORY_NOT_OOS','candidates_total':int(selected.sum()),
             'candidates_kept':int((selected&allowed).sum()),'candidates_filtered':len(dropped),
             'filtered_missing_prior':int(dropped.prior_20d_return.isna().sum()),'results':results,
             'inputs':{'btc':sha(Path(MARKET)/'BTCUSDT_5m.csv.gz'),'eth':sha(Path(MARKET)/'ETHUSDT_5m.csv.gz'),
                       'funding':sha(Path(MARKET)/'ETHUSDT_funding.csv.gz'),'definition':sha(DEFINITION),
                       'code':sha(Path(__file__)),'replay':sha(ROOT/'verify/tph_ledger.py'),
                       'signals':sha(ROOT/'verify/tph_frozen_audit.py')},
             'note':'20% selected after inspecting historical groups; not causal or independent. End-of-bar open fills are hypothetical.'}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
