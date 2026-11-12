"""BTC EMA initialization diagnostic; descriptive and retrospective only."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import MARKET
from .prove_method import load5


def compare_daily(daily):
    e50=daily.ewm(span=50,adjust=False).mean();e200=daily.ewm(span=200,adjust=False).mean()
    full=(daily>e50)&(e50>e50.shift(5))&(daily>e200)
    r50=pd.Series(np.nan,index=daily.index);r200=r50.copy()
    for i in range(204,len(daily)):
        w=daily.iloc[i-204:i+1]
        r50.iloc[i]=w.ewm(span=50,adjust=False).mean().iloc[-1]
        r200.iloc[i]=w.ewm(span=200,adjust=False).mean().iloc[-1]
    short=(daily>r50)&(r50>r50.shift(5))&(daily>r200)
    valid=r200.notna()&r50.shift(5).notna()
    return full,short,valid


def main():
    out=Path('data/verify/ema-warmup-diagnostic-20261030.json')
    if out.exists(): raise SystemExit('refusing to overwrite')
    b=load5('BTCUSDT'); b=b[(b.ts>=pd.Timestamp('2022-01-01',tz='UTC'))&(b.ts<pd.Timestamp('2026-10-25',tz='UTC'))]
    daily=b.set_index('ts').close.resample('D').last()
    if daily.isna().any(): raise ValueError('missing daily price')
    full,short,valid=compare_daily(daily);diff=valid&(full!=short)
    rows=[{'day_utc':str(t.date()),'close':float(daily.loc[t]),'full_history':bool(full.loc[t]),'rolling_205':bool(short.loc[t])} for t in daily.index[diff]]
    result={'status':'EXPLORATORY_NOT_VALIDATED','method':'adjust=False; 205-day rolling reinitialization vs all available since 2022-01-01; daily state before next-day lag',
            'source_sha256':hashlib.sha256((Path(MARKET)/'BTCUSDT_5m.csv.gz').read_bytes()).hexdigest(),
            'definition_sha256':hashlib.sha256(Path('docs/EMA预热敏感性-事前定义-20261030.md').read_bytes()).hexdigest(),
            'comparable_days':int(valid.sum()),'disagreement_days':len(rows),'disagreement_fraction_pct':round(float(diff.sum()/valid.sum()*100),3),
            'initial_weight_after_205':(1-2/201)**204,'disagreement_dates':rows,
            'limitations':['not true EMA or proof of real market data','rolling reset is a diagnostic, not a proposed production rule','not PnL or independent prospective validation']}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='disagreement_dates'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
