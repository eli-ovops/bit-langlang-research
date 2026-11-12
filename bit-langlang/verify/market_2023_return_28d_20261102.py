"""Predeclared 7/28-day close return facts, no future labels."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
R=Path('data/verify');OUT=R/'market-2023-return-windows-20261102-01'
def returned(d,start,side,bound,n):
 for i in range(n):
  t=start+pd.Timedelta(days=i)
  if t not in d.index or not d.loc[t,'good']:return 'UNKNOWN_INCOMPLETE',None,None
  close=float(d.loc[t,'close'])
  if (side=='UPPER_BREAK' and close<bound) or (side=='LOWER_BREAK' and close>bound):return 'RETURN',(t+pd.Timedelta(days=1)).isoformat(),close
 return 'NO_RETURN',None,None

def main():
 if OUT.exists():raise FileExistsError(OUT)
 rows=[];files=[Path(__file__),Path('docs/春秋-2023冻结检验与收回时限-事前定义-20261102.md')]
 for name in ['binance','kucoin']:
  p=R/('market-2023-'+name+'-20261102-01');files.extend([p/'bars-4h.csv.gz',p/'future.csv']);d,h=read(p/'bars-4h.csv.gz');f=pd.read_csv(p/'future.csv')
  for e in f.itertuples():
   row={'source':name,'as_of_utc':e.as_of_utc,'first':e.first,'first_time_utc':e.first_time_utc}
   if e.first in ('UPPER_BREAK','LOWER_BREAK'):
    bound=e.frozen_upper if e.first=='UPPER_BREAK' else e.frozen_lower;first=pd.Timestamp(e.first_time_utc)
    for n in (7,28):
     status,when,price=returned(d,first,e.first,bound,n);row.update({f'status_{n}':status,f'return_time_{n}':when,f'return_price_{n}':price})
    original={'RETURN_INSIDE_SIDE':'RETURN','NO_RETURN_7D':'NO_RETURN','UNKNOWN_INCOMPLETE':'UNKNOWN_INCOMPLETE'}[e.followup];assert row['status_7']==original and (pd.isna(e.return_time_utc) or row['return_time_7']==e.return_time_utc)
   else:row.update(status_7='NO_BREAK' if e.first=='UNRESOLVED_28D' else 'UNKNOWN',status_28='NO_BREAK' if e.first=='UNRESOLVED_28D' else 'UNKNOWN')
   rows.append(row)
 OUT.mkdir();df=pd.DataFrame(rows);df.to_csv(OUT/'returns.csv',index=False);summary={name:{f'status_{n}':g[f'status_{n}'].value_counts().to_dict() for n in (7,28)} for name,g in df.groupby('source')};(OUT/'summary.json').write_text(json.dumps({'results':summary,'input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files}},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
