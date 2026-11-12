"""Exploratory fixed-ledger resampling; not a future profit probability."""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    src=Path('data/verify/ledger-audit-20261030/oos_closed.csv')
    out=Path('data/verify/event-clustering-diagnostic-20261030.json')
    if out.exists(): raise SystemExit('refusing to overwrite')
    d=pd.read_csv(src); t=pd.to_datetime(d.exit_ts,utc=True); pnl=pd.to_numeric(d.net_pnl)
    if t.isna().any() or pnl.isna().any(): raise ValueError('invalid dates or pnl')
    calendar=pd.date_range('2024-07-01','2026-10-24',freq='D',tz='UTC')
    daily=pd.Series(pnl.to_numpy(),index=t.dt.floor('D')).groupby(level=0).sum().reindex(calendar,fill_value=0).to_numpy()
    if not np.isclose(daily.sum(),pnl.sum()): raise ValueError('trades outside declared sample window')
    rng=np.random.default_rng(20261030); count=5000
    iid=pnl.to_numpy()[rng.integers(0,len(pnl),size=(count,len(pnl)))].sum(axis=1)
    per_day=daily[rng.integers(0,len(daily),size=(count,len(daily)))].sum(axis=1)
    blocks=(rng.integers(0,len(daily),size=(count,int(np.ceil(len(daily)/7)),1))+np.arange(7))%len(daily)
    weekly=daily[blocks].reshape(count,-1)[:,:len(daily)].sum(axis=1)
    def stats(a): return {'positive_resample_pct':round(float((a>0).mean()*100),2),
                          'sum_usdt_q025_q50_q975':[round(float(x),2) for x in np.quantile(a,[.025,.5,.975])]}
    result={'status':'EXPLORATORY_NOT_VALIDATED','sample':'2024-07-01 inclusive to 2026-10-25 exclusive, realized closed ledger in USDT',
            'actual_trade_count':len(d),'calendar_days':len(calendar),'observed_net_usdt':round(float(pnl.sum()),2),
            'resamples':count,'seed':20261030,'block_days':7,
            'warning':'Descriptive resampling of fixed historical realized PnL, no capital-path recalculation or causal claim; ignores regime changes, unresolved costs, liquidation and earlier selection. Percentages are NOT probabilities of future profits. Seven-day circular blocks join sample end to beginning.',
            'iid_trades':stats(iid),'iid_calendar_days':stats(per_day),'circular_7day_blocks':stats(weekly)}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
