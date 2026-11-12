"""Retain predeclared BTC/USD trade samples and aggregate four hourly windows."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import csv, gzip, hashlib, json, requests

OUT=Path('data/verify/market-2020q3-trades-20261103-01')
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    OUT.mkdir(exist_ok=False)
    url='https://datasets.tardis.dev/v1/bitstamp/trades/2020/08/01/BTCUSD.csv.gz'
    r=requests.get(url,timeout=60);r.raise_for_status();p=OUT/'bitstamp-2020-08-01.csv.gz';p.write_bytes(r.content)
    with gzip.open(p,'rt',newline='') as f: stamp=list(csv.DictReader(f))
    start=int(datetime(2020,8,1,tzinfo=timezone.utc).timestamp())
    result={'tardis_url':url,'tardis_sha256':digest(p),'tardis_day_rows':len(stamp),'hours':[]}
    for hour in range(4):
        a=start+3600*hour
        s=[x for x in stamp if a*1000000<=int(x['timestamp'])<(a+3600)*1000000]
        params={'start':a*1000,'end':(a+3600)*1000-1,'sort':1,'limit':10000}
        q=requests.get('https://api-pub.bitfinex.com/v2/trades/tBTCUSD/hist',params=params,timeout=60);q.raise_for_status();path=OUT/f'bitfinex-{hour}.json';path.write_bytes(q.content);f=json.loads(q.text,parse_float=Decimal)
        assert isinstance(f,list) and all(isinstance(x,list) and len(x)>=4 and a*1000<=x[1]<(a+3600)*1000 for x in f)
        assert len({x[0] for x in f})==len(f) and len({x['id'] for x in s})==len(s)
        def stats(prices,vols):
            if not prices:return {'count':0,'status':'UNKNOWN'}
            assert all(x>0 for x in prices+vols)
            return {'count':len(prices),'low':str(min(prices)),'high':str(max(prices)),'volume':str(sum(vols))}
        result['hours'].append({'hour_utc':hour,'bitstamp':stats([Decimal(x['price']) for x in s],[Decimal(x['amount']) for x in s]),'bitfinex':stats([Decimal(str(x[3])) for x in f],[abs(Decimal(str(x[2]))) for x in f]),'bitfinex_limit_reached':len(f)>=10000,'bitfinex_url':q.url,'bitfinex_sha256':digest(path)})
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
