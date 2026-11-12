import csv,hashlib,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import requests
R=Path(__file__).resolve().parents[1]
OUT=R/'data/verify/cycle-forward-180day-prehistory-20261109-01'
OLD=R/'data/verify/cycle-recent-four-days-20261109-01/bitfinex-response.json'
END=datetime(2026,11,9,tzinfo=timezone.utc)
START=END-timedelta(days=180)
URL='https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist'
H=3600000

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 params={'start':int(START.timestamp()*1000),'end':int(END.timestamp()*1000)-1,'limit':10000,'sort':1}
 result={'url':URL,'params':params,'status':'UNKNOWN'}
 try:
  resp=requests.get(URL,params=params,timeout=35);result.update(http=resp.status_code,retrieved_utc=datetime.now(timezone.utc).isoformat());resp.raise_for_status()
  (OUT/'response.json').write_bytes(resp.content);result['response_sha256']=hashlib.sha256(resp.content).hexdigest();payload=resp.json()
  if not isinstance(payload,list):raise ValueError('unexpected response shape')
  bars={}
  for row in payload:
   if not isinstance(row,list) or len(row)<6:raise ValueError('invalid row')
   ts=int(row[0]); o,c,h,l,v=map(float,row[1:6])
   if ts in bars:raise ValueError('duplicate timestamp')
   if ts%H or not all(math.isfinite(x) and x>0 for x in (o,c,h,l,v)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('invalid OHLCV')
   bars[ts]=(o,c,h,l,v)
  grid=range(params['start'],params['end']+1,H);missing=[t for t in grid if t not in bars]
  old=json.loads(OLD.read_text());cross=0;conflicts=[]
  for row in old:
   t=int(row[0]);v=tuple(float(x) for x in row[1:6])
   if t in bars:
    cross+=1
    if bars[t]!=v:conflicts.append(t)
  result.update(expected_hours=4320,valid_hours=4320-len(missing),missing_utc=[datetime.fromtimestamp(t/1000,timezone.utc).isoformat() for t in missing],overlap_hours=cross,overlap_conflicts=conflicts,old_response_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest())
  if not missing and not conflicts and cross:result['status']='COMPLETE'
 except (requests.RequestException,ValueError,KeyError,IndexError,TypeError) as e:result['error']=f'{type(e).__name__}: {e}'
 (OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
