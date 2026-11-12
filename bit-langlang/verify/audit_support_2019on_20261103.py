"""Reconstruct pivot-low state and events directly from 4h prices."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

DATA=Path('data/market/btc-2019on-usd-cross-20261102-01');BASE=Path('data/verify/market-prior28-2019on-20261103-01');SRC=Path('data/verify/market-support-2019on-20261103-01');OUT=Path('data/verify/market-support-2019on-independent-20261103-01')
def day(b,t):
    q=b.reindex(pd.date_range(t,periods=6,freq='4h'))
    if q[['open','high','low','close']].isna().any().any():return None
    return float(q.close.iloc[-1])
def main():
    if OUT.exists():raise FileExistsError(OUT)
    x=pd.read_csv(SRC/'asof_and_future.csv');b0=pd.read_csv(BASE/'asof.csv');joint=pd.read_csv(SRC/'joint.csv');flags={pd.Timestamp(z).floor('D') for z in json.loads((BASE/'summary.json').read_text())['quality_flags_utc']};states={};count=events=forward=0
    for name in ('bitstamp','bitfinex'):
        b=pd.read_csv(DATA/(name+'-4h.csv.gz'));b.index=pd.to_datetime(b.ts,unit='ms',utc=True);b=b[~b.index.floor('D').isin(flags)];base=b0[b0.source==name].set_index('as_of_utc')
        for r in x[x.source==name].itertuples():
            t=pd.Timestamp(r.as_of_utc);a=base.loc[r.as_of_utc];focus=a['long']=='UP' and a['big']=='UP' and a['small']=='DOWN';assert r.focus==focus
            if a.swing=='UNKNOWN' or pd.isna(a.l_new_price) or pd.isna(a.l_new_known):state='UNKNOWN';event='UNKNOWN'
            else:
                level=float(a.l_new_price);start=pd.Timestamp(a.l_new_known);cur=t-pd.Timedelta(days=1)
                if start>cur:state='WAIT_CONFIRM';event='UNKNOWN'
                else:
                    dates=pd.date_range(start,cur-pd.Timedelta(days=1),freq='D') if start<cur else [];past=[day(b,z) for z in dates];c=day(b,cur)
                    if c is None or any(z is None for z in past):state='UNKNOWN';event='UNKNOWN'
                    else:
                        prior='PRIOR_BROKEN' if any(z<level for z in past) else 'PRIOR_UNBROKEN';pos='BELOW' if c<level else 'ABOVE' if c>level else 'EQUAL';state=prior+'_'+pos;assert np.isclose(r.level,level) and r.known==start.isoformat() and np.isclose(r.close,c);event='NOT_APPLICABLE'
                        if pos=='BELOW' or prior=='PRIOR_UNBROKEN':
                            event='NO_RETURN' if pos=='BELOW' else 'NO_BREAK'
                            for i in range(7):
                                d=t+pd.Timedelta(days=i);v=day(b,d)
                                if v is None:event='UNKNOWN_INCOMPLETE';break
                                if (pos=='BELOW' and v>level) or (pos!='BELOW' and v<level):
                                    event='RETURN' if pos=='BELOW' else 'BREAK';assert r.event_time==(d+pd.Timedelta(days=1)).isoformat() and np.isclose(r.event_close,v);break
                            events+=1
            assert r.support_state==state and r.event_7==event,(name,t,state,event,r.support_state,r.event_7)
            for n in (7,28):
                p=day(b,t-pd.Timedelta(days=1));z=[day(b,t+pd.Timedelta(days=i)) for i in range(n)];complete=p is not None and all(v is not None for v in z);assert getattr(r,f'future_{n}_status')==('COMPLETE' if complete else 'UNKNOWN')
                if complete:assert np.isclose(getattr(r,f'future_{n}_pct'),(z[-1]/p-1)*100)
                forward+=1
            states[(name,r.as_of_utc)]=(state,focus);count+=1
    for r in joint.itertuples():
        a,fa=states[('bitstamp',r.as_of_utc)];b,fb=states[('bitfinex',r.as_of_utc)];expected='UNKNOWN' if a in ('UNKNOWN','WAIT_CONFIRM') or b in ('UNKNOWN','WAIT_CONFIRM') else 'JOINT_'+a if a==b else 'DISAGREE';assert r.joint==expected and r.focus_both==(fa and fb)
    files=[Path(__file__),SRC/'asof_and_future.csv',SRC/'joint.csv',BASE/'asof.csv',BASE/'summary.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','source_points':count,'support_event_checks':events,'forward_checks':forward,'joint_points':len(joint),'scope':'raw 4h price support and events, based on independently audited prior pivots; not phase truth','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',count,events,forward,len(joint))
if __name__=='__main__':main()
