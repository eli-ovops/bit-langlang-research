"""Retrospective joint gate removal and causal dedup; no platform orders."""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .forward_scan import read_raw_candles
from .historical_pullback_candidate import COINS, BEGIN, END, PANEL, pullback_pattern, sha
from .historical_entry_replica import eligible_match
from .historical_signal_dedup import deduplicate, controls

SOURCE=Path('data/verify/historical-pullback-candidate-20261030-01')
PREV=Path('data/verify/historical-entry-ablation-20261030-02')
DEDUP=Path('data/verify/historical-signal-dedup-20261030-01')
DEFINITION=Path('docs/历史入场-去目标代理与去重联合定义-20261030.md')

def run(out):
    idx=pd.date_range(BEGIN,END-pd.Timedelta(minutes=5),freq='5min');frames={};daily={}
    files=[PANEL,DEFINITION,Path(__file__),SOURCE/'pullback_delayed_candidate-signal-times.json',SOURCE/'pullback_delayed_candidate-rows.csv',PREV/'rows.csv',PREV/'summary.json',DEDUP/'deduplicated-signals.json']
    files += [Path('data/market')/f'{c}USDT_5m.csv.gz' for c in sorted(COINS)]
    hashes={str(p):sha(p) for p in files}
    for c in sorted(COINS):
        f=read_raw_candles(c+'USDT').set_index('ts')
        if f.index.has_duplicates or not f.index.is_monotonic_increasing:raise ValueError('invalid index')
        f=f.reindex(idx);frames[c]=f;daily[c]=f.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
    btc=daily['BTC'];regime=(btc.close>(btc.high.rolling(20,min_periods=20).max()+btc.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False)
    br=btc.close.pct_change(7,fill_method=None);scores={};warm={};targets={}
    for c,d in daily.items():
        warm[c]=d.open.eq(288).shift(1,fill_value=False).rolling(30,min_periods=30).sum().eq(30)
        scores[c]=(d.close.pct_change(7,fill_method=None)-br).shift(1).where(warm[c]);targets[c]=d.high.rolling(20,min_periods=20).max().shift(1)
    scores=pd.DataFrame(scores).where(regime,axis=0);ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first')
    signals={v:{} for v in ('old','old_dedup','revised','revised_dedup')};old=json.loads((SOURCE/'pullback_delayed_candidate-signal-times.json').read_text());prior_dedup=json.loads((DEDUP/'deduplicated-signals.json').read_text())
    for c in sorted(COINS):
        f=frames[c];days=idx.floor('D'); hi=f.high.shift(1).rolling(48,min_periods=48).max();lo=f.low.shift(1).rolling(48,min_periods=48).min()
        bg=(regime & warm[c]).reindex(days).to_numpy() if c=='BTC' else (ranks[c].reindex(days).to_numpy()<=2)
        mask=bg & warm[c].reindex(days).to_numpy(dtype=bool) & pullback_pattern(f).to_numpy(dtype=bool) & (f.close>=(hi+lo)/2).to_numpy(dtype=bool) & (idx+pd.Timedelta(minutes=15)<END)
        target=targets[c].reindex(days).to_numpy();entry=f.open.shift(-2).to_numpy()*(1+.0002);risk=entry-f.low.to_numpy()
        old_mask=mask & (target>f.close.to_numpy()) & np.isfinite(entry) & (risk>0) & ((target-entry)>=2*risk)
        for v,m in [('old',old_mask),('revised',mask)]:
            vals=(idx[m]+pd.Timedelta(minutes=15)).asi8;signals[v][c]=vals;signals[v+'_dedup'][c]=np.asarray(deduplicate(vals),dtype=np.int64)
        if not np.array_equal(signals['old'][c],np.asarray(old[c],dtype=np.int64)):raise ValueError('old signals differ '+c)
        if not np.array_equal(signals['old_dedup'][c],np.asarray(prior_dedup[c],dtype=np.int64)):raise ValueError('dedup signals differ '+c)
    prev=json.loads((PREV/'summary.json').read_text());
    if sum(len(x) for x in signals['revised'].values())!=prev['variants']['target_and_risk']['signals']:raise ValueError('revised count differs')
    prev_rows=pd.read_csv(PREV/'rows.csv').set_index('panel_row');source=pd.read_csv(SOURCE/'pullback_delayed_candidate-rows.csv');panel=pd.read_csv(PANEL)
    if len(source)!=len(panel):raise ValueError('row count mismatch')
    indices={c:f.index[f.open.notna()] for c,f in frames.items()};rows=[]
    for i,(s,p) in enumerate(zip(source.itertuples(index=False),panel.itertuples(index=False))):
        if s.coin!=p.coin or s.side!=p.side:raise ValueError('identity mismatch')
        if s.status not in ('SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'):continue
        c=s.coin;t=pd.to_datetime(s.entry_assumed_utc,utc=True);row={'panel_row':i,'coin':c,'entry_original':p.entry_time,'entry_assumed_utc':t.isoformat(),'entry_price':p.entry,'price_inside_binance_bar':bool(s.price_inside_bar),'stop_order':'UNKNOWN_NOT_RECORDED','target_order':'UNKNOWN_NOT_RECORDED'}
        for v,per in signals.items():
            m=eligible_match(per[c],t.value);ct=controls(t,c,indices[c],per[c]);row[v+'_match']=m is not None;row[v+'_time']=pd.Timestamp(m,tz='UTC').isoformat() if m is not None else None;row[v+'_lag_seconds']=(t.value-m)/1e9 if m is not None else None;row[v+'_control_expected']=ct['expected']
        if row['old_match']!=(s.status=='SIGNAL_OVERLAP') or row['revised_match']!=bool(prev_rows.loc[i,'match_target_and_risk']):raise ValueError('row differs')
        rows.append(row)
    df=pd.DataFrame(rows);df['year']=pd.to_datetime(df.entry_assumed_utc,utc=True).dt.year
    groups={'all':df,'inside_binance_bar':df[df.price_inside_binance_bar],'outside_binance_bar':df[~df.price_inside_binance_bar], '2022_2023':df[df.year<=2023],'2024':df[df.year==2024]}
    groups.update({'coin_'+c:g for c,g in df.groupby('coin')})
    stats={}
    for name,group in groups.items():
        stats[name]={'rows':len(group)}
        for v,per in signals.items():
            selected=group[group[v+'_match']];stats[name][v]={'matches':len(selected),'unique_signals':len(selected[['coin',v+'_time']].drop_duplicates()),'control_expected':float(group[v+'_control_expected'].sum())}
    result={'status':'POST_HOC_CANDIDATE_NOT_REPLICATION','signal_counts':{v:sum(len(x) for x in per.values()) for v,per in signals.items()},'groups':stats,
            'transitions':{'revised_lost_to_dedup':int((df.revised_match&~df.revised_dedup_match).sum()),'revised_new_from_dedup':int((~df.revised_match&df.revised_dedup_match).sum()),'old_to_revised_dedup_gained':int((~df.old_match&df.revised_dedup_match).sum()),'old_to_revised_dedup_lost':int((df.old_match&~df.revised_dedup_match).sum())},'input_sha256':hashes,
            'limitations':['Historical sample reused; not independent or predictive evidence.','Positions are aggregated, execution and account identity are unverified.','Unmatched signals cannot be labeled false or losing trades.','Same-source bar inclusion is not venue/time certification.','Controls are descriptive, not significance or profit.','Actual stop/target orders unknown.']}
    if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('input changed')
    out.mkdir(parents=True,exist_ok=False);df.to_csv(out/'rows.csv',index=False);(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(out/'signals.json').write_text(json.dumps({v:{c:[int(t) for t in a] for c,a in per.items()} for v,per in signals.items()})+'\n')
    print(json.dumps({'signal_counts':result['signal_counts'],'all':stats['all'],'inside':stats['inside_binance_bar'],'outside':stats['outside_binance_bar'],'transitions':result['transitions']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);out=Path(p.parse_args().outdir)
    if out.exists():raise FileExistsError('refusing overwrite')
    run(out)
