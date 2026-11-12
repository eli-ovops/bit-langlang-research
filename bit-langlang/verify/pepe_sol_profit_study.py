"""Per-record historical entry/exit study; no inference of stops or targets."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .forward_scan import read_raw_candles
from .historical_pullback_candidate import sha

SOURCE=Path('data/processed/trades_clean.csv')
DEF=Path('docs/PEPE与SOL逐笔盈利模式-研究定义-20261031.md')
OUT=Path('data/verify/pepe-sol-profit-study-20261031-01')
SYMS={'PEPE':('1000PEPE',1000,'data/market'),'SOL':('SOL',1,'data/market'), 'UNI':('UNI',1,'data/market/historical-replica-20261030-01'),'AAVE':('AAVE',1,'data/market/historical-replica-20261030-01'),'LINK':('LINK',1,'data/market/historical-replica-20261030-01')}

def extrema(p0,px,side,middle):
    """Observed extrema are bounds, using only endpoints and fully held bars."""
    if p0<=0 or px<=0 or side not in ('多','空'):raise ValueError('invalid position')
    highs=[p0,px];lows=[p0,px]
    if len(middle):highs.append(float(middle.high.max()));lows.append(float(middle.low.min()))
    return ((max(highs)/p0-1)*100,(min(lows)/p0-1)*100) if side=='多' else ((1-min(lows)/p0)*100,(1-max(highs)/p0)*100)

def main():
    if OUT.exists():raise FileExistsError('refusing overwrite')
    files=[SOURCE,DEF,Path(__file__),Path('data/market/BTCUSDT_5m.csv.gz')]+[Path(root)/f'{symbol}USDT_5m.csv.gz' for symbol,scale,root in SYMS.values()]
    hashes={str(p):sha(p) for p in files};frames={};daily={}
    for coin,(symbol,scale,root) in SYMS.items():
        f=read_raw_candles(symbol+'USDT',root).set_index('ts')
        if f.index.has_duplicates or not f.index.is_monotonic_increasing:raise ValueError('invalid index '+coin)
        frames[coin]=f
    btc=read_raw_candles('BTCUSDT').set_index('ts');daily=btc.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'})
    trades=pd.read_csv(SOURCE);trades=trades[trades.base.isin(SYMS)];rows=[]
    if trades.id.duplicated().any():raise ValueError('duplicate id')
    for tr in trades.itertuples(index=False):
        symbol,scale,root=SYMS[tr.base];f=frames[tr.base];entry=pd.to_datetime(tr.entry_time,utc=True,errors='coerce')-pd.Timedelta(hours=8);exit_=pd.to_datetime(tr.exit_time,utc=True,errors='coerce')-pd.Timedelta(hours=8)
        row={'id':tr.id,'coin':tr.base,'side':tr.side,'entry_original':tr.entry_time,'exit_original':tr.exit_time,'entry_utc_assumed':entry.isoformat() if pd.notna(entry) else None,'exit_utc_assumed':exit_.isoformat() if pd.notna(exit_) else None,
          'entry_price':tr.entry_price,'exit_price':tr.exit_price,'recorded_pnl':tr.pnl,'recorded_fee':tr.fee,'pnl_fee_relationship':'UNKNOWN','funding':'UNKNOWN','stop_order':'UNKNOWN_NOT_RECORDED','target_order':'UNKNOWN_NOT_RECORDED','price_scale':scale}
        if pd.isna(entry) or pd.isna(exit_) or exit_<entry or tr.side not in ('多','空') or not np.isfinite([tr.entry_price,tr.exit_price]).all() or min(tr.entry_price,tr.exit_price)<=0:
            row['status']='UNKNOWN_INVALID_RECORD';rows.append(row);continue
        a=entry.floor('5min');b=exit_.floor('5min');row['hold_minutes']=(exit_-entry).total_seconds()/60
        p0=tr.entry_price*scale;px=tr.exit_price*scale;sign=1 if tr.side=='多' else -1
        row['recorded_price_move_pct']=100*sign*(px/p0-1)
        row['btc_midpoint_prior20']='UNKNOWN';past=daily.loc[entry.floor('D')-pd.Timedelta(days=20):entry.floor('D')-pd.Timedelta(days=1)]
        if len(past)==20 and past.open.eq(288).all():row['btc_midpoint_prior20']='ABOVE' if past.close.iloc[-1]>(past.high.max()+past.low.min())/2 else 'BELOW_OR_EQUAL'
        if a not in f.index or b not in f.index:
            row['status']='UNKNOWN_MARKET_COVERAGE';rows.append(row);continue
        eb=f.loc[a];xb=f.loc[b];row['entry_price_inside_bar']=bool(eb.low<=p0<=eb.high);row['exit_price_inside_bar']=bool(xb.low<=px<=xb.high)
        pre=f.loc[a-pd.Timedelta(hours=4):a-pd.Timedelta(minutes=5)]
        if len(pre)==48 and (pre.index.to_series().diff().dropna()==pd.Timedelta(minutes=5)).all():
            row['past_4h_price_pct']=float((pre.close.iloc[-1]/pre.open.iloc[0]-1)*100)
            row['last_completed_bar_direction']='UP' if pre.close.iloc[-1]>pre.open.iloc[-1] else 'DOWN' if pre.close.iloc[-1]<pre.open.iloc[-1] else 'FLAT'
        mid=f.loc[a+pd.Timedelta(minutes=5):b-pd.Timedelta(minutes=5)] if b>a else f.iloc[0:0]
        expected=max(0,int((b-a)/pd.Timedelta(minutes=5))-1);row['fully_held_bars']=len(mid)
        if len(mid)!=expected or (len(mid)>1 and not (mid.index.to_series().diff().dropna()==pd.Timedelta(minutes=5)).all()):row['status']='UNKNOWN_PATH_GAPS'
        else:
            row['observed_favorable_pct'],row['observed_adverse_pct']=extrema(p0,px,tr.side,mid)
            row['status']='OBSERVED_ENDPOINTS_ONLY' if not len(mid) else 'OBSERVED_INTERNAL_BARS_AND_ENDPOINTS'
        rows.append(row)
    if len(rows)!=len(trades) or len({r['id'] for r in rows})!=len(rows):raise ValueError('missing source row')
    df=pd.DataFrame(rows);summary={}
    for c,g in df.groupby('coin'):
        matched=g[(g.status.isin(['OBSERVED_ENDPOINTS_ONLY','OBSERVED_INTERNAL_BARS_AND_ENDPOINTS']))&g.entry_price_inside_bar.eq(True)&g.exit_price_inside_bar.eq(True)]
        by_side={}
        for side,h in matched.groupby('side'):
            by_side[side]={'rows':len(h),'hold_minutes_median':float(h.hold_minutes.median()),'price_move_median_pct':float(h.recorded_price_move_pct.median()),'observed_favorable_median_pct':float(h.observed_favorable_pct.median()),'observed_adverse_median_pct':float(h.observed_adverse_pct.median()),'btc_above':int((h.btc_midpoint_prior20=='ABOVE').sum()),'btc_known':int((h.btc_midpoint_prior20!='UNKNOWN').sum()),'endpoints_only':int((h.status=='OBSERVED_ENDPOINTS_ONLY').sum())}
        summary[c]={'source_rows':len(g),'status_counts':{str(k):int(v) for k,v in g.status.value_counts().items()},'entry_strict_in_bar':int(g.entry_price_inside_bar.eq(True).sum()),'exit_strict_in_bar':int(g.exit_price_inside_bar.eq(True).sum()),'both_and_path_valid':len(matched),'by_side':by_side}
    if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('input changed')
    OUT.mkdir(parents=True);df.to_csv(OUT/'records.csv',index=False);result={'status':'DESCRIPTIVE_NOT_A_PROFIT_REPLICATION','summary':summary,'input_sha256':hashes,'scope':'one row per cleaned source record; not independent complete trades','limitations':['UTC+8 and venue unknown, account and records not independently verified.','No historical stop or take-profit orders.','Observed paths are bounds; 5-minute bars lack within-bar sequencing.','PNL fee inclusion and funding unknown.','All data used previously; cross-coins are not independent out-of-sample.']};(OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
