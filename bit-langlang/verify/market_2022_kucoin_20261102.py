"""Separately sourced KuCoin prices, same frozen weekly study; no splicing."""
import hashlib,json,random
from pathlib import Path
import pandas as pd,requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from verify.market_2018_transition_20261102 import read,event
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.season_casebook_20261102 import draw
OUT=Path('data/verify/market-2022-kucoin-20261102-01');BASE='https://api.kucoin.com/api/ua/v2/market/kline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);cuts=pd.to_datetime(['2022-01-01','2022-04-01','2022-07-01','2022-10-01'],utc=True);records=[];receipts=[]
 for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
  params={'symbol':'BTC-USDT','tradeType':'SPOT','interval':'4hour','startAt':int(a.timestamp()),'endAt':int(b.timestamp())-1};r=requests.get(BASE,params=params,timeout=40);r.raise_for_status();p=OUT/f'raw-{i}.json';p.write_bytes(r.content);x=r.json();assert x['code']=='200000' and x['data']['symbol']=='BTC-USDT';records.extend(x['data']['list']);receipts.append({'url':BASE,'params':params,'sha256':sha(p)})
 f=pd.DataFrame([{'ts':int(z[0])*1000,'open':float(z[1]),'high':float(z[2]),'low':float(z[3]),'close':float(z[4])} for z in records]).sort_values('ts');f.to_csv(OUT/'bars-4h.csv.gz',index=False,compression='gzip');d,h=read(OUT/'bars-4h.csv.gz');start,end=cuts[0],cuts[-1];expected=pd.date_range(start,end-pd.Timedelta(hours=4),freq='4h');missing=expected.difference(h.index);assert len(h)+len(missing)==len(expected) and h.good.all()
 times=pd.date_range('2022-03-07','2022-08-29',freq='7D',tz='UTC');rows=[];future=[]
 for t in times:
  rows.append({'as_of_utc':t.isoformat(),**evaluate_extended(d,h,t)});rec={'as_of_utc':t.isoformat(),'first':'UNKNOWN_INPUT','followup':'UNKNOWN'};p=d[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)]
  if len(p)==28 and p.good.all():
   hi,lo=float(p.high.max()),float(p.low.min());ev=event(d,t,hi,lo);rec.update(frozen_upper=hi,frozen_lower=lo,first=ev['status'],first_close=ev.get('event_close'),first_time_utc=ev.get('event_time_utc'),first_days=ev['observed_days'])
   if ev['status'] in ('UPPER_BREAK','LOWER_BREAK'):
    b=pd.Timestamp(ev['event_time_utc']);rec['followup']='NO_RETURN_7D'
    for i in range(7):
     day=b+pd.Timedelta(days=i)
     if day not in d.index or not d.loc[day,'good']:rec['followup']='UNKNOWN_INCOMPLETE';break
     c=float(d.loc[day,'close'])
     if (ev['status']=='UPPER_BREAK' and c<hi) or (ev['status']=='LOWER_BREAK' and c>lo):rec.update(followup='RETURN_INSIDE_SIDE',return_time_utc=(day+pd.Timedelta(days=1)).isoformat(),return_close=c);break
   elif ev['status']=='UNRESOLVED_28D':rec['followup']='NO_BREAK'
  future.append(rec)
 pd.DataFrame(rows).to_csv(OUT/'asof.csv',index=False);pd.DataFrame(future).to_csv(OUT/'future.csv',index=False)
 order=list(times[::2]);random.Random(20220401).shuffle(order);charts=OUT/'blind-charts';charts.mkdir();mapping=[];daily=h.resample('D').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'))
 for i,t in enumerate(order,1):
  a=daily[(daily.index>=t-pd.Timedelta(days=56))&(daily.index<t)];b=h[(h.index>=t-pd.Timedelta(days=14))&(h.index<t)];name=f'K{i:02}.png'
  if len(a)!=56 or not a.n.eq(6).all() or len(b)!=84 or not b.good.all():mapping.append({'case':name,'as_of_utc':t.isoformat(),'status':'UNKNOWN_INCOMPLETE'});continue
  fig,axes=plt.subplots(2,1,figsize=(12,7),constrained_layout=True)
  for ax,z,title in [(axes[0],a,'56 completed daily candles'),(axes[1],b,'84 completed 4-hour candles')]:
   z=z.copy();z[['open','high','low','close']]=z[['open','high','low','close']]/z.close.iloc[0]*100;draw(ax,z);ax.set_xticks([0,len(z)//2,len(z)-1]);ax.set_xticklabels(['oldest','middle','latest']);ax.set_title(title,loc='left');ax.set_ylabel('index')
  fig.savefig(charts/name,dpi=110);plt.close(fig);mapping.append({'case':name,'as_of_utc':t.isoformat(),'status':'COMPLETE','chart_sha256':sha(charts/name)})
 (OUT/'sealed-map.json').write_text(json.dumps(mapping,indent=2)+'\n');files=[Path(__file__),Path('docs/春秋-2022独立时间段与假突破-事前定义-20261102.md'),OUT/'bars-4h.csv.gz',OUT/'asof.csv',OUT/'future.csv',OUT/'sealed-map.json'];(OUT/'manifest.json').write_text(json.dumps({'source':'KuCoin BTC-USDT spot 4h','expected':len(expected),'bars':len(h),'missing_utc':[x.isoformat() for x in missing],'invalid':int((~h.good).sum()),'requests':receipts,'hashes':{str(x):sha(x) for x in files},'charts_complete':sum(x['status']=='COMPLETE' for x in mapping),'limits':['Independent exchange price, not independent human labels.']},indent=2)+'\n');print('bars',len(h),'missing',len(missing),'charts',sum(x['status']=='COMPLETE' for x in mapping))
if __name__=='__main__':main()
