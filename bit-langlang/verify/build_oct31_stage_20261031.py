import json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
from .stage_oct31_spot_20261031 import ROOT,PRIOR,CUT,END
OUT=Path('data/market/nine-futures-stage-oct31-20261031-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 receipts=json.loads((ROOT/'receipts.json').read_text());
 for r in receipts:
  if sha(ROOT/r['file'])!=r['sha256']:raise ValueError('raw hash mismatch')
 prior=json.loads((PRIOR/'manifest.json').read_text());OUT.mkdir();meta={}
 for s in tuple(prior['symbols'])+('BTCUSDT',):
  src=PRIOR/(s+'_5m.csv.gz') if s!='BTCUSDT' else Path('data/market/BTCUSDT_5m.csv.gz');f=pd.read_csv(src);f=f[f.ts<CUT][['ts','open','high','low','close']]
  if s!='BTCUSDT' and sha(src)!=prior['symbols'][s]['price_sha256']:raise ValueError('prior price mismatch')
  raw=[]
  for p in sorted(ROOT.glob(s+'-extension-*.json')):raw+=json.loads(p.read_text())
  extra=pd.DataFrame([row[:5] for row in raw],columns=f.columns).apply(pd.to_numeric,errors='raise');f=pd.concat([f,extra],ignore_index=True)
  if f.ts.duplicated().any() or not f.ts.is_monotonic_increasing or not f.ts.diff().dropna().eq(300000).all() or f.ts.iloc[-1]!=END-300000:raise ValueError('bad bars '+s)
  if not np.isfinite(f.to_numpy(dtype=float)).all() or (f[['open','high','low','close']]<=0).any().any() or (f.low>f[['open','high','close']].min(axis=1)).any() or (f.high<f[['open','low','close']].max(axis=1)).any():raise ValueError('bad OHLC '+s)
  dest=OUT/(s+'_5m.csv.gz');f.to_csv(dest,index=False,compression='gzip');v={'price_sha256':sha(dest),'prior_price_sha256':sha(src),'bars':len(f),'last_ms':int(f.ts.iloc[-1])}
  if s!='BTCUSDT':
   p=PRIOR/(s+'_funding.csv.gz');assert sha(p)==prior['symbols'][s]['funding_sha256'];rates=pd.read_csv(p);ext=json.loads((ROOT/(s+'-funding.json')).read_text());d=pd.DataFrame([{'ts':int(x['fundingTime']),'funding_rate':float(x['fundingRate'])} for x in ext]);rates=pd.concat([rates,d],ignore_index=True)
   if rates.ts.duplicated().any() or not rates.ts.is_monotonic_increasing or (rates.ts.diff().dropna()>28860000).any() or END-rates.ts.iloc[-1]>28860000:raise ValueError('bad funding '+s)
   dest=OUT/(s+'_funding.csv.gz');rates.to_csv(dest,index=False,compression='gzip');v.update(funding_sha256=sha(dest),prior_funding_sha256=sha(p),funding_records=len(rates))
  meta[s]=v
 (OUT/'manifest.json').write_text(json.dumps({'status':'RESEARCH_NOT_VENUE_VALIDATED','receipts_sha256':sha(ROOT/'receipts.json'),'symbols':meta},indent=2)+'\n');print('validated',len(meta),'series')
if __name__=='__main__':main()
