"""Completed-day close versus 28 preceding days; research facts only."""
from pathlib import Path
import hashlib, json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2016_pivot_20261102 import pivots
from verify.market_2017_pivot_guard_20261102 import guard
from verify.market_2023_return_28d_20261102 import returned

DATA=Path('data/market/btc-2014q1-usd-cross-20261102-01')
OUT=Path('data/verify/market-prior28-2014q1-20261103-02')
SPEC=Path('docs/排除当前日大区间-2014一季度事前定义-20261103.md')

def classify(d,t):
    if t.hour or t.minute or t.second or t.microsecond or t.nanosecond: raise ValueError('decision must be UTC midnight')
    prior=d.loc[(d.index>=t-pd.Timedelta(days=29))&(d.index<t-pd.Timedelta(days=1))]
    current=d.loc[(d.index>=t-pd.Timedelta(days=1))&(d.index<t)]
    if len(prior)!=28 or not prior.good.all() or len(current)!=1 or not current.good.all(): return {'range_state':'UNKNOWN'}
    hi=float(prior.high.max());lo=float(prior.low.min());close=float(current.close.iloc[0])
    if hi<=lo: return {'range_state':'UNKNOWN'}
    state='ABOVE' if close>hi else 'BELOW' if close<lo else 'INSIDE'
    return {'range_state':state,'ref_high':hi,'ref_low':lo,'current_close':close,'reference_start':(t-pd.Timedelta(days=29)).isoformat(),'reference_end_exclusive':(t-pd.Timedelta(days=1)).isoformat(),'current_day':(t-pd.Timedelta(days=1)).isoformat()}

def combine(a,b):
    if 'UNKNOWN' in (a,b): return 'UNKNOWN'
    return 'JOINT_'+a if a==b else 'DISAGREE'

def main():
    if OUT.exists():raise FileExistsError(OUT)
    paths={n:DATA/(n+'-4h.csv.gz') for n in ('bitstamp','bitfinex')}
    a=pd.read_csv(paths['bitstamp']);b=pd.read_csv(paths['bitfinex']);m=a.merge(b,on='ts',suffixes=('_a','_b'))
    bad=pd.Series(False,index=m.index)
    for col in ('high','low'):
        ratio=m[col+'_b']/m[col+'_a'];bad|=(ratio>1.1)|(ratio<0.9)
    flags=pd.to_datetime(m.loc[bad,'ts'],unit='ms',utc=True)
    times=pd.date_range('2014-01-06','2014-03-31',freq='D',tz='UTC');assert len(times)==85
    rows=[]
    for name,path in paths.items():
        d,h=read(path)
        for flag in flags:
            if flag in h.index:h.loc[flag,'good']=False
            if flag.floor('D') in d.index:d.loc[flag.floor('D'),'good']=False
        for t in times:
            x=evaluate_extended(d,h,t);p=pivots(d,t);c=classify(d,t);r={'source':name,'as_of_utc':t.isoformat(),'weekly':t.weekday()==0,'long':x['long_relation'],'big':x['big_relation'],'small':x['small_relation'],'spring_watch':x['spring_watch'],'autumn_watch':x['autumn_watch'],**p,**c,'season_truth':'UNKNOWN'}
            r.update(guard(d,t,r))
            s=c['range_state'];r.update(return_7='UNKNOWN' if s=='UNKNOWN' else 'NOT_APPLICABLE',return_time=None,return_close=None)
            if s in ('ABOVE','BELOW'):
                st,at,price=returned(d,t,'UPPER_BREAK' if s=='ABOVE' else 'LOWER_BREAK',c['ref_high'] if s=='ABOVE' else c['ref_low'],7);r.update(return_7=st,return_time=at,return_close=price)
            rows.append(r)
    x=pd.DataFrame(rows);A=x[x.source=='bitstamp'].set_index('as_of_utc');B=x[x.source=='bitfinex'].set_index('as_of_utc');assert A.index.equals(B.index)
    joint=pd.DataFrame([{'as_of_utc':t,'weekly':bool(A.loc[t,'weekly']),'bitstamp_state':A.loc[t,'range_state'],'bitfinex_state':B.loc[t,'range_state'],'joint':combine(A.loc[t,'range_state'],B.loc[t,'range_state'])} for t in A.index])
    files=[SPEC,Path(__file__),DATA/'manifest.json',*paths.values(),Path('verify/market_2020_cross_20261102.py'),Path('verify/market_2016_pivot_20261102.py'),Path('verify/market_2023_return_28d_20261102.py')]
    OUT.mkdir();x.to_csv(OUT/'asof.csv',index=False);joint.to_csv(OUT/'joint.csv',index=False)
    summary={'quality_flags_utc':[z.isoformat() for z in flags],'points':len(joint),'joint':joint.joint.value_counts().to_dict(),'weekly_joint':joint[joint.weekly].joint.value_counts().to_dict(),'sources':{n:{'range':g.range_state.value_counts().to_dict(),'return':g.return_7.value_counts().to_dict()} for n,g in x.groupby('source')},'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'limits':['No independent human stage reference.','Overlapping events are not independent probabilities.','Results are price facts, not trading rules.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ('quality_flags_utc','points','joint','weekly_joint','sources')},indent=2))
if __name__=='__main__':main()
