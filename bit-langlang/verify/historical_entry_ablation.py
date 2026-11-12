"""Post-hoc gate ablation; price proxies are not recorded trader orders."""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .forward_scan import read_raw_candles
from .historical_pullback_candidate import COINS, BEGIN, END, PANEL, pullback_pattern, sha
from .historical_entry_replica import eligible_match
from .historical_signal_dedup import controls

SOURCE=Path('data/verify/historical-pullback-candidate-20261030-01')
DEFINITION=Path('docs/历史入场-逐笔门槛消融-定义-20261030.md')
GATES=('regime','rank','pattern','midpoint','target','risk')

def run(out):
    idx=pd.date_range(BEGIN,END-pd.Timedelta(minutes=5),freq='5min'); data={}; daily={}
    files=[PANEL,DEFINITION,Path(__file__),SOURCE/'pullback_delayed_candidate-signal-times.json',SOURCE/'pullback_delayed_candidate-rows.csv']
    files += [Path('data/market')/f'{c}USDT_5m.csv.gz' for c in sorted(COINS)]
    hashes={str(p):sha(p) for p in files}
    for coin in sorted(COINS):
        f=read_raw_candles(coin+'USDT').set_index('ts')
        if f.index.has_duplicates or not f.index.is_monotonic_increasing: raise ValueError('invalid market index')
        f=f.reindex(idx); data[coin]=f
        daily[coin]=f.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
    bd=daily['BTC']; regime=(bd.close>(bd.high.rolling(20,min_periods=20).max()+bd.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False)
    br=bd.close.pct_change(7,fill_method=None); scores={}; warm={}; targets={}
    for c,d in daily.items():
        warm[c]=d.open.eq(288).shift(1,fill_value=False).rolling(30,min_periods=30).sum().eq(30)
        scores[c]=(d.close.pct_change(7,fill_method=None)-br).shift(1).where(warm[c])
        targets[c]=d.high.rolling(20,min_periods=20).max().shift(1)
    scores=pd.DataFrame(scores).where(regime,axis=0); ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first')
    # Rank itself must be available even when regime is removed; otherwise the ablation is not independent.
    raw_scores={c:(d.close.pct_change(7,fill_method=None)-br).shift(1).where(warm[c]) for c,d in daily.items()}
    raw_scores=pd.DataFrame(raw_scores); raw_ranks=raw_scores.where(raw_scores>0).rank(axis=1,ascending=False,method='first')
    old=json.loads((SOURCE/'pullback_delayed_candidate-signal-times.json').read_text()); masks={}; signals={k:{} for k in ('base',)+GATES+('target_and_risk',)}
    for c in sorted(COINS):
        f=data[c]; days=idx.floor('D'); tar=targets[c].reindex(days).to_numpy(); entry=f.open.shift(-2).to_numpy()*(1+.0002); risk=entry-f.low.to_numpy()
        hi=f.high.shift(1).rolling(48,min_periods=48).max(); lo=f.low.shift(1).rolling(48,min_periods=48).min()
        gates={'regime':regime.reindex(days).to_numpy(dtype=bool),
               'rank':np.ones(len(idx),dtype=bool) if c=='BTC' else (raw_ranks[c].reindex(days).to_numpy()<=2),
               'pattern':pullback_pattern(f).to_numpy(dtype=bool), 'midpoint':(f.close>=(hi+lo)/2).to_numpy(dtype=bool),
               'target':tar>f.close.to_numpy(), 'risk':np.isfinite(entry)&(risk>0)&((tar-entry)>=2*risk)}
        valid=warm[c].reindex(days).to_numpy(dtype=bool)&(idx+pd.Timedelta(minutes=15)<END)
        masks[c]={**gates, 'valid':valid}
        for variant in signals:
            drop=set() if variant=='base' else ({'target','risk'} if variant=='target_and_risk' else {variant})
            mask=valid.copy()
            for name in GATES:
                if name not in drop: mask &= gates[name]
            signals[variant][c]=(idx[mask]+pd.Timedelta(minutes=15)).asi8
        if not np.array_equal(signals['base'][c],np.asarray(old[c],dtype=np.int64)): raise ValueError(f'base differs for {c}')
    source=pd.read_csv(SOURCE/'pullback_delayed_candidate-rows.csv');panel=pd.read_csv(PANEL)
    if len(source)!=len(panel):raise ValueError('panel mismatch')
    market_index={c: f.index[f.open.notna()] for c,f in data.items()}
    records=[]; aggregates={k:{'signals':sum(len(v) for v in per.values()),'matched':0,'control_expected':0.0} for k,per in signals.items()}
    for i,(s,p) in enumerate(zip(source.itertuples(index=False),panel.itertuples(index=False))):
        if s.coin!=p.coin or s.side!=p.side: raise ValueError('row identity mismatch')
        if s.status not in ('SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'):continue
        t=pd.to_datetime(s.entry_assumed_utc,utc=True); c=s.coin
        # T is bar opening; execution at T+15. Inclusive 15m window gives up to four 5m grid points.
        end=(t-pd.Timedelta(minutes=15)).floor('5min'); start=t-pd.Timedelta(minutes=30)
        positions=idx.get_indexer(pd.date_range(start.ceil('5min'),end,freq='5min'))
        positions=positions[positions>=0]; row={'panel_row':i,'coin':c,'entry_assumed_utc':t.isoformat(),'stop_order':'UNKNOWN_NOT_RECORDED','target_order':'UNKNOWN_NOT_RECORDED'}
        for g in GATES: row[g+'_any_in_window']=bool((masks[c][g][positions]&masks[c]['valid'][positions]).any())
        cumulative=masks[c]['valid'][positions].copy()
        for g in GATES:
            cumulative &= masks[c][g][positions];row['after_'+g]=bool(cumulative.any())
        for variant,per in signals.items():
            match=eligible_match(per[c],t.value);row['match_'+variant]=match is not None
            control=controls(t,c,market_index[c],per[c]); aggregates[variant]['matched']+=int(match is not None)
            if control['expected'] is not None:aggregates[variant]['control_expected']+=control['expected']
        if row['match_base']!=(s.status=='SIGNAL_OVERLAP'):raise ValueError('base row mismatch')
        records.append(row)
    if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('input changed')
    df=pd.DataFrame(records); sequential={g:int(df['after_'+g].sum()) for g in GATES}
    result={'status':'POST_HOC_ABLATION_NOT_REPLICATION','rows':len(df),'variants':aggregates,'sequential_window_pass':sequential,
            'individual_any_window':{g:int(df[g+'_any_in_window'].sum()) for g in GATES},'input_sha256':hashes,
            'limitations':['Retrospective ten coin subset; venue and timezone uncertain.','Signals are not executed trades or profits.',
            'Risk and target are model proxies, not recorded stops or take profits.','Same-day nearby controls are descriptive and do not control structure or clustering.']}
    out.mkdir(parents=True,exist_ok=False);df.to_csv(out/'rows.csv',index=False);(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--outdir',required=True);args=ap.parse_args();out=Path(args.outdir)
    if out.exists():raise FileExistsError('refusing overwrite')
    run(out)
