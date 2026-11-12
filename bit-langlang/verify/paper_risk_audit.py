"""Conservative count checks across closed ledger and open snapshot, paper only."""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

from .forward_open import evaluate as evaluate_open
from .forward_report import CFG, capacity_bounds, load, report


def initial_price_risk_bounds(intervals):
    """Bounds of recorded initial risk when entry/exit ordering is unknown."""
    events={}
    for row in intervals.itertuples():
        events.setdefault(row.entry_time,[0.0,0.0])[1]+=row.initial_risk
        events.setdefault(row.exit_time,[0.0,0.0])[0]+=row.initial_risk
    current=lower=upper=0.0
    for time in sorted(events):
        exits,entries=events[time]
        upper=max(upper,current+entries)
        current+=entries-exits
        lower=max(lower,current)
    return lower,upper


def peak_initial_price_risk(intervals):
    """Compatibility: lower bound, not a maximum loss guarantee."""
    return initial_price_risk_bounds(intervals)[0]


def flat_entry_equity_check(closed, opened):
    """Compare entry equity only when recorded positions were flat beforehand."""
    trades=pd.DataFrame([{**record,'_closed':is_closed}
                         for frame,is_closed in ((closed,True),(opened,False))
                         for record in frame.to_dict('records')])
    if trades.empty: return []
    for col in ('exit_time','exit','fee_cost','funding_cost'):
        if col not in trades: trades[col]=pd.NA
    trades['entry_time']=pd.to_datetime(trades.entry_time,utc=True)
    trades['exit_time']=pd.to_datetime(trades.exit_time,utc=True)
    for col in ('entry','exit','qty','fee_cost','funding_cost','equity_at_entry'):
        trades[col]=pd.to_numeric(trades[col],errors='coerce')
    trades['_net']=(trades.exit-trades.entry)*trades.qty-trades.fee_cost-trades.funding_cost
    records=[]
    for row in trades.itertuples():
        t=row.entry_time
        simultaneous=trades.entry_time.eq(t).sum()>1
        prior=trades[trades.entry_time<t]
        overlap=(~prior._closed | (prior.exit_time>=t)).any()
        if simultaneous or overlap:
            records.append({'trade_id':str(row.trade_id),'status':'UNKNOWN_OVERLAP_OR_ORDER'})
            continue
        expected=CFG['sizing']['account_usdt']+prior._net.sum()
        difference=float(row.equity_at_entry-expected)
        records.append({'trade_id':str(row.trade_id),
                        'status':'MATCH_ASSUMED' if abs(difference)<=.01 else 'MISMATCH_ASSUMED',
                        'expected_usdt':round(float(expected),6),'recorded_usdt':round(float(row.equity_at_entry),6),
                        'difference_usdt':round(difference,6)})
    return records


