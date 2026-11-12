"""Reconstruct exchange 4h snapshots directly from retained public responses."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
DATA=Path('data/market/btc-2012year-usd-cross-20261103-01');OUT=Path('data/verify/market-2012year-source-audit-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    m=json.loads((DATA/'manifest.json').read_text());A=pd.Timestamp(m['start']).value//10**6;B=pd.Timestamp(m['end_exclusive']).value//10**6;results={};files=[Path(__file__),DATA/'manifest.json']
    for name in ('bitstamp','bitfinex'):
        info=m['sources'][name];assert not info['failure'];rows=[]
        for i,receipt in enumerate(info['requests']):
            p=DATA/(f'bitstamp-{i}.json' if name=='bitstamp' else 'bitfinex-4h.json');assert sha(p)==receipt['sha256'];files.append(p);z=json.loads(p.read_text())
            if name=='bitstamp':rows.extend({'ts':int(q['timestamp'])*1000,**{k:float(q[k]) for k in ('open','high','low','close')}} for q in z['data']['ohlc'])
            else:rows.extend({'ts':int(q[0]),'open':float(q[1]),'close':float(q[2]),'high':float(q[3]),'low':float(q[4])} for q in z)
        a=pd.DataFrame(rows,columns=['ts','open','high','low','close']);a=a[(a.ts>=A)&(a.ts<B)].sort_values('ts').reset_index(drop=True);p=DATA/(name+'-4h.csv.gz');assert sha(p)==info['csv_sha256'];files.append(p);b=pd.read_csv(p).sort_values('ts').reset_index(drop=True);assert len(a)==len(b)==info['bars'] and np.array_equal(a.ts.to_numpy(),b.ts.to_numpy()) and np.allclose(a[['open','high','low','close']].to_numpy(),b[['open','high','low','close']].to_numpy(),rtol=0,atol=1e-10);results[name]=len(a)
    OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','raw_to_4h_rows':results,'scope':'Reconstruction of received responses only; not independent confirmation of exchange price authenticity.','input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print('PASS',results)
if __name__=='__main__':main()
