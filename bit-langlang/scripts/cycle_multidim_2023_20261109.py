import csv,gzip,hashlib,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[ROOT/x for x in ('data/market/btc-2022nine-usd-cross-20261104-01/bitstamp-4h.csv.gz','data/market/btc-2022q4-usd-cross-20261103-01/bitstamp-4h.csv.gz','data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv')]
SUMMARY=ROOT/'data/verify/cycle-market-archive-corrected-20261109-01/summary.json'
OUT=ROOT/'data/verify/cycle-multidim-2023-two-weeks-20261109-01'


def main():
    raw={};overlap=0
    for path in SOURCES:
        seen=set()
        with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as f:
            for r in csv.DictReader(f):
                t=datetime.fromtimestamp(int(r['ts'])/1000,timezone.utc);assert t not in seen;seen.add(t)
                v=tuple(float(r[k]) for k in ('open','high','low','close','volume'));o,h,l,c,vol=v
                if not(all(math.isfinite(x) and x>0 for x in v) and l<=min(o,c)<=max(o,c)<=h):raise ValueError('INVALID_4H')
                if t in raw:
                    overlap+=1
                    if raw[t]!=v:raise ValueError('OVERLAP_MISMATCH')
                raw[t]=v
    records=json.loads(SUMMARY.read_text());chosen=[x for x in records if x['index'] in (7,8)];assert len(chosen)==2 and all(x['status']=='DATA_READY' for x in chosen)
    OUT.mkdir(parents=True,exist_ok=False);result=[]
    for r in chosen:
        cap=datetime.fromisoformat(r['capture_utc']);end=cap.replace(hour=0,minute=0,second=0,microsecond=0);days=[]
        for i in range(180,0,-1):
            dt=end-timedelta(days=i);b=[raw.get(dt+timedelta(hours=4*j)) for j in range(6)]
            if any(x is None for x in b):raise ValueError('INCOMPLETE_180_DAYS')
            days.append({'date_utc':dt.isoformat(),'open':b[0][0],'high':max(x[1] for x in b),'low':min(x[2] for x in b),'close':b[-1][3]})
        with (OUT/f"{r['index']:02}.csv").open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(days[0]));w.writeheader();w.writerows(days)
        scale=100/days[-1]['close'];a=[[d[k]*scale for k in ('open','high','low','close')] for d in days];fig,axes=plt.subplots(3,1,figsize=(14,10),constrained_layout=True)
        for ax,n in zip(axes,(180,56,14)):chart(ax,a[-n:],-n);ax.set_title(f'{n} completed daily candles')
        fig.suptitle(f"Observation {r['as_of_utc'][:10]}: latest completed daily candles before market snapshot")
        fig.savefig(OUT/f"{r['index']:02}.png",dpi=130,metadata={'Software':'Matplotlib'});plt.close(fig)
        receipt=ROOT/f"data/verify/cycle-report-archive-20261109-01/{r['index']-2:02}/receipt.json";article=json.loads(receipt.read_text());pub=datetime.fromisoformat(article['published_time'].replace('Z','+00:00'));acap=datetime.fromisoformat(article['capture_utc']);assert pub<=acap<=cap
        result.append({'index':r['index'],'observation_utc':r['as_of_utc'],'market_capture_utc':r['capture_utc'],'price_end_utc':end.isoformat(),'last_close':days[-1]['close'],'min180':min(x['low'] for x in days),'max180':max(x['high'] for x in days),'min56':min(x['low'] for x in days[-56:]),'max56':max(x['high'] for x in days[-56:]),'min14':min(x['low'] for x in days[-14:]),'max14':max(x['high'] for x in days[-14:]),'sample_up':r['count_up'],'sample_down':r['count_down'],'sample_zero':r['count_zero'],'article_capture_utc':article['capture_utc'],'article_published_utc':article['published_time'],'article_url':article['archive_url']})
    (OUT/'summary.json').write_text(json.dumps({'overlapping_4h':overlap,'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*SOURCES,SUMMARY]},'points':result},indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
