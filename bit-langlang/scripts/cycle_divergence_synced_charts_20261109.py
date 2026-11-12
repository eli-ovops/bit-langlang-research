import csv,gzip,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart
R=Path(__file__).resolve().parents[1];OUT=R/'data/verify/cycle-divergence-synced-20261109-01'
INPUT=R/'data/verify/cycle-fixed26-btc-market-contrast-20261109-01/all-26.csv'
S={13:['data/market/btc-2022q4-usd-cross-20261103-01/bitstamp-4h.csv.gz','data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv'],21:['data/market/btc-2025q1-usd-cross-20261104-01/bitstamp-4h.csv.gz','data/market/btc-2025q2-usd-cross-20261104-01/bitstamp-4h.csv.gz']}
STEP=14400000

def main():
 with INPUT.open() as f: rows={int(x['index']):x for x in csv.DictReader(f)}
 OUT.mkdir(parents=True,exist_ok=False);out=[]
 for index,paths in S.items():
  src=rows[index];assert src['comparison']=='BTC_UP_OTHERS_MOST_DOWN'
  data={};overlap=0
  for name in paths:
   p=R/name
   with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:
    for row in csv.DictReader(f):
     t=int(row['ts']);v=tuple(float(row[k]) for k in ('open','high','low','close','volume'))
     if t in data:
      assert data[t]==v;overlap+=1
     data[t]=v
  cap=int(datetime.fromisoformat(src['capture']).timestamp()*1000);end=cap-cap%STEP
  assert end<=cap<end+STEP and end%86400000==0
  raw=[data[t] for t in range(end-180*6*STEP,end,STEP)]
  assert all(0<x[2]<=min(x[0],x[3])<=max(x[0],x[3])<=x[1] and x[4]>0 for x in raw)
  days=[(b[0][0],max(v[1] for v in b),min(v[2] for v in b),b[-1][3]) for b in (raw[i:i+6] for i in range(0,len(raw),6))]
  scale=100/days[-1][3];fig,axes=plt.subplots(2,2,figsize=(14,9),constrained_layout=True)
  for ax,seq,title in zip(axes.flat,(days,days[-56:],days[-14:],raw[-42:]),('180 daily','56 daily','14 daily','42 x 4h')):
   chart(ax,[[z*scale for z in x[:4]] for x in seq],-len(seq));ax.set_title(title)
   if title.endswith('4h'):ax.set_xlabel('4h bars before cutoff')
  cutoff=datetime.fromtimestamp(end/1000,timezone.utc).isoformat();fig.suptitle('Bitstamp BTC/USD; cutoff '+cutoff);p=OUT/f'{index:02}.png';fig.savefig(p,dpi=130);plt.close(fig)
  out.append({'index':index,'market_capture':src['capture'],'price_cutoff':cutoff,'price_close':days[-1][3],'prior180_low':min(x[2] for x in days),'prior180_high':max(x[1] for x in days),'up':int(src['up']),'down':int(src['down']),'zero':int(src['zero']),'overlap':overlap,'source_sha256':{p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in paths},'chart_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 (OUT/'summary.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

if __name__=='__main__':main()
