"""5-minute isolated-margin research replay; not an exchange simulator.

Fee, maintenance margin, mark proxy and order path are explicit assumptions.
Output is invalid for determining real liquidation or live trading readiness.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals


def replay(candles, hit, ema20, funding, start, end, fee=0.0005, slip=0.0, maintenance=0.005, risk_basis='equity', structural_stop=None,
           stop_trigger_low=None, liq_trigger_low=None, delayed_stop=False):
    """Long ETH; fixed leverage 5x, isolated proxy; end-exclusive UTC.

    OHLC low is a last-price proxy, not exchange mark. If stop and liquidation
    are both possible in one bar, liquidate first; intra-bar order is unknown.
    Fundings within a bar use its open as an approximate mark price.
    """
    if risk_basis not in ('equity','initial'): raise ValueError('unknown risk basis')
    if structural_stop is not None:
        if risk_basis!='initial' or len(structural_stop)!=len(candles): raise ValueError('invalid structural stop inputs')
        structural_stop=np.asarray(structural_stop,dtype=float)
    begin=pd.Timestamp(start, tz='UTC'); finish=pd.Timestamp(end, tz='UTC')
    ts=candles.ts; op=candles.open.to_numpy(); low=candles.low.to_numpy(); close=candles.close.to_numpy()
    ft=pd.to_datetime(funding.ts,unit='ms',utc=True); fr=funding.funding_rate.to_numpy()
    fidx=np.searchsorted(ft.array.asi8,begin.value); cash=2000.; positions=[]; closed=[]; curve=[(begin,2000.)]
    daily_count={}; skip=0; skip_invalid_stop=0; skip_capacity=0; skip_cash=0
    next_id=0; pending_exit=False; ambiguous=0; pending_open_mark_ambiguous=0; last_i=None
    a=int(np.searchsorted(ts.array.asi8,begin.value)); b=int(np.searchsorted(ts.array.asi8,finish.value))
    stop_low=low if stop_trigger_low is None else np.asarray(stop_trigger_low,dtype=float)
    liq_low=low if liq_trigger_low is None else np.asarray(liq_trigger_low,dtype=float)
    for trigger in (stop_low,liq_low):
        if len(trigger)!=len(candles) or not np.isfinite(trigger[a:b]).all() or (trigger[a:b]<=0).any():
            raise ValueError('invalid trigger price series')
    def close_pos(p, price, when, reason):
        nonlocal cash
        price=price*(1-slip); fee_out=p['qty']*price*fee
        gross=p['qty']*(price-p['entry']); cash+=p['margin']+gross-fee_out
        closed.append({**p,'exit_ts':str(when),'exit':price,'reason':reason,'gross_pnl':gross,
                       'exit_fee':fee_out,'net_pnl':gross-p['entry_fee']-fee_out-p['funding_paid']})
    for i in range(a,b):
        t=ts.iloc[i]; last_i=i
        # With a last-price liquidation proxy, an opening gap through the
        # proxy threshold precedes any assumed opening-price strategy exit.
        # A separate mark-price low does not reveal its value at the open.
        stay=[]
        for p in positions:
            liq=(p['entry']-p['margin']/p['qty'])/(1-maintenance)
            opening_exit=(p.get('pending_stop',False) or pending_exit or t>=p['entry_time']+pd.Timedelta(days=30))
            if liq_trigger_low is None and op[i]<=liq:
                close_pos(p,op[i],t,'liquidation_proxy')
            else:
                if liq_trigger_low is not None and opening_exit and liq_low[i]<=liq:
                    pending_open_mark_ambiguous+=1
                stay.append(p)
        positions=stay
        if delayed_stop:
            stay=[]
            for p in positions:
                if p.get('pending_stop'): close_pos(p,op[i],t,'stop_next_open')
                else: stay.append(p)
            positions=stay
        if pending_exit:
            for p in positions: close_pos(p,op[i],t,'ema20_next_open')
            positions=[]; pending_exit=False
        stay=[]
        for p in positions:
            if t>=p['entry_time']+pd.Timedelta(days=30): close_pos(p,op[i],t,'max_30d')
            else: stay.append(p)
        positions=stay
        if i>0 and hit[i-1]:
            day=t.date(); equity=cash+sum(p['margin']+p['qty']*(op[i]-p['entry']) for p in positions)
            risk=(max(0.,equity) if risk_basis=='equity' else 2000. if equity>0 else 0.)*.0015
            entry=op[i]*(1+slip)
            stop=entry*(1-.004) if structural_stop is None else structural_stop[i-1]
            invalid_stop=not np.isfinite(stop) or stop<=0 or stop>=entry
            if invalid_stop:
                margin=0.
            elif structural_stop is None:
                margin=min(risk/.004/5,max(0.,cash/(1+5*fee)))
            else:
                margin=min(750/5,risk/(entry-stop)*entry/5,max(0.,cash/(1+5*fee)))
            if len(positions)>=3 or daily_count.get(day,0)>=3:
                skip+=1;skip_capacity+=1
            elif invalid_stop:
                skip+=1;skip_invalid_stop+=1
            elif margin<=0:
                skip+=1;skip_cash+=1
            else:
                qty=margin*5/entry; entry_fee=qty*entry*fee
                cash-=margin+entry_fee;next_id+=1;daily_count[day]=daily_count.get(day,0)+1
                positions.append({'trade_id':next_id,'entry_time':t,'entry_ts':str(t),'entry':entry,'qty':qty,
                                  'margin':margin,'entry_fee':entry_fee,'funding_paid':0.,'stop':stop})
        # Funding position eligibility/order within a 5m bar cannot be determined.
        while fidx<len(ft) and ft.iloc[fidx]<t+pd.Timedelta(minutes=5):
            if ft.iloc[fidx]>=t:
                for p in positions:
                    amount=p['qty']*op[i]*fr[fidx];cash-=amount;p['funding_paid']+=amount
            fidx+=1
        stay=[]
        for p in positions:
            liq=(p['entry']-p['margin']/p['qty'])/(1-maintenance)
            liq_hit=liq_low[i]<=liq; stop_hit=stop_low[i]<=p['stop']
            if liq_hit:
                if stop_hit: ambiguous+=1
                close_pos(p,min(op[i],liq),t+pd.Timedelta(minutes=5),'liquidation_proxy')
            elif stop_hit:
                if delayed_stop:
                    p['pending_stop']=True;p['stop_trigger_bar']=str(t);stay.append(p)
                else: close_pos(p,min(op[i],p['stop']),t+pd.Timedelta(minutes=5),'stop')
            else: stay.append(p)
        positions=stay
        # Closing-equity observation; not a tick-by-tick drawdown.
        equity=cash+sum(p['margin']+p['qty']*(close[i]-p['entry']) for p in positions)
        curve.append((t+pd.Timedelta(minutes=5),equity))
        if t.hour==23 and t.minute==55 and close[i]<ema20.get(t.floor('D'),np.nan): pending_exit=True
    if last_i is None: raise ValueError('empty time window')
    mark=close[last_i]
    open_rows=[]
    for p in positions:
        open_rows.append({**p,'mark':mark,'unrealized_pnl':p['qty']*(mark-p['entry']),
                          'net_pnl_to_date':p['qty']*(mark-p['entry'])-p['entry_fee']-p['funding_paid']})
    series=pd.Series([v for _,v in curve],index=pd.DatetimeIndex([t for t,_ in curve]))
    equity=float(series.iloc[-1]);years=(finish-begin).total_seconds()/(365.25*86400)
    for row in closed+open_rows: row.pop('entry_time',None)
    audit=sum(x['net_pnl'] for x in closed)+sum(x['net_pnl_to_date'] for x in open_rows)
    return {'status':'EXPLORATORY_NOT_VALIDATED','initial':2000.,'equity_end':equity,'cash_end':cash,
            'return_pct':(equity/2000-1)*100,'cagr_pct':((equity/2000)**(1/years)-1)*100 if equity>0 else None,
            'mdd_close_5m_pct':float((series/series.cummax()-1).min()*100),'closed':len(closed),
            'open':len(open_rows),'skipped':skip,'skipped_invalid_stop':skip_invalid_stop,
            'skipped_capacity':skip_capacity,'skipped_cash':skip_cash,'proxy_liquidations':sum(x['reason']=='liquidation_proxy' for x in closed),
            'ambiguous_stop_liquidation_bars':ambiguous,
            'pending_open_mark_liquidation_order_unknown':pending_open_mark_ambiguous,
            'ledger_reconciliation_error':equity-2000-audit},closed,open_rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--outdir',required=True);args=ap.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    btc=load5('BTCUSDT');eth=load5('ETHUSDT');fund=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    hit,_,ema20=signals(btc,eth)
    report={'status':'EXPLORATORY_NOT_VALIDATED','assumptions':{'fee_per_side':.0005,'slippage_per_side':0.,
      'margin_mode':'isolated proxy, not verified','leverage':5,'maintenance_rate':.005,
      'mark_price':'last-price OHLC proxy; not verified','funding_price':'5m open proxy',
      'liquidation_order':'liquidation before stop when both possible, no liquidation fee',
      'exit_at_window_end':'mark open positions; no forced close','position_risk':'0.15%','btc_signals':'0 under frozen rule'},'windows':{}}
    for name,start,end in [('full','2022-05-01','2026-10-25'),('oos','2024-07-01','2026-10-25')]:
        result,closed,opened=replay(eth,hit,ema20,fund,start,end)
        report['windows'][name]=result
        pd.DataFrame(closed).to_csv(out/f'{name}_closed.csv',index=False)
        pd.DataFrame(opened).to_csv(out/f'{name}_open.csv',index=False)
    (out/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
