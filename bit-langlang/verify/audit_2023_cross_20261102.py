"""Cross-venue comparison after both independent datasets are fixed."""
from pathlib import Path
import json,hashlib,pandas as pd
R=Path('data/verify');B=R/'market-2023-binance-20261102-01';K=R/'market-2023-kucoin-20261102-01';O=R/'market-2023-cross-20261102-01'
def main():
 if O.exists():raise FileExistsError(O)
 b=pd.read_csv(B/'bars-4h.csv.gz');k=pd.read_csv(K/'bars-4h.csv.gz');x=b.merge(k,on='ts',suffixes=('_binance','_kucoin'),validate='one_to_one');assert len(x)==1824
 flags=pd.Series(False,index=x.index)
 for v in ('high','low'):
  ratio=x[v+'_kucoin']/x[v+'_binance'];flags|=(ratio>1.1)|(ratio<.9)
 a=pd.read_csv(B/'asof.csv').merge(pd.read_csv(K/'asof.csv'),on='as_of_utc',suffixes=('_binance','_kucoin'),validate='one_to_one');e=pd.read_csv(B/'future.csv').merge(pd.read_csv(K/'future.csv'),on='as_of_utc',suffixes=('_binance','_kucoin'),validate='one_to_one');r=a[['as_of_utc','spring_watch_binance','spring_watch_kucoin','autumn_watch_binance','autumn_watch_kucoin']].merge(e,on='as_of_utc',validate='one_to_one')
 stats={'matched_4h_bars':len(x),'ohlc_extremes_over_10pct':int(flags.sum()),'points':len(r),'spring_watch_equal':int((r.spring_watch_binance==r.spring_watch_kucoin).sum()),'autumn_watch_equal':int((r.autumn_watch_binance==r.autumn_watch_kucoin).sum()),'first_event_equal':int((r.first_binance==r.first_kucoin).sum()),'followup_equal':int((r.followup_binance==r.followup_kucoin).sum()),'first_event_time_equal':int(r.first_time_utc_binance.fillna('').eq(r.first_time_utc_kucoin.fillna('')).sum()),'note':'10 percent is predeclared quality alert only, cannot certify prices; venue agreement is not season truth.'}
 files=[B/'bars-4h.csv.gz',K/'bars-4h.csv.gz',B/'asof.csv',K/'asof.csv',B/'future.csv',K/'future.csv',Path(__file__)];O.mkdir();r.to_csv(O/'comparison.csv',index=False);(O/'summary.json').write_text(json.dumps({'results':stats,'inputs_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print(json.dumps(stats,indent=2))
if __name__=='__main__':main()
