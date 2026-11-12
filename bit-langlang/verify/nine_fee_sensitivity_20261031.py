"""Retrospective hypothetical fee sensitivity, not account rates."""
import json
from pathlib import Path
import numpy as np,pandas as pd
from . import nine_futures_oct31_20261031 as model
from .forward_scan import read_raw_candles
from .nine_futures_compound_20261031 import sha
START=model.START;END=model.END

def simulate(idx,data,start=START,end=END,reward_multiple=2.0,fee_rate=.0005):
    cash=2000.;position=None;closed=[];curve=[];skips={};candidates=0;ties=0;ambiguous=0;boundary=[]
    start_i=int(idx.searchsorted(start));end_i=int(idx.searchsorted(end));ms=idx.asi8//1_000_000
    def count(reason):skips[reason]=skips.get(reason,0)+1
    def close(p,price,t,reason):
        nonlocal cash
        fill=price*(1-.0002);fee=p['qty']*fill*fee_rate;gross=p['qty']*(fill-p['entry'])
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
                        qty=min(equity*.01/risk,equity*.25*5/entry,cash/(entry/5+entry*fee_rate))
                        if qty<=0:count('no_cash')
                        else:
                            margin=qty*entry/5;fee=qty*entry*fee_rate;cash-=margin+fee
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
              'estimated_exit_fee':p['qty']*mark*(1-.0002)*fee_rate}]
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
 stage=Path('data/market/nine-futures-stage-oct31-20261031-01');out=Path('data/verify/nine-fee-sensitivity-20261031-01');definition=Path('docs/九币30日强势-费用敏感性定义-20261031.md')
 if out.exists():raise FileExistsError(out)
 idx,data=model.prepare(stage);days=idx.floor('D');btc=read_raw_candles('BTCUSDT',stage).set_index('ts').reindex(idx).resample('D').agg({'high':'max','low':'min','close':'last','open':'count'});phase=(btc.close>(btc.high.rolling(20,min_periods=20).max()+btc.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False).reindex(days).to_numpy();br=btc.close.pct_change(30,fill_method=None);frames={};scores={}
 for s in data:
  f=read_raw_candles(s,stage).set_index('ts').reindex(idx);frames[s]=f;daily=f.resample('D').agg({'close':'last','open':'count'});warm=daily.open.eq(288).shift(1,fill_value=False).rolling(31,min_periods=31).sum().eq(31);scores[s]=(daily.close.pct_change(30,fill_method=None)-br).shift(1).where(warm)
 scores=pd.DataFrame(scores);ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first');changed={}
 for s,d in data.items():
  f=frames[s];lo=f.low.shift(1).rolling(20,min_periods=20).min();hi=f.high.shift(1).rolling(20,min_periods=20).max();lo4=f.low.shift(1).rolling(48,min_periods=48).min();hi4=f.high.shift(1).rolling(48,min_periods=48).max();pattern=((f.close.shift(1)<f.open.shift(1))&(f.close>f.open)&(f.close>f.close.shift(1))&(f.close>=(lo+hi)/2)&(f.close>=(lo4+hi4)/2)).to_numpy();rank=ranks[s].reindex(days).to_numpy();changed[s]={**d,'signal':pattern&(rank<=2)&phase,'rank':rank,'relative_strength':scores[s].reindex(days).to_numpy()}
 out.mkdir(parents=True);result={}
 for name,rate in [('zero',0.),('half',.00025),('base',.0005),('higher',.00075)]:
  metrics,closed,opened=simulate(idx,changed,START,END,fee_rate=rate);result[name]=metrics;(out/f'{name}-closed.json').write_text(json.dumps(closed,allow_nan=False)+'\n');(out/f'{name}-open.json').write_text(json.dumps(opened,allow_nan=False)+'\n')
 old=json.loads(Path('data/verify/nine-slow-research-20261031-01/summary.json').read_text())['results']['strength30']['full']
 for k in ('equity_end','closed_count','win_count','fees_usdt','funding_usdt'):assert result['base'][k]==old[k],k
 (out/'summary.json').write_text(json.dumps({'status':'POST_HOC_COST_SENSITIVITY','definition_sha256':sha(definition),'code_sha256':sha(__file__),'results':result,'limits':['Retrospective; assumed maker/taker, spreads, liquidation and funding.','Zero fee is theoretical and includes assumed slippage.']},indent=2)+'\n');print(json.dumps({k:{q:v[q] for q in ('equity_end','return_pct','mdd_close_5m_pct','closed_count','open_count','fees_usdt','funding_usdt')} for k,v in result.items()},indent=2))
if __name__=='__main__':main()
