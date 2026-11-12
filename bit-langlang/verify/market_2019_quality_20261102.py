"""Mark observed cross-venue high discrepancy without altering either feed."""
from pathlib import Path
import hashlib,json
import pandas as pd
ROOT=Path('data/verify');p=ROOT/'market-2019-kucoin-20261102-01';q=ROOT/'market-2019-manual-20261102-01';out=ROOT/'market-2019-quality-20261102-01'
def main():
 if out.exists():raise FileExistsError(out)
 ku=pd.read_csv(p/'bars-4h.csv.gz');bn=pd.read_csv(q/'bars-4h.csv.gz');x=ku.merge(bn,on='ts',suffixes=('_ku','_bn'));x['high_ratio']=x.high_ku/x.high_bn
 bad=x[(x.high_ratio>1.1)|(x.high_ratio<.9)].copy();bad['utc']=pd.to_datetime(bad.ts,unit='ms',utc=True).astype(str)
 assert len(bad)==1;ts=pd.Timestamp(int(bad.ts.iloc[0]),unit='ms',tz='UTC');a=pd.read_csv(p/'asof.csv');f=pd.read_csv(p/'future.csv');g=a[['as_of_utc','spring_watch','autumn_watch']].merge(f,on='as_of_utc');t=pd.to_datetime(g.as_of_utc,utc=True)
 g['prior56_contains_suspect']=(t>ts)&(t<=ts+pd.Timedelta(days=56));g['prior28_contains_suspect']=(t>ts)&(t<=ts+pd.Timedelta(days=28));g['cautious_watch']=g.spring_watch.where(~g.prior56_contains_suspect,'UNKNOWN_PRICE_DISCREPANCY')
 out.mkdir();bad.to_csv(out/'cross-source-high-discrepancies.csv',index=False);g.to_csv(out/'sensitivity.csv',index=False)
 files=[p/'bars-4h.csv.gz',q/'bars-4h.csv.gz',p/'asof.csv',p/'future.csv',Path(__file__)];obj={'suspect_candle_utc':ts.isoformat(),'kucoin_high':float(bad.high_ku.iloc[0]),'binance_high':float(bad.high_bn.iloc[0]),'kucoin_close':float(bad.close_ku.iloc[0]),'binance_close':float(bad.close_bn.iloc[0]),'high_ratio':float(bad.high_ratio.iloc[0]),'weekly_points_prior56_containing_candle':int(g.prior56_contains_suspect.sum()),'weekly_points_prior28_containing_candle':int(g.prior28_contains_suspect.sum()),'scope':'10 percent heuristic for review, not proof of bad data or actual trade; no imputation; quality flag defined after observation','inputs_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}};(out/'summary.json').write_text(json.dumps(obj,indent=2)+'\n');print(json.dumps(obj,indent=2))
if __name__=='__main__':main()
