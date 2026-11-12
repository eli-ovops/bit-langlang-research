"""Post-hoc conservative sensitivity to reported zero-volume 4h bars."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2016_pivot_20261102 import pivots
from verify.market_support_fallback_2014sp_20261103 import fallback

DATA=Path('data/market/btc-2012year-usd-cross-20261103-01');BASE=Path('data/verify/market-support-fallback-2012year-20261103-01');SPEC=Path('docs/2012零成交柱-事后敏感性定义-20261103.md');OUT=Path('data/verify/market-2012-zero-volume-sensitivity-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    manifest=json.loads((DATA/'manifest.json').read_text());items=[];inputs=[Path(__file__),SPEC,DATA/'manifest.json',DATA/'bitstamp-4h.csv.gz',BASE/'asof_and_future.csv']
    for i,receipt in enumerate(manifest['sources']['bitstamp']['requests']):
        p=DATA/f'bitstamp-{i}.json';assert sha(p)==receipt['sha256'];inputs.append(p)
        items.extend({'ts':int(q['timestamp'])*1000,**{k:float(q[k]) for k in ('open','high','low','close','volume')}} for q in json.loads(p.read_text())['data']['ohlc'])
    raw=pd.DataFrame(items);A=pd.Timestamp(manifest['start']).value//10**6;B=pd.Timestamp(manifest['end_exclusive']).value//10**6;raw=raw[(raw.ts>=A)&(raw.ts<B)].sort_values('ts').reset_index(drop=True);saved=pd.read_csv(DATA/'bitstamp-4h.csv.gz').sort_values('ts').reset_index(drop=True)
    assert len(raw)==len(saved) and not raw.ts.duplicated().any() and np.array_equal(raw.ts.to_numpy(),saved.ts.to_numpy()) and np.allclose(raw[['open','high','low','close']],saved[['open','high','low','close']],rtol=0,atol=1e-10) and np.isfinite(raw.volume).all() and raw.volume.ge(0).all()
    raw.index=pd.to_datetime(raw.ts,unit='ms',utc=True);zero=raw[raw.volume.eq(0)];zero_days=set(zero.index.floor('D'));flat=int((zero[['open','high','low']].eq(zero.close,axis=0)).all(axis=1).sum());d,h=read(DATA/'bitstamp-4h.csv.gz');d.loc[d.index.isin(zero_days),'good']=False;h.loc[h.index.floor('D').isin(zero_days),'good']=False
    old=pd.read_csv(BASE/'asof_and_future.csv');old=old[old.source=='bitstamp'].set_index('as_of_utc');rows=[]
    for t in pd.date_range('2012-01-01','2012-12-31',freq='D',tz='UTC'):
        x=evaluate_extended(d,h,t);p=pivots(d,t);s,method=fallback(d,t,p);prior=d[(d.index>=t-pd.Timedelta(days=57))&(d.index<t)];clean57=len(prior)==57 and prior.good.all();assert clean57==all(t-pd.Timedelta(days=i) not in zero_days for i in range(1,58))
        q={'as_of_utc':t.isoformat(),'old_focus':bool(old.loc[t.isoformat(),'focus']),'old_state':old.loc[t.isoformat(),'new_state'],'strict_long':x['long_relation'],'strict_big':x['big_relation'],'strict_small':x['small_relation'],'strict_focus':x['long_relation']=='UP' and x['big_relation']=='UP' and x['small_relation']=='DOWN','strict_state':s['support_state'],'method':method,'clean_prior_57':bool(clean57)}
        for n in (7,28):
            w=d[(d.index>=t)&(d.index<t+pd.Timedelta(days=n))];clean=len(w)==n and w.good.all();assert clean==all(t+pd.Timedelta(days=i) not in zero_days for i in range(n));q[f'clean_future_{n}']=bool(clean)
        rows.append(q)
    a=pd.DataFrame(rows);OUT.mkdir();a.to_csv(OUT/'sensitivity.csv',index=False);zero[['ts','open','high','low','close','volume']].to_csv(OUT/'zero_volume_bars.csv',index=False)
    sample=a[a.old_focus];summary={'raw_bars':len(raw),'zero_bars':len(zero),'zero_flat_bars':flat,'zero_days':len(zero_days),'zero_2012_bars':int((zero.index.year==2012).sum()),'zero_2012_days':len({t for t in zero_days if t.year==2012}),'points':len(a),'clean_prior_57':int(a.clean_prior_57.sum()),'old_focus':len(sample),'old_focus_clean_prior_57':int(sample.clean_prior_57.sum()),'old_focus_strict_state':sample.strict_state.value_counts().to_dict(),'strict_focus':int(a.strict_focus.sum()),'clean_future_7':int(a.clean_future_7.sum()),'clean_future_28':int(a.clean_future_28.sum()),'status':'POST_HOC_SENSITIVITY_NOT_TRUTH','input_sha256':{str(p):sha(p) for p in inputs}}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='input_sha256'},indent=2))
if __name__=='__main__':main()
