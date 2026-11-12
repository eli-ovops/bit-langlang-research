"""Frozen retrospective BTC regime proxy; no trades, orders, or current advice."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd

SOURCE=Path('data/market/nine-futures-stage-oct31-20261031-01/BTCUSDT_5m.csv.gz')
DEF=Path('docs/市场阶段-四季研究口径冻结-20261102.md')
OUT=Path('data/verify/market-season-research-20261102-01')
START=pd.Timestamp('2025-10-01',tz='UTC');END=pd.Timestamp('2026-10-31',tz='UTC')
LABELS={'SPRING':'春候选','SUMMER':'夏候选','AUTUMN':'秋候选','WINTER':'冬候选','UNKNOWN':'UNKNOWN'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def relation(old_high,old_low,new_high,new_low):
 if not np.isfinite([old_high,old_low,new_high,new_low]).all() or old_high<old_low or new_high<new_low:return 'MIXED'
 if new_high>old_high and new_low>old_low:return 'UP'
 if new_high<old_high and new_low<old_low:return 'DOWN'
 if new_high<=old_high and new_low>=old_low:return 'INSIDE'
 return 'MIXED'

def season(daily,blocks):
 """Inputs are exactly the completed daily and 4h bars before decision time."""
 if len(daily)!=14 or len(blocks)!=48 or not daily.good.all() or not blocks.good.all():return {'season':'UNKNOWN','reason':'INCOMPLETE_OR_INVALID_DATA'}
 old,new=daily.iloc[:7],daily.iloc[7:];a,b=blocks.iloc[:24],blocks.iloc[24:]
 dr=relation(old.high.max(),old.low.min(),new.high.max(),new.low.min());hr=relation(a.high.max(),a.low.min(),b.high.max(),b.low.min());mid=(daily.high.max()+daily.low.min())/2;above=bool(daily.close.iloc[-1]>mid)
 label='UNKNOWN';reason='UNRESOLVED_OR_CONFLICT'
 if dr=='INSIDE' and hr=='UP' and above:label,reason='SPRING','INSIDE_DAILY_LOCAL_UP_ABOVE_MID'
 elif dr=='UP' and hr=='UP':label,reason='SUMMER','BOTH_WINDOWS_UP'
 elif dr=='UP' and hr=='DOWN':label,reason='AUTUMN','DAILY_UP_4H_DOWN_MAY_BE_PULLBACK'
 elif dr=='DOWN' and hr=='DOWN':label,reason='WINTER','BOTH_WINDOWS_DOWN_MAY_REVERSE'
 return {'season':label,'reason':reason,'daily_relation':dr,'four_hour_relation':hr,'prior_close':float(daily.close.iloc[-1]),'daily14_mid':float(mid),'close_above_daily14_mid':above,
         'daily_old_high':float(old.high.max()),'daily_old_low':float(old.low.min()),'daily_new_high':float(new.high.max()),'daily_new_low':float(new.low.min()),
         'h4_old_high':float(a.high.max()),'h4_old_low':float(a.low.min()),'h4_new_high':float(b.high.max()),'h4_new_low':float(b.low.min())}

def aggregates(f):
 f=f.copy();values=f[['open','high','low','close']];f['bad']=(~np.isfinite(values).all(axis=1))|(values<=0).any(axis=1)|(f.low>values.min(axis=1))|(f.high<values.max(axis=1))
 def res(freq,expected):
  g=f.resample(freq).agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('close','size'),bad=('bad','sum'));g['good']=g.n.eq(expected)&g.bad.eq(0);return g
 return res('D',288),res('4h',48)

def classify_asof(daily,blocks,t):
 return season(daily.loc[(daily.index>=t-pd.Timedelta(days=14))&(daily.index<t)],blocks.loc[(blocks.index>=t-pd.Timedelta(days=8))&(blocks.index<t)])

def main():
 if OUT.exists():raise FileExistsError('refusing overwrite')
 inputs={str(p):sha(p) for p in (SOURCE,DEF,Path(__file__))};f=pd.read_csv(SOURCE);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True,errors='raise');f=f.set_index('time')
 if f.index.has_duplicates or not f.index.is_monotonic_increasing or np.any((f.index.asi8//1_000_000)%300000):raise ValueError('invalid grid order/alignment')
 daily,blocks=aggregates(f);times=pd.date_range(START,END-pd.Timedelta(nanoseconds=1),freq='7D');items=[];forward=[]
 for i,t in enumerate(times):
  item={'as_of_utc':t.isoformat(),'interval_end_utc':min(t+pd.Timedelta(days=7),END).isoformat(),**classify_asof(daily,blocks,t)}
  prev20=daily.loc[(daily.index>=t-pd.Timedelta(days=20))&(daily.index<t)]
  item['old_mid_gate']=bool(prev20.close.iloc[-1]>(prev20.high.max()+prev20.low.min())/2) if len(prev20)==20 and prev20.good.all() else None
  items.append(item)
  fwd=daily.loc[(daily.index>=t)&(daily.index<t+pd.Timedelta(days=7))]
  if len(fwd)==7 and fwd.good.all() and 'prior_close' in item:
   price=item['prior_close'];forward.append({'as_of_utc':t.isoformat(),'season':item['season'],'status':'POST_HOC_DESCRIPTIVE','future_7d_close_pct':float((fwd.close.iloc[-1]/price-1)*100),'future_7d_high_pct':float((fwd.high.max()/price-1)*100),'future_7d_low_pct':float((fwd.low.min()/price-1)*100)})
  else:forward.append({'as_of_utc':t.isoformat(),'season':item['season'],'status':'UNKNOWN_FUTURE_COVERAGE_OR_INPUT'})
 segments=[]
 for row in items:
  if segments and segments[-1]['season']==row['season']:
   segments[-1]['end_utc_exclusive']=row['interval_end_utc'];segments[-1]['decision_points']+=1
  else:segments.append({'start_utc':row['as_of_utc'],'end_utc_exclusive':row['interval_end_utc'],'season':row['season'],'decision_points':1})
 if any(sha(p)!=h for p,h in inputs.items()):raise ValueError('input changed')
 OUT.mkdir(parents=True);pd.DataFrame(items).to_csv(OUT/'weekly.csv',index=False);pd.DataFrame(forward).to_csv(OUT/'forward-descriptive.csv',index=False);pd.DataFrame(segments).to_csv(OUT/'segments.csv',index=False)
 groups=pd.DataFrame(items);future=pd.DataFrame(forward);summary={'status':'RETROSPECTIVE_PROXY_NOT_VERIFIED','counts':groups.season.value_counts().to_dict(),'points':len(items),'segments':len(segments),'unknown_fraction':float(groups.season.eq('UNKNOWN').mean()),'old_gate_by_season':{k:{'on':int(v.old_mid_gate.eq(True).sum()),'off':int(v.old_mid_gate.eq(False).sum())} for k,v in groups.groupby('season')},'future_coverage':future.status.value_counts().to_dict(),'inputs_sha256':inputs,'limits':['No external ground truth or human-independent labels.','Prior history studied; no blind or independent validation.','Weekly states are held until next point, not known market truth.','BTC only; sentiment and other asset conditions unknown.']}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
