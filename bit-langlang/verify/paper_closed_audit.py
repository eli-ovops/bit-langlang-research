"""Shared one-trade ledger, hypothetical costs and funding reconciliation."""
import math
import pandas as pd

from .forward_open import FIELDS as OPEN_FIELDS
from .forward_report import MISSING_TOKENS, report
from .funding_reconcile import reconcile as funding_reconcile


def audit(ledger, entry, exit_event, entry_bid, entry_ask, exit_bid, exit_ask,
          funding, start, as_of, schedule=None):
    """Assumes caller separately verified event and quote causality/depth."""
    try:
        if len(ledger)!=1:
            raise ValueError('账本必须仅包含一笔已平仓交易')
        row=ledger.iloc[0];qty=float(row['qty'])
        entry_price=float(entry['price']);exit_price=float(exit_event['price'])
        if not all(math.isfinite(float(x)) and float(x)>0 for x in
                   (qty,entry_price,exit_price,entry_bid,entry_ask,exit_bid,exit_ask)):
            raise ValueError('成交或报价价格与数量无效')
        if entry_bid>entry_ask or exit_bid>exit_ask:
            raise ValueError('买卖报价倒置')
        if not math.isclose(entry_price,entry_ask*1.0002,rel_tol=1e-9,abs_tol=1e-9) or not math.isclose(exit_price,exit_bid*.9998,rel_tol=1e-9,abs_tol=1e-9):
            raise ValueError('假设成交价不符合双边滑点口径')
        if (str(row['trade_id'])!=str(entry['trade_id']) or str(row['trade_id'])!=str(exit_event['trade_id'])
                or row['symbol']!='ETHUSDT' or entry.get('symbol')!='ETHUSDT' or exit_event.get('symbol')!='ETHUSDT'
                or pd.to_datetime(row['entry_time'],utc=True,errors='raise')!=pd.to_datetime(entry['event_time_utc'],utc=True,errors='raise')
                or pd.to_datetime(row['exit_time'],utc=True,errors='raise')!=pd.to_datetime(exit_event['event_time_utc'],utc=True,errors='raise')):
            raise ValueError('账本与事件编号、标的或时间不匹配')
        for field,value in (('entry',entry_price),('exit',exit_price),('stop',entry_price*.996),
                            ('reference_entry',entry_ask),('reference_exit',exit_bid),
                            ('fee_cost',qty*(entry_price+exit_price)*.0005)):
            if not math.isclose(float(row[field]),value,rel_tol=1e-9,abs_tol=1e-8):
                raise ValueError('账本字段不匹配: '+field)
        if str(row.get('reference_source','')).strip().upper() in MISSING_TOKENS:
            raise ValueError('账本缺少参考报价来源')
        result=report(ledger,start,as_of)
        if result['status'] in ('INVALID','STOP'):
            return {'status':result['status'],'report':result}
        if result['paper_initial_leverage_status']!='PROVIDED_UNVERIFIED':
            return {'status':'UNKNOWN_MARGIN','report':result,'reason':'缺少纸面初始保证金，不能验证名义倍数'}
        entry_mid=(entry_bid+entry_ask)/2;exit_mid=(exit_bid+exit_ask)/2
        spread=qty*((entry_ask-entry_mid)+(exit_mid-exit_bid))
        slippage=qty*((entry_price-entry_ask)+(exit_bid-exit_price))
        fees=float(row['fee_cost']);funding_cost=float(row['funding_cost'])
        mid_gross=qty*(exit_mid-entry_mid);mid_cost=spread+slippage+fees+funding_cost
        net=qty*(exit_price-entry_price)-fees-funding_cost
        if not math.isclose(mid_gross-mid_cost,net,rel_tol=1e-9,abs_tol=1e-8):
            raise ValueError('相对中间价的成本分解不平衡')
        costs={'basis':'两个公开一级报价 mid；点差与额外滑点均为假设，非实际成交',
               'sampled_spread_cost_usdt':round(spread,6),'assumed_slippage_usdt':round(slippage,6),
               'fee_usdt':round(fees,6),'funding_cost_usdt_unverified':round(funding_cost,6),
               'mid_reference_gross_pnl_usdt':round(mid_gross,6),'total_cost_vs_mid_usdt':round(mid_cost,6),
               'cost_over_positive_mid_gross_pct':round(mid_cost/mid_gross*100,4) if mid_gross>0 else None,
               'net_pnl_reconciled_usdt':round(net,6),
               'report_reference_basis':'原报告以入场 ask / 出场 bid 为参考，点差已体现在该参考毛盈亏内'}
        empty=pd.DataFrame(columns=OPEN_FIELDS)
        if 'trade_id' in funding and not funding.trade_id.astype(str).eq(str(entry['trade_id'])).all():
            raise ValueError('资金费明细包含其他交易编号；本检查仅支持单笔交易')
        funding_result=funding_reconcile(ledger,empty,funding,start,as_of,schedule=schedule,verify_flat_equity=False)
        if funding_result['status'] in ('INVALID','STOP'):
            return {'status':funding_result['status'],'report':result,'funding_check':funding_result}
        if schedule is None:
            return {'status':'UNKNOWN_FUNDING','report':result,'costs_vs_mid_unverified':costs,
                    'reason':'未提供资金费覆盖快照；不能将账本零值视为已验证'}
        if funding_result['status']!='PARTIAL':
            return {'status':'UNKNOWN_FUNDING' if funding_result['status']=='UNKNOWN' else funding_result['status'],
                    'report':result,'funding_check':funding_result}
        return {'status':'PARTIAL_NOT_REGISTERED','report':result,'funding_check':funding_result,'costs_vs_mid_unverified':costs,
                'entry_equity_context':'UNKNOWN_REQUIRES_FULL_LEDGER',
                'reason':'仅为单笔、非认证来源的条件性账本核对；无法证明连续监控、止损先后、真实费用或成交。'}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
        return {'status':'INVALID','reason':str(exc)}
