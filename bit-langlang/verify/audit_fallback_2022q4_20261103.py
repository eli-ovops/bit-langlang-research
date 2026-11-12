"""Independent 4h reconstruction of the earlier snapshot and fallback state."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

DATA=Path('data/market/btc-2022q4-usd-cross-20261103-01');BASE=Path('data/verify/market-prior28-2022q4-20261103-01');OLD=Path('data/verify/market-support-2022q4-20261103-01');SRC=Path('data/verify/market-support-fallback-2022q4-20261103-01');OUT=Path('data/verify/market-support-fallback-2022q4-independent-20261103-01')
def day(b,t):
    x=b.reindex(pd.date_range(t,periods=6,freq='4h'))
    if x[['open','high','low','close']].isna().any().any():return None
    return {'high':float(x.high.max()),'low':float(x.low.min()),'close':float(x.close.iloc[-1])}
def snapshot_low(b,t):
    snap=t-pd.Timedelta(days=1);days=[day(b,snap-pd.Timedelta(days=56-i)) for i in range(56)]
    if any(z is None for z in days):return None
    highs=[];lows=[]
    for i in range(2,54):
        center=days[i];others=days[i-2:i]+days[i+1:i+3];hi=all(center['high']>q['high'] for q in others);lo=all(center['low']<q['low'] for q in others)
        if hi and not lo:highs.append(i)
        if lo and not hi:lows.append(i)
    if len(highs)<2 or len(lows)<2:return None
    i=lows[-1];return days[i]['low'],snap-pd.Timedelta(days=56-i)+pd.Timedelta(days=3)
def main():
    if OUT.exists():raise FileExistsError(OUT)
    x=pd.read_csv(SRC/'asof_and_future.csv');old=pd.read_csv(OLD/'asof_and_future.csv');j=pd.read_csv(SRC/'joint.csv');flags={pd.Timestamp(s).floor('D') for s in json.loads((BASE/'summary.json').read_text())['quality_flags_utc']};states={};n=events=fallbacks=0
    for name in ('bitstamp','bitfinex'):
        b=pd.read_csv(DATA/(name+'-4h.csv.gz'));b.index=pd.to_datetime(b.ts,unit='ms',utc=True);b=b[~b.index.floor('D').isin(flags)];ref=old[old.source==name].set_index('as_of_utc')
        for r in x[x.source==name].itertuples():
            t=pd.Timestamp(r.as_of_utc);oldrow=ref.loc[r.as_of_utc];assert r.old_state==oldrow.support_state
            if r.old_state!='WAIT_CONFIRM':
                state=r.old_state;method='UNCHANGED';assert r.event_7==oldrow.event_7
                if pd.notna(oldrow.level):assert np.isclose(r.new_level,oldrow.level) and r.new_known==oldrow.known
            else:
                q=snapshot_low(b,t);state='UNKNOWN';method='FALLBACK_UNAVAILABLE'
                if q is not None:
                    level,known=q;cur=t-pd.Timedelta(days=1);prior=[day(b,z) for z in pd.date_range(known,cur-pd.Timedelta(days=1),freq='D')] if known<cur else [];current=day(b,cur)
                    if current is not None and all(p is not None for p in prior):
                        hist='PRIOR_BROKEN' if any(p['close']<level for p in prior) else 'PRIOR_UNBROKEN';v=current['close'];position='BELOW' if v<level else 'ABOVE' if v>level else 'EQUAL';state=hist+'_'+position;method='FALLBACK_USED';assert np.isclose(r.new_level,level) and r.new_known==known.isoformat() and np.isclose(r.close,v)
                        event='NOT_APPLICABLE'
                        if position=='BELOW' or hist=='PRIOR_UNBROKEN':
                            event='NO_RETURN' if position=='BELOW' else 'NO_BREAK'
                            for i in range(7):
                                z=t+pd.Timedelta(days=i);d=day(b,z)
                                if d is None:event='UNKNOWN_INCOMPLETE';break
                                c=d['close']
                                if (position=='BELOW' and c>level) or (position!='BELOW' and c<level):
                                    event='RETURN' if position=='BELOW' else 'BREAK';assert r.event_time==(z+pd.Timedelta(days=1)).isoformat() and np.isclose(r.event_close,c);break
                            events+=1
                        assert event==r.event_7
                if method=='FALLBACK_UNAVAILABLE':assert r.event_7=='UNKNOWN'
                fallbacks+=1
            assert (r.new_state,r.method)==(state,method),(name,t,state,method,r.new_state,r.method)
            states[(name,r.as_of_utc)]=state;n+=1
    for r in j.itertuples():
        a=states[('bitstamp',r.as_of_utc)];b=states[('bitfinex',r.as_of_utc)];q='UNKNOWN' if a in ('UNKNOWN','WAIT_CONFIRM') or b in ('UNKNOWN','WAIT_CONFIRM') else 'JOINT_'+a if a==b else 'DISAGREE';assert r.joint==q
    files=[Path(__file__),SRC/'asof_and_future.csv',SRC/'joint.csv',OLD/'asof_and_future.csv',BASE/'summary.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','source_points':n,'fallback_points':fallbacks,'fallback_event_checks':events,'joint_points':len(j),'scope':'raw 4h independent earlier pivot snapshot, prior break and events; unchanged old state relies on independently audited baseline','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',n,fallbacks,events,len(j))
if __name__=='__main__':main()
