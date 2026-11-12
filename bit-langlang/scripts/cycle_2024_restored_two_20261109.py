import csv,gzip,hashlib,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
SRC=[ROOT/p for p in ('data/market/btc-2023nov-usd-cross-20261103-01/bitstamp-4h.csv.gz','data/verify/cycle-2023q4-phase-20261104-01/bitstamp-4h.csv','data/market/btc-2024q1-usd-cross-20261104-01/bitstamp-4h.csv.gz','data/verify/cycle-2024q2-phase-20261104-02/bitstamp-4h.csv')]
REC=ROOT/'data/verify/cycle-2024-gzip-recovery-20261109-01/summary.json'
PREV=ROOT/'data/verify/cycle-2024q2-reports-20261109-01'
OUT=ROOT/'data/verify/cycle-2024q2-restored-two-20261109-01'
STEP=14400000

def main():
    bars={};overlaps=0
    for p in SRC:
        with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
            for r in csv.DictReader(f):
                t=int(r['ts']); v=tuple(float(r[k]) for k in ('open','high','low','close','volume'))
                if t in bars:
                    assert bars[t]==v;overlaps+=1
                bars[t]=v
    records=json.loads(REC.read_text());old=json.loads((PREV/'summary.json').read_text())
    OUT.mkdir(parents=True,exist_ok=False);results=[]
    for n in (2,6):
        r=next(x for x in records if x['source']==PREV.name and x['index']==n);assert r['status']=='MATCH'
        original=next(x for x in old if x['index']==n)
        cap=datetime.fromisoformat(original['capture_utc']); t=cap.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        assert cap<t<datetime.fromisoformat(original['as_of_utc'])
        end=int(t.timestamp()*1000)
        x=[bars[z] for z in range(end-180*6*STEP,end,STEP)]
        assert len(x)==1080 and all(0<v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1] and v[4]>0 for v in x)
        day=[(b[0][0],max(v[1] for v in b),min(v[2] for v in b),b[-1][3]) for b in (x[i:i+6] for i in range(0,len(x),6))]
        source=BeautifulSoup((PREV/f'{n:02d}.html').read_bytes(),'html.parser')
        pub=datetime.fromisoformat(source.find('meta',attrs={'property':'article:published_time'})['content'].replace('Z','+00:00'))
        assert pub<cap<t
        scale=100/day[-1][3];fig,axes=plt.subplots(2,2,figsize=(14,9),constrained_layout=True)
        for ax,b,title in zip(axes.flat,(day,day[-56:],day[-14:],x[-42:]),('180 daily','56 daily','14 daily','42 x 4h')):
            chart(ax,[[v*scale for v in z[:4]] for z in b],-len(b));ax.set_title(title)
            if title.endswith('4h'):ax.set_xlabel('4h bars before observation')
        fig.suptitle('Bitstamp BTC/USD — cutoff '+t.isoformat());p=OUT/f'{n:02d}.png';fig.savefig(p,dpi=130);plt.close(fig)
        results.append({'index':n,'original_weekly':original['as_of_utc'],'article_published':pub.isoformat(),'capture':cap.isoformat(),'asof':t.isoformat(),'close':day[-1][3],'low180':min(v[2] for v in day),'high180':max(v[1] for v in day),'low7':min(v[2] for v in x[-42:]),'high7':max(v[1] for v in x[-42:]),'png_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    assert len(results)==2
    (OUT/'summary.json').write_text(json.dumps({'inputs_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SRC+[REC]},'same_venue_overlap_checked':overlaps,'records':results},indent=2))
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
