"""Retrospective as-of structural facts, with future outcome kept separate."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
P=Path('data/market/nine-futures-stage-oct31-20261031-01/BTCUSDT_5m.csv.gz');OUT=Path('data/verify/cycle-adversarial-20261102-01')
DATES=('2025-10-01','2026-03-01','2026-10-25','2026-10-31')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 before=sha(P);f=pd.read_csv(P);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True)
 if f.time.duplicated().any() or not f.time.is_monotonic_increasing or not f.time.diff().dropna().eq(pd.Timedelta(minutes=5)).all():raise ValueError('market grid')
 d=f.set_index('time').resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'))
 h=f.set_index('time').resample('4h').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'));records=[]
 for day in DATES:
  t=pd.Timestamp(day,tz='UTC');d14=d.loc[t-pd.Timedelta(days=14):t-pd.Timedelta(days=1)];d20=d.loc[t-pd.Timedelta(days=20):t-pd.Timedelta(days=1)];h8=h.loc[t-pd.Timedelta(hours=192):t-pd.Timedelta(hours=4)]
  if len(d14)!=14 or len(d20)!=20 or len(h8)!=48 or not d20.n.eq(288).all() or not h8.n.eq(48).all():raise ValueError('incomplete histories')
  past,latest=d14.iloc[:7],d14.iloc[7:];h1,h2=h8.iloc[:24],h8.iloc[24:];mid=(d20.high.max()+d20.low.min())/2;prev=d20.close.iloc[-1]
  records.append({'as_of_utc':t.isoformat(),'prior_close':float(prev),'old_20d_midpoint':float(mid),'old_gate':bool(prev>mid),'prior_7d_high':float(past.high.max()),'latest_7d_high':float(latest.high.max()),'prior_7d_low':float(past.low.min()),'latest_7d_low':float(latest.low.min()),'4h_prior4d_high':float(h1.high.max()),'4h_latest4d_high':float(h2.high.max()),'4h_prior4d_low':float(h1.low.min()),'4h_latest4d_low':float(h2.low.min()),'season':'UNKNOWN','sentiment':'UNKNOWN'})
 if sha(P)!=before:raise ValueError('data changed')
 OUT.mkdir(parents=True);(OUT/'as-of-snapshots.json').write_text(json.dumps({'status':'RETROSPECTIVE_NOT_BLIND','source_sha256':before,'script_sha256':sha(Path(__file__)),'records':records},ensure_ascii=False,indent=2)+'\n')
 forward=[]
 for row in records:
  t=pd.Timestamp(row['as_of_utc']);end=t+pd.Timedelta(days=6)
  if end not in d.index or d.loc[t:end,'n'].size!=7 or not d.loc[t:end,'n'].eq(288).all():forward.append({'as_of_utc':row['as_of_utc'],'subsequent_seven_days_close_change_pct':None,'status':'UNKNOWN_NO_COVERAGE'})
  else:forward.append({'as_of_utc':row['as_of_utc'],'subsequent_seven_days_close_change_pct':float((d.loc[end,'close']/row['prior_close']-1)*100),'status':'DESCRIPTIVE_AFTER_THE_FACT'})
 (OUT/'later-outcomes.json').write_text(json.dumps(forward,indent=2)+'\n');print(json.dumps({'as_of':records,'after':forward},indent=2))
if __name__=='__main__':main()
