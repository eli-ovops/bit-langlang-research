"""Independent aggregation validation for raw Bitfinex 1h response."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
D=Path('data/market/btc-2020am-usd-cross-20261102-01');O=Path('data/verify/market-2020am-bitfinex-source-audit-20261102-01')
def main():
 if O.exists():raise FileExistsError(O)
 p=D/'bitfinex-1h.json';z=pd.DataFrame(json.loads(p.read_text()),columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric).set_index('ts').sort_index();v=z[['open','high','low','close']];assert not z.index.duplicated().any() and (z.index%3600000==0).all() and np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (z.low<=v.min(axis=1)).all() and (z.high>=v.max(axis=1)).all();o=pd.read_csv(D/'bitfinex-4h.csv.gz').set_index('ts')
 for ts,row in o.iterrows():
  a=z.reindex([ts+i*3600000 for i in range(4)]);assert not a.open.isna().any();v=[a.open.iloc[0],a.high.max(),a.low.min(),a.close.iloc[-1]];assert np.allclose(v,row[['open','high','low','close']].to_numpy(dtype=float))
 O.mkdir();files=[p,D/'bitfinex-4h.csv.gz',Path(__file__)];(O/'summary.json').write_text(json.dumps({'status':'PASS','checked_4h':len(o),'raw_1h':len(z),'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',len(o))
if __name__=='__main__':main()
