"""Compare KuCoin time bucket aggregation; no alteration of exchange data."""
from pathlib import Path
import hashlib,json,requests,pandas as pd
OUT=Path('data/verify/kucoin-2019-spike-detail-20261102-01');URL='https://api.kucoin.com/api/ua/v2/market/kline'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);start=1553788800;end=start+4*3600;data={}
 for interval in ['1min','5min','15min','1hour','4hour']:
  params={'symbol':'BTC-USDT','tradeType':'SPOT','interval':interval,'startAt':start,'endAt':end-1};r=requests.get(URL,params=params,timeout=35);r.raise_for_status();p=OUT/(interval+'.json');p.write_bytes(r.content);x=r.json();assert x['code']=='200000' and x['data']['symbol']=='BTC-USDT';lst=x['data']['list'];data[interval]={'records':len(lst),'high':max((float(a[2]) for a in lst),default=None),'volume':sum(float(a[5]) for a in lst),'amount':sum(float(a[6]) for a in lst),'request':r.url,'sha256':hashlib.sha256(r.content).hexdigest(),'peak_rows':[a for a in lst if float(a[2])>5000]}
 (OUT/'summary.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))
if __name__=='__main__':main()
