"""Conditional paper-equity arithmetic, never a verified account balance."""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

from .forward_report import CFG, load
from .paper_risk_audit import audit as risk_audit


def evaluate(closed,opened,start,as_of):
    risk=risk_audit(closed,opened,start,as_of)
    if risk['status']=='INVALID': return {'status':'INVALID','risk_status':'INVALID','reason':'持仓或交易账本无效'}
    if closed.empty and opened.empty:
        return {'status':'UNKNOWN','risk_status':risk['status'],'reason':'空记录不能证明账户空仓或余额'}
    now=pd.to_datetime(as_of,utc=True)
    closed_times=pd.to_datetime(closed.exit_time,utc=True)
    closed_entries=pd.to_datetime(closed.entry_time,utc=True)
    if not opened.empty:
        marks=pd.to_datetime(opened.mark_time,utc=True)
        if marks.nunique()!=1:
            return {'status':'STOP' if risk['status']=='STOP' else 'UNKNOWN','risk_status':risk['status'],
                    'reason':'未平仓估值时刻不一致，不能作为同步组合权益'}
        valuation=marks.iloc[0]
        if ((closed_entries<=valuation)&(closed_times>=valuation)).any():
            return {'status':'STOP' if risk['status']=='STOP' else 'UNKNOWN','risk_status':risk['status'],
                    'reason':'存在估值时仍持有或恰在该时刻平仓的历史仓位，缺少其同步估值或先后顺序'}
        realized=closed.loc[closed_times<valuation].copy()
    else:
        valuation=closed_times.max();realized=closed.copy()
    def num(frame,name):return pd.to_numeric(frame[name],errors='raise')
    closed_net=float(((num(realized,'exit')-num(realized,'entry'))*num(realized,'qty')
                      -num(realized,'fee_cost')-num(realized,'funding_cost')).sum())
    open_gross=float(((num(opened,'mark_price')-num(opened,'entry'))*num(opened,'qty')).sum())
    open_fee=float(num(opened,'entry_fee').sum());open_funding=float(num(opened,'funding_cost').sum())
    opening=float(CFG['sizing']['account_usdt'])
    equity=opening+closed_net+open_gross-open_fee-open_funding
    if not all(math.isfinite(x) for x in (closed_net,open_gross,open_fee,open_funding,equity)):
        return {'status':'INVALID','risk_status':risk['status'],'reason':'组合金额计算结果非有限值'}
    status=('STOP' if risk['status']=='STOP' or equity<=0 else 'STALE' if risk['status']=='STALE'
            else 'AMBIGUOUS_ORDER' if risk['status']=='AMBIGUOUS_ORDER' else 'REVIEW')
    return {'status':status,'risk_status':risk['status'],'valuation_time_utc':valuation.isoformat(),
            'initial_equity_assumed_usdt':opening,'closed_net_pnl_usdt':round(closed_net,6),
            'open_unrealized_gross_usdt':round(open_gross,6),'open_entry_fee_usdt':round(open_fee,6),
            'open_funding_cost_usdt':round(open_funding,6),'modeled_equity_usdt':round(equity,6),
            'closed_trades_after_valuation_excluded':int((closed_entries>valuation).sum()),
            'valuation_before_as_of':bool(valuation<now),'cash_balance':'UNKNOWN','liquidation':'UNKNOWN',
            'reason':'假设初始 2000U、账本完整、无出入金、无遗漏费用或其他资产且未发生额外强平损失；这些均未证实。入场时权益未独立对账，价格、资金费与持仓仅为所给快照，不能证明账户偿付能力、实际权益或当前状态。'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--closed',required=True);p.add_argument('--open',required=True,dest='open_file')
    p.add_argument('--start',required=True);p.add_argument('--as-of',required=True);args=p.parse_args()
    if not Path(args.closed).is_file() or not Path(args.open_file).is_file():
        print(json.dumps({'status':'UNKNOWN','reason':'账本或持仓文件不存在'},ensure_ascii=False));return
    now=pd.to_datetime(args.as_of,utc=True,errors='coerce')
    if pd.isna(now) or now>pd.Timestamp.now(tz='UTC'):
        print(json.dumps({'status':'INVALID','reason':'检查时间无效或晚于现在'},ensure_ascii=False));return
    print(json.dumps(evaluate(load(args.closed),load(args.open_file),args.start,args.as_of),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
