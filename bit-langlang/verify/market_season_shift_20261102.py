"""Post-hoc, 24-hour sampling sensitivity with identical phase rules."""
import json,hashlib
from pathlib import Path
import pandas as pd
from .market_season_research_20261102 import SOURCE,aggregates,classify_asof,sha
BASE=Path('data/verify/market-season-research-20261102-01');OUT=Path('data/verify/market-season-shift-20261102-01');DEF=Path('docs/四季研究-采样日期扰动定义-20261102.md')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 inputs={str(p):sha(p) for p in (SOURCE,BASE/'weekly.csv',DEF,Path(__file__))};f=pd.read_csv(SOURCE);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);d,h=aggregates(f.set_index('time'));base=pd.read_csv(BASE/'weekly.csv');rows=[]
 for row in base.itertuples(index=False):
  t=pd.Timestamp(row.as_of_utc);current=classify_asof(d,h,t);assert current['season']==row.season
  shifted=classify_asof(d,h,t+pd.Timedelta(days=1));rows.append({'original_utc':t.isoformat(),'shifted_utc':(t+pd.Timedelta(days=1)).isoformat(),'original_season':row.season,'shifted_season':shifted['season'],'equal':row.season==shifted['season']})
 if any(sha(p)!=x for p,x in inputs.items()):raise ValueError('source changed')
 x=pd.DataFrame(rows);out={'status':'POST_HOC_SAMPLING_SENSITIVITY','points':len(x),'same':int(x.equal.sum()),'changed':int((~x.equal).sum()),'known_to_unknown':int(((x.original_season!='UNKNOWN')&(x.shifted_season=='UNKNOWN')).sum()),'unknown_to_known':int(((x.original_season=='UNKNOWN')&(x.shifted_season!='UNKNOWN')).sum()),'known_to_different_known':int(((x.original_season!='UNKNOWN')&(x.shifted_season!='UNKNOWN')&(~x.equal)).sum()),'input_sha256':inputs,'limitations':['Markets may actually change during the day; not a label error rate.','Previously examined history, no independent ground truth.']};OUT.mkdir();x.to_csv(OUT/'pairs.csv',index=False);(OUT/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
