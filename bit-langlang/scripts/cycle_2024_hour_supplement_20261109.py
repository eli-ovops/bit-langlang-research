import csv, gzip, hashlib, json
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'data/market/btc-2024-usd-cross-20261102-01/bitfinex-1h.json'
Q=ROOT/'data/market/btc-2024q1-usd-cross-20261104-01/bitfinex-1h.csv.gz'
S=ROOT/'data/verify/cycle-2024q2-phase-20261104-02/bitstamp-4h.csv'
I=ROOT/'data/verify/cycle-2024q2-near-time-20261109-01/asof.csv'
OUT=ROOT/'data/verify/cycle-2024q2-hour-supplement-20261109-01'
H=3600000


def main():
    bars={int(x[0]):tuple(map(float,x[1:])) for x in json.loads(P.read_text())}
    assert len(bars)==len(json.loads(P.read_text()))
    overlap=0
    with gzip.open(Q,'rt') as f:
        for r in csv.DictReader(f):
            t=int(r['ts']); v=tuple(float(r[k]) for k in ('open','close','high','low','volume'))
            if t in bars:
                assert bars[t]==v
                overlap+=1
            bars[t]=v
    for t,(o,c,h,l,v) in bars.items():
        assert t%H==0 and 0<l<=min(o,c)<=max(o,c)<=h and v>=0
    with S.open() as f:
        stamp={int(r['ts']):float(r['close']) for r in csv.DictReader(f)}
    with I.open() as f:
        rows=list(csv.DictReader(f))
    OUT.mkdir(parents=True,exist_ok=False)
    result=[]
    for r in rows:
        item={'index':int(r['index']),'asof':r['near_asof_utc'],'status':'UNKNOWN','reason':r['reason']}
        if r['status']!='READY':
            result.append(item);continue
        end=int(datetime.fromisoformat(r['near_asof_utc']).timestamp()*1000)
        missing=[t for t in range(end-168*H,end,H) if t not in bars]
        item['missing_utc']=[datetime.fromtimestamp(t/1000,datetime.fromisoformat(r['near_asof_utc']).tzinfo).isoformat() for t in missing]
        if missing:
            item['reason']='MISSING_HOURLY_BARS'; result.append(item);continue
        hourly=[bars[t] for t in range(end-168*H,end,H)]
        pairs=[(bars[t+3*H][1],stamp[t]) for t in range(end-168*H,end,4*H) if t in stamp]
        item.update(status='READY',reason='',paired_4h=len(pairs),max_abs_close_diff_pct=max((abs(a/b-1)*100 for a,b in pairs),default=None))
        f=100/hourly[-1][1]
        candles=[[o*f,h*f,l*f,c*f] for o,c,h,l,v in hourly]
        fig,ax=plt.subplots(figsize=(14,4.5),constrained_layout=True)
        chart(ax,candles,-168);ax.set_xlabel('Completed 1h bars before observation');ax.set_title('Bitfinex BTC/USD — 168 completed 1h bars; cutoff '+r['near_asof_utc'])
        path=OUT/(str(item['index']).zfill(2)+'.png');fig.savefig(path,dpi=130);plt.close(fig)
        item['png_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();result.append(item)
    assert len(result)==13 and sum(x['status']=='READY' for x in result)==10
    (OUT/'summary.json').write_text(json.dumps({'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (P,Q,S,I)},'same_source_overlaps':overlap,'samples':result},indent=2))
    print('10 charts; 1 missing hourly data; 2 article UNKNOWN; overlap',overlap)

if __name__=='__main__': main()
