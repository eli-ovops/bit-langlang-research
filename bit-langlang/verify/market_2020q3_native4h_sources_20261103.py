"""Post-hoc Bitfinex native-4h sensitivity, with untouched Bitstamp data."""
from pathlib import Path
import hashlib,json
import pandas as pd
import requests
from verify.market_2018_transition_20261102 import read
SRC=Path('data/market/btc-2020q3-usd-cross-20261103-01');OUT=Path('data/market/btc-2020q3native-usd-cross-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    OUT.mkdir(exist_ok=False);a=pd.Timestamp('2020-05-01',tz='UTC');b=pd.Timestamp('2020-11-01',tz='UTC');params={'start':int(a.timestamp()*1000),'end':int(b.timestamp()*1000)-1,'sort':1,'limit':10000};r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:4h:tBTCUSD/hist',params=params,timeout=60);r.raise_for_status();raw=OUT/'bitfinex-native-4h.json';raw.write_bytes(r.content);z=r.json();assert isinstance(z,list) and len(z)<10000 and all(len(q)==6 for q in z);f=pd.DataFrame(z,columns=['ts','open','close','high','low','volume']).sort_values('ts');assert not f.ts.duplicated().any();f.to_csv(OUT/'bitfinex-4h.csv.gz',index=False,compression='gzip');original=SRC/'bitstamp-4h.csv.gz';(OUT/'bitstamp-4h.csv.gz').write_bytes(original.read_bytes());assert sha(original)==sha(OUT/'bitstamp-4h.csv.gz')
    expected=pd.date_range(a,b,inclusive='left',freq='4h');result={}
    for name in ('bitstamp','bitfinex'):
        path=OUT/(name+'-4h.csv.gz');_,h=read(path);result[name]={'bars':len(h),'missing_utc':[x.isoformat() for x in expected.difference(h.index)],'invalid_ohlc':int((~h.good).sum()),'nonpositive_volume':int((h.volume<=0).sum()),'sha256':sha(path)}
    (OUT/'manifest.json').write_text(json.dumps({'sources':result,'bitfinex_url':r.url,'bitfinex_raw_sha256':sha(raw),'scope':'post-hoc native 4h, no hourly-trade completeness proof'},indent=2)+'\n');print(result)
if __name__=='__main__':main()
