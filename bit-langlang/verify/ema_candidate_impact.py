"""Map fixed EMA-warmup diagnostic state differences into candidate counts."""
import hashlib,json
from pathlib import Path
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals


def impact(pre,old,day,rows):
    new=old.copy()
    for row in rows:
        date=pd.Timestamp(row['day_utc'],tz='UTC')+pd.Timedelta(days=1)
        new.loc[day==date]=bool(row['rolling_205'])
    return {'candidate_added':int((pre & ~old & new).sum()),'candidate_removed':int((pre & old & ~new).sum())}


def main():
    src=Path('data/verify/ema-warmup-diagnostic-20261030.json');out=Path('data/verify/ema-candidate-impact-20261030.json')
    if out.exists(): raise SystemExit('refusing to overwrite')
    r=json.loads(src.read_text()); btcfile=Path(MARKET)/'BTCUSDT_5m.csv.gz'
    if hashlib.sha256(btcfile.read_bytes()).hexdigest()!=r['source_sha256']: raise ValueError('BTC source changed')
    btc=load5('BTCUSDT');eth=load5('ETHUSDT');res={}
    for name,data in [('BTC_H1',btc),('ETH_frozen',eth)]:
        _,f,_=signals(btc,data);prev=data.close.shift(1);low=data.low.rolling(20,min_periods=20).min()
        pre=(f.dist_hi<.03)&(data.low<=low*1.001)&(data.close>prev)
        if name=='ETH_frozen': pre=pre&(f.rs7>0)
        res[name]=impact(pre,f.risk_on.eq(True),data.ts.dt.floor('D'),r['disagreement_dates'])
    payload={'status':'EXPLORATORY_NOT_VALIDATED','source_diagnostic_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
             'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [btcfile,Path(MARKET)/'ETHUSDT_5m.csv.gz']},
             'result':res,'note':'Maps state changes to subsequent-day raw candidates only. Not a PnL test; overlapping trades and position constraints ignored. Earlier 205-day EMA initialization is not known to be true.'}
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
