"""Fixed 2019 spot windows: preserve source and keep observation/future separate."""
import io,zipfile,hashlib,json,random
from pathlib import Path
import numpy as np,pandas as pd,requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from verify.market_2018_transition_20261102 import read,event
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.season_casebook_20261102 import draw

OUT=Path('data/verify/market-2023-binance-20261102-01');DEF=Path('docs/春秋-2023冻结检验与收回时限-事前定义-20261102.md');BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);archives=[];frames=[]
 for month in pd.date_range('2023-01-01','2023-10-01',freq='MS'):
  name=f'BTCUSDT-4h-{month:%Y-%m}.zip';p=OUT/name
  for suffix in ('','.CHECKSUM'):
   r=requests.get(f'{BASE}/{name}{suffix}',timeout=60);r.raise_for_status();(OUT/(name+suffix)).write_bytes(r.content)
  assert sha(p)==(OUT/(name+'.CHECKSUM')).read_text().split()[0].lower()
  with zipfile.ZipFile(p) as z:
   assert len(z.namelist())==1
   f=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])),header=None,usecols=[0,1,2,3,4]);frames.append(f)
  archives.append({'file':str(p),'url':f'{BASE}/{name}','sha256':sha(p),'official_checksum_verified':True})
 f=pd.concat(frames,ignore_index=True);f.columns=['ts','open','high','low','close'];f=f.apply(pd.to_numeric);f.to_csv(OUT/'bars-4h.csv.gz',index=False,compression='gzip');d,h=read(OUT/'bars-4h.csv.gz')
 start=pd.Timestamp('2023-01-01',tz='UTC');end=pd.Timestamp('2023-11-01',tz='UTC');expected=pd.date_range(start,end-pd.Timedelta(hours=4),freq='4h');missing=expected.difference(h.index)
 assert (h.index>=start).all() and (h.index<end).all() and len(h)+len(missing)==len(expected)
 times=pd.date_range('2023-03-06','2023-08-28',freq='7D',tz='UTC');rows=[];future=[]
 for t in times:
  x=evaluate_extended(d,h,t);rows.append({'as_of_utc':t.isoformat(),**x});record={'as_of_utc':t.isoformat(),'first':'UNKNOWN_INPUT','followup':'UNKNOWN'}
  p=d[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)]
  if len(p)==28 and p.good.all():
   hi,lo=float(p.high.max()),float(p.low.min());ev=event(d,t,hi,lo);record.update(frozen_upper=hi,frozen_lower=lo,first=ev['status'],first_close=ev.get('event_close'),first_time_utc=ev.get('event_time_utc'),first_days=ev['observed_days'])
   if ev['status'] in ('UPPER_BREAK','LOWER_BREAK'):
    b=pd.Timestamp(ev['event_time_utc']);record['followup']='NO_RETURN_7D'
    for i in range(7):
     day=b+pd.Timedelta(days=i)
     if day not in d.index or not d.loc[day,'good']:
      record['followup']='UNKNOWN_INCOMPLETE';break
     c=float(d.loc[day,'close'])
     if (ev['status']=='UPPER_BREAK' and c<hi) or (ev['status']=='LOWER_BREAK' and c>lo):
      record.update(followup='RETURN_INSIDE_SIDE',return_time_utc=(day+pd.Timedelta(days=1)).isoformat(),return_close=c);break
   elif ev['status']=='UNRESOLVED_28D':record['followup']='NO_BREAK'
  future.append(record)
 pd.DataFrame(rows).to_csv(OUT/'asof.csv',index=False);pd.DataFrame(future).to_csv(OUT/'future.csv',index=False)
 # Selection is independent of rule candidate; deterministic shuffle, mapping sealed separately.
 sample=list(times[::2]);assert len(sample)==13
 order=list(sample);random.Random(20230306).shuffle(order);chartdir=OUT/'blind-charts';chartdir.mkdir();mapping=[]
 for i,t in enumerate(order,1):
  daily=h.resample('D').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'))
  a=daily[(daily.index>=t-pd.Timedelta(days=56))&(daily.index<t)];b=h[(h.index>=t-pd.Timedelta(days=14))&(h.index<t)]
  name=f'C{i:02}.png'
  if len(a)!=56 or not a.n.eq(6).all() or len(b)!=84 or not b.good.all():mapping.append({'case':name,'as_of_utc':t.isoformat(),'status':'UNKNOWN_INCOMPLETE'});continue
  # Axis labels are relative bar offsets; prices normalized separately for clarity.
  fig,axes=plt.subplots(2,1,figsize=(12,7),constrained_layout=True)
  for ax,z,title in [(axes[0],a,'56 completed daily candles'),(axes[1],b,'84 completed 4-hour candles')]:
   z=z.copy();z[['open','high','low','close']]=z[['open','high','low','close']]/z.close.iloc[0]*100;draw(ax,z);ax.set_xticks([0,len(z)//2,len(z)-1]);ax.set_xticklabels(['oldest','middle','latest']);ax.set_title(title,loc='left');ax.set_ylabel('index')
  fig.savefig(chartdir/name,dpi=110);plt.close(fig);mapping.append({'case':name,'as_of_utc':t.isoformat(),'status':'COMPLETE','chart_sha256':sha(chartdir/name)})
 (OUT/'sealed-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
 files=[DEF,Path(__file__),OUT/'bars-4h.csv.gz',OUT/'asof.csv',OUT/'future.csv',OUT/'sealed-map.json',Path('verify/market_2020_cross_20261102.py'),Path('verify/market_multilevel_20261102.py'),Path('verify/market_2018_transition_20261102.py')]
 (OUT/'manifest.json').write_text(json.dumps({'status':'HISTORICAL_PRICE_RESEARCH_NO_HUMAN_LABELS','source':'Binance BTCUSDT spot 4h monthly archives','start':start.isoformat(),'end_exclusive':end.isoformat(),'expected':len(expected),'bars':len(h),'missing_utc':[x.isoformat() for x in missing],'invalid_bars':int((~h.good).sum()),'archives':archives,'hashes':{str(p):sha(p) for p in files},'weekly_points':len(times),'fixed_manual_sample':len(sample),'limits':['Not independently human labelled.','Future event and 7-day return are proxies, not truth.','Familiar public history, not strictly blind.']},indent=2)+'\n');print('bars',len(h),'missing',len(missing),'invalid',int((~h.good).sum()),'points',len(times),'charts',len(mapping))
if __name__=='__main__':main()
