"""Compare three predeclared month-start trade windows to venue-local bars."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import csv, gzip, hashlib, json, time, requests

OUT=Path('data/verify/market-2022q4-trades-20261103-01')
DATA=Path('data/market/btc-2022q4-usd-cross-20261103-01')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    OUT.mkdir(exist_ok=True)
    if any(OUT.iterdir()): raise FileExistsError('retain previous responses; do not overwrite')
    result=[]
    for month in (10,11,12):
        stamp=datetime(2022,month,1,tzinfo=timezone.utc);start=int(stamp.timestamp());url=f'https://datasets.tardis.dev/v1/bitstamp/trades/2022/{month:02d}/01/BTCUSD.csv.gz'
        r=requests.get(url,timeout=60);r.raise_for_status();p=OUT/f'bitstamp-{month}.csv.gz';p.write_bytes(r.content)
        with gzip.open(p,'rt',newline='') as f:rows=list(csv.DictReader(f))
        record={'month':month,'tardis_url':url,'tardis_sha256':sha(p),'tardis_day_rows':len(rows),'hours':[]}
        for h in range(4):
            a=start+h*3600;s=[x for x in rows if a*1000000<=int(x['timestamp'])<(a+3600)*1000000]
            params={'start':a*1000,'end':(a+3600)*1000-1,'sort':1,'limit':10000};q=requests.get('https://api-pub.bitfinex.com/v2/trades/tBTCUSD/hist',params=params,timeout=60);q.raise_for_status();path=OUT/f'bitfinex-{month}-{h}.json';path.write_bytes(q.content);f=json.loads(q.text,parse_float=Decimal)
            assert isinstance(f,list) and all(isinstance(x,list) and len(x)>=4 and a*1000<=x[1]<(a+3600)*1000 for x in f)
            assert len({x[0] for x in f})==len(f) and len({x['id'] for x in s})==len(s)
            def stat(prices,volumes):
                if not prices:return {'count':0,'status':'UNKNOWN'}
                assert all(x>0 for x in prices+volumes)
                return {'count':len(prices),'low':str(min(prices)),'high':str(max(prices)),'volume':str(sum(volumes))}
            record['hours'].append({'hour_utc':h,'bitstamp':stat([Decimal(x['price']) for x in s],[Decimal(x['amount']) for x in s]),'bitfinex':stat([Decimal(str(x[3])) for x in f],[abs(Decimal(str(x[2]))) for x in f]),'bitfinex_limit_reached':len(f)>=10000,'bitfinex_url':q.url,'bitfinex_sha256':sha(path)})
            time.sleep(1)
        result.append(record)
    (OUT/'summary.json').write_text(json.dumps({'windows':result},indent=2)+'\n');print(json.dumps({'counts':[(x['month'],[(h['bitstamp']['count'],h['bitfinex']['count'],h['bitfinex_limit_reached']) for h in x['hours']]) for x in result]},indent=2))
if __name__=='__main__':main()
