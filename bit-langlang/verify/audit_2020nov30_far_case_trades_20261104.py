"""Predeclared one-minute reported Kraken and Bitfinex BTC/USD trade checks."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import hashlib,json,time
import requests

OUT=Path('data/verify/market-2020nov30-far-case-trades-20261104-01')
def main():
    OUT.mkdir(exist_ok=False);results=[]
    for i,day in enumerate(('2020-11-30',)):
        end=int(datetime.fromisoformat(day+'T00:00:00+00:00').timestamp());start=end-60;items=[];cursor=str(start*10**9);receipt=[];crossed=False
        for page in range(5):
            r=requests.get('https://api.kraken.com/0/public/Trades',params={'pair':'XBTUSD','since':cursor,'count':1000},timeout=60);r.raise_for_status();p=OUT/f'kraken-{i}-{page}.json';p.write_bytes(r.content);z=json.loads(r.text,parse_float=Decimal);assert not z['error'];batch=z['result']['XXBTZUSD'];receipt.append({'url':r.url,'sha256':hashlib.sha256(r.content).hexdigest(),'count':len(batch)});items.extend(batch)
            if batch and Decimal(str(batch[-1][2]))>=end:crossed=True;break
            new=z['result']['last']
            if not batch or new==cursor:break
            cursor=new;time.sleep(2)
        rows=[x for x in items if Decimal(start)<=Decimal(str(x[2]))<end];assert all(len(x)>=7 and Decimal(str(x[0]))>0 and Decimal(str(x[1]))>0 for x in rows);ids=[x[6] for x in rows];unique=len(ids)==len(set(ids))
        r=requests.get('https://api-pub.bitfinex.com/v2/trades/tBTCUSD/hist',params={'start':start*1000,'end':end*1000-1,'sort':1,'limit':10000},timeout=60);r.raise_for_status();p=OUT/f'bitfinex-{i}.json';p.write_bytes(r.content);f=json.loads(r.text,parse_float=Decimal);assert isinstance(f,list) and all(len(q)>=4 and start*1000<=q[1]<end*1000 and Decimal(str(q[3]))>0 and Decimal(str(q[2]))!=0 for q in f);fu=len({q[0] for q in f})==len(f)
        def stats(prices,volumes):
            if not prices:return {'count':0,'status':'UNKNOWN'}
            return {'count':len(prices),'low':str(min(prices)),'high':str(max(prices)),'volume':str(sum(volumes))}
        results.append({'decision_utc':day+'T00:00:00Z','window_start_utc_seconds':start,'kraken':stats([Decimal(str(q[0])) for q in rows],[Decimal(str(q[1])) for q in rows]),'kraken_crossed_end':crossed,'kraken_unique_ids':unique,'kraken_receipts':receipt,'bitfinex':stats([Decimal(str(q[3])) for q in f],[abs(Decimal(str(q[2]))) for q in f]),'bitfinex_unique_ids':fu,'bitfinex_limit_reached':len(f)>=10000,'bitfinex_url':r.url,'bitfinex_sha256':hashlib.sha256(r.content).hexdigest()});time.sleep(2)
    (OUT/'summary.json').write_text(json.dumps({'posthoc':False,'cases':results,'limitations':['Both sources separately correspond to their own OHLC history.','One minute cannot certify complete hour/day or authentic trades.']},indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
