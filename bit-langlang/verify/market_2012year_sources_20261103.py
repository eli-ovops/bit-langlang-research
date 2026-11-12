"""Retain official 4h responses independently; gaps and unavailable venues stay empty."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import requests
from verify.market_2018_transition_20261102 import read

OUT=Path('data/market/btc-2012year-usd-cross-20261103-01');A=pd.Timestamp('2011-11-01',tz='UTC');B=pd.Timestamp('2013-02-01',tz='UTC')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir(); expected=pd.date_range(A,B-pd.Timedelta(hours=4),freq='4h');info={}
    for name in ('bitstamp','bitfinex'):
        receipt=[];items=[];failure=None
        try:
            if name=='bitstamp':
                cut=B
                for i in range(4):
                    params={'step':14400,'limit':1000,'end':int(cut.timestamp())};r=requests.get('https://www.bitstamp.net/api/v2/ohlc/btcusd/',params=params,timeout=50);r.raise_for_status();p=OUT/f'bitstamp-{i}.json';p.write_bytes(r.content);z=r.json()['data']['ohlc'];receipt.append({'url':r.url,'sha256':sha(p),'rows':len(z)});items.extend([{'ts':int(x['timestamp'])*1000,**{k:float(x[k]) for k in ('open','high','low','close')}} for x in z])
                    if not z:break
                    next_cut=pd.Timestamp(min(int(x['timestamp']) for x in z),unit='s',tz='UTC')-pd.Timedelta(seconds=1)
                    if next_cut>=cut:raise ValueError('nondecreasing pagination')
                    cut=next_cut
                    if cut<A:break
            else:
                params={'start':int(A.timestamp()*1000),'end':int(B.timestamp()*1000)-1,'limit':10000,'sort':1};r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:4h:tBTCUSD/hist',params=params,timeout=60);r.raise_for_status();p=OUT/'bitfinex-4h.json';p.write_bytes(r.content);z=r.json();assert isinstance(z,list) and (not z or isinstance(z[0],list));receipt.append({'url':r.url,'sha256':sha(p),'rows':len(z)});items=[{'ts':int(x[0]),'open':float(x[1]),'close':float(x[2]),'high':float(x[3]),'low':float(x[4])} for x in z]
        except (requests.RequestException,ValueError,KeyError,AssertionError,TypeError) as exc:failure=type(exc).__name__
        f=pd.DataFrame(items,columns=['ts','open','high','low','close']).sort_values('ts');f=f[(f.ts>=int(A.timestamp()*1000))&(f.ts<int(B.timestamp()*1000))];path=OUT/(name+'-4h.csv.gz')
        if f.ts.duplicated().any():failure='DUPLICATE_TIMESTAMPS'
        if not f.empty and not failure:
            f.to_csv(path,index=False,compression='gzip');_,h=read(path);missing=expected.difference(h.index);extra=h.index.difference(expected);invalid=int((~h.good).sum());assert not len(extra)
        else:
            f.iloc[0:0].to_csv(path,index=False,compression='gzip');missing=expected;invalid=0
        info[name]={'bars':len(f) if not failure else 0,'expected':len(expected),'missing_utc':[t.isoformat() for t in missing],'invalid':invalid,'failure':failure,'requests':receipt,'csv_sha256':sha(path)}
    (OUT/'manifest.json').write_text(json.dumps({'start':A.isoformat(),'end_exclusive':B.isoformat(),'sources':info,'source_script_sha256':sha(Path(__file__))},indent=2)+'\n');print({k:(v['bars'],len(v['missing_utc']),v['invalid'],v['failure']) for k,v in info.items()})
if __name__=='__main__':main()
