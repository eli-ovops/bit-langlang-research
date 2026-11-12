"""Research-only, as-of price/known-age sensitivity; no trade actions."""
from pathlib import Path
import hashlib,json,math,sys
from decimal import Decimal
import pandas as pd

def gate(state,level,close,known,when):
    if state in ('UNKNOWN','WAIT_CONFIRM') or pd.isna(level) or pd.isna(close) or pd.isna(known):
        return {'signed_distance':None,'absolute_distance':None,'known_age_days':None,'D10':'UNKNOWN_INPUT','A28':'UNKNOWN_INPUT','BOTH':'UNKNOWN_INPUT'}
    l,c=float(level),float(close)
    if not math.isfinite(l) or not math.isfinite(c) or min(l,c)<=0:return {'signed_distance':None,'absolute_distance':None,'known_age_days':None,'D10':'UNKNOWN_INPUT','A28':'UNKNOWN_INPUT','BOTH':'UNKNOWN_INPUT'}
    t,k=pd.Timestamp(when),pd.Timestamp(known)
    if t.tz is None or k.tz is None or k>t:return {'signed_distance':None,'absolute_distance':None,'known_age_days':None,'D10':'UNKNOWN_INPUT','A28':'UNKNOWN_INPUT','BOTH':'UNKNOWN_INPUT'}
    signed=(c-l)/c;distance=abs(signed);age=(t-k).total_seconds()/86400
    far=abs(Decimal(str(close))-Decimal(str(level)))>Decimal(str(close))*Decimal('0.10');old=(t-k).total_seconds()>28*86400
    return {'signed_distance':signed,'absolute_distance':distance,'known_age_days':age,'D10':'UNKNOWN_FAR' if far else state,'A28':'UNKNOWN_OLD' if old else state,'BOTH':'UNKNOWN_FAR_OLD' if far and old else 'UNKNOWN_FAR' if far else 'UNKNOWN_OLD' if old else state}

def main(period):
    src=Path(f'data/verify/market-support-fallback-{period}-20261104-01/asof_and_future.csv');out=Path(f'data/verify/market-support-freshness-{period}-20261104-01');assert not out.exists();x=pd.read_csv(src);assert len(x)==(180 if period=='2025q1' else 184)
    extra=[gate(r.new_state,r.new_level,r.close,r.new_known,r.as_of_utc) for r in x.itertuples()];x=pd.concat([x,pd.DataFrame(extra)],axis=1);joint=[]
    for t,g in x.groupby('as_of_utc',sort=True):
        assert len(g)==2 and set(g.source)=={'bitstamp','bitfinex'};item={'as_of_utc':t,'focus_both':bool(g.focus.all())}
        for col in ('new_state','D10','A28','BOTH'):
            u,v=g[col].tolist();item[col]='UNKNOWN' if u.startswith('UNKNOWN') or v.startswith('UNKNOWN') or u=='WAIT_CONFIRM' or v=='WAIT_CONFIRM' else 'JOINT_'+u if u==v else 'DISAGREE'
        joint.append(item)
    j=pd.DataFrame(joint);out.mkdir();x.to_csv(out/'source-all.csv',index=False);j.to_csv(out/'joint-all.csv',index=False)
    s={'points':len(j),'focus_both':int(j.focus_both.sum()),'all':{c:j[c].value_counts().to_dict() for c in ('new_state','D10','A28','BOTH')},'focus':{c:j[j.focus_both][c].value_counts().to_dict() for c in ('new_state','D10','A28','BOTH')},'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'definition_sha256':hashlib.sha256(Path('docs/摆低距离时间-2025一季度事前验证-20261104.md').read_bytes()).hexdigest(),'limits':['Retrospective price and availability facts only; no human phase labels or causal proof.','10% and 28 days are provisional research examples.']};(out/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s,indent=2))

if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('2024q4','2025q1'):raise SystemExit('period must be 2024q4 or 2025q1')
    main(sys.argv[1])
