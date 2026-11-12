import csv,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

R=Path(__file__).resolve().parents[1];OUT=R/'data/verify/cycle-dual-market-dryrun-20261109-01'
BIT=R/'data/verify/cycle-forward-180day-prehistory-20261109-01/response.json'
KDAY=R/'data/verify/cycle-kraken-180day-prehistory-20261109-01/response.json'
KFOUR=R/'data/verify/cycle-recent-four-days-20261109-01/kraken-4h.csv'
T=int(datetime(2026,11,9,tzinfo=timezone.utc).timestamp()); DAY=86400


def main():
 b={int(x[0])//1000:tuple(float(x[i]) for i in (1,3,4,2,5)) for x in json.loads(BIT.read_text())}
 j=json.loads(KDAY.read_text());k={int(x[0]):tuple(float(x[i]) for i in (1,2,3,4,6)) for x in j['result']['XXBTZUSD']}
 with KFOUR.open() as f:
  k4={int(datetime.fromisoformat(x['time_utc']).timestamp()):tuple(float(x[i]) for i in ('open','high','low','close','volume')) for x in csv.DictReader(f)}
 bd=[]
 for day in range(T-180*DAY,T,DAY):
  v=[b[day+i*3600] for i in range(24)];bd.append((v[0][0],max(x[1] for x in v),min(x[2] for x in v),v[-1][3]))
 kd=[k[day][:4] for day in range(T-180*DAY,T,DAY)]
 b4=[]
 for t in range(T-42*14400,T,14400):
  v=[b[t+i*3600] for i in range(4)];b4.append((v[0][0],max(x[1] for x in v),min(x[2] for x in v),v[-1][3]))
 kk4=[k4[t][:4] for t in range(T-42*14400,T,14400)]
 assert len(bd)==len(kd)==180 and len(b4)==len(kk4)==42
 assert bd[-1][3]==b4[-1][3] and kd[-1][3]==kk4[-1][3]
 assert all(0<x[2]<=min(x[0],x[3])<=max(x[0],x[3])<=x[1] for x in bd+kd+b4+kk4)
 OUT.mkdir(parents=True,exist_ok=False);result=[]
 for name,daily,four in [('bitfinex',bd,b4),('kraken',kd,kk4)]:
  fig,axes=plt.subplots(2,2,figsize=(14,9),constrained_layout=True);scale=100/daily[-1][3]
  for ax,seq,title in zip(axes.flat,(daily,daily[-56:],daily[-14:],four),('180 daily','56 daily','14 daily','42 x 4h')):
   chart(ax,[[z*scale for z in x] for x in seq],-len(seq));ax.set_title(title)
   if title.endswith('4h'):ax.set_xlabel('4h bars before observation')
  fig.suptitle(name+' BTC/USD historical dry run; cutoff 2026-11-09 00:00 UTC')
  path=OUT/(name+'.png');fig.savefig(path,dpi=130);plt.close(fig)
  result.append({'source':name,'last_close':daily[-1][3],'daily_bars':len(daily),'four_hour_bars':len(four),'png_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 (OUT/'summary.json').write_text(json.dumps({'asof':'2026-11-09T00:00:00Z','is_prospective_sample':False,'inputs_sha256':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BIT,KDAY,KFOUR)},'results':result},indent=2))
 print(json.dumps(result))

if __name__=='__main__':main()
