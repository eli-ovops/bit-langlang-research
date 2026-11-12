"""H1 BTC relative-strength exemption, exploratory fixed historical diagnostic."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals
from .tph_ledger import replay


def btc_eligible_signals(btc):
    _,features,ema20=signals(btc,btc)
    low=btc.low.rolling(20,min_periods=20).min()
    hit=((features.dist_hi<.03)&(features.risk_on==True)&(btc.low<=low*1.001)&(btc.close>btc.close.shift(1))).fillna(False).to_numpy()
    return hit,ema20


def main():
    out=Path('data/verify/btc-h1-historical-20261030.json')
    if out.exists(): raise SystemExit('refusing to overwrite existing result')
    btc=load5('BTCUSDT'); funding=pd.read_csv(Path(MARKET)/'BTCUSDT_funding.csv.gz')
    hit,ema20=btc_eligible_signals(btc)
    start='2024-07-01';end='2026-10-25'
    result,closed,opened=replay(btc,hit,ema20,funding,start,end,slip=.0002)
    mask=(btc.ts>=pd.Timestamp(start,tz='UTC'))&(btc.ts<pd.Timestamp(end,tz='UTC'))
    values=btc.loc[mask,'close'];growth=values/values.iloc[0];years=(pd.Timestamp(end)-pd.Timestamp(start)).days/365.25
    candidate=int((hit & mask.to_numpy()).sum())
    data={'status':'EXPLORATORY_NOT_VALIDATED','hypothesis':'BTC exempt from BTC-relative strength, all other signal rules fixed',
          'preregistration_sha256':hashlib.sha256(Path('docs/BTC候选-H1-事前定义-20261030.md').read_bytes()).hexdigest(),
          'config_sha256':hashlib.sha256(Path('verify/frozen_config.json').read_bytes()).hexdigest(),
          'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(MARKET)/'BTCUSDT_5m.csv.gz',Path(MARKET)/'BTCUSDT_funding.csv.gz')},
          'candidate_count':candidate,'result':result,
          'benchmark_no_cost_unleveraged_BTC':{'return_pct':float((growth.iloc[-1]-1)*100),'cagr_pct':float((growth.iloc[-1]**(1/years)-1)*100),'mdd_close_5m_pct':float((growth/growth.cummax()-1).min()*100)},
          'limitations':['not a combined BTC/ETH portfolio','historical chosen interval is not independent OOS','proxy liquidation, 5m close equity, assumed costs and funding mark','BTC OHLC and funding source authenticity not independently verified','not a prospective or live trading result']}
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
