"""As-of confirmed pivot-low history, not a season or a trading rule."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2023_return_28d_20261102 import returned

DATA=Path('data/market/btc-2020q3native-usd-cross-20261103-01')
BASE=Path('data/verify/market-prior28-2020q3native-20261103-01')
OUT=Path('data/verify/market-support-2020q3native-20261103-01')
SPEC=Path('docs/2020三季度-Bitfinex原生四小时事后敏感性定义-20261103.md')

from verify.market_support_2019on_20261103 import support,first_break

def main():
    if OUT.exists():raise FileExistsError(OUT)
    src=pd.read_csv(BASE/'asof.csv');flags=[pd.Timestamp(x).floor('D') for x in json.loads((BASE/'summary.json').read_text())['quality_flags_utc']];rows=[]
    for name in ('bitstamp','bitfinex'):
        d,_=read(DATA/(name+'-4h.csv.gz'));d.loc[d.index.isin(flags),'good']=False
        for r in src[src.source==name].to_dict('records'):
            t=pd.Timestamp(r['as_of_utc']);s=support(d,t,r);state=s['support_state'];z={'source':name,'as_of_utc':r['as_of_utc'],'weekly':r['weekly'],'focus':r['long']=='UP' and r['big']=='UP' and r['small']=='DOWN','long':r['long'],'big':r['big'],'small':r['small'],'spring':r['spring_watch'],'autumn':r['autumn_watch'],'range_state':r['range_state'],**s,'phase':'UNKNOWN','event_7':'UNKNOWN' if state in ('UNKNOWN','WAIT_CONFIRM') else 'NOT_APPLICABLE','event_time':None,'event_close':None}
            if state not in ('UNKNOWN','WAIT_CONFIRM'):
                if s['position']=='BELOW':st,at,p=returned(d,t,'LOWER_BREAK',s['level'],7);z.update(event_7=st,event_time=at,event_close=p)
                elif s['history']=='PRIOR_UNBROKEN':st,at,p=first_break(d,t,s['level']);z.update(event_7=st,event_time=at,event_close=p)
            for n in (7,28):
                prev=t-pd.Timedelta(days=1);w=d[(d.index>=t)&(d.index<t+pd.Timedelta(days=n))];ok=prev in d.index and d.loc[prev,'good'] and len(w)==n and w.good.all()
                z[f'future_{n}_status']='COMPLETE' if ok else 'UNKNOWN';z[f'future_{n}_pct']=(float(w.close.iloc[-1])/float(d.loc[prev,'close'])-1)*100 if ok else None
            rows.append(z)
    a=pd.DataFrame(rows);j=[]
    for t,g in a.groupby('as_of_utc',sort=True):
        assert len(g)==2;u,v=g.sort_values('source').support_state.tolist();joint='UNKNOWN' if u in ('UNKNOWN','WAIT_CONFIRM') or v in ('UNKNOWN','WAIT_CONFIRM') else 'JOINT_'+u if u==v else 'DISAGREE';j.append({'as_of_utc':t,'focus_both':bool(g.focus.all()),'focus_any':bool(g.focus.any()),'joint':joint})
    j=pd.DataFrame(j);OUT.mkdir();a.to_csv(OUT/'asof_and_future.csv',index=False);j.to_csv(OUT/'joint.csv',index=False)
    paths=[Path(__file__),Path('verify/market_support_2019on_20261103.py'),SPEC,BASE/'asof.csv',BASE/'summary.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];summary={'source_points':len(a),'joint_points':len(j),'focus_both':int(j.focus_both.sum()),'joint':j.joint.value_counts().to_dict(),'focus_joint':j[j.focus_both].joint.value_counts().to_dict(),'per_source':{n:{'states':g.support_state.value_counts().to_dict(),'focus':int(g.focus.sum()),'future_28':g.future_28_status.value_counts().to_dict()} for n,g in a.groupby('source')},'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'limitations':['Price facts, not independent human phase labels.','Overlapping outcomes are not independent probabilities.']};(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ('source_points','joint_points','focus_both','joint','focus_joint','per_source')},indent=2))
if __name__=='__main__':main()
