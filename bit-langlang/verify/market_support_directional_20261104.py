"""Post-hoc exploratory direction-sensitive distance display; not trading logic."""
from decimal import Decimal
from pathlib import Path
import hashlib,json
import pandas as pd

def classify(state,low,close):
    if state in ('UNKNOWN','WAIT_CONFIRM') or pd.isna(low) or pd.isna(close):return 'UNKNOWN_INPUT','UNKNOWN'
    l,c=Decimal(str(low)),Decimal(str(close))
    if not l.is_finite() or not c.is_finite() or min(l,c)<=0:return 'UNKNOWN_INPUT','UNKNOWN'
    if (state.endswith('_BELOW') and not c<l) or (state.endswith('_ABOVE') and not c>l):return 'UNKNOWN_INCONSISTENT','UNKNOWN'
    if c-l>c*Decimal('0.10'):return 'UNKNOWN_FAR_BELOW_PRICE','FAR_BELOW_PRICE'
    if l-c>c*Decimal('0.10'):return state,'FAR_ABOVE_PRICE'
    return state,'WITHIN_10PCT'

def main():
    result={}
    for period in ('2024q4','2025q1'):
        src=Path(f'data/verify/market-support-freshness-{period}-20261104-01/source-all.csv');out=Path(f'data/verify/market-support-directional-{period}-20261104-01');assert not out.exists();x=pd.read_csv(src);vals=[classify(r.new_state,r.new_level,r.close) for r in x.itertuples()];x['directional_state']=[v[0] for v in vals];x['distance_flag']=[v[1] for v in vals];rows=[]
        for t,g in x.groupby('as_of_utc',sort=True):
            assert len(g)==2;u,v=g.directional_state.tolist();rows.append({'as_of_utc':t,'focus_both':bool(g.focus.all()),'directional_joint':'UNKNOWN' if u.startswith('UNKNOWN') or v.startswith('UNKNOWN') else 'JOINT_'+u if u==v else 'DISAGREE','far_above_price_any':bool((g.distance_flag=='FAR_ABOVE_PRICE').any())})
        j=pd.DataFrame(rows);out.mkdir();x.to_csv(out/'source-all.csv',index=False);j.to_csv(out/'joint-all.csv',index=False);d={'period':period,'all':j.directional_joint.value_counts().to_dict(),'focus':j[j.focus_both].directional_joint.value_counts().to_dict(),'joint_days_far_above_warning':int(j.far_above_price_any.sum()),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'posthoc':True};(out/'summary.json').write_text(json.dumps(d,indent=2)+'\n');result[period]=d
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
