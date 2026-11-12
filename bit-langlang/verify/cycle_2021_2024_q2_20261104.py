"""Continuous phase evidence: independent venue OHLC, no trade or phase ground truth."""
from pathlib import Path
import hashlib,json
import pandas as pd,requests
from verify.market_2018_transition_20261102 import read
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
from verify.cycle_2021q1_2024q4_evidence_20261104 import future21
from verify.cycle_2023q3_2025q2_priorrange_20261104 import prior_evidence
SPEC=Path('docs/周期研究-2021与2024二季度连续复盘定义-20261104.md');RAW=Path('data/market/kraken-xbtusd-native4h-20261104-01/XBTUSD_240.csv');OLD=Path('data/market/btc-2020am-usd-cross-20261102-01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for year in (2021,2024):
  out=Path(f'data/verify/cycle-{year}q2-phase-20261104-01');assert not out.exists();out.mkdir(parents=True);A=pd.Timestamp(f'{year}-04-01',tz='UTC');B=pd.Timestamp(f'{year}-07-01',tz='UTC');lo=A-pd.Timedelta(days=57);hi=B+pd.Timedelta(days=28);exp=pd.date_range(lo,hi,freq='4h',inclusive='left');receipts=[];raw=[]
  cut=hi
  for i in range(2):
   r=requests.get('https://www.bitstamp.net/api/v2/ohlc/btcusd/',params={'step':14400,'limit':1000,'end':int(cut.timestamp())},timeout=60);r.raise_for_status();p=out/f'bitstamp-{i}.json';p.write_bytes(r.content);items=r.json()['data']['ohlc'];assert items;raw.extend(items);receipts.append({'url':r.url,'sha256':sha(p),'rows':len(items)});cut=pd.Timestamp(min(int(x['timestamp']) for x in items),unit='s',tz='UTC')-pd.Timedelta(seconds=1)
  assert cut<lo
  f=pd.DataFrame(raw).rename(columns={'timestamp':'ts'});f['ts']=pd.to_numeric(f.ts)*1000
  for c in ['open','high','low','close','volume']:f[c]=pd.to_numeric(f[c])
  f=f[(f.ts>=lo.timestamp()*1000)&(f.ts<hi.timestamp()*1000)].sort_values('ts');assert not f.ts.duplicated().any();f[['ts','open','high','low','close','volume']].to_csv(out/'bitstamp-4h.csv',index=False)
  assert sha(RAW)==json.loads(RAW.with_name('manifest.json').read_text())['raw_sha256'];k=pd.read_csv(RAW,header=None,names=['sec','open','high','low','close','volume','trades']);assert k.sec.is_monotonic_increasing and not k.sec.duplicated().any();k=k[(k.sec>=lo.timestamp())&(k.sec<hi.timestamp())].copy();k['ts']=k.sec*1000;k[['ts','open','high','low','close','volume']].to_csv(out/'kraken-4h.csv',index=False)
  sources={}
  for name in ('bitstamp','kraken'):
   d,h=read(out/(name+'-4h.csv'));assert h.index.equals(exp) and h.good.all();bad_volume=h.index[h.volume<=0];bad_days_volume=bad_volume.floor('D').unique();h.loc[h.index.floor('D').isin(bad_days_volume),'good']=False;d.loc[d.index.isin(bad_days_volume),'good']=False;sources[name]=(d,h)
  a,b=(sources[n][1] for n in ('bitstamp','kraken'));flags=pd.Series(False,index=exp)
  for c in ('high','low'):flags|=(a[c]/b[c]>1.1)|(a[c]/b[c]<.9)
  flag_times=exp[flags];bad_days=flag_times.floor('D').unique()
  for d,h in sources.values():d.loc[d.index.isin(bad_days),'good']=False;h.loc[h.index.floor('D').isin(bad_days),'good']=False
  daily=[];segments=[]
  for name,(d,h) in sources.items():
   for t in pd.date_range(A,B,freq='D',inclusive='left'):
    r=asof(d,h,t);p=prior_evidence(d,t);daily.append({'source':name,'as_of_utc':t.isoformat(),**r,**p,'phase':'UNKNOWN','sentiment':'UNKNOWN'})
   for t in pd.date_range(A,B,freq='7D',inclusive='left'):
    stop=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);p=prior_evidence(d,t);week=subsequent(d,t,stop,r);week['segment_end_close']=week.pop('last_close',None);future=future21(d,t,r) if r['range_status']=='OK' else {'first':'UNKNOWN'};dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==r and prior_evidence(dd,t)==p;segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':stop.isoformat(),**r,**p,**week,**future,'phase':'UNKNOWN'})
  df=pd.DataFrame(daily);sf=pd.DataFrame(segments);assert len(df)==(B-A).days*2;df.to_csv(out/'daily.csv',index=False);sf.to_csv(out/'segments.csv',index=False);paths=[SPEC,Path(__file__),RAW,out/'bitstamp-4h.csv',out/'kraken-4h.csv'];summary={'period':[A.isoformat(),B.isoformat()],'days':(B-A).days,'expected_4h_per_source':len(exp),'data_quality_flags_utc':[x.isoformat() for x in flag_times],'nonpositive_volume_utc':{name:[x.isoformat() for x in h.index[h.volume<=0]] for name,(d,h) in sources.items()},'bitstamp_receipts':receipts,'input_sha256':{str(p):sha(p) for p in paths},'limits':['Historic interval exposed to prior research, not independent truth.','Kraken member CRC compared to received ZIP directory, no whole archive SHA.','Close-based proxies and volume do not prove phase, sentiment, fake breakout or trade authenticity.']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(year,'days',len(df),'segments',len(sf),'flags',summary['data_quality_flags_utc'])
if __name__=='__main__':main()
