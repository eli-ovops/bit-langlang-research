"""Reconcile saved reported trades to each venue's saved bars using Decimal."""
from pathlib import Path
from decimal import Decimal
import csv, gzip, json, hashlib

ROOT=Path('data/verify/market-2025q3-trades-20261104-01')
DATA=Path('data/market/btc-2025q3-usd-cross-20261104-01')
OUT=Path('data/verify/market-2025q3-trades-reconcile-20261104-01')
def main():
    t=1754006400;stamp=[]
    with gzip.open(ROOT/'bitstamp-2025-08-01.csv.gz','rt',newline='') as f:
        for r in csv.DictReader(f):
            if t*1000000<=int(r['timestamp'])<(t+14400)*1000000:stamp.append(r)
    assert stamp and len({r['id'] for r in stamp})==len(stamp) and all(r['exchange']=='bitstamp' and r['symbol']=='BTCUSD' and Decimal(r['price'])>0 and Decimal(r['amount'])>0 for r in stamp)
    bars=[]
    for p in DATA.glob('bitstamp-[0-9].json'):
        bars.extend(r for r in json.loads(p.read_text())['data']['ohlc'] if int(r['timestamp'])==t)
    assert len(bars)==1;b=bars[0];vol=sum(Decimal(r['amount']) for r in stamp);low=min(Decimal(r['price']) for r in stamp);high=max(Decimal(r['price']) for r in stamp)
    stamp_delta=vol-Decimal(b['volume']);stamp_ok=low==Decimal(b['low']) and high==Decimal(b['high']) and abs(stamp_delta)<Decimal('0.00000001')
    hourbars={}
    for p in DATA.glob('bitfinex-1h-[0-9].json'):
        for r in json.loads(p.read_text(),parse_float=Decimal):
            if t*1000<=r[0]<(t+14400)*1000:hourbars[r[0]]=r
    hours=[]
    for i in range(4):
        rows=json.loads((ROOT/f'bitfinex-{i}.json').read_text(),parse_float=Decimal);bar=hourbars[(t+3600*i)*1000];assert rows and len(rows)<10000 and len({r[0] for r in rows})==len(rows) and all((t+3600*i)*1000<=r[1]<(t+3600*(i+1))*1000 and Decimal(str(r[3]))>0 and Decimal(str(r[2]))!=0 for r in rows)
        delta=sum(abs(Decimal(str(r[2]))) for r in rows)-Decimal(str(bar[5]));ok=min(Decimal(str(r[3])) for r in rows)==Decimal(str(bar[4])) and max(Decimal(str(r[3])) for r in rows)==Decimal(str(bar[3])) and abs(delta)<Decimal('0.00000001');hours.append({'hour':i,'count':len(rows),'ok':ok,'volume_delta':str(delta)})
    result={'bitstamp':{'count':len(stamp),'ok':stamp_ok,'volume_delta':str(stamp_delta)},'bitfinex':hours,'limitations':['Third-party capture and same-exchange APIs do not certify executions or full-quarter trade completeness.','Timestamp tie order and day-boundary completeness not proved.']};OUT.mkdir(exist_ok=False);(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));assert stamp_ok and all(x['ok'] for x in hours)
if __name__=='__main__':main()
