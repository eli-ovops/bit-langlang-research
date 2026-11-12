"""Review an open-position snapshot; price source and actual liquidation remain UNKNOWN."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .forward_report import CFG, MISSING_TOKENS, valid_trade_id, paper_margin_check

FIELDS=['trade_id','entry_time','symbol','side','entry','stop','qty','equity_at_entry',
        'mark_price','mark_time','mark_source','entry_fee','funding_cost']
NUMBERS=['entry','stop','qty','equity_at_entry','mark_price','entry_fee','funding_cost']


def evaluate(data, as_of=None, max_age_minutes=15):
    missing=[k for k in FIELDS if k not in data.columns]
    if missing: return {'status':'INVALID','reason':'缺少字段: '+', '.join(missing)}
    now=pd.to_datetime(as_of,utc=True,errors='coerce') if as_of else pd.Timestamp.now(tz='UTC')
    if pd.isna(now): return {'status':'INVALID','reason':'检查时间无效'}
    d=data.copy()
    if d.empty: return {'status':'NO_DATA','reason':'快照没有持仓；不能据此证明账户实际空仓'}
    for k in ['entry_time','mark_time']: d[k]=pd.to_datetime(d[k],utc=True,errors='coerce')
    for k in NUMBERS: d[k]=pd.to_numeric(d[k],errors='coerce')
    if d[FIELDS].isna().any().any() or not np.isfinite(d[NUMBERS].to_numpy()).all():
        return {'status':'INVALID','reason':'必要字段缺失或无效'}
    invalid=(not d.trade_id.map(valid_trade_id).all() or d.trade_id.astype(str).duplicated().any()
             or d.mark_source.astype(str).str.strip().str.upper().isin(MISSING_TOKENS).any()
             or (~d.symbol.isin(CFG['universe'])).any() or (d.symbol=='BTCUSDT').any()
             or (~d.side.str.lower().isin(['long','多'])).any()
             or (d[['entry','stop','qty','equity_at_entry','mark_price']]<=0).any().any()
             or (d.entry_fee<0).any() or (d.stop>=d.entry).any()
             or (((d.entry-d.stop)/d.entry-CFG['stop_pct']).abs()>.0001).any()
             or (d.entry_time>d.mark_time).any() or (d.mark_time>now).any())
    if invalid: return {'status':'INVALID','reason':'持仓字段、时间、方向或冻结止损条件无效'}
    margin_check=paper_margin_check(d)
    if margin_check['status']=='INVALID': return {'status':'INVALID','reason':'纸面初始保证金无效或名义倍数非有限值'}
    d['initial_risk']=(d.entry-d.stop)*d.qty
    d['risk_pct']=d.initial_risk/d.equity_at_entry*100
    if ((d.initial_risk<=0).any() or
            not np.isfinite(d[['initial_risk','risk_pct']].to_numpy(dtype=float)).all() or
            not np.isfinite(d.initial_risk.sum())):
        return {'status':'INVALID','reason':'计算后的初始风险或风险比例非有限值，或风险下溢为零'}
    over_concurrent=len(d)>CFG['sizing']['max_concurrent']
    over_risk=bool((d.risk_pct>CFG['sizing']['risk_pct_per_trade']*100+1e-9).any())
    age=(now-d.mark_time).dt.total_seconds()/60
    fresh_stop_hit=bool(((age<=max_age_minutes)&(d.mark_price<=d.stop)).any())
    if (age>max_age_minutes).any():
        return {'status':'ALERT' if over_concurrent or over_risk or fresh_stop_hit or margin_check['over_limit'] else 'STALE',
                'reason':'至少一笔价格过期；过期持仓浮亏和是否触损 UNKNOWN，新鲜记录触损及初始风险超限仍告警。',
                'oldest_age_minutes':float(age.max()),
                'violations':{'over_max_concurrent':over_concurrent,'over_price_risk':over_risk,
                              'paper_initial_leverage_over_cap':margin_check['over_limit'],
                              'mark_at_or_below_stop':True if fresh_stop_hit else 'UNKNOWN'},
                'paper_initial_leverage_status':margin_check['status'],'actual_exchange_leverage':'UNKNOWN',
                'liquidation':'UNKNOWN','portfolio_equity':'UNKNOWN'}
    d['unrealized']=d.qty*(d.mark_price-d.entry)
    d['net_to_date']=d.unrealized-d.entry_fee-d.funding_cost
    if (not np.isfinite(d[['unrealized','net_to_date']].to_numpy(dtype=float)).all() or
            not np.isfinite([d.unrealized.sum(),d.net_to_date.sum()]).all()):
        return {'status':'INVALID','reason':'计算后的浮动盈亏或汇总非有限值'}
    violations={'over_max_concurrent':over_concurrent,
                'over_price_risk':over_risk,
                'paper_initial_leverage_over_cap':margin_check['over_limit'],
                'mark_at_or_below_stop':bool((d.mark_price<=d.stop).any())}
    return {'status':'ALERT' if any(violations.values()) else 'REVIEW','count':len(d),
            'unrealized_gross_usdt':round(float(d.unrealized.sum()),6),
            'unrealized_after_recorded_costs_usdt':round(float(d.net_to_date.sum()),6),
            'valuation_time_first_utc':d.mark_time.min().isoformat(),
            'valuation_time_last_utc':d.mark_time.max().isoformat(),
            'valuation_timestamps_identical':bool(d.mark_time.nunique()==1),
            'initial_price_risk_usdt':round(float(d.initial_risk.sum()),6),
            'paper_initial_leverage_status':margin_check['status'],'actual_exchange_leverage':'UNKNOWN',
            'paper_initial_leverage_by_trade':{str(i):round(float(v),6) if pd.notna(v) else None
                                               for i,v in zip(d.trade_id,margin_check['ratios'])},
            'violations':violations,'liquidation':'UNKNOWN','portfolio_equity':'UNKNOWN',
            'reason':'浮盈亏为各笔所给时刻估值之和；时间不同时不是同步组合估值。未包含未来出场费、跳空、真实强平或账号完整性。'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--file',required=True);a=ap.parse_args()
    print(json.dumps(evaluate(pd.read_csv(Path(a.file),dtype=str,keep_default_na=False)),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
