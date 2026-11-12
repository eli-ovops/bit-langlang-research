"""Read-only public archive staging for historical replay diagnostics."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import requests

from .stage_five_futures import BASE

SYMBOLS=('UNIUSDT','AAVEUSDT','LINKUSDT')
FIRST=pd.Timestamp('2022-04-01',tz='UTC');END=pd.Timestamp('2024-04-01',tz='UTC')


def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args()
    root=Path(a.outdir);root.mkdir(parents=True,exist_ok=False);session=requests.Session();manifest={}
    for symbol in SYMBOLS:
        folder=root/symbol;folder.mkdir();parts=[];receipts=[]
        for month in pd.date_range(FIRST,END-pd.Timedelta(days=1),freq='MS'):
            name=f'{symbol}-5m-{month:%Y-%m}.zip';url=f'{BASE}/{symbol}/5m/{name}'
            response=session.get(url,timeout=40);response.raise_for_status();body=response.content
            (folder/name).write_bytes(body)
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                names=z.namelist()
                if len(names)!=1:raise ValueError('unexpected archive members')
                frame=pd.read_csv(io.BytesIO(z.read(names[0])),header=None,usecols=[0,1,2,3,4])
            if len(frame) and str(frame.iloc[0,0]).strip()=='open_time':frame=frame.iloc[1:]
            parts.append(frame);receipts.append({'url':url,'file':name,'sha256':sha(body)})
        d=pd.concat(parts,ignore_index=True);d.columns=['ts','open','high','low','close']
        for c in d.columns:d[c]=pd.to_numeric(d[c],errors='raise')
        expected=pd.date_range(FIRST,END-pd.Timedelta(minutes=5),freq='5min').asi8//1000000
        if (not np.array_equal(d.ts.to_numpy(),expected) or not np.isfinite(d.to_numpy(dtype=float)).all()
                or (d[['open','high','low','close']]<=0).any().any()
                or (d.low>d[['open','high','close']].min(axis=1)).any()
                or (d.high<d[['open','low','close']].max(axis=1)).any()):raise ValueError(f'{symbol}: invalid OHLC/grid')
        path=root/f'{symbol}_5m.csv.gz';d.to_csv(path,index=False,compression='gzip')
        manifest[symbol]={'bars':len(d),'sha256':sha(path.read_bytes()),'requests':receipts}
        print(symbol,'bars',len(d),flush=True)
    (root/'manifest.json').write_text(json.dumps({'status':'PUBLIC_SOURCE_UNVERIFIED','symbols':manifest},indent=2)+'\n')


if __name__=='__main__':main()
