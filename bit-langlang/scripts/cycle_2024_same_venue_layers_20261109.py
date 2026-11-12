import csv, gzip, hashlib, json
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
H=3600000
ONE=ROOT/'data/market/btc-2024-usd-cross-20261102-01/bitfinex-1h.json'
FOUR=ROOT/'data/market/btc-2024-usd-cross-20261102-01/bitfinex-4h.csv.gz'
INPUT=ROOT/'data/verify/cycle-2024q2-hour-supplement-20261109-01/summary.json'
OUT=ROOT/'data/verify/cycle-2024q2-same-venue-layers-20261109-01'


def main():
    hours={int(x[0]):x for x in json.loads(ONE.read_text())}
    with gzip.open(FOUR,'rt') as f:
        check={int(r['ts']):tuple(float(r[k]) for k in ('open','high','low','close')) for r in csv.DictReader(f)}
    samples=json.loads(INPUT.read_text())['samples']
    OUT.mkdir(parents=True,exist_ok=False)
    report=[]
    for r in samples:
        if r['status']!='READY':
            report.append({'index':r['index'],'status':'UNKNOWN','reason':r['reason']}); continue
        end=int(datetime.fromisoformat(r['asof']).timestamp()*1000)
        times=list(range(end-168*H,end,H))
        raw=[hours[t] for t in times]
        one=[(float(x[1]),float(x[3]),float(x[4]),float(x[2])) for x in raw]
        four=[]
        for i in range(0,168,4):
            b=one[i:i+4]; c=(b[0][0],max(x[1] for x in b),min(x[2] for x in b),b[-1][3])
            assert c==check[times[i]],(r['index'],times[i])
            four.append(c)
        assert len(one)==168 and len(four)==42 and four[-1][-1]==one[-1][-1]
        factor=100/one[-1][-1]
        fig,axes=plt.subplots(2,1,figsize=(14,8),constrained_layout=True)
        for ax,bars,label in zip(axes,(four,one),('4h (42 bars aggregated from 1h)','1h (168 native bars)')):
            chart(ax,[[v*factor for v in b] for b in bars],-len(bars))
            ax.set_xlabel('Completed '+label.split()[0]+' bars before observation')
            ax.set_title(label)
        fig.suptitle('Bitfinex BTC/USD; cutoff '+r['asof'])
        out=OUT/(str(r['index']).zfill(2)+'.png');fig.savefig(out,dpi=130);plt.close(fig)
        report.append({'index':r['index'],'status':'READY','asof':r['asof'],'bars_1h':168,'bars_4h':42,'matched_archived_4h':42,'png_sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
    assert len(report)==13 and sum(x['status']=='READY' for x in report)==10
    (OUT/'summary.json').write_text(json.dumps({'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ONE,FOUR,INPUT)},'samples':report},indent=2))
    print('10 charts; 420 aggregated OHLC bars matched; 3 UNKNOWN')

if __name__=='__main__': main()
