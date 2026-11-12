"""Fixed 28d descriptive closing changes; not realized returns or phase labels."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
D=Path('data/market/btc-2014-usd-cross-20261102-01');SRC=Path('data/verify/market-2014-position-20261102-01');OUT=Path('data/verify/market-2014-close-context-20261102-01')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 a=pd.read_csv(SRC/'asof.csv');pairs=pd.read_csv(SRC/'pairs.csv');flags=[pd.Timestamp(x) for x in json.loads((SRC/'summary.json').read_text())['results']['bitstamp_bitfinex']['flags_utc']];rows=[]
 for venue in ('bitstamp','bitfinex'):
  d,_=read(D/(venue+'-4h.csv.gz'))
  for flag in flags:d.loc[flag.floor('D'),'good']=False
  for r in a[a.source==venue].itertuples():
   t=pd.Timestamp(r.as_of_utc);prev=t-pd.Timedelta(days=1);z=d[(d.index>=t)&(d.index<t+pd.Timedelta(days=28))];row={'source':venue,'as_of_utc':r.as_of_utc,'position':r.position,'joint_position':pairs[pairs.as_of_utc==r.as_of_utc].iloc[0].new_position_joint,'status':'UNKNOWN_INCOMPLETE'}
   if prev in d.index and d.loc[prev,'good'] and len(z)==28 and z.good.all():
    p=float(d.loc[prev,'close']);last=float(z.close.iloc[-1]);row.update(status='COMPLETE_DESCRIPTIVE',asof_close=p,close_after_28d=last,close_after_28d_utc=(t+pd.Timedelta(days=28)).isoformat(),close_change_pct=(last/p-1)*100)
   rows.append(row)
 out=pd.DataFrame(rows);OUT.mkdir();out.to_csv(OUT/'close-context.csv',index=False);files=[Path(__file__),SRC/'asof.csv',SRC/'pairs.csv',SRC/'summary.json',D/'bitstamp-4h.csv.gz',D/'bitfinex-4h.csv.gz'];(OUT/'summary.json').write_text(json.dumps({'rows':len(out),'complete':int(out.status.eq('COMPLETE_DESCRIPTIVE').sum()),'input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files},'scope':'Descriptive 28d close difference, not return from trading or phase truth.'},indent=2)+'\n');print('rows',len(out),'complete',int(out.status.eq('COMPLETE_DESCRIPTIVE').sum()))
if __name__=='__main__':main()
