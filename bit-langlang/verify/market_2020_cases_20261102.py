"""Chart every frozen spring/autumn watch using only pre-decision candles."""
import json
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .season_casebook_20261102 import draw
from .market_season_research_20261102 import sha
DATA=Path('data/market/btc-2020-cross-20261102-02/BTCUSDT-binance-5m.csv.gz');RECORD=Path('data/verify/market-2020-cross-20261102-01/layers.csv');OUT=Path('data/verify/market-2020-watch-cases-20261102-01')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 w=pd.read_csv(RECORD);subset=w[(w.source=='binance_perp')&((w.spring_watch=='YES')|(w.autumn_watch=='YES'))].sort_values('as_of_utc');assert len(subset)==6
 f=pd.read_csv(DATA);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.set_index('time')
 def frame(freq,n):
  x=f.resample(freq).agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('close','size'));x['good']=x.n.eq(n);return x
 d=frame('D',288);h=frame('4h',48);OUT.mkdir();cases=[]
 for i,row in enumerate(subset.itertuples(index=False),1):
  t=pd.Timestamp(row.as_of_utc);daily=d.loc[(d.index>=t-pd.Timedelta(days=56))&(d.index<t)];h4=h.loc[(h.index>=t-pd.Timedelta(days=14))&(h.index<t)]
  assert len(daily)==56 and len(h4)==84 and daily.good.all() and h4.good.all() and daily.index[-1]+pd.Timedelta(days=1)==t and h4.index[-1]+pd.Timedelta(hours=4)==t
  name=f'case{i:02}';fig,axes=plt.subplots(2,1,figsize=(13,7.4),constrained_layout=True);draw(axes[0],daily);draw(axes[1],h4);axes[0].set_title(f'{name}: BTC daily as of {t:%Y-%m-%d %H:%M} UTC',loc='left');axes[1].set_title('BTC 4h, last 14 days; no future bars',loc='left');axes[0].set_ylabel('USDT');axes[1].set_ylabel('USDT');fig.savefig(OUT/(name+'.png'),dpi=140);plt.close(fig)
  cases.append({'name':name,'as_of':t.isoformat(),'spring_watch':row.spring_watch,'autumn_watch':row.autumn_watch,'chart_sha256':sha(OUT/(name+'.png')),'independent_reviewer':'UNKNOWN'})
 (OUT/'manifest.json').write_text(json.dumps({'status':'AS_OF_CHARTS_NO_GROUND_TRUTH','source_sha256':sha(DATA),'input_sha256':sha(RECORD),'cases':cases,'limitations':['Selected watch cases not random; date and known historical context visible.','Not independent human judgment.']},indent=2)+'\n');print(json.dumps(cases,indent=2))
if __name__=='__main__':main()
