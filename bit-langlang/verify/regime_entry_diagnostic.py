"""Descriptive, causal-at-entry grouping of an existing historical ledger."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent.parent
DEFINITION=ROOT/'docs/周期近似-入场时分组-事前定义-20261030.md'
MARKET=ROOT/'data/market/ETHUSDT_5m.csv.gz'
LEDGER=ROOT/'data/verify/ledger-audit-20261030/oos_closed.csv'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(market,ledger):
    m=market.copy();m['ts']=pd.to_datetime(m.ts,unit='ms',utc=True,errors='raise')
    m['day']=m.ts.dt.floor('D');m['close']=pd.to_numeric(m.close,errors='raise')
    if (m.close<=0).any() or not np.isfinite(m.close).all():raise ValueError('行情价格无效')
    rows=[]
    for day,group in m.groupby('day',sort=True):
        ts=group.ts.sort_values()
        valid=(len(ts)==288 and ts.is_unique and ts.iloc[0]==day and ts.iloc[-1]==day+pd.Timedelta(hours=23,minutes=55)
               and ts.diff().dropna().eq(pd.Timedelta(minutes=5)).all())
        if valid:rows.append((day,float(group.loc[group.ts.idxmax(),'close'])))
    daily=dict(rows);records=[]
    for trade in ledger.itertuples():
        t=pd.Timestamp(trade.entry_ts)
        if t.tzinfo is None:raise ValueError('入场时间必须带时区')
        day=t.tz_convert('UTC').floor('D')-pd.Timedelta(days=1)
        prior=day-pd.Timedelta(days=20);risk=(float(trade.entry)-float(trade.stop))*float(trade.qty)
        net=float(trade.net_pnl)
        if risk<=0 or not np.isfinite([risk,net]).all():raise ValueError('账本风险或损益无效')
        ret=daily[day]/daily[prior]-1 if day in daily and prior in daily else None
        label='UNKNOWN' if ret is None else 'LE_0' if ret<=0 else 'GE_20' if ret>=.2 else 'BETWEEN_0_20'
        records.append({'trade_id':str(trade.trade_id),'entry_ts':t.isoformat(),'reference_day':day.isoformat(),
                        'return_20d':ret,'group':label,'net_pnl':net,'net_R':net/risk})
    f=pd.DataFrame(records);groups={}
    for name in ('LE_0','BETWEEN_0_20','GE_20','UNKNOWN'):
        g=f[f.group==name]
        groups[name]={'trades':len(g),'entry_days':g.entry_ts.str[:10].nunique(),'net_pnl_usdt':float(g.net_pnl.sum()),
                      'mean_net_R':float(g.net_R.mean()) if len(g) else None,
                      'median_net_R':float(g.net_R.median()) if len(g) else None,'wins':int((g.net_pnl>0).sum())}
    return {'status':'DESCRIPTIVE_NOT_OOS','groups':groups,'records':records}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    market=pd.read_csv(MARKET,usecols=['ts','close']);ledger=pd.read_csv(LEDGER,dtype={'trade_id':str})
    if len(ledger)!=106:raise ValueError('账本笔数与预先定义不符')
    result=classify(market,ledger);result['input_sha256']={'market':digest(MARKET),'ledger':digest(LEDGER),
        'definition':digest(DEFINITION),'code':digest(Path(__file__))}
    result['limitations']='Historical selected trades, conditional on original position path; no causal or out-of-sample inference.'
    with open(args.out,'x',encoding='utf-8') as out:json.dump(result,out,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'status':result['status'],'groups':result['groups'],'input_sha256':result['input_sha256']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
