import csv,hashlib,json,math
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import requests
R=Path(__file__).resolve().parents[1]; OUT=R/'data/verify/cycle-kraken-180day-prehistory-20261109-01'
OLD=R/'data/verify/cycle-recent-four-days-20261109-01/kraken-4h.csv'
END=datetime(2026,11,9,tzinfo=timezone.utc);START=END-timedelta(days=180)
URL='https://api.kraken.com/0/public/OHLC'

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 params={'pair':'XBTUSD','interval':1440,'since':int(START.timestamp())}; result={'url':URL,'params':params,'status':'UNKNOWN'}
 try:
  response=requests.get(URL,params=params,timeout=35);result.update(http=response.status_code,retrieved_utc=datetime.now(timezone.utc).isoformat());response.raise_for_status()
  (OUT/'response.json').write_bytes(response.content);result['response_sha256']=hashlib.sha256(response.content).hexdigest();j=response.json()
  if j['error']:raise ValueError(str(j['error']))
  keys=[k for k in j['result'] if k!='last'];assert len(keys)==1
  daily={}
  for x in j['result'][keys[0]]:
   ts=int(x[0]);v=tuple(Decimal(str(x[i])) for i in (1,2,3,4,6))
   if ts in daily:raise ValueError('duplicate day')
   if ts%86400 or not all(z.is_finite() and z>0 for z in v) or not v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1]:raise ValueError('invalid daily candle')
   daily[ts]=v
  start=int(START.timestamp());end=int(END.timestamp());missing=[t for t in range(start,end,86400) if t not in daily]
  with OLD.open() as f:
   old={int(datetime.fromisoformat(r['time_utc']).timestamp()):tuple(Decimal(r[k]) for k in ('open','high','low','close','volume')) for r in csv.DictReader(f)}
  checked=0;bad=[];vol_diff=[]
  for t in range(start,end,86400):
   if t not in daily or any(t+j*14400 not in old for j in range(6)):continue
   x=[old[t+j*14400] for j in range(6)];got=(x[0][0],max(z[1] for z in x),min(z[2] for z in x),x[-1][3]);v=daily[t];checked+=1
   if got!=v[:4]:bad.append(datetime.fromtimestamp(t,timezone.utc).isoformat())
   vol_diff.append(abs(sum(z[4] for z in x)-v[4]))
  result.update(pair_key=keys[0],expected_days=180,valid_days=180-len(missing),missing_utc=[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in missing],days_compared_with_old_4h=checked,ohlc_conflicts=bad,max_volume_absolute_diff=str(max(vol_diff,default=Decimal(0))),old_4h_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest())
  if not missing and not bad and checked:result['status']='DAILY_COMPLETE'
 except (requests.RequestException,ValueError,KeyError,IndexError,TypeError,AssertionError) as e:result['error']=f'{type(e).__name__}: {e}'
 (OUT/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
