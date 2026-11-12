"""Ten-coin retrospective entry visibility, no account or actual stop claims."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_scan import read_raw_candles
from .historical_entry_replica import eligible_match
from .historical_entry_candidate import three_bar_pattern

COINS=('BTC','ETH','SOL','DOGE','PEOPLE','TRB','WLD','APT','ORDI','1000PEPE')
BEGIN=pd.Timestamp('2022-01-01',tz='UTC');END=pd.Timestamp('2024-06-21',tz='UTC')
PANEL=Path('data/entry_exit/trades_panel.csv')
DEFINITION=Path('docs/历史入场-回踩确认降噪候选-定义-20261030.md')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def behavior_pattern(f):
    low=f.low.shift(1).rolling(20,min_periods=20).min()
    high=f.high.shift(1).rolling(20,min_periods=20).max()
    return (f.close>f.open)&(high>low)&(f.close>=(high+low)/2)


def pullback_pattern(f):
    return (behavior_pattern(f)&(f.close.shift(1)<f.open.shift(1))
            &(f.close>f.close.shift(1)))


def run():
    idx=pd.date_range(BEGIN,END-pd.Timedelta(minutes=5),freq='5min')
    data={};daily={};hashes={}
    for coin in sorted(COINS):
        path=Path('data/market')/f'{coin}USDT_5m.csv.gz';hashes[str(path)]=sha(path)
        f=read_raw_candles(coin+'USDT').set_index('ts')
        if f.index.duplicated().any() or not f.index.is_monotonic_increasing:raise ValueError(f'{coin}: invalid time ordering')
        f=f.loc[(f.index>=BEGIN)&(f.index<END)]
        if f.empty or (f.index.to_series().diff().dropna()!=pd.Timedelta(minutes=5)).any():raise ValueError(f'{coin}: missing 5m bars')
        vals=f[['open','high','low','close']]
        if (not np.isfinite(vals.to_numpy()).all() or (vals<=0).any().any()
                or (f.low>f[['open','high','close']].min(axis=1)).any()
                or (f.high<f[['open','low','close']].max(axis=1)).any()):raise ValueError(f'{coin}: invalid OHLC')
        f=f.reindex(idx);data[coin]=f
        daily[coin]=f.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
    bd=daily['BTC'];regime=(bd.close>(bd.high.rolling(20,min_periods=20).max()+bd.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False)
    btc_ret=bd.close.pct_change(7,fill_method=None);scores={};targets={};warmups={}
    for coin in sorted(COINS):
        dd=daily[coin];warm=dd.open.eq(288).shift(1,fill_value=False).rolling(30,min_periods=30).sum().eq(30)
        scores[coin]=(dd.close.pct_change(7,fill_method=None)-btc_ret).shift(1).where(warm)
        targets[coin]=dd.high.rolling(20,min_periods=20).max().shift(1);warmups[coin]=warm
    scores=pd.DataFrame(scores).where(regime,axis=0);ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first')
    outcomes={name:{} for name in ('original_sweep','three_bar_candidate','three_bar_btc_exception','behavior_candidate','pullback_delayed_candidate')}
    for coin in sorted(COINS):
        f=data[coin];previous=f.low.shift(1).rolling(20,min_periods=20).min();hi=f.high.shift(1).rolling(48,min_periods=48).max();lo=f.low.shift(1).rolling(48,min_periods=48).min()
        rank=ranks[coin].reindex(idx.floor('D')).to_numpy();target=targets[coin].reindex(idx.floor('D')).to_numpy();stop=f.low.to_numpy()
        midpoint=(f.close>=(hi+lo)/2).to_numpy();entry=f.open.shift(-2).to_numpy()*(1+.0002);risk=entry-stop
        other_conditions=midpoint&(target>f.close.to_numpy())&np.isfinite(entry)&(risk>0)&((target-entry)>=2*risk)
        common=(rank<=2)&other_conditions
        btc_enabled=(regime & warmups[coin]).reindex(idx.floor('D')).to_numpy() if coin=='BTC' else (rank<=2)
        exception_common=btc_enabled&other_conditions
        patterns={'original_sweep':((f.low<previous)&(f.close>previous)).to_numpy(),
                  'three_bar_candidate':three_bar_pattern(f).to_numpy()}
        patterns['behavior_candidate']=behavior_pattern(f).to_numpy()
        patterns['three_bar_btc_exception']=patterns['three_bar_candidate']
        patterns['pullback_delayed_candidate']=pullback_pattern(f).to_numpy()
        for label,mask in patterns.items():
            selected=exception_common if label in ('three_bar_btc_exception','behavior_candidate','pullback_delayed_candidate') else common
            times=idx[selected&mask]+pd.Timedelta(minutes=15 if label=='pullback_delayed_candidate' else 10)
            if label=='pullback_delayed_candidate':times=times[times<END]
            outcomes[label][coin]=times.asi8
    panel=pd.read_csv(PANEL);results={};rows_by={}
    for label,signals in outcomes.items():
        rows=[]
        for row in panel.itertuples(index=False):
            coin=str(row.coin);side=str(row.side);t=pd.to_datetime(row.entry_utc,utc=True,errors='coerce')
            item={'coin':coin,'side':side,'entry_assumed_utc':str(row.entry_utc),
                  'recorded_entry':row.entry,'price_scale':row.price_scale,
                  'stop_order_status':'UNKNOWN_NOT_RECORDED','target_order_status':'UNKNOWN_NOT_RECORDED'}
            if coin not in data:item['status']='UNKNOWN_SYMBOL'
            elif pd.isna(t) or not BEGIN<=t<END:item['status']='UNKNOWN_TIME'
            elif side!='多':item['status']='OUT_OF_SCOPE_SHORT'
            elif t.floor('5min') not in data[coin].index or pd.isna(data[coin].loc[t.floor('5min'),'open']):item['status']='UNKNOWN_MARKET'
            elif not bool(warmups[coin].get(t.floor('D'),False)):item['status']='UNKNOWN_INSUFFICIENT_WARMUP'
            elif not np.isfinite([row.entry,row.price_scale]).all() or row.entry<=0 or row.price_scale<=0:item['status']='UNKNOWN_PRICE'
            else:
                candle=data[coin].loc[t.floor('5min')];px=float(row.entry)*float(row.price_scale)
                found=eligible_match(signals[coin],t.value)
                item.update(status='SIGNAL_OVERLAP' if found is not None else 'NO_SIGNAL_OVERLAP',
                            price_inside_bar=bool(candle.low<=px<=candle.high),
                            matched_time=pd.Timestamp(found,tz='UTC').isoformat() if found is not None else None,
                            lag_seconds=(t.value-found)/1e9 if found is not None else None)
            rows.append(item)
        df=pd.DataFrame(rows);valid=df[df.status.isin(['SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'])];matched=valid[valid.status=='SIGNAL_OVERLAP']
        bycoin={}
        for c,g in valid.groupby('coin'):
            bycoin[c]={'evaluable':len(g),'matched':int((g.status=='SIGNAL_OVERLAP').sum()),'entry_in_bar':int(g.price_inside_bar.sum())}
        keys={(r.coin,r.matched_time) for r in matched.itertuples()}
        years=pd.to_datetime(valid.entry_assumed_utc,utc=True).dt.year
        results[label]={'total_positions':len(df),'statuses':{str(k):int(v) for k,v in df.status.value_counts().items()},
                        'evaluable_longs':len(valid),'matched_rows':len(matched),'unique_matched_signals':len(keys),
                        'total_simulated_signals':sum(len(x) for x in signals.values()),'by_coin':bycoin,
                        'by_year':{str(y):{'evaluable':int((years==y).sum()),'matched':int(((years==y)&(valid.status=='SIGNAL_OVERLAP')).sum())} for y in sorted(years.unique())}}
        rows_by[label]=rows
    for path,digest in hashes.items():
        if sha(path)!=digest:raise ValueError('input changed')
    return results,rows_by,hashes,outcomes


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();output=Path(a.outdir)
    if output.exists():raise FileExistsError('output exists')
    inputs={str(p):sha(p) for p in (PANEL,DEFINITION,Path(__file__))};results,rows,hashes,outcomes=run()
    if any(sha(p)!=v for p,v in inputs.items()):raise ValueError('input changed')
    output.mkdir(parents=True,exist_ok=False)
    for label,records in rows.items():pd.DataFrame(records).to_csv(output/f'{label}-rows.csv',index=False)
    for label,per_coin in outcomes.items():
        (output/f'{label}-signal-times.json').write_text(json.dumps({coin:[int(x) for x in times] for coin,times in per_coin.items()})+'\n')
    report={'status':'POST_HOC_ENTRY_VISIBILITY_NOT_REPLICATION','results':results,'input_sha256':{**inputs,**hashes},
            'limitations':['Expanded 10-coin rank, not original 5-coin strategy.',
                'Panel positions not original rows, source/UTC assumption and venue unverified.',
                'No account constraints, actual orders, confirmed stops or targets.']}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
