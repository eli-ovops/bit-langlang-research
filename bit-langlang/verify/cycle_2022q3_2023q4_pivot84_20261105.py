"""Full-period as-of pivot evidence. No phase, trading or ground-truth claims."""
from pathlib import Path
import hashlib,json
import pandas as pd,requests
from verify.market_2018_transition_20261102 import read
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
from verify.cycle_2021q1_2024q4_evidence_20261104 import future21
from verify.cycle_pivot_asof_20261105 import facts
SPEC=Path('docs/周期研究-2022三季度与2023四季度-局部结构全期定义-20261105.md');RAW=Path('data/market/kraken-xbtusd-native4h-20261104-01/XBTUSD_240.csv');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
JOBS=[('2022q3','2022-07-01','2022-10-01'),('2023q4','2023-10-01','2024-01-01')]
def main():
 for label,start,end in JOBS:
  out=Path('data/verify/cycle-'+label+'-pivot84-20261105-02');assert not out.exists();out.mkdir(parents=True);A=pd.Timestamp(start,tz='UTC');B=pd.Timestamp(end,tz='UTC');lo=A-pd.Timedelta(days=84);hi=B+pd.Timedelta(days=28);grid=pd.date_range(lo,hi,freq='4h',inclusive='left');cut=hi;raw=[];receipts=[]
  for i in range(2):
   params={'step':14400,'limit':1000,'end':int(cut.timestamp())};p=out/f'bitstamp-{i}.json';url=requests.Request('GET','https://www.bitstamp.net/api/v2/ohlc/btcusd/',params=params).prepare().url
   if label=='2022q3':p.write_bytes((out.parent/'cycle-2022q3-pivot84-20261105-01'/f'bitstamp-{i}.json').read_bytes());origin='retained_from_failed_calculation';items=json.loads(p.read_text())['data']['ohlc']
   else:
    response=requests.get('https://www.bitstamp.net/api/v2/ohlc/btcusd/',params=params,timeout=60);response.raise_for_status();p.write_bytes(response.content);url=response.url;origin='fresh_response';items=response.json()['data']['ohlc']
   assert items;raw.extend(items);receipts.append({'url':url,'sha256':sha(p),'rows':len(items),'origin':origin});cut=pd.Timestamp(min(int(x['timestamp']) for x in items),unit='s',tz='UTC')-pd.Timedelta(seconds=1)
  assert cut<lo
  f=pd.DataFrame(raw).rename(columns={'timestamp':'ts'});f.ts=pd.to_numeric(f.ts)*1000
  for c in ('open','high','low','close','volume'):f[c]=pd.to_numeric(f[c])
  f=f[(f.ts>=lo.timestamp()*1000)&(f.ts<hi.timestamp()*1000)].sort_values('ts');assert not f.ts.duplicated().any();f[['ts','open','high','low','close','volume']].to_csv(out/'bitstamp-4h.csv',index=False)
  assert sha(RAW)==json.loads(RAW.with_name('manifest.json').read_text())['raw_sha256'];k=pd.read_csv(RAW,header=None,names=['sec','open','high','low','close','volume','trades']);assert k.sec.is_monotonic_increasing and not k.sec.duplicated().any();k=k[(k.sec>=lo.timestamp())&(k.sec<hi.timestamp())].copy();k['ts']=k.sec*1000;k[['ts','open','high','low','close','volume']].to_csv(out/'kraken-4h.csv',index=False)
  src={};quality={}
  for name in ('bitstamp','kraken'):
   _,h=read(out/(name+'-4h.csv'));h=h.reindex(grid);h['good']=h.good.fillna(False)&h.volume.gt(0);quality[name]=[t.isoformat() for t in h.index[~h.good]];d=h.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('good','size'),ok=('good','sum'));d['good']=d.n.eq(6)&d.ok.eq(6);src[name]=(d,h)
  a,b=(src[n][1] for n in ('bitstamp','kraken'));bad=pd.Series(False,index=grid)
  for c in ('high','low'):bad|=(a[c]/b[c]>1.1)|(a[c]/b[c]<.9)
  flags=grid[bad];bad_days=flags.floor('D').unique()
  for d,h in src.values():d.loc[d.index.isin(bad_days),'good']=False;h.loc[h.index.floor('D').isin(bad_days),'good']=False
  rows=[];outcomes=[];weekly=[]
  for name,(d,h) in src.items():
   for t in pd.date_range(A,B,freq='D',inclusive='left'):
    base=asof(d,h,t);window=d[(d.index>=t-pd.Timedelta(days=84))&(d.index<t)];valid=len(window)==84 and window.good.all();r=facts(d,h,t) if valid else {**base,'long84':'UNKNOWN','swing':'UNKNOWN','pivot_reason':'INCOMPLETE_84D'}
    dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==base
    if valid:assert facts(dd,hh,t)==r
    rows.append({'source':name,'as_of_utc':t.isoformat(),**r,'phase':'UNKNOWN','sentiment':'UNKNOWN'})
    fwd=future21(d,t,base) if base['range_status']=='OK' else {'first':'UNKNOWN'};outcomes.append({'source':name,'as_of_utc':t.isoformat(),**fwd})
   for t in pd.date_range(A,B,freq='7D',inclusive='left'):
    stop=min(t+pd.Timedelta(days=7),B);base=asof(d,h,t);w=subsequent(d,t,stop,base);w['segment_end_close']=w.pop('last_close',None);weekly.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':stop.isoformat(),**base,**w,'phase':'UNKNOWN'})
  x=pd.DataFrame(rows);fwd=pd.DataFrame(outcomes);assert len(x)==184 and len(fwd)==184;pair=[]
  for t,g in x.groupby('as_of_utc',sort=True):
   assert len(g)==2;any_unknown=bool(((g['long']=='UNKNOWN')|(g['small']=='UNKNOWN')).any());focus='YES' if ((g['long']=='UP')&(g['small']=='DOWN')).all() else 'NO' if any((u!='UP' and u!='UNKNOWN') or (v!='DOWN' and v!='UNKNOWN') for u,v in zip(g['long'],g['small'])) else 'UNKNOWN' if any_unknown else 'NO'
   sw=g['swing'].tolist();broken=g.get('l_new_already_crossed',pd.Series([None,None])).tolist();missing=any(v=='UNKNOWN' or pd.isna(v) for v in sw) or any(pd.isna(v) for v in broken)
   joint='UNKNOWN' if missing else 'DISAGREE' if len(set(sw))>1 or len(set(broken))>1 else str(sw[0])+('_LOW_PRIOR_BROKEN' if bool(broken[0]) else '_LOW_NOT_BROKEN')
   pair.append({'as_of_utc':t,'focus_both':focus,'joint_pivot':joint})
  pairs=pd.DataFrame(pair);x.to_csv(out/'daily-asof.csv',index=False);fwd.to_csv(out/'future-21d.csv',index=False);pd.DataFrame(weekly).to_csv(out/'weekly.csv',index=False);pairs.to_csv(out/'joint.csv',index=False)
  merged=x.merge(fwd,on=['source','as_of_utc']);summary={'period':[start,end],'points':len(pairs),'expected_4h_per_source':len(grid),'quality':quality,'cross_flags_utc':[t.isoformat() for t in flags],'focus_counts':pairs.focus_both.value_counts().to_dict(),'joint_pivot':pairs.joint_pivot.value_counts().to_dict(),'focus_pivot':pairs[pairs.focus_both=='YES'].joint_pivot.value_counts().to_dict(),'per_source_future_events':{name:g['first'].value_counts(dropna=False).to_dict() for name,g in merged.groupby('source')},'input_sha256':{str(p):sha(p) for p in [SPEC,Path(__file__),Path('verify/cycle_pivot_asof_20261105.py'),Path('verify/market_2016_pivot_20261102.py'),RAW,out/'bitstamp-4h.csv',out/'kraken-4h.csv']},'bitstamp_receipts':receipts,'limitations':['Past intervals used in project, not independent sample or phase truth.','Focus days overlap and are not independent events.','21-day price events do not validate phase or profitability.']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(label,json.dumps({k:v for k,v in summary.items() if k in ('points','focus_counts','joint_pivot','focus_pivot','per_source_future_events','cross_flags_utc')},indent=2))
if __name__=='__main__':main()
