import csv,gzip,hashlib,json
from pathlib import Path
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart
R=Path(__file__).resolve().parents[1]
S=[R/'data/market/btc-2022nine-usd-cross-20261104-01/bitstamp-4h.csv.gz',R/'data/market/btc-2022q4-usd-cross-20261103-01/bitstamp-4h.csv.gz',R/'data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv']
M=R/'data/verify/cycle-2023-2025-gzip-recovery-20261109-01/summary.json'
O=R/'data/verify/cycle-2023-restored-context-20261109-01'
STEP=14400000

def main():
 bars={};overlap=0
 for p in S:
  with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
   for r in csv.DictReader(f):
    t=int(r['ts']);v=tuple(float(r[k]) for k in ('open','high','low','close','volume'))
    if t in bars:
     assert bars[t]==v;overlap+=1
    bars[t]=v
 samples=[x for x in json.loads(M.read_text()) if x['status']=='READY'];assert len(samples)==3
 O.mkdir(parents=True,exist_ok=False);result=[]
 for r in samples:
  end=int(datetime.fromisoformat(r['asof']).timestamp()*1000)
  raw=[bars[t] for t in range(end-180*6*STEP,end,STEP)]
  assert all(0<x[2]<=min(x[0],x[3])<=max(x[0],x[3])<=x[1] and x[4]>0 for x in raw)
  daily=[(z[0][0],max(x[1] for x in z),min(x[2] for x in z),z[-1][3]) for z in (raw[i:i+6] for i in range(0,len(raw),6))];assert len(daily)==180
  fac=100/daily[-1][3];fig,axes=plt.subplots(2,2,figsize=(14,9),constrained_layout=True)
  for ax,seq,title in zip(axes.flat,(daily,daily[-56:],daily[-14:],raw[-42:]),('180 daily','56 daily','14 daily','42 x 4h')):
   chart(ax,[[v*fac for v in x[:4]] for x in seq],-len(seq));ax.set_title(title)
   if title.endswith('4h'):ax.set_xlabel('4h bars before observation')
  fig.suptitle('Bitstamp BTC/USD cutoff '+r['asof']);p=O/f"{r['index']:02}.png";fig.savefig(p,dpi=130);plt.close(fig)
  result.append({'index':r['index'],'asof':r['asof'],'close':daily[-1][3],'low180':min(x[2] for x in daily),'high180':max(x[1] for x in daily),'low7':min(x[2] for x in raw[-42:]),'high7':max(x[1] for x in raw[-42:]),'market':[r['up'],r['down'],r['zero']],'png_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 (O/'summary.json').write_text(json.dumps({'overlaps_checked':overlap,'sources_sha256':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in S+[M]},'samples':result},indent=2))
 print(json.dumps(result))

if __name__=='__main__':main()
