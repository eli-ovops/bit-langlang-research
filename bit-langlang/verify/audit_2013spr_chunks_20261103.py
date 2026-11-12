"""Independently verify retained chunk responses and 1h-to-4h reconstruction."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
DATA=Path('data/market/btc-2013sprchunk-usd-cross-20261103-01');OLD=Path('data/market/btc-2013spr-usd-cross-20261102-01');OUT=Path('data/verify/market-2013spr-chunks-independent-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    manifest=json.loads((DATA/'manifest.json').read_text());rows={};files=[Path(__file__),DATA/'manifest.json',DATA/'bitfinex-4h.csv.gz',OLD/'bitfinex-4h.csv.gz']
    for i,item in enumerate(manifest['sources']['bitfinex']['requests']):
        p=DATA/f'bitfinex-1h-{i}.json';assert sha(p)==item['sha256'];files.append(p)
        for q in json.loads(p.read_text()):
            ts=int(q[0]);assert ts not in rows;rows[ts]=[float(q[1]),float(q[3]),float(q[4]),float(q[2])]
    out=pd.read_csv(DATA/'bitfinex-4h.csv.gz');old=pd.read_csv(OLD/'bitfinex-4h.csv.gz');assert out.equals(old)
    for r in out.itertuples():
        z=[rows[int(r.ts+i*3600000)] for i in range(4)];v=[z[0][0],max(x[1] for x in z),min(x[2] for x in z),z[-1][3]];assert np.allclose(v,[r.open,r.high,r.low,r.close],rtol=0,atol=1e-10)
    assert len(out)==manifest['sources']['bitfinex']['bars'] and not manifest['sources']['bitfinex']['conflicting_hourly_utc'];OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','hourly_rows':len(rows),'aggregated_4h':len(out),'old_4h_equal':True,'scope':'Same-venue responses only, not independent price authenticity.','input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print('PASS',len(rows),len(out),'old_equal')
if __name__=='__main__':main()
