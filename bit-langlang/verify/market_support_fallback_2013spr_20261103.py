"""Use only the pivot snapshot known before the compared day, when newest was too late."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2016_pivot_20261102 import pivots
from verify.market_support_2019on_20261103 import support,first_break
from verify.market_2023_return_28d_20261102 import returned

DATA=Path('data/market/btc-2013spr-usd-cross-20261102-01');BASE=Path('data/verify/market-prior28-2013spr-20261103-01');OLD=Path('data/verify/market-support-2013spr-20261103-01');OUT=Path('data/verify/market-support-fallback-2013spr-20261103-01');SPEC=Path('docs/双所完整支撑对照-2013春事前筛查-20261103.md')
from verify.market_support_fallback_2014sp_20261103 import fallback

def main():
    if OUT.exists():raise FileExistsError(OUT)
    base=pd.read_csv(BASE/'asof.csv');previous=pd.read_csv(OLD/'asof_and_future.csv');flags=[pd.Timestamp(x).floor('D') for x in json.loads((BASE/'summary.json').read_text())['quality_flags_utc']];rows=[]
    for name in ('bitstamp','bitfinex'):
        d,_=read(DATA/(name+'-4h.csv.gz'));d.loc[d.index.isin(flags),'good']=False;prev=previous[previous.source==name].set_index('as_of_utc')
        for r in base[base.source==name].to_dict('records'):
            t=pd.Timestamp(r['as_of_utc']);old=support(d,t,r);assert old['support_state']==prev.loc[r['as_of_utc'],'support_state'];new,method=fallback(d,t,r);state=new['support_state'];q={'source':name,'as_of_utc':r['as_of_utc'],'focus':bool(r['long']=='UP' and r['big']=='UP' and r['small']=='DOWN'),'long':r['long'],'big':r['big'],'small':r['small'],'range_state':r['range_state'],'old_state':old['support_state'],'old_level':old.get('level'),'old_known':old.get('known'),'new_state':state,'method':method,'new_level':new.get('level'),'new_known':new.get('known'),'close':new.get('close'),'snapshot_cutoff':(t-pd.Timedelta(days=1)).isoformat() if method!='UNCHANGED' else None,'snapshot_start':(t-pd.Timedelta(days=57)).isoformat() if method!='UNCHANGED' else None,'phase':'UNKNOWN','event_7':'UNKNOWN' if state in ('UNKNOWN','WAIT_CONFIRM') else 'NOT_APPLICABLE','event_time':None,'event_close':None,'future_7_status':prev.loc[r['as_of_utc'],'future_7_status'],'future_7_pct':prev.loc[r['as_of_utc'],'future_7_pct'],'future_28_status':prev.loc[r['as_of_utc'],'future_28_status'],'future_28_pct':prev.loc[r['as_of_utc'],'future_28_pct']}
            if state not in ('UNKNOWN','WAIT_CONFIRM'):
                if new['position']=='BELOW':st,at,p=returned(d,t,'LOWER_BREAK',new['level'],7);q.update(event_7=st,event_time=at,event_close=p)
                elif new['history']=='PRIOR_UNBROKEN':st,at,p=first_break(d,t,new['level']);q.update(event_7=st,event_time=at,event_close=p)
            rows.append(q)
    a=pd.DataFrame(rows);pairs=[]
    for t,g in a.groupby('as_of_utc',sort=True):
        assert len(g)==2;u,v=g.sort_values('source').new_state.tolist();joint='UNKNOWN' if u in ('UNKNOWN','WAIT_CONFIRM') or v in ('UNKNOWN','WAIT_CONFIRM') else 'JOINT_'+u if u==v else 'DISAGREE';pairs.append({'as_of_utc':t,'focus_both':bool(g.focus.all()),'joint':joint})
    j=pd.DataFrame(pairs);files=[Path(__file__),Path('verify/market_support_fallback_2014sp_20261103.py'),Path('verify/market_support_2019on_20261103.py'),Path('verify/market_2016_pivot_20261102.py'),SPEC,BASE/'asof.csv',BASE/'summary.json',OLD/'asof_and_future.csv',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];OUT.mkdir();a.to_csv(OUT/'asof_and_future.csv',index=False);j.to_csv(OUT/'joint.csv',index=False);summary={'points':len(j),'source_points':len(a),'methods':a.method.value_counts().to_dict(),'old_joint':json.loads((OLD/'summary.json').read_text())['joint'],'new_joint':j.joint.value_counts().to_dict(),'focus_both':int(j.focus_both.sum()),'per_source':{n:{'old':g.old_state.value_counts().to_dict(),'new':g.new_state.value_counts().to_dict(),'methods':g.method.value_counts().to_dict()} for n,g in a.groupby('source')},'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'limits':['Fallback is research proxy not phase truth or evidence of profitability.','No independent human labels.']};(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ('points','source_points','methods','old_joint','new_joint','focus_both','per_source')},indent=2))
if __name__=='__main__':main()
