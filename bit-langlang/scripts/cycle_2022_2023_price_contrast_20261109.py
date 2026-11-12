import base64, csv, gzip, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]
S=[R/'data/market/btc-2022nine-usd-cross-20261104-01/bitstamp-4h.csv.gz',R/'data/market/btc-2022q4-usd-cross-20261103-01/bitstamp-4h.csv.gz',R/'data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv']
OUT=R/'data/verify/cycle-2022-2023-contrast-20261109-01'
STEP=14400000

def main():
    bars={};overlap=0
    for p in S:
        with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
            for x in csv.DictReader(f):
                t=int(x['ts']); v=tuple(float(x[k]) for k in ('open','high','low','close','volume'))
                assert t%STEP==0 and 0<v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1] and v[4]>=0
                if t in bars:
                    assert bars[t]==v
                    overlap+=1
                bars[t]=v
    observations=[]
    for dt in ((2022,8,2),(2023,1,22)):
        end=int(datetime(*dt,tzinfo=timezone.utc).timestamp()*1000)
        d={'asof':datetime(*dt,tzinfo=timezone.utc).isoformat()}
        for days in (180,56,14,7):
            values=[bars[t] for t in range(end-days*6*STEP,end,STEP)]
            assert len(values)==days*6 and all(v[4]>0 for v in values)
            d[str(days)]={'first_open':values[0][0],'last_close':values[-1][3],'low':min(x[2] for x in values),'high':max(x[1] for x in values)}
        observations.append(d)
    p=R/'data/verify/cycle-report-archive-20261109-01/02/archive.html'
    receipt=json.loads((p.parent/'receipt.json').read_text())
    got=base64.b32encode(hashlib.sha1(p.read_bytes()).digest()).decode()
    assert got!=receipt['cdx_digest']
    OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'summary.json').write_text(json.dumps({'sources_sha256':{str(x.relative_to(R)):hashlib.sha256(x.read_bytes()).hexdigest() for x in S},'overlaps_equal':overlap,'observations':observations,'article_2023':{'original_sha1_base32':got,'cdx_digest':receipt['cdx_digest'],'comparison':'decoded_body_vs_cdx_raw_not_equivalent','mismatch':True,'source_receipt':str((p.parent/'receipt.json').relative_to(R))}},indent=2))
    print('Both 180-day windows complete; same-source overlaps:',overlap,'decoded-body and raw-CDX digest differ; compare raw response separately')

if __name__=='__main__': main()
