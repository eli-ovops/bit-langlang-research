"""Check 1h raw candles against 4h data without source script helpers."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
D=Path('data/market/btc-2016-usd-cross-20261102-01');O=Path('data/verify/market-2016-coinbase-source-audit-20261102-01')
def main():
 if O.exists():raise FileExistsError(O)
 paths=sorted(D.glob('coinbase-*.json'));rows=[]
 for p in paths:rows.extend(json.loads(p.read_text()))
 z=pd.DataFrame(rows,columns=['s','low','high','open','close','volume']).apply(pd.to_numeric);v=z[['open','high','low','close']];assert (z.s%3600==0).all() and np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (z.low<=v.min(axis=1)).all() and (z.high>=v.max(axis=1)).all()
 assert (z.groupby('s')[['low','high','open','close','volume']].nunique().max(axis=1)<=1).all();z=z.drop_duplicates('s').set_index('s').sort_index();o=pd.read_csv(D/'coinbase-4h.csv.gz').set_index('ts');checked=0
 for ts,row in o.iterrows():
  expected=[ts//1000+i*3600 for i in range(4)];a=z.reindex(expected);assert not a.open.isna().any();vals=[a.open.iloc[0],a.high.max(),a.low.min(),a.close.iloc[-1]];assert np.allclose(vals,row[['open','high','low','close']].to_numpy(dtype=float));checked+=1
 hours=pd.date_range('2016-01-01','2016-10-01',inclusive='left',freq='h',tz='UTC');missing=hours.difference(pd.to_datetime(z.index,unit='s',utc=True));assert len(o)==1642 and len(missing)>0
 files=[Path(__file__),D/'coinbase-4h.csv.gz']+paths;O.mkdir();(O/'summary.json').write_text(json.dumps({'status':'PASS','raw_1h_rows':len(rows),'unique_1h':len(z),'checked_4h':checked,'missing_1h_utc':[x.isoformat() for x in missing],'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',checked,'four-hour candles, missing hours',len(missing))
if __name__=='__main__':main()
