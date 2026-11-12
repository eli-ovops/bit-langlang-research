"""Do not count remaining beyond an old anchor as a new crossover."""
from pathlib import Path
import hashlib,json,pandas as pd
from verify.market_2018_transition_20261102 import read
DATA=Path('data/market/btc-2016-usd-cross-20261102-01');SRC=Path('data/verify/market-2016-pivot-20261102-01');OUT=Path('data/verify/market-2016-pivot-correction-20261102-01');DEF=Path('docs/2016摆点事件-观察时已在边界外修正-20261102.md')
def classify(close,upper,lower):
 if pd.isna(close):return 'UNKNOWN_ASOF'
 if close>upper:return 'ALREADY_ABOVE_ASOF'
 if close<lower:return 'ALREADY_BELOW_ASOF'
 return 'WITHIN_OR_EQUAL_ASOF'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 ev=pd.read_csv(SRC/'events.csv');rows=[];flag=pd.Timestamp('2016-06-07 12:00',tz='UTC')
 for name,g in ev.groupby('source'):
  d,_=read(DATA/(name+'-4h.csv.gz'));d.loc[flag.floor('D'),'good']=False
  for x in g.to_dict('records'):
   t=pd.Timestamp(x['as_of_utc']);prev=t-pd.Timedelta(days=1)
   if x['status'] in ('UNKNOWN_INPUT','UNKNOWN_BOUNDARY') or prev not in d.index or not d.loc[prev,'good']:status='UNKNOWN_ASOF';close=None
   else:close=float(d.loc[prev,'close']);status=classify(close,x['upper'],x['lower'])
   if x['kind']=='fixed_28':assert status in ('WITHIN_OR_EQUAL_ASOF','UNKNOWN_ASOF')
   x['asof_close']=close;x['asof_boundary_state']=status;x['new_break_status']=x['status'] if status=='WITHIN_OR_EQUAL_ASOF' else status;x['new_break_follow']=x['follow'] if status=='WITHIN_OR_EQUAL_ASOF' else 'NOT_APPLICABLE';rows.append(x)
 df=pd.DataFrame(rows);OUT.mkdir();df.to_csv(OUT/'events-corrected.csv',index=False);summary={name:{kind:{'asof_state':g.asof_boundary_state.value_counts().to_dict(),'new_status':g.new_break_status.value_counts().to_dict(),'follow':g.new_break_follow.value_counts().to_dict()} for kind,g in q.groupby('kind')} for name,q in df.groupby('source')};files=[Path(__file__),DEF,SRC/'events.csv',DATA/'bitstamp-4h.csv.gz',DATA/'coinbase-4h.csv.gz'];(OUT/'summary.json').write_text(json.dumps({'results':summary,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'limitation':'Post-result correction, do not treat initial outside as a new breakout.'},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
