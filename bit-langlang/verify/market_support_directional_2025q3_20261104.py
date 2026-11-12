"""Frozen direction-aware 10% candidate on preselected 2025Q3 only."""
from pathlib import Path
from decimal import Decimal
import hashlib,json
import pandas as pd
from verify.market_support_directional_20261104 import classify

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    src=Path('data/verify/market-support-fallback-2025q3-20261104-01/asof_and_future.csv');spec=Path('docs/方向化摆低-2025三季度事前筛查-20261104.md');out=Path('data/verify/market-support-directional-2025q3-20261104-01');assert not out.exists();x=pd.read_csv(src);assert len(x)==184
    vals=[classify(r.new_state,r.new_level,r.close) for r in x.itertuples()];x['directional_state']=[v[0] for v in vals];x['distance_flag']=[v[1] for v in vals];x['signed_distance']=[float((Decimal(str(r.close))-Decimal(str(r.new_level)))/Decimal(str(r.close))) if pd.notna(r.new_level) and pd.notna(r.close) and float(r.close)>0 else None for r in x.itertuples()];j=[]
    for t,g in x.groupby('as_of_utc',sort=True):
        assert len(g)==2 and set(g.source)=={'bitstamp','bitfinex'};row={'as_of_utc':t,'focus_both':bool(g.focus.all()),'far_above_price_any':bool((g.distance_flag=='FAR_ABOVE_PRICE').any())}
        for key in ('new_state','directional_state'):
            u,v=g[key].tolist();row[key]='UNKNOWN' if u.startswith('UNKNOWN') or v.startswith('UNKNOWN') or u=='WAIT_CONFIRM' or v=='WAIT_CONFIRM' else 'JOINT_'+u if u==v else 'DISAGREE'
        j.append(row)
    j=pd.DataFrame(j);out.mkdir();x.to_csv(out/'source-all.csv',index=False);j.to_csv(out/'joint-all.csv',index=False);s={'points':len(j),'focus_both':int(j.focus_both.sum()),'all':{k:j[k].value_counts().to_dict() for k in ('new_state','directional_state')},'focus':{k:j[j.focus_both][k].value_counts().to_dict() for k in ('new_state','directional_state')},'far_above_price_any':int(j.far_above_price_any.sum()),'input_sha256':{str(p):sha(p) for p in (src,spec,Path(__file__),Path('verify/market_support_directional_20261104.py'))},'limitations':['Other project research exposed to period.','No independent human phase reference.','Threshold is research hypothesis, not Bit Langlang verified rule.']};(out/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s,indent=2))
if __name__=='__main__':main()