def audit(closed, opened, start, as_of, *, verify_flat_equity=True):
    closed_result=report(closed, start, as_of)
    open_result=evaluate_open(opened, as_of)
    if closed_result['status']=='INVALID' or open_result['status']=='INVALID':
        return {'status':'INVALID','closed':closed_result,'open':open_result}
    now=pd.to_datetime(as_of,utc=True,errors='coerce')
    begin=pd.to_datetime(start,utc=True,errors='coerce')
    if pd.isna(now) or pd.isna(begin):
        return {'status':'INVALID','reason':'时间格式无效'}
    closed_ids=set(closed.trade_id.astype(str))
    open_ids=set(opened.trade_id.astype(str))
    if closed_ids & open_ids:
        return {'status':'INVALID','reason':'同一交易编号同时出现于已平仓和未平仓记录'}
    opened_times=pd.to_datetime(opened.entry_time,utc=True,errors='coerce')
    if (opened_times<begin).any() or (opened_times>now).any():
        return {'status':'INVALID','reason':'未平仓入场时间不在前瞻区间'}
    entry_equity=flat_entry_equity_check(closed,opened) if verify_flat_equity else []
    intervals=pd.DataFrame({'entry_time':pd.to_datetime(closed.entry_time,utc=True),
                            'exit_time':pd.to_datetime(closed.exit_time,utc=True)})
    # Open positions are active through as_of, including entries exactly at as_of.
    live=pd.DataFrame({'entry_time':opened_times,'exit_time':now+pd.Timedelta(nanoseconds=1)})
    intervals=pd.concat([intervals,live],ignore_index=True)
    daily,concurrent,concurrent_upper,order_ambiguous=capacity_bounds(intervals)
    nonempty=[f[['entry','stop','qty']] for f in (closed,opened) if not f.empty]
    combined=pd.concat(nonempty,ignore_index=True) if nonempty else pd.DataFrame(columns=['entry','stop','qty'])
    intervals['initial_risk']=(pd.to_numeric(combined.entry)-pd.to_numeric(combined.stop))*pd.to_numeric(combined.qty)
    peak_risk,peak_risk_upper=initial_price_risk_bounds(intervals)
    if not all(math.isfinite(value) for value in (peak_risk,peak_risk_upper)):
        return {'status':'INVALID','reason':'组合峰值初始价格风险计算非有限值'}
    limits={'daily_entries_over_limit':daily>CFG['sizing']['max_new_per_day'],
            'concurrent_over_limit':concurrent>CFG['sizing']['max_concurrent']}
    concurrent_assessment=('EXCEEDED' if limits['concurrent_over_limit'] else
                           'AMBIGUOUS_ORDER' if concurrent_upper>CFG['sizing']['max_concurrent'] else
                           'WITHIN_RECORDED_BOUNDS')
    if any(limits.values()) or closed_result['status']=='STOP' or open_result['status']=='ALERT' or any(x['status']=='MISMATCH_ASSUMED' for x in entry_equity):
        status='STOP'
    elif open_result['status']=='STALE':
        status='STALE'
    elif intervals.empty:
        status='UNKNOWN'
    elif order_ambiguous:
        status='AMBIGUOUS_ORDER'
    else:
        status='REVIEW'
    return {'status':status,'max_daily_entries_recorded':daily,'max_concurrent_recorded':concurrent,
            'max_concurrent_upper_recorded':concurrent_upper,'same_time_order_ambiguous':order_ambiguous,
            'peak_initial_price_risk_usdt_recorded':round(float(peak_risk),6),
            'peak_initial_price_risk_upper_usdt_recorded':round(float(peak_risk_upper),6),
            'concurrent_limit_assessment':concurrent_assessment,
            'combined_limit_violations':limits,'flat_entry_equity_check':entry_equity,
            'flat_entry_equity_context':'ASSUMED_COMPLETE_LEDGER' if verify_flat_equity else 'UNKNOWN_INCOMPLETE_LEDGER',
            'closed':closed_result,'open':open_result,
            'reason':'仅检查提供的记录；同刻入出场的并发和初始价格风险给出上下界，顺序不明不得按下界确认合规。入场权益只在假设初始2000U、账本完整且无资金流等条件下核对记录上的空仓时点，有重叠或同刻次序不明则 UNKNOWN。峰值不是最大可能损失；现金、资金费完整性及真实强平 UNKNOWN，不能自动 PASS。'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--closed',required=True)
    parser.add_argument('--open',required=True,dest='open_file')
    parser.add_argument('--start',required=True)
    parser.add_argument('--as-of',required=True)
    args=parser.parse_args()
    if not Path(args.closed).is_file() or not Path(args.open_file).is_file():
        print(json.dumps({'status':'UNKNOWN','reason':'已平仓或未平仓文件不存在，不能当作空记录'},ensure_ascii=False));return
    now=pd.to_datetime(args.as_of,utc=True,errors='coerce')
    if pd.isna(now) or now>pd.Timestamp.now(tz='UTC'):
        print(json.dumps({'status':'INVALID','reason':'检查时间无效或晚于现在'},ensure_ascii=False));return
    print(json.dumps(audit(load(args.closed),load(args.open_file),args.start,args.as_of),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
