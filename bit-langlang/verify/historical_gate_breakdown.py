"""Post-hoc accounting of fixed entry gates, not a causal strategy test."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .historical_entry_replica import FIRST,END,SYMBOLS,sha
from .forward_scan import read_raw_candles


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--audit',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    output=Path(a.out)
    if output.exists():raise FileExistsError('refusing overwrite')
    stage=Path(a.stage);audit=Path(a.audit);manifest=json.loads((stage/'manifest.json').read_text())
    for sym in SYMBOLS:
        if sha(stage/f'{sym}_5m.csv.gz')!=manifest['symbols'][sym]['sha256']:raise ValueError('market hash differs')
    idx=pd.date_range(FIRST,END-pd.Timedelta(minutes=5),freq='5min')
    btc=read_raw_candles('BTCUSDT').set_index('ts').reindex(idx)
    bd=btc.resample('1D').agg({'high':'max','low':'min','close':'last'})
    regime=(bd.close>(bd.high.rolling(20,min_periods=20).max()+bd.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False)
    br=bd.close.pct_change(7,fill_method=None);frames={};daily={};score={};parts={}
    for sym in sorted(SYMBOLS):
        f=read_raw_candles(sym,stage).set_index('ts').reindex(idx);frames[sym]=f
        dd=f.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'});daily[sym]=dd
        warm=dd.open.eq(288).shift(1,fill_value=False).rolling(30,min_periods=30).sum().eq(30)
        score[sym]=(dd.close.pct_change(7,fill_method=None)-br).shift(1).where(warm)
        prior=f.low.shift(1).rolling(20,min_periods=20).min()
        hi=f.high.shift(1).rolling(48,min_periods=48).max();lo=f.low.shift(1).rolling(48,min_periods=48).min()
        parts[sym]={'sweep':(f.low<prior)&(f.close>prior),'midpoint':f.close>=(hi+lo)/2,
                    'target':dd.high.rolling(20,min_periods=20).max().shift(1)}
    scores=pd.DataFrame(score);ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first')
    rows=pd.read_csv(audit/'assumed_beijing-rows.csv');rows=rows[rows.status.isin(['SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'])]
    gates=['btc_regime','positive_relative','top_two','sweep_reclaim','four_hour_midpoint','target_above','two_R']
    stats={name:0 for name in gates};cumulative={name:0 for name in gates};details=[]
    for r in rows.itertuples(index=False):
        entry=pd.Timestamp(r.entry_assumed_utc);latest=entry.floor('5min'); sym=r.base+'USDT';examined=[]
        for execution in pd.date_range(latest-pd.Timedelta(minutes=15),latest,freq='5min'):
            if not entry-pd.Timedelta(minutes=15)<=execution<=entry:continue
            signal=execution-pd.Timedelta(minutes=10);day=signal.floor('D')
            if signal not in idx or execution not in idx:continue
            f=frames[sym];bar=f.loc[signal];buy=float(f.loc[execution,'open'])*(1+.0002);target=float(parts[sym]['target'].loc[day]);risk=buy-float(bar.low)
            values=[bool(regime.loc[day]),bool(pd.notna(scores.loc[day,sym]) and scores.loc[day,sym]>0),
                    bool(pd.notna(ranks.loc[day,sym]) and ranks.loc[day,sym]<=2),bool(parts[sym]['sweep'].loc[signal]),
                    bool(parts[sym]['midpoint'].loc[signal]),bool(np.isfinite(target) and target>bar.close),
                    bool(np.isfinite(target) and risk>0 and target-buy>=2*risk)]
            examined.append(values)
        if not examined:raise ValueError('expected comparable signal windows')
        independent=[any(x[i] for x in examined) for i in range(len(gates))]
        all_through=[any(all(x[:i+1]) for x in examined) for i in range(len(gates))]
        for i,name in enumerate(gates):stats[name]+=int(independent[i]);cumulative[name]+=int(all_through[i])
        details.append({'id':int(r.id),'base':r.base,'entry_assumed_utc':r.entry_assumed_utc,
                        'candidate_timestamps':len(examined),'independent':dict(zip(gates,independent)),
                        'cumulative':dict(zip(gates,all_through))})
    original=json.loads((audit/'summary.json').read_text())['results']['assumed_beijing'];assert cumulative[gates[-1]]==original['matched_rows']
    report={'status':'POST_HOC_DESCRIPTIVE_NOT_CAUSAL','evaluable':len(rows),'independent_gates':stats,
            'cumulative_gates_in_fixed_order':cumulative,'details':details,'audit_sha256':sha(audit/'summary.json'),
            'limitation':'Independent gates may pass on different candles; cumulative same-candle checks, no causal attribution.'}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
