"""Past-only price features versus same-coin same-day controls; not an order model."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_scan import read_raw_candles
from .historical_ten_replica import COINS,BEGIN,END,PANEL

DEFINITION=Path('docs/历史交割-入场周期强势-对照定义-20261030.md')
SEED=20261030


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def past_features(frame):
    close=frame.close;high=frame.high.shift(1).rolling(20,min_periods=20).max();low=frame.low.shift(1).rolling(20,min_periods=20).min()
    width=high-low
    return pd.DataFrame({'return4h':close/close.shift(48)-1,'range_position':(close-low)/width.where(width>0),
                         'entity':close-frame.open},index=frame.index)


def run():
    idx=pd.date_range(BEGIN,END-pd.Timedelta(minutes=5),freq='5min');frames={};features={};daily={};hashes={}
    for coin in sorted(COINS):
        path=Path('data/market')/f'{coin}USDT_5m.csv.gz';hashes[str(path)]=sha(path)
        raw=read_raw_candles(coin+'USDT').set_index('ts');raw=raw.loc[(raw.index>=BEGIN)&(raw.index<END)]
        if raw.empty or raw.index.duplicated().any() or not raw.index.is_monotonic_increasing or (raw.index.to_series().diff().dropna()!=pd.Timedelta(minutes=5)).any():raise ValueError(f'{coin}: invalid grid')
        v=raw[['open','high','low','close']]
        if (not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (raw.low>raw[['open','high','close']].min(axis=1)).any() or (raw.high<raw[['open','low','close']].max(axis=1)).any()):raise ValueError(f'{coin}: invalid OHLC')
        frames[coin]=raw.reindex(idx);features[coin]=past_features(frames[coin]);daily[coin]=frames[coin].resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
    btc=daily['BTC'];btc_warm=btc.open.eq(288).rolling(20,min_periods=20).sum().eq(20)
    btc_phase=(btc.close>(btc.high.rolling(20,min_periods=20).max()+btc.low.rolling(20,min_periods=20).min())/2).where(btc_warm).shift(1)
    score={}
    for coin in sorted(COINS):
        if coin=='BTC':continue
        dd=daily[coin];warm=dd.open.eq(288).rolling(30,min_periods=30).sum().eq(30)
        score[coin]=(dd.close.pct_change(7,fill_method=None).where(warm)).shift(1)
    scores=pd.DataFrame(score);n=scores.notna().sum(axis=1)
    rank=scores.rank(axis=1,ascending=False,method='average');percentile=1-(rank-1).div((n-1).where(n>=3),axis=0)
    panel=pd.read_csv(PANEL);rng=np.random.default_rng(SEED);records=[]
    for ordinal,row in enumerate(panel.itertuples(index=False)):
        coin=str(row.coin); t=pd.to_datetime(row.entry_utc,utc=True,errors='coerce');side=str(row.side)
        item={'row_number':ordinal,'coin':coin,'side':side,'entry_assumed_utc':str(row.entry_utc),
              'entry_bar_price_check':'UNKNOWN','stop_order':'UNKNOWN_NOT_RECORDED','target_order':'UNKNOWN_NOT_RECORDED'}
        if coin not in frames or pd.isna(t) or side not in ('多','空') or not BEGIN<=t<END:
            item['status']='UNKNOWN_TIME_SYMBOL_SIDE';records.append(item);continue
        last=t.floor('5min')-pd.Timedelta(minutes=5);day=t.floor('D');feature=features[coin]
        if last not in feature.index or feature.loc[last].isna().any():
            item['status']='UNKNOWN_ENTRY_WARMUP';records.append(item);continue
        cand=pd.date_range(day,day+pd.Timedelta(hours=23,minutes=50),freq='5min');available=feature.reindex(cand).dropna()
        if available.empty:
            item['status']='UNKNOWN_CONTROL';records.append(item);continue
        controls=available.iloc[rng.integers(0,len(available),size=20)];actual=feature.loc[last];sgn=1 if side=='多' else -1
        phase=btc_phase.get(day);pr=percentile.at[day,coin] if coin!='BTC' and day in percentile.index else np.nan
        row_scores=percentile.loc[day].dropna() if day in percentile.index else pd.Series(dtype=float)
        baseline=float((row_scores>=.75).mean()) if side=='多' and len(row_scores)>=3 else float((row_scores<=.25).mean()) if len(row_scores)>=3 else None
        item.update(status='EVALUABLE',last_completed_open=last.isoformat(),control_n=20,
                    control_bar_open_ns=json.dumps([int(x) for x in controls.index.asi8]),
                    actual_return4h=float(sgn*actual.return4h),control_return4h=float(sgn*controls.return4h.mean()),
                    actual_position=float(actual.range_position if sgn==1 else 1-actual.range_position),
                    control_position=float(controls.range_position.mean() if sgn==1 else 1-controls.range_position.mean()),
                    actual_entity=int(sgn*actual.entity>0),control_entity=float((sgn*controls.entity>0).mean()),
                    btc_above_midpoint=bool(phase) if pd.notna(phase) else None,
                    asset_relative_percentile=float(pr) if pd.notna(pr) else None,
                    strong_selected=bool(pr>=.75 if sgn==1 else pr<=.25) if pd.notna(pr) else None,
                    strong_peer_baseline=baseline if coin!='BTC' else None)
        bar=frames[coin].loc[t.floor('5min')];price=float(row.entry)*float(row.price_scale)
        if np.isfinite(price) and np.isfinite([bar.low,bar.high]).all():item['entry_bar_price_check']='INSIDE' if bar.low<=price<=bar.high else 'OUTSIDE'
        records.append(item)
    for path,digest in hashes.items():
        if sha(path)!=digest:raise ValueError('source changed')
    return records,hashes


def summaries(records):
    d=pd.DataFrame(records);d=d[d.status=='EVALUABLE'].copy();d['day']=pd.to_datetime(d.entry_assumed_utc,utc=True).dt.floor('D');d['year']=d.day.dt.year
    groups={'all':d,'long':d[d.side=='多'],'short':d[d.side=='空'],
            '2022_2023':d[d.year<=2023],'2024':d[d.year==2024],
            'long_2022_2023':d[(d.side=='多')&(d.year<=2023)],'long_2024':d[(d.side=='多')&(d.year==2024)],
            'short_2022_2023':d[(d.side=='空')&(d.year<=2023)],'short_2024':d[(d.side=='空')&(d.year==2024)]};out={}
    for group,frame in groups.items():
        metrics={};rng=np.random.default_rng(SEED)
        for metric in ('return4h','position','entity'):
            a=pd.to_numeric(frame['actual_'+metric]);b=pd.to_numeric(frame['control_'+metric]);difference=a-b
            means=difference.groupby(frame.day).mean().to_numpy();bootstrap=np.mean(rng.choice(means,size=(1000,len(means)),replace=True),axis=1) if len(means) else []
            metrics[metric]={'rows':len(frame),'days':len(means),'actual_mean':float(a.mean()),'control_mean':float(b.mean()),
                             'trade_weighted_difference':float(difference.mean()),'day_equal_difference':float(np.mean(means)),
                             'day_bootstrap_95':np.quantile(bootstrap,[.025,.975]).tolist() if len(means) else None}
        selected=frame[frame.strong_selected.notna()];phase=frame[frame.btc_above_midpoint.notna()]
        rank_difference=(selected.strong_selected.astype(float)-selected.strong_peer_baseline.astype(float)).groupby(selected.day).mean()
        out[group]={'rows':len(frame),'distinct_days':int(frame.day.nunique()),'metrics':metrics,
                    'btc_phase_n':len(phase),'btc_above_midpoint_fraction':float(phase.btc_above_midpoint.astype(bool).mean()) if len(phase) else None,
                    'rank_n':len(selected),'rank_selected_fraction':float(selected.strong_selected.astype(bool).mean()) if len(selected) else None,
                    'rank_peer_expected_fraction':float(selected.strong_peer_baseline.astype(float).mean()) if len(selected) else None,
                    'rank_day_equal_difference':float(rank_difference.mean()) if len(selected) else None,
                    'rank_days':int(len(rank_difference))}
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();output=Path(a.outdir)
    if output.exists():raise FileExistsError('output exists')
    inputs={str(p):sha(p) for p in (PANEL,DEFINITION,Path(__file__))};records,hashes=run();summary=summaries(records)
    if any(sha(p)!=v for p,v in inputs.items()):raise ValueError('input changed')
    output.mkdir(parents=True,exist_ok=False);pd.DataFrame(records).to_csv(output/'records.csv',index=False)
    result={'status':'POST_HOC_EXPLORATORY_NOT_VALIDATED','seed':SEED,'input_sha256':{**inputs,**hashes},
            'status_counts':{str(k):int(v) for k,v in pd.DataFrame(records).status.value_counts().items()},'groups':summary,
            'limitations':['History previously investigated; not independent out-of-sample.',
                'Past-only price proxies cannot reveal trader intent, true emotion or exchange fills.',
                'Coin universe chosen retrospectively, dates and source identity unverified.',
                'Controls uniform in day, not conditional on time of day or price regime.']}
    (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status_counts':result['status_counts'],'groups':summary},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
