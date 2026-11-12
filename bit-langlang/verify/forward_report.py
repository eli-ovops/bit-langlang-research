#!/usr/bin/env python3
"""Paper-only forward ledger. Costs in USDT; execution prices include slippage.

funding_cost is signed: positive paid, negative received. start/as-of are UTC.
PASS is deliberately disabled until the forward protocol is re-registered.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import VERIFY

CFG = json.loads(Path(__file__).with_name('frozen_config.json').read_text())
REQUIRED = ['trade_id','entry_time','exit_time','symbol','side','entry','stop','exit','qty',
            'equity_at_entry','fee_cost','funding_cost','five_q_pass','stop_placed','added','reversed','plan_deviation']
NUMERIC = ['entry','stop','exit','qty','equity_at_entry','fee_cost','funding_cost']
FLAGS = ['five_q_pass','stop_placed','added','reversed','plan_deviation']
REFERENCES = ['reference_entry','reference_exit','reference_source']
MISSING_TOKENS={'','UNKNOWN','N/A','NA','NAN','?','[?]','NULL','NONE','<NA>'}


def valid_trade_id(value):
    text=str(value)
    return text==text.strip() and text.upper() not in MISSING_TOKENS


def load(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def paper_margin_check(d):
    """Optional allocated initial margin, not exchange leverage verification."""
    raw=d['margin_at_entry'] if 'margin_at_entry' in d else pd.Series('',index=d.index)
    supplied=~raw.fillna('').astype(str).str.strip().str.upper().isin(MISSING_TOKENS)
    margin=pd.to_numeric(raw.where(supplied),errors='coerce')
    if (supplied & (~np.isfinite(margin) | (margin<=0))).any():
        return {'status':'INVALID','over_limit':False,'ratios':None}
    ratios=(d.entry*d.qty/margin).where(supplied)
    if (supplied & ~np.isfinite(ratios)).any():
        return {'status':'INVALID','over_limit':False,'ratios':None}
    return {'status':'PROVIDED_UNVERIFIED' if supplied.all() else 'UNKNOWN_INCOMPLETE',
            'over_limit':bool((ratios>CFG['sizing']['leverage_cap']+1e-9).any()),'ratios':ratios}


def capacity_bounds(d):
    """Concurrency bounds when exits and entries share a timestamp."""
    if d.empty:
        return 0, 0, 0, False
    max_daily=int(d.groupby(d.entry_time.dt.floor('D')).size().max())
    events={}
    for row in d.itertuples():
        events.setdefault(row.entry_time, [0, 0])[1] += 1
        events.setdefault(row.exit_time, [0, 0])[0] += 1
    current=peak_lower=peak_upper=0
    ambiguous=False
    for exits, entries in (events[t] for t in sorted(events)):
        if exits and entries: ambiguous=True
        peak_upper=max(peak_upper,current+entries)
        current += entries-exits
        peak_lower=max(peak_lower,current)
    return max_daily,peak_lower,peak_upper,ambiguous


def capacity_counts(d):
    """Compatibility: lower bound treats same-time exits before entries."""
    daily,lower,_,_=capacity_bounds(d)
    return daily,lower


def report(data, start=None, as_of=None):
    missing = [x for x in REQUIRED if x not in data.columns]
    if missing: return {'status':'INVALID','reason':'缺少必需字段: '+', '.join(missing)}
    if not start: return {'status':'INVALID','reason':'必须提供新的纸面前瞻起点 --start（UTC）；不能追溯填报。'}
    try:
        start = pd.to_datetime(start, utc=True, errors='raise')
        now = pd.to_datetime(as_of, utc=True, errors='raise') if as_of else pd.Timestamp.now(tz='UTC')
    except (TypeError, ValueError):
        return {'status':'INVALID','reason':'起点或检查时间格式无效。'}
    if pd.isna(start) or pd.isna(now):
        return {'status':'INVALID','reason':'起点或检查时间格式无效。'}
    if start < pd.Timestamp(CFG['frozen_at'], tz='UTC'):
        return {'status':'INVALID','reason':'前瞻起点早于冻结日期。'}
    if start > now: return {'status':'INVALID','reason':'前瞻起点晚于检查时间。'}
    d = data.copy()
    if d.empty: return {'status':'NO_DATA','n':0,'days':(now-start).days,'reason':'没有已平仓纸面记录；不得回填历史交易。'}
    for c in ['entry_time','exit_time']: d[c] = pd.to_datetime(d[c], utc=True, errors='coerce')
    for c in NUMERIC: d[c] = pd.to_numeric(d[c], errors='coerce')
    errors=[]
    if d[REQUIRED].isna().any().any(): errors.append('时间或数值无效/缺失')
    if not d.trade_id.map(valid_trade_id).all() or d.trade_id.astype(str).duplicated().any(): errors.append('交易编号缺失、带首尾空格或重复')
    if ((d.entry_time < start) | (d.exit_time <= d.entry_time) | (d.exit_time > now)).any(): errors.append('时间超出前瞻区间，或出场不晚于入场（需更精确时间）')
    if (~d.symbol.isin(CFG['universe']) | ~d.side.str.lower().isin(['long','多'])).any(): errors.append('交易币种或方向不符合冻结规则')
    if (d.symbol == 'BTCUSDT').any(): errors.append('冻结条件使 BTC 相对自身强度恒为零，BTC 入场不能算合规信号')
    if ((d[['entry','stop','exit','qty','equity_at_entry']] <= 0).any(axis=1) | (d.stop >= d.entry) | (d.fee_cost < 0)).any(): errors.append('价格、数量、权益、手续费或止损方向无效')
    if (((d.entry-d.stop)/d.entry-CFG['stop_pct']).abs() > 0.0001).any(): errors.append('止损距离与冻结 0.4% 不一致（允许 1bp 价格取整）')
    if (~np.isfinite(d[NUMERIC].to_numpy(dtype=float))).any(): errors.append('数值必须有限')
    for flag in FLAGS:
        if not d[flag].astype(str).isin(['0','1']).all(): errors.append(flag+' 必须为 0 或 1')
    if errors: return {'status':'INVALID','n':len(d),'reason':'；'.join(errors)}
    margin_check=paper_margin_check(d)
    if margin_check['status']=='INVALID': return {'status':'INVALID','n':len(d),'reason':'纸面初始保证金无效或名义倍数非有限值'}
    d['paper_initial_leverage']=margin_check['ratios']
    d['risk_usdt']=(d.entry-d.stop)*d.qty
    d['risk_pct_actual']=d.risk_usdt/d.equity_at_entry*100
    d['gross_pnl']=(d.exit-d.entry)*d.qty
    d['net_pnl']=d.gross_pnl-d.fee_cost-d.funding_cost
    d['net_R']=d.net_pnl/d.risk_usdt
    calculated=['risk_usdt','risk_pct_actual','gross_pnl','net_pnl','net_R']
    if (d.risk_usdt<=0).any() or not np.isfinite(d[calculated].to_numpy(dtype=float)).all():
        return {'status':'INVALID','n':len(d),'reason':'计算后的风险、盈亏或净 R 非有限值或风险下溢为零'}
    # Closed records alone give a lower bound: missing/open trades are not counted.
    max_daily_entries,max_concurrent,max_concurrent_upper,order_ambiguous=capacity_bounds(d)
    d=d.sort_values(['exit_time','trade_id'])
    gross_wins=d.gross_pnl.clip(lower=0).sum()
    fee_funding=(d.fee_cost+d.funding_cost).sum()
    fee_ratio=fee_funding/gross_wins*100 if gross_wins>0 else None
    # The execution prices already include slippage. Reference prices are
    # needed to attribute it; never deduct it twice from the recorded PnL.
    reference_complete=False
    cost_ratio=slippage_total=reference_wins=None
    for c in REFERENCES:
        if c not in d.columns: d[c]=''
    supplied=d[REFERENCES].fillna('').astype(str).apply(lambda c:~c.str.strip().str.upper().isin(MISSING_TOKENS))
    refs=d[['reference_entry','reference_exit']].apply(pd.to_numeric,errors='coerce')
    invalid_ref=(supplied[['reference_entry','reference_exit']] & (~np.isfinite(refs) | (refs<=0))).any().any()
    if invalid_ref: return {'status':'INVALID','n':len(d),'reason':'提供的参考价格必须为有限正数'}
    reference_complete=bool(supplied.all(axis=None))
    if reference_complete:
        d['reference_gross_pnl']=(refs.reference_exit-refs.reference_entry)*d.qty
        d['slippage_cost']=d.reference_gross_pnl-d.gross_pnl
        slippage_total=float(d.slippage_cost.sum())
        reference_wins=float(d.reference_gross_pnl.clip(lower=0).sum())
        if reference_wins>0: cost_ratio=(fee_funding+slippage_total)/reference_wins*100
    violations={
        'five_q_fail':int((d.five_q_pass!='1').sum()),
        'stop_not_placed':int((d.stop_placed!='1').sum()),
        'added':int((d.added=='1').sum()), 'reversed':int((d.reversed=='1').sum()),
        'plan_deviation':int((d.plan_deviation=='1').sum()),
        'risk_over_frozen':int((d.risk_pct_actual > CFG['sizing']['risk_pct_per_trade']*100+1e-9).sum()),
        'daily_entries_over_limit':int(max_daily_entries > CFG['sizing']['max_new_per_day']),
        'concurrent_over_limit':int(max_concurrent > CFG['sizing']['max_concurrent']),
        'paper_initial_leverage_over_cap':int((d.paper_initial_leverage>CFG['sizing']['leverage_cap']+1e-9).sum()),
    }
    net_wins=d.net_pnl.clip(lower=0).sum(); net_losses=-d.net_pnl.clip(upper=0).sum()
    totals=[d.gross_pnl.sum(),d.fee_cost.sum(),d.funding_cost.sum(),d.net_pnl.sum(),d.net_R.sum(),
            gross_wins,fee_funding,net_wins,net_losses]
    totals.extend(value for value in (fee_ratio,slippage_total,reference_wins,cost_ratio) if value is not None)
    if reference_complete:
        totals.extend(d[['reference_gross_pnl','slippage_cost']].to_numpy(dtype=float).ravel())
    if not np.isfinite(np.asarray(totals,dtype=float)).all() or (net_losses>0 and not np.isfinite(net_wins/net_losses)):
        return {'status':'INVALID','n':len(d),'reason':'计算后的成本、盈亏或汇总比例非有限值'}
    g=CFG['validation_gates']; n=len(d); days=(now-start).days
    stop=sum(violations.values())>0 or (n>=g['min_trades'] and d.net_R.mean()<g['stop_if_net_R_lt'])
    candidate_gate=(n>=g['min_trades'] and days>=g['min_days'] and d.net_R.mean()>0 and cost_ratio<=g['pass_cost_over_gross_pct_le']) if cost_ratio is not None else None
    if order_ambiguous: candidate_gate=None
    concurrent_assessment=('EXCEEDED' if violations['concurrent_over_limit'] else
                           'AMBIGUOUS_ORDER' if max_concurrent_upper>CFG['sizing']['max_concurrent'] else
                           'WITHIN_RECORDED_BOUNDS')
    return {'status':'STOP' if stop else 'HOLD', 'n':n,'days':days,'gross_pnl_usdt':round(float(d.gross_pnl.sum()),6),
            'fee_usdt':round(float(d.fee_cost.sum()),6),'funding_cost_usdt':round(float(d.funding_cost.sum()),6),
            'net_pnl_usdt':round(float(d.net_pnl.sum()),6),'avg_net_R':round(float(d.net_R.mean()),6),
            'total_net_R':round(float(d.net_R.sum()),6),'net_win_rate_pct':round(float((d.net_pnl>0).mean()*100),2),
            'net_profit_factor':round(float(net_wins/net_losses),4) if net_losses>0 else None,
            'fee_funding_over_execution_gross_profit_pct':round(float(fee_ratio),4) if fee_ratio is not None else None,
            'reference_status':'PROVIDED_UNVERIFIED' if reference_complete else 'UNKNOWN_INCOMPLETE',
            'slippage_cost_usdt':round(slippage_total,6) if slippage_total is not None else None,
            'total_estimated_cost_usdt':round(float(fee_funding+slippage_total),6) if slippage_total is not None else None,
            'reference_gross_profit_usdt':round(reference_wins,6) if reference_wins is not None else None,
            'cost_over_gross_profit_pct':round(float(cost_ratio),4) if cost_ratio is not None else None,
            'max_daily_entries_closed_only':max_daily_entries,'max_concurrent_closed_only':max_concurrent,
            'max_concurrent_upper_closed_only':max_concurrent_upper,'same_time_order_ambiguous':order_ambiguous,
            'concurrent_limit_assessment_closed_only':concurrent_assessment,
            'max_initial_price_risk_pct':round(float(d.risk_pct_actual.max()),6),'violations':violations,
            'paper_initial_leverage_status':margin_check['status'],
            'actual_exchange_leverage':'UNKNOWN',
            'numeric_gate_met_unverified':None,'candidate_threshold_met_unverified':candidate_gate,
            'reason':'总成本比例以参考价毛利为分母、含签名滑点与资金费，参考价来源未验证；历史门槛口径未明确，不能当作通过。仅计算已平仓记录；并发上下界不覆盖漏记或未平仓，同刻先后不明不得以较小值确认实际风险。初始价格风险不含费用或跳空，未平仓浮亏、记录真实性及完整性未验收。',
            'records':[{'trade_id':str(x.trade_id),'risk_usdt':round(float(x.risk_usdt),6),'risk_pct':round(float(x.risk_pct_actual),6),
                        'paper_initial_leverage':round(float(x.paper_initial_leverage),6) if pd.notna(x.paper_initial_leverage) else None,
                        'gross_pnl_usdt':round(float(x.gross_pnl),6),'net_pnl_usdt':round(float(x.net_pnl),6),'net_R':round(float(x.net_R),6),
                        'reference_gross_pnl_usdt':round(float(x.reference_gross_pnl),6) if reference_complete else None,
                        'slippage_cost_usdt':round(float(x.slippage_cost),6) if reference_complete else None,
                        'reference_source':str(x.reference_source) if reference_complete else None} for x in d.itertuples()]}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--file',default=str(Path(VERIFY)/'forward_paper_v1.csv'))
    ap.add_argument('--start',required=True,help='actual prospective start in UTC, never backdate')
    ap.add_argument('--as-of',help='UTC evaluation time; default current time')
    a=ap.parse_args()
    if a.as_of and pd.to_datetime(a.as_of,utc=True)>pd.Timestamp.now(tz='UTC'):
        raise SystemExit('检查时间不得晚于当前 UTC 时间')
    p=Path(a.file)
    result=report(load(p),a.start,a.as_of) if p.exists() else {'status':'UNKNOWN','reason':'纸面记录文件不存在；无法判断是否有未记录的交易。'}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
