"""Retrospective entry overlap audit; unrecorded stops/targets remain unknown."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_scan import read_raw_candles
from .stage_historical_replica import FIRST,END,SYMBOLS

TRADE_PATH=Path('data/processed/trades_clean.csv')
DEFINITION=Path('docs/历史交割-五币入场复刻-诊断定义-20261030.md')
BTC_PATH=Path('data/market/BTCUSDT_5m.csv.gz')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signals(stage):
    idx=pd.date_range(FIRST,END-pd.Timedelta(minutes=5),freq='5min')
    btc=read_raw_candles('BTCUSDT').set_index('ts').reindex(idx)
    if btc[['open','high','low','close']].isna().any().any():raise ValueError('BTC grid incomplete')
    if (not np.isfinite(btc[['open','high','low','close']].to_numpy(dtype=float)).all()
            or (btc[['open','high','low','close']]<=0).any().any()
            or (btc.low>btc[['open','high','close']].min(axis=1)).any()
            or (btc.high<btc[['open','low','close']].max(axis=1)).any()):raise ValueError('BTC invalid OHLC')
    bd=btc.resample('1D').agg({'high':'max','low':'min','close':'last'})
    btc_regime=(bd.close>(bd.high.rolling(20,min_periods=20).max()+bd.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False)
    br=bd.close.pct_change(7,fill_method=None);data={};daily={};scores={}
    for sym in sorted(SYMBOLS):
        f=read_raw_candles(sym,stage).set_index('ts').reindex(idx)
        if f[['open','high','low','close']].isna().any().any():raise ValueError(f'{sym} grid incomplete')
        data[sym]=f
        dd=f.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
        eligible=dd.open.eq(288).shift(1,fill_value=False).rolling(30,min_periods=30).sum().eq(30)
        scores[sym]=(dd.close.pct_change(7,fill_method=None)-br).shift(1).where(eligible)
        daily[sym]=dd.high.rolling(20,min_periods=20).max().shift(1)
    s=pd.DataFrame(scores).where(btc_regime,axis=0);rank=s.where(s>0).rank(axis=1,ascending=False,method='first')
    results={}
    for sym in sorted(SYMBOLS):
        f=data[sym];prior=f.low.shift(1).rolling(20,min_periods=20).min()
        hi=f.high.shift(1).rolling(48,min_periods=48).max();lo=f.low.shift(1).rolling(48,min_periods=48).min()
        rank5=rank[sym].reindex(idx.floor('D')).to_numpy();target=daily[sym].reindex(idx.floor('D')).to_numpy()
        pattern=((f.low<prior)&(f.close>prior)&(f.close>=(hi+lo)/2)).to_numpy()
        base=pattern & (rank5<=2) & (target>f.close.to_numpy())
        entry=f.open.shift(-2).to_numpy()*(1+.0002);stop=f.low.to_numpy()
        distance=entry-stop;qualified=base & np.isfinite(entry) & (distance>0) & ((target-entry)>=2*distance)
        # The signal is executable in the model only two bars after its opening.
        times=idx[qualified]+pd.Timedelta(minutes=10)
        results[sym]={'execution_ns':times.asi8,'candidate_count':len(times),'market':f}
    return results


def eligible_match(execution_ns,entry_ns,window_ns=15*60*1_000_000_000):
    """Last simulated entry no later than the recorded entry, max 15m earlier."""
    pos=int(np.searchsorted(execution_ns,entry_ns,side='right'))-1
    if pos<0 or entry_ns-int(execution_ns[pos])>window_ns:return None
    return int(execution_ns[pos])


def audit(trades,market,offset_hours):
    rows=[]
    for t in trades.itertuples(index=False):
        base=str(t.base);side=str(t.side);sym=base+'USDT'
        record={'id':int(t.id),'base':base,'side':side,'entry_time_original':str(t.entry_time),
                'stop_order_status':'UNKNOWN_NOT_RECORDED','take_profit_order_status':'UNKNOWN_NOT_RECORDED'}
        if sym not in market or side!='多':
            record['status']='OUT_OF_SCOPE_SYMBOL' if sym not in market else 'OUT_OF_SCOPE_SHORT';rows.append(record);continue
        t_utc=pd.to_datetime(t.entry_time,utc=True,errors='coerce')-pd.Timedelta(hours=offset_hours)
        if pd.isna(t_utc) or not FIRST<=t_utc<END:
            record['status']='UNKNOWN_TIME_OUTSIDE_COVERAGE';rows.append(record);continue
        frame=market[sym]['market'];bar_time=t_utc.floor('5min')
        if bar_time not in frame.index:
            record['status']='UNKNOWN_NO_MARKET_BAR';rows.append(record);continue
        bar=frame.loc[bar_time];price=float(t.entry_price)
        if not np.isfinite(price) or price<=0:
            record['status']='UNKNOWN_INVALID_RECORDED_PRICE';rows.append(record);continue
        found=eligible_match(market[sym]['execution_ns'],t_utc.value)
        record.update(entry_assumed_utc=t_utc.isoformat(),bar_open_utc=bar_time.isoformat(),
                      entry_price=price,bar_low=float(bar.low),bar_high=float(bar.high),
                      price_inside_bar=bool(bar.low<=price<=bar.high),
                      status='SIGNAL_OVERLAP' if found is not None else 'NO_SIGNAL_OVERLAP',
                      matched_model_time_utc=pd.Timestamp(found,tz='UTC').isoformat() if found is not None else None,
                      lag_seconds=(t_utc.value-found)/1e9 if found is not None else None)
        rows.append(record)
    return rows


def summary(rows,market):
    d=pd.DataFrame(rows);valid=d[d.status.isin(['SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'])];matched=valid[valid.status=='SIGNAL_OVERLAP']
    by_symbol={}
    for name,g in valid.groupby('base'):
        m=g[g.status=='SIGNAL_OVERLAP']
        by_symbol[name]={'evaluable':len(g),'matched_rows':len(m),'entry_in_binance_bar':int(g.price_inside_bar.sum())}
    signal_keys=[(r.base,r.matched_model_time_utc) for r in matched.itertuples()]
    return {'total_rows':len(d),'statuses':{str(k):int(v) for k,v in d.status.value_counts().items()},
            'evaluable':len(valid),'matched_rows':len(matched),'price_inside_binance_bar':int(valid.price_inside_bar.sum()),
            'matched_unique_signals':len(set(signal_keys)),'duplicate_matched_rows':len(signal_keys)-len(set(signal_keys)),
            'full_window_simulated_signal_count':sum(v['candidate_count'] for v in market.values()),
            'by_symbol':by_symbol}


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--outdir',required=True);a=p.parse_args()
    stage=Path(a.stage);manifest=json.loads((stage/'manifest.json').read_text())
    for sym in SYMBOLS:
        if sha(stage/f'{sym}_5m.csv.gz')!=manifest['symbols'][sym]['sha256']:raise ValueError('input hash mismatch')
    inputs={str(x):sha(x) for x in (TRADE_PATH,BTC_PATH,stage/'manifest.json',DEFINITION,Path(__file__))}
    trades=pd.read_csv(TRADE_PATH);market=signals(stage);result={};output=Path(a.outdir);output.mkdir(parents=True,exist_ok=False)
    for name,offset in [('assumed_beijing',8),('alternative_utc',0)]:
        rows=audit(trades,market,offset);result[name]=summary(rows,market)
        pd.DataFrame(rows).to_csv(output/f'{name}-rows.csv',index=False)
    if any(sha(x)!=v for x,v in inputs.items()):raise ValueError('input changed')
    report={'status':'POST_HOC_REPLICA_DIAGNOSTIC_NOT_VALIDATED','inputs_sha256':inputs,'results':result,
            'limits':['Three-coin retrospective universe, not full five-coin or full market.',
                      'Both timezone choices unverified; source, venue and fill identity unverified.',
                      'Stops/targets not recorded; not a trading or PnL backtest.']}
    (output/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
