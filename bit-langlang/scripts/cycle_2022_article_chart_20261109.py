import csv, gzip, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verify/cycle-external-2022-20261109-01'
SOURCES=[ROOT/'data/market/btc-2022nine-usd-cross-20261104-01'/f for f in ('bitstamp-4h.csv.gz','bitfinex-4h.csv.gz')]
END=int(datetime(2022,8,2,tzinfo=timezone.utc).timestamp()*1000)
STEP=4*3600*1000


def main():
    stats=[]
    for path in SOURCES:
        with gzip.open(path,'rt') as f:
            rows=list(csv.DictReader(f))
        data={int(x['ts']):x for x in rows}
        assert len(rows)==len(data)
        bars=[]
        for t in range(END-180*6*STEP,END,STEP):
            x=data[t]
            o,h,l,c,v=(float(x[k]) for k in ('open','high','low','close','volume'))
            assert 0<l<=min(o,c)<=max(o,c)<=h and v>0
            bars.append((o,h,l,c))
        daily=[(b[0][0],max(x[1] for x in b),min(x[2] for x in b),b[-1][3]) for b in (bars[i:i+6] for i in range(0,len(bars),6))]
        assert len(daily)==180 and len(bars)==1080
        scale=100/daily[-1][3]
        fig,axes=plt.subplots(2,2,figsize=(14,9),constrained_layout=True)
        for ax,seq,title in zip(axes.flat,(daily,daily[-56:],daily[-14:],bars[-42:]),('180 daily','56 daily','14 daily','42 x 4h')):
            chart(ax,[[v*scale for v in x] for x in seq],-len(seq));ax.set_title(title)
            if title.endswith('4h'):ax.set_xlabel('4h bars before observation')
        fig.suptitle(path.name.split('-')[0]+' BTC/USD before 2022-08-02 00:00 UTC')
        out=OUT/(path.name.split('-')[0]+'-asof.png');fig.savefig(out,dpi=130);plt.close(fig)
        stats.append({'source':str(path.relative_to(ROOT)),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bars_4h':len(bars),'close':daily[-1][3],'min_180':min(x[2] for x in daily),'max_180':max(x[1] for x in daily),'min_56':min(x[2] for x in daily[-56:]),'max_56':max(x[1] for x in daily[-56:]),'png_sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
    (OUT/'price-audit.json').write_text(json.dumps(stats,indent=2))
    print('2 exchanges, 180 days each; 2160 valid 4h candles')

if __name__=='__main__':main()
