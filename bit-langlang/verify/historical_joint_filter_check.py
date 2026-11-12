"""Independent direct checks of stored retrospective signal and match outputs."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .forward_scan import read_raw_candles
from .historical_pullback_candidate import COINS, BEGIN, END, PANEL, sha
from .historical_entry_replica import eligible_match

BASE=Path('data/verify/historical-joint-filter-20261030-01')

def main():
    report=json.loads((BASE/'summary.json').read_text());data=json.loads((BASE/'signals.json').read_text());rows=pd.read_csv(BASE/'rows.csv');panel=pd.read_csv(PANEL)
    for v in data:
        assert sum(len(x) for x in data[v].values())==report['signal_counts'][v]
    # Independently rebuild the greedy cooldown for all timestamps.
    for c in COINS:
        for source,target in [('old','old_dedup'),('revised','revised_dedup')]:
            kept=[]
            for t in data[source][c]:
                if not kept or t-kept[-1]>=30*60*10**9:kept.append(t)
            assert kept==data[target][c]
    for r in rows.itertuples(index=False):
        p=panel.iloc[r.panel_row];assert p.coin==r.coin and p.entry_time==r.entry_original
        t=pd.Timestamp(r.entry_assumed_utc).value
        for v in data:
            found=eligible_match(data[v][r.coin],t)
            assert bool(getattr(r,v+'_match'))==(found is not None)
            if found is not None:assert pd.Timestamp(getattr(r,v+'_time')).value==found
    rng=np.random.default_rng(20261030);all_times=[(c,t) for c,a in data['revised'].items() for t in a]
    sampled=[all_times[i] for i in rng.choice(len(all_times),size=30,replace=False)]
    frames={c:read_raw_candles(c+'USDT').set_index('ts') for c in COINS}
    daily={c:f.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'}) for c,f in frames.items()}
    for c,raw in sampled:
        execution=pd.Timestamp(raw,tz='UTC');at=execution-pd.Timedelta(minutes=15);day=at.floor('D');f=frames[c];bar=f.loc[at];prev=f.loc[at-pd.Timedelta(minutes=5)]
        btc=daily['BTC'].loc[day-pd.Timedelta(days=20):day-pd.Timedelta(days=1)]
        assert len(btc)==20 and btc.close.iloc[-1]>(btc.high.max()+btc.low.min())/2
        prior30=daily[c].loc[day-pd.Timedelta(days=30):day-pd.Timedelta(days=1)];assert len(prior30)==30 and prior30.open.eq(288).all()
        if c!='BTC':
            b7=daily['BTC'].loc[day-pd.Timedelta(days=1),'close']/daily['BTC'].loc[day-pd.Timedelta(days=8),'close']-1
            scores={}
            for coin,d in daily.items():
                w=d.loc[day-pd.Timedelta(days=30):day-pd.Timedelta(days=1)]
                if len(w)==30 and w.open.eq(288).all():scores[coin]=d.loc[day-pd.Timedelta(days=1),'close']/d.loc[day-pd.Timedelta(days=8),'close']-1-b7
            ordered=sorted(((-score,coin) for coin,score in scores.items() if score>0))
            assert c in [coin for _,coin in ordered[:2]]
        p20=f.loc[at-pd.Timedelta(minutes=100):at-pd.Timedelta(minutes=5)];p48=f.loc[at-pd.Timedelta(minutes=240):at-pd.Timedelta(minutes=5)]
        assert len(p20)==20 and len(p48)==48
        assert bar.close>bar.open and prev.close<prev.open and bar.close>prev.close and bar.close>=(p20.high.max()+p20.low.min())/2
        assert bar.close>=(p48.high.max()+p48.low.min())/2
    checks={'source_sha256':{str(p):sha(p) for p in [BASE/'summary.json',BASE/'rows.csv',BASE/'signals.json',Path(__file__)]},'all_signals_cooldown_verified':True,'all_rows_times_verified':len(rows),'direct_raw_revised_signal_checks':len(sampled),'same_market_source_not_independent_venue':True}
    out=BASE/'independent-check.json'
    if out.exists():raise FileExistsError('refusing overwrite')
    out.write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
