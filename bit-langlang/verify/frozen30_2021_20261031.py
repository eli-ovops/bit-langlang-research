"""Nine-symbol shared-equity OHLC research proxy. Not exchange fills or advice."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_scan import read_raw_candles,closed_snapshot
SYMBOLS=('SOLUSDT','UNIUSDT','AAVEUSDT','LINKUSDT')

START=pd.Timestamp('2021-01-01',tz='UTC');END=pd.Timestamp('2022-01-01',tz='UTC')
DATA_START=pd.Timestamp('2020-11-01',tz='UTC')
DEFINITION=Path('docs/30日强势-2021时间外推-冻结定义-20261031.md')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(stage):
    idx=pd.date_range(DATA_START,END-pd.Timedelta(minutes=5),freq='5min')
    btc,state=closed_snapshot(read_raw_candles('BTCUSDT',stage),END,minimum_bars=205*288)
    if btc is None or state['status']!='FRESH':raise ValueError('BTC data invalid')
    btc=btc.set_index('ts').reindex(idx)
    if btc[['open','high','low','close']].isna().any().any():raise ValueError('BTC history missing')
    bd=btc.resample('1D').agg({'high':'max','low':'min','close':'last'})
    regime=(bd.close>(bd.high.rolling(20,min_periods=20).max()+bd.low.rolling(20,min_periods=20).min())/2).shift(1).fillna(False)
    br=bd.close.pct_change(30,fill_method=None)
    frames={};daily={};rank_data={};funding={}
    for symbol in sorted(SYMBOLS):
        f=read_raw_candles(symbol,stage)
        if f is None or f.ts.duplicated().any() or not f.ts.is_monotonic_increasing or (f.ts.diff().dropna()!=pd.Timedelta(minutes=5)).any():raise ValueError('invalid symbol grid')
        f=f.set_index('ts').reindex(idx)
        frames[symbol]=f
        dd=f.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
        complete=dd.open.eq(288)
        eligible=complete.shift(1).fillna(False).rolling(31,min_periods=31).sum().eq(31)
        rank_data[symbol]=(dd.close.pct_change(30,fill_method=None)-br).shift(1).where(eligible)
        daily[symbol]=dd.high.rolling(20,min_periods=20).max().shift(1)
        rates=pd.read_csv(Path(stage)/f'{symbol}_funding.csv.gz')
        if rates.ts.duplicated().any() or not rates.ts.is_monotonic_increasing or not np.isfinite(rates.to_numpy(dtype=float)).all():raise ValueError('funding invalid')
        # Preserve each settlement time rather than treating absent records as zero.
        funding[symbol]={int(r.ts)//300000*300000:(int(r.ts),float(r.funding_rate)) for r in rates.itertuples()}
        if len(funding[symbol])!=len(rates):raise ValueError('multiple settlements within one bar')
    scores=pd.DataFrame(rank_data).where(regime,axis=0)
    ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first')
    data={}
    for symbol in sorted(SYMBOLS):
        f=frames[symbol];prior=f.low.shift(1).rolling(20,min_periods=20).min()
        four_hi=f.high.shift(1).rolling(48,min_periods=48).max();four_lo=f.low.shift(1).rolling(48,min_periods=48).min()
        day=idx.floor('D'); target=daily[symbol].reindex(day).to_numpy();rank=ranks[symbol].reindex(day).to_numpy()
        relative_strength=scores[symbol].reindex(day).to_numpy()
        prior_hi=f.high.shift(1).rolling(20,min_periods=20).max()
        signal=((f.close.shift(1)<f.open.shift(1)) & (f.close>f.open) & (f.close>f.close.shift(1))
                & (f.close>=(prior_hi+prior)/2) & (f.close>=(four_hi+four_lo)/2)).to_numpy()
        stop=f.low.rolling(12,min_periods=12).min().to_numpy()
        data[symbol]={'open':f.open.to_numpy(),'high':f.high.to_numpy(),'low':f.low.to_numpy(),'close':f.close.to_numpy(),
                      'signal':signal & (rank<=2),'rank':rank,'relative_strength':relative_strength,
                      'stop':stop,'target':target,'funding':funding[symbol]}
    return idx,data


def simulate(idx,data,start=START,end=END):
    cash=2000.;position=None;closed=[];curve=[];skips={};candidates=0;ties=0;ambiguous=0;boundary=[]
    start_i=int(idx.searchsorted(start));end_i=int(idx.searchsorted(end));ms=idx.asi8//1_000_000
    def count(reason):skips[reason]=skips.get(reason,0)+1
    def close(p,price,t,reason):
        nonlocal cash
        fill=price*(1-.0002);fee=p['qty']*fill*.0005;gross=p['qty']*(fill-p['entry'])
        cash+=p['margin']+gross-fee
        net=gross-p['entry_fee']-fee-p['funding_paid']
        close_ms=t.value//1_000_000
        included={event['ts'] for event in p['funding_events']}
        possible=data[p['symbol']]['funding']
        for bucket in {((close_ms+offset)//300000)*300000 for offset in (-60000,0,60000)}:
            event=possible.get(bucket)
            if event and abs(event[0]-close_ms)<=60000:
                boundary.append({'symbol':p['symbol'],'event':event[0],'kind':'exit','included':event[0] in included})
        closed.append({**p,'exit_ts':t.isoformat(),'exit':fill,'reason':reason,'gross_pnl':gross,
                       'exit_fee':fee,'net_pnl':net,'net_R':net/p['initial_risk']})
    daily_count={}
    for i in range(start_i,end_i):
        t=idx[i]
        if position:
            p=position;d=data[p['symbol']];op=d['open'][i]
            liq=(p['entry']-p['margin']/p['qty'])/(1-p['maintenance'])
            if op<=liq:
                close(p,op,t,'liquidation_proxy_open');position=None
            elif p.get('pending') or t>=pd.Timestamp(p['entry_ts'])+pd.Timedelta(days=30):
                close(p,op,t,p.get('pending') or 'max_30d');position=None
        day=t.date().isoformat()
        if i>=2 and idx[i-2]>=start:
            hit=[s for s in sorted(data) if data[s]['signal'][i-2]]
            candidates+=len(hit)
            if hit:
                if position:count('occupied')
                elif daily_count.get(day,0)>=3:count('daily_limit')
                else:
                    if len(hit)>1:ties+=1
                    hit.sort(key=lambda s:(data[s]['rank'][i-2],s));s=hit[0];d=data[s]
                    entry=float(d['open'][i])*(1+.0002);stop=float(d['stop'][i-2]);risk=entry-stop;target=entry+2*risk
                    equity=cash
                    if not np.isfinite([entry,stop,target,equity]).all() or risk<=0 or target<=entry or equity<=0:
                        count('invalid_or_space')
                    else:
                        qty=min(equity*.01/risk,equity*.25*5/entry,cash/(entry/5+entry*.0005))
                        if qty<=0:count('no_cash')
                        else:
                            margin=qty*entry/5;fee=qty*entry*.0005;cash-=margin+fee
                            position={'symbol':s,'signal_ts':idx[i-2].isoformat(),'entry_ts':t.isoformat(),
                                      'signal_close':float(d['close'][i-2]),'signal_rank':int(d['rank'][i-2]),
                                      'signal_relative_strength':float(d['relative_strength'][i-2]),
                                      'entry_reference_open':float(d['open'][i]),
                                      'entry':entry,'stop':stop,'target':target,'qty':qty,'margin':margin,
                                      'entry_fee':fee,'funding_paid':0.,'funding_events':[],'entry_equity':equity,
                                      'initial_risk':qty*risk,'maintenance':.10 if s=='LITUSDT' else .005}
                            daily_count[day]=daily_count.get(day,0)+1
                    if len(hit)>1:count('other_simultaneous_candidates')
        if position:
            p=position;d=data[p['symbol']];f=d['funding'].get(int(ms[i]))
            if f:
                stamp,rate=f;amount=p['qty']*float(d['open'][i])*rate;cash-=amount;p['funding_paid']+=amount
                p['funding_events'].append({'ts':stamp,'rate':rate,'reference_open':float(d['open'][i]),'amount':amount})
                if abs(stamp-int(pd.Timestamp(p['entry_ts']).value//1_000_000))<=60000:boundary.append({'symbol':p['symbol'],'event':stamp,'kind':'entry'})
            liq=(p['entry']-p['margin']/p['qty'])/(1-p['maintenance'])
            low=float(d['low'][i]);high=float(d['high'][i]);op=float(d['open'][i])
            stop_hit=low<=p['stop'];target_hit=high>=p['target'];liq_hit=low<=liq
            if stop_hit and (target_hit or liq_hit):ambiguous+=1
            if liq_hit:
                close(p,min(op,liq),t+pd.Timedelta(minutes=5),'liquidation_proxy');position=None
            elif stop_hit or target_hit:
                p['pending']='stop_next_open' if stop_hit else 'target_next_open'
        equity=cash+(position['margin']+position['qty']*(float(data[position['symbol']]['close'][i])-position['entry']) if position else 0.)
        if not np.isfinite(equity):raise ValueError('nonfinite equity')
        curve.append(float(equity))
        if equity<=0:break
    if not curve:raise ValueError('empty window')
    opened=[]
    if position:
        p=position;mark=float(data[p['symbol']]['close'][i]);opened=[{**p,'mark':mark,'unrealized_gross':p['qty']*(mark-p['entry']),
              'net_to_date':p['qty']*(mark-p['entry'])-p['entry_fee']-p['funding_paid'],
              'estimated_exit_fee':p['qty']*mark*(1-.0002)*.0005}]
    audit=2000+sum(x['net_pnl'] for x in closed)+sum(x['net_to_date'] for x in opened)
    if abs(curve[-1]-audit)>1e-7:raise ValueError('ledger equity mismatch')
    values=np.asarray(curve);peaks=np.maximum.accumulate(np.r_[2000.,values])[1:]
    results={'initial':2000.,'equity_end':float(values[-1]),'end_observed':(idx[i]+pd.Timedelta(minutes=5)).isoformat(),
             'return_pct':float((values[-1]/2000-1)*100),'mdd_close_5m_pct':float((values/peaks-1).min()*100),
             'closed_count':len(closed),'open_count':len(opened),'win_count':int(sum(x['net_pnl']>0 for x in closed)),
             'candidate_events':candidates,'skipped_events':skips,'simultaneous_candidate_bars':ties,
             'ambiguous_trigger_bars':ambiguous,'ledger_error':float(curve[-1]-audit),
             'liquidations':sum(x['reason'].startswith('liquidation_proxy') for x in closed),
             'fees_usdt':float(sum(x['entry_fee']+x['exit_fee'] for x in closed)+sum(x['entry_fee'] for x in opened)),
             'funding_usdt':float(sum(x['funding_paid'] for x in closed+opened)),'funding_boundaries':boundary}
    return results,closed,opened


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--outdir',required=True);args=p.parse_args()
    stage=Path(args.stage);manifest=json.loads((stage/'manifest.json').read_text())
    for symbol in SYMBOLS:
        for suffix,key in (('_5m.csv.gz','price_sha256'),('_funding.csv.gz','funding_sha256')):
            if sha(stage/(symbol+suffix))!=manifest['symbols'][symbol][key]:raise ValueError('input hash mismatch')
    btc=stage/'BTCUSDT_5m.csv.gz';btc_hash=sha(btc)
    idx,data=prepare(stage);metrics,closed,opened=simulate(idx,data)
    if sha(btc)!=btc_hash:raise ValueError('BTC changed')
    output=Path(args.outdir);output.mkdir(parents=True,exist_ok=False)
    report={'status':'EXPLORATORY_NOT_VALIDATED','definition_sha256':sha(DEFINITION),'code_sha256':sha(__file__),
            'manifest_sha256':sha(stage/'manifest.json'),'btc_sha256':btc_hash,'metrics':metrics,
            'limitations':['Single account; simulated 5m OHLC, not executable prices or actual mark.',
                           'Historical user-selected coins and subjective proxies, no independent OOS.',
                           'Funding completeness, margin, liquidity and settlement timing unverified.']}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (output/'closed.json').write_text(json.dumps(closed,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (output/'open.json').write_text(json.dumps(opened,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(metrics,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
