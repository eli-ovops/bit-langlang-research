"""Cross-check 28d closes by raw 4h slices."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.audit_2018_transition_20261102 import calc
D=Path('data/market/btc-2014-usd-cross-20261102-01');S=Path('data/verify/market-2014-close-context-20261102-01');O=Path('data/verify/market-2014-close-context-independent-20261102-01')
def main():
 if O.exists():raise FileExistsError(O)
 x=pd.read_csv(S/'close-context.csv');n=0
 for name in ('bitstamp','bitfinex'):
  f=pd.read_csv(D/(name+'-4h.csv.gz'));f.index=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.drop(pd.Timestamp('2014-08-14 08:00',tz='UTC'),errors='ignore')
  for r in x[x.source==name].itertuples():
   t=pd.Timestamp(r.as_of_utc);prior=calc(f,t,1);post=calc(f,t+pd.Timedelta(days=28),28);status='COMPLETE_DESCRIPTIVE' if prior is not None and post is not None else 'UNKNOWN_INCOMPLETE';assert r.status==status,(name,t,status,r.status)
   if status=='COMPLETE_DESCRIPTIVE':
    p=prior.close.iloc[-1];q=post.close.iloc[-1];assert np.isclose(p,r.asof_close) and np.isclose(q,r.close_after_28d) and np.isclose((q/p-1)*100,r.close_change_pct) and r.close_after_28d_utc==(t+pd.Timedelta(days=28)).isoformat()
   n+=1
 O.mkdir();files=[Path(__file__),S/'close-context.csv',D/'bitstamp-4h.csv.gz',D/'bitfinex-4h.csv.gz'];(O/'summary.json').write_text(json.dumps({'status':'PASS','rows_checked':n,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',n)
if __name__=='__main__':main()
