"""Frozen TPH research replay. Uses only information available at signal close.

Output is exploratory: BTC cannot pass its self-relative-strength rule, and
fixed cost assumptions have not been verified against an execution venue.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .forward_scan import CFG


def signals(btc, coin):
    def daily(d):
        d = d.set_index('ts')
        return d.resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'})
    bd, cd = daily(btc), daily(coin)
    e50 = bd.close.ewm(span=50, adjust=False).mean()
    e200 = bd.close.ewm(span=200, adjust=False).mean()
    context = pd.DataFrame(index=cd.index)
    context['rs7'] = cd.close.pct_change(7) - bd.close.pct_change(7).reindex(cd.index)
    context['dist_hi'] = (cd.high.rolling(20).max() - cd.close) / cd.close
    context['risk_on'] = ((bd.close > e50) & (e50 > e50.shift(5)) & (bd.close > e200)).reindex(cd.index)
    context = context.shift(1).reindex(coin.ts.dt.floor('D')).reset_index(drop=True)
    low = coin.low.rolling(20, min_periods=20).min()
    hit = ((context.rs7 > 0) & (context.dist_hi < .03) & (context.risk_on == True)
           & (coin.low <= low * 1.001) & (coin.close > coin.close.shift(1)))
    return hit.fillna(False).to_numpy(), context, cd.close.ewm(span=20, adjust=False).mean()


def generate(btc, coin, funding, start, end):
    hit, context, ema20 = signals(btc, coin)
    ts = coin.ts; o=coin.open.to_numpy(); low=coin.low.to_numpy(); close=coin.close.to_numpy()
    ft=pd.to_datetime(funding.ts, unit='ms', utc=True).astype('int64').to_numpy()
    rates=funding.funding_rate.to_numpy(); prefix=np.r_[0.0,np.cumsum(rates)]
    out=[]; last=pd.Timestamp(end, tz='UTC'); first=pd.Timestamp(start,tz='UTC')
    for i in np.flatnonzero(hit):
        if i+1>=len(coin) or ts.iloc[i+1]<first or ts.iloc[i+1]>=last: continue
        entry=o[i+1]; stop=entry*(1-CFG['stop_pct']); j=i+1; exit_price=None; reason=None
        deadline=ts.iloc[i+1]+pd.Timedelta(days=30)
        while j<len(coin) and ts.iloc[j]<last:
            if low[j]<=stop:
                exit_price=min(o[j],stop); reason='stop'; break
            # Daily exit is decided after the final 5m candle closes, filled next open.
            if (ts.iloc[j].hour==23 and ts.iloc[j].minute==55 and j+1<len(coin)
                    and ts.iloc[j+1]<last and close[j]<ema20.get(ts.iloc[j].floor('D'), np.nan)):
                j+=1; exit_price=o[j]; reason='ema20_next_open'; break
            if ts.iloc[j]>=deadline:
                exit_price=o[j]; reason='max_30d'; break
            j+=1
        if exit_price is None:
            # No synthetic close at dataset boundary: report the truncated position separately.
            continue
        exit_time = ts.iloc[j] + (pd.Timedelta(minutes=5) if reason == 'stop' else pd.Timedelta(0))
        t0=ts.iloc[i+1].value; t1=exit_time.value
        funding_sum=prefix[np.searchsorted(ft,t1,side='left')]-prefix[np.searchsorted(ft,t0,side='left')]
        gross=(exit_price-entry)/(entry*CFG['stop_pct'])
        cost=.001/CFG['stop_pct']+funding_sum/CFG['stop_pct']
        out.append(dict(symbol='ETHUSDT',entry_ts=ts.iloc[i+1],exit_ts=exit_time,entry=entry,exit=exit_price,
                        gross_R=gross,cost_R=cost,net_R=gross-cost,reason=reason,rs7=float(context.rs7.iloc[i])))
    return pd.DataFrame(out)


def simulate(tr, start, end):
    equity=2000.; positions=[]; used=0.; taken=0; skipped=0; per_day={}; curve=[(pd.Timestamp(start,tz='UTC'),equity)]
    for t in tr.sort_values('entry_ts').itertuples():
        remaining=[]
        for ex,pnl,margin in sorted(positions):
            if ex<=t.entry_ts:
                equity+=pnl; used-=margin;curve.append((ex,equity))
            else: remaining.append((ex,pnl,margin))
        positions=remaining; day=t.entry_ts.date()
        if len(positions)>=3 or per_day.get(day,0)>=3 or equity<=0:
            skipped+=1;continue
        risk=min(equity*.0015,max(0.,equity-used)*5*.004)
        if risk<=0: skipped+=1;continue
        margin=risk/.004/5;used+=margin;positions.append((t.exit_ts,t.net_R*risk,margin));taken+=1
        per_day[day]=per_day.get(day,0)+1
    for ex,pnl,margin in sorted(positions):
        equity+=pnl;curve.append((ex,equity))
    curve.append((pd.Timestamp(end,tz='UTC'),equity))
    v=pd.Series([e for _,e in curve],index=pd.DatetimeIndex([t for t,_ in curve])).sort_index()
    years=(pd.Timestamp(end)-pd.Timestamp(start)).days/365.25
    monthly=v.resample('ME').last().ffill().pct_change().dropna()
    return {'initial':2000,'final':round(equity,2),'return_pct':round((equity/2000-1)*100,2),
            'cagr_pct':round(((equity/2000)**(1/years)-1)*100,2) if equity>0 else None,
            'realized_mdd_pct':round(float((v/v.cummax()-1).min()*100),2),
            'monthly_sharpe':round(float(monthly.mean()/monthly.std()*np.sqrt(12)),2) if len(monthly)>2 and monthly.std()>0 else None,
            'taken':taken,'skipped':skipped}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);a=ap.parse_args()
    path=Path(a.out)
    if path.exists(): raise SystemExit('refusing to overwrite output')
    btc=load5('BTCUSDT');eth=load5('ETHUSDT');f=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    summary={'status':'EXPLORATORY_NOT_VALIDATED','notes':['冻结规则 BTC 相对自身始终为零','10bp 往返为假设，非实际手续费/滑点','回撤仅按已实现权益计算，不含浮亏','窗口末未平仓候选未计入，存在截尾偏差','无强平与订单簿建模','事后选择的样本外不是真正前瞻'],'windows':{}}
    for name,start,end in [('full','2022-05-01','2026-10-25'),('oos','2024-07-01','2026-10-25')]:
        tr=generate(btc,eth,f,start,end)
        summary['windows'][name]={'candidates':len(tr),'by_symbol':{'BTCUSDT':0,'ETHUSDT':len(tr)},'metrics':simulate(tr,start,end) if len(tr) else None}
    path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
