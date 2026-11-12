"""Verify retained exchange archives and copy exact 4h files into a new research snapshot."""
from pathlib import Path
import hashlib,io,json,zipfile
import numpy as np
import pandas as pd
from verify.market_2018_transition_20261102 import read

OUT=Path('data/market/btc-2023ma-spot-cross-20261102-01')
ROOT=Path('data/verify')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    info={}; sources={}
    for name in ('binance','kucoin'):
        root=ROOT/f'market-2023-{name}-20261102-01';m=json.loads((root/'manifest.json').read_text());path=root/'bars-4h.csv.gz';assert sha(path)==m['hashes'][str(path)];sources[name]=path;stored=pd.read_csv(path).sort_values('ts').reset_index(drop=True)
        if name=='binance':
            frames=[]
            for item in m['archives']:
                p=Path(item['file']);assert sha(p)==item['sha256']==Path(str(p)+'.CHECKSUM').read_text().split()[0].lower()
                with zipfile.ZipFile(p) as z:
                    assert len(z.namelist())==1;frames.append(pd.read_csv(io.BytesIO(z.read(z.namelist()[0])),header=None,usecols=[0,1,2,3,4]))
            raw=pd.concat(frames,ignore_index=True);raw.columns=['ts','open','high','low','close'];raw=raw.apply(pd.to_numeric).sort_values('ts').reset_index(drop=True)
        else:
            rows=[]
            for i,item in enumerate(m['requests']):
                p=root/f'raw-{i}.json';assert sha(p)==item['sha256'];data=json.loads(p.read_text());assert data['code']=='200000' and data['data']['symbol']=='BTC-USDT';rows.extend(data['data']['list'])
            raw=pd.DataFrame([{'ts':int(z[0])*1000,'open':float(z[1]),'high':float(z[2]),'low':float(z[3]),'close':float(z[4])} for z in rows]).sort_values('ts').reset_index(drop=True)
        assert len(raw)==len(stored) and np.array_equal(raw.ts.to_numpy(),stored.ts.to_numpy()) and np.allclose(raw[['open','high','low','close']].to_numpy(),stored[['open','high','low','close']].to_numpy(),rtol=0,atol=1e-10)
        _,h=read(path);expected=pd.date_range('2023-01-01','2023-11-01',inclusive='left',freq='4h',tz='UTC');missing=expected.difference(h.index);assert not len(h.index.difference(expected))
        info[name]={'bars':len(h),'expected':len(expected),'missing_utc':[t.isoformat() for t in missing],'invalid':int((~h.good).sum()),'original_csv_sha256':sha(path),'original_manifest_sha256':sha(root/'manifest.json'),'raw_reconstructed':True}
    OUT.mkdir()
    for name,path in sources.items():
        with (OUT/(name+'-4h.csv.gz')).open('xb') as f:f.write(path.read_bytes())
        assert sha(OUT/(name+'-4h.csv.gz'))==sha(path)
    (OUT/'manifest.json').write_text(json.dumps({'source':'BTC/USDT spot; previous retained exchange data, selected on known case','start':'2023-01-01T00:00:00+00:00','end_exclusive':'2023-11-01T00:00:00+00:00','sources':info,'source_script_sha256':sha(Path(__file__))},indent=2)+'\n');print({k:(v['bars'],len(v['missing_utc']),v['invalid']) for k,v in info.items()})
if __name__=='__main__':main()
