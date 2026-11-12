"""Earliest two watches per direction, historical-only charts; descriptive selection."""
from pathlib import Path
import hashlib,json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from verify.season_casebook_20261102 import draw

DATA=Path('data/market/btc-2018-spot-cross-20261102-02/binance-spot-4h.csv.gz')
EVENTS=Path('data/verify/market-2018-transitions-20261102-01/events.csv')
OUT=Path('data/verify/market-2018-transition-cases-20261102-01')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 e=pd.read_csv(EVENTS);e=e[(e.source=='binance')&(e.watch_state=='YES')].sort_values('as_of_utc').groupby('watch').head(2).sort_values('as_of_utc')
 f=pd.read_csv(DATA);f.index=pd.to_datetime(f.ts,unit='ms',utc=True)
 daily=f.resample('D').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'))
 OUT.mkdir();cases=[]
 for r in e.itertuples():
  t=pd.Timestamp(r.as_of_utc);d=daily[(daily.index>=t-pd.Timedelta(days=56))&(daily.index<t)];h=f[(f.index>=t-pd.Timedelta(days=14))&(f.index<t)]
  assert len(d)==56 and d.n.eq(6).all() and len(h)==84 and h.index[-1]+pd.Timedelta(hours=4)==t
  fig,axes=plt.subplots(2,1,figsize=(13,7.4),constrained_layout=True);draw(axes[0],d);draw(axes[1],h)
  axes[0].set_title(f'BTC USDT spot daily, 56 days BEFORE {t:%Y-%m-%d %H:%M} UTC',loc='left');axes[1].set_title('BTC USDT spot 4h, 14 days BEFORE observation',loc='left')
  for ax in axes:ax.set_ylabel('USDT')
  path=OUT/(t.strftime('%Y-%m-%d')+'-'+r.watch+'.png');fig.savefig(path,dpi=140);plt.close(fig)
  cases.append({'as_of_utc':r.as_of_utc,'research_watch':r.watch,'chart':str(path),'sha256':digest(path),'last_daily_close_end':t.isoformat(),'independent_human_label':'UNKNOWN'})
 (OUT/'manifest.json').write_text(json.dumps({'cases':cases,'selection':'Earliest two Binance watches of each direction; concrete chart sampling specified after event results were visible.','limits':['No future bars shown.','Charts are for review; historical labels not independently adjudicated.'],'inputs':{str(DATA):digest(DATA),str(EVENTS):digest(EVENTS),str(Path(__file__)):digest(Path(__file__))}},indent=2)+'\n');print(json.dumps(cases,indent=2))
if __name__=='__main__':main()
