"""Predeclared four-hour BTC/USDT trades from two Tardis day files."""
from pathlib import Path
from decimal import Decimal
import csv, gzip, hashlib, json, requests

OUT=Path('data/verify/market-2022q4-usdt-trades-20261103-01')
def main():
    OUT.mkdir(exist_ok=False);out=[]
    for venue,symbol in [('binance','BTCUSDT'),('kucoin','BTC-USDT')]:
        url=f'https://datasets.tardis.dev/v1/{venue}/trades/2022/11/01/{symbol}.csv.gz';r=requests.get(url,stream=True,timeout=90);r.raise_for_status();p=OUT/(venue+'.csv.gz');size=0;digest=hashlib.sha256()
        with p.open('xb') as f:
            for block in r.iter_content(1024*1024):
                size+=len(block)
                if size>100_000_000:raise ValueError('download cap reached; retain partial evidence')
                f.write(block);digest.update(block)
        a=1667260800*1000000;b=a+4*3600*1000000;count=0;vol=Decimal(0);lo=None;hi=None;ids=set()
        with gzip.open(p,'rt',newline='') as f:
            for x in csv.DictReader(f):
                if not a<=int(x['timestamp'])<b:continue
                assert x['exchange']==venue and x['symbol']==symbol
                price=Decimal(x['price']);amount=Decimal(x['amount']);assert price>0 and amount>0 and x['id'] not in ids
                ids.add(x['id']);count+=1;vol+=amount;lo=price if lo is None else min(lo,price);hi=price if hi is None else max(hi,price)
        out.append({'venue':venue,'symbol':symbol,'url':url,'bytes':size,'sha256':digest.hexdigest(),'count':count,'volume':str(vol),'low':str(lo),'high':str(hi),'status':'REPORTED' if count else 'UNKNOWN'})
    (OUT/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
