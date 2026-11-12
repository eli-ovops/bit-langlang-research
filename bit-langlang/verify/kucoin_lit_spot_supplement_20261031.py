"""Add KuCoin Lighter spot to existing eight-asset plus cash baseline."""
import json,hashlib
from decimal import Decimal as D
from pathlib import Path
import pandas as pd,numpy as np
source=Path('data/market/lighter-kucoin-spot-20261031-01');prior=Path('data/verify/nine-spot-reference-20261031-01');out=Path('data/verify/nine-spot-cross-venue-20261031-01')
def main():
 if out.exists():raise FileExistsError(out)
 receipt=json.loads((source/'receipt.json').read_text());body=(source/'response.json').read_bytes();assert hashlib.sha256(body).hexdigest()==receipt['sha256'];j=json.loads(body);assert j['code']=='200000' and j['data']['symbol']=='LIT-USDT';rows=sorted(j['data']['list'],key=lambda x:int(x[0]))
 dates=pd.date_range('2026-01-16','2026-10-30',freq='D',tz='UTC');ts=pd.DatetimeIndex(pd.to_datetime([int(x[0]) for x in rows],unit='s',utc=True));assert ts.equals(dates)
 vals=np.asarray([[float(x[i]) for i in (1,2,3,4)] for x in rows]);assert np.isfinite(vals).all() and (vals>0).all() and (vals[:,2]<=vals.min(axis=1)).all() and (vals[:,1]>=vals.max(axis=1)).all() # OHLC = open high low close
 base=pd.read_csv(prior/'daily-equity.csv');base['date']=pd.to_datetime(base.date,utc=True);assert base.date.is_monotonic_increasing
 allocation=2000/9;price=float(rows[0][1]);qty=allocation/(price*1.0002*1.001);lit=pd.Series(allocation,index=pd.DatetimeIndex(base.date));lit.loc[dates]=qty*vals[:,3];combined=base.equity.to_numpy()-allocation+lit.to_numpy();peaks=np.maximum.accumulate(np.r_[2000.,combined])[1:]
 old=json.loads((prior/'summary.json').read_text());sold=old['estimated_sale_net_usdt']-allocation+qty*vals[-1,3]*.9998*.999
 report={'status':'CROSS_VENUE_PROXY_NO_REAL_TRANSFER','initial':2000.,'equity_end':float(combined[-1]),'return_pct':float((combined[-1]/2000-1)*100),'estimated_sale_net_usdt':float(sold),'mdd_daily_pct':float((combined/peaks-1).min()*100),'lit':{'initial_cash':allocation,'venue':'KuCoin','entry_utc':dates[0].isoformat(),'entry_reference_open':price,'quantity':qty,'end_close':float(vals[-1,3]),'end_mark':float(qty*vals[-1,3])},'assumptions':['Retrospective chosen assets; not tradable universe at start.','LIT held cash before 2026-01-16; HYPE before 2026-09-25.','Fees 0.1% and slippage 0.02% per side are assumptions across venues.','Cross-exchange transfers, fees and actual access unknown.']}
 out.mkdir();(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');pd.DataFrame({'date':base.date.astype(str),'equity':combined,'lit':lit.to_numpy()}).to_csv(out/'daily-equity.csv',index=False)
 exact=(D(2000)/D(9))/(D(str(rows[0][1]))*D('1.0002')*D('1.001'))*D(str(rows[-1][4]));assert abs(exact-D(str(report['lit']['end_mark'])))<D('0.000001');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
