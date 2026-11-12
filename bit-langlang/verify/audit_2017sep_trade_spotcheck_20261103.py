"""Independent raw JSON + CSV Decimal reconstruction of the two post-hoc hours."""
from pathlib import Path
from decimal import Decimal
import csv,gzip,hashlib,json

SRC=Path('data/verify/market-2017sep-trade-spotcheck-20261103-01');DATA=Path('data/market/btc-2017sep-usd-cross-20261103-01');OUT=Path('data/verify/market-2017sep-trade-spotcheck-independent-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    m=json.loads((SRC/'summary.json').read_text());path=DATA/'bitfinex-1h.csv.gz'
    with gzip.open(path,'rt',newline='') as f:candles={int(r['ts']):r for r in csv.DictReader(f)}
    files=[Path(__file__),path,SRC/'summary.json'];counts=[]
    for i,q in enumerate(m['cases']):
        p=SRC/f'trades-{i}.json';assert sha(p)==m['input_sha256'][str(p)];files.append(p);records=json.loads(p.read_text(),parse_float=Decimal);start=int(q['request_url'].split('start=')[1].split('&')[0]);end=start+3600000
        assert q['status']=='REPORTED_RECORDS_MATCH' and len(records)==q['rows']<10000 and len({int(r[0]) for r in records})==len(records) and all(start<=int(r[1])<end and Decimal(str(r[3]))>0 and Decimal(str(r[2]))!=0 for r in records)
        prices=[Decimal(str(r[3])) for r in records];vol=sum((abs(Decimal(str(r[2]))) for r in records),Decimal(0));c=candles[start];assert max(prices)==Decimal(c['high']) and min(prices)==Decimal(c['low']) and abs(vol-Decimal(c['volume']))<=Decimal('0.00000001');counts.append(len(records))
    OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','trade_rows':counts,'scope':'Independent arithmetic on same retained exchange responses; not proof of API or trade authenticity/completeness.','input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print('PASS',counts)
if __name__=='__main__':main()
