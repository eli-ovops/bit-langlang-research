"""Post-hoc limited alternatives, not trader rules or out-of-sample."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from . import nine_futures_compound_20261031 as model
from .forward_scan import read_raw_candles
from .nine_futures_compound_20261031 import START,END,sha

def simulate(idx,data,start=START,end=END,reward_multiple=2.0):
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
                    entry=float(d['open'][i])*(1+.0002);stop=float(d['stop'][i-2]);risk=entry-stop;target=entry+reward_multiple*risk
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
    stage=Path('data/market/nine-futures-stage-20261031-01');out=Path('data/verify/nine-variant-study-20261031-01');definition=Path('docs/九币入场退出-事后敏感性定义-20261031.md')
    if out.exists():raise FileExistsError('refusing overwrite')
    meta=json.loads((stage/'manifest.json').read_text());symbols=tuple(sorted(meta['symbols']));model.SYMBOLS=symbols
    for symbol in symbols:
        for suffix,key in [('_5m.csv.gz','price_sha256'),('_funding.csv.gz','funding_sha256')]:
            if sha(stage/(symbol+suffix))!=meta['symbols'][symbol][key]:raise ValueError('hash mismatch')
    idx,data=model.prepare(stage);trend={}
    for s in symbols:
        f=read_raw_candles(s,stage).set_index('ts').reindex(idx);trend[s]=(f.close>f.close.shift(48)).fillna(False).to_numpy()
    scenarios={'base':(False,2.0),'trend_filter':(True,2.0),'target_1R':(False,1.0),'target_3R':(False,3.0)}
    windows={'full':(START,END),'first':(START,pd.Timestamp('2026-03-01',tz='UTC')),'second':(pd.Timestamp('2026-03-01',tz='UTC'),END)}
    out.mkdir(parents=True);results={}
    for label,(filter_on,reward) in scenarios.items():
        d={s:{**value,'signal':value['signal'] & trend[s] if filter_on else value['signal']} for s,value in data.items()}
        results[label]={}
        for period,(start,end) in windows.items():
            metric,closed,opened=simulate(idx,d,start,end,reward_multiple=reward);results[label][period]=metric
            (out/f'{label}-{period}-closed.json').write_text(json.dumps(closed,ensure_ascii=False,allow_nan=False)+'\n')
            (out/f'{label}-{period}-open.json').write_text(json.dumps(opened,ensure_ascii=False,allow_nan=False)+'\n')
    existing=json.loads(Path('data/verify/nine-futures-compound-20261031-01/summary.json').read_text())['metrics']
    for k in ('equity_end','closed_count','win_count','fees_usdt','funding_usdt'):
        if results['base']['full'][k]!=existing[k]:raise ValueError('base mismatch '+k)
    report={'status':'POST_HOC_NOT_OUT_OF_SAMPLE','definition_sha256':sha(definition),'code_sha256':sha(__file__),'source_manifest_sha256':sha(stage/'manifest.json'),'results':results,'limitations':['All periods researched before model changes; not OOS.','User-selected nine assets retrospectively.','Execution and liquidation are OHLC approximations; actual stop target unknown.']}
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({s:{w:{k:v[k] for k in ('equity_end','return_pct','mdd_close_5m_pct','closed_count','open_count','win_count','fees_usdt')} for w,v in periods.items()} for s,periods in results.items()},indent=2))
if __name__=='__main__':main()
