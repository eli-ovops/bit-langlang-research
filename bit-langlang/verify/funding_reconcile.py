"""Reconcile supplied funding evidence; no claim of completeness or settlement."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_report import MISSING_TOKENS, load, valid_trade_id
from .paper_risk_audit import audit as risk_audit

FIELDS=['trade_id','symbol','funding_time','funding_rate','reference_mark_price','qty','funding_cost','source']
NUMERIC=['funding_rate','reference_mark_price','qty','funding_cost']


def read_schedule(folder):
    """Check captured file consistency; does not authenticate exchange origin."""
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text())
    if manifest.get('schema')!='paper-funding-snapshot-v2' or manifest.get('source')!='Binance USD-M public fundingRate': raise ValueError('invalid snapshot schema or source')
    begin=pd.to_datetime(manifest['start_utc'],utc=True,errors='raise')
    end=pd.to_datetime(manifest['end_utc_exclusive'],utc=True,errors='raise')
    captured=pd.to_datetime(manifest['captured_at_utc'],utc=True,errors='raise')
    if (pd.isna(begin) or pd.isna(end) or pd.isna(captured) or begin>=end
            or end.value//1_000_000>int(manifest['query_server_time_ms'])
            or int(manifest['query_server_time_ms'])>int(manifest['server_time_ms'])): raise ValueError('invalid snapshot bounds or capture time')
    snapshots={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        info=manifest['symbols'][symbol]
        if info['file']!=symbol+'.json': raise ValueError('invalid snapshot filename')
        raw=(folder/info['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=info['sha256']: raise ValueError('snapshot hash mismatch')
        rows=json.loads(raw)
        if not isinstance(rows,list) or len(rows)!=info['count']: raise ValueError('invalid snapshot count')
        indexed={}
        for row in rows:
            stamp=pd.to_datetime(int(row['fundingTime']),unit='ms',utc=True)
            rate=float(row['fundingRate']);price=float(row['markPrice'])
            if (row['symbol']!=symbol or not begin<=stamp<end or stamp in indexed
                    or not np.isfinite(rate) or not np.isfinite(price) or price<=0): raise ValueError('invalid snapshot event')
            indexed[stamp]=(rate,price)
        if list(indexed)!=sorted(indexed): raise ValueError('snapshot events out of order')
        snapshots[symbol]=indexed
    return begin,end,snapshots,hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),int(manifest['server_time_ms']),captured


def reconcile(closed, opened, funding, start, as_of, boundary_seconds=60, schedule=None, *, verify_flat_equity=True):
    risk=risk_audit(closed,opened,start,as_of,verify_flat_equity=verify_flat_equity)
    if risk['status']=='INVALID': return {'status':'INVALID','reason':'持仓或交易账本无效','risk_status':risk['status']}
    if any(c not in funding for c in FIELDS): return {'status':'INVALID','reason':'资金费明细缺少必需字段','risk_status':risk['status']}
    if not np.isfinite(boundary_seconds) or boundary_seconds<0: return {'status':'INVALID','reason':'结算时间模糊区间无效'}
    records={}
    for is_open, frame in ((False,closed),(True,opened)):
        for row in frame.itertuples():
            records[str(row.trade_id)]={'symbol':row.symbol,'entry':pd.to_datetime(row.entry_time,utc=True),
                'exit':None if is_open else pd.to_datetime(row.exit_time,utc=True),
                'mark_time':pd.to_datetime(row.mark_time,utc=True) if is_open else None,
                'qty':float(row.qty),'funding_cost':float(row.funding_cost)}
    if not records: return {'status':'UNKNOWN','reason':'没有可核查的持仓记录；不能证明空仓','risk_status':risk['status']}
    f=funding.copy();f['funding_time']=pd.to_datetime(f.funding_time,utc=True,errors='coerce')
    for col in NUMERIC: f[col]=pd.to_numeric(f[col],errors='coerce')
    if f[FIELDS].isna().any().any() or not np.isfinite(f[NUMERIC].to_numpy(dtype=float)).all():
        return {'status':'INVALID','reason':'资金费时间、数值或来源缺失','risk_status':risk['status']}
    sources=f.source.astype(str).str.strip().str.upper()
    if (not f.trade_id.map(valid_trade_id).all() or sources.isin(MISSING_TOKENS).any()
        or (f[['reference_mark_price','qty']]<=0).any().any()
        or f.duplicated(['trade_id','funding_time']).any()):
        return {'status':'INVALID','reason':'资金费编号、来源、价格、数量或时间重复无效','risk_status':risk['status']}
    errors=[];ambiguous=[];counts={k:0 for k in records};sums={k:0.0 for k in records}
    now=pd.to_datetime(as_of,utc=True);window=pd.Timedelta(seconds=boundary_seconds)
    coverage={k:False for k in records};schedule_hash=None;market_events={}
    if schedule is not None:
        try:
            begin,end,market_events,schedule_hash,server_time_ms,captured=read_schedule(schedule)
            if server_time_ms*1_000_000>now.value or captured>now: raise ValueError('snapshot was captured after evaluation time')
            for key,trade in records.items():
                last=(trade['mark_time'] if trade['exit'] is None else trade['exit'])+window
                # end is exclusive; an event exactly at the far boundary
                # remains relevant to the inclusive ambiguity window.
                coverage[key]=begin<=trade['entry']-window and end>last
        except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
            return {'status':'INVALID','reason':'资金费快照无效：'+str(exc),'risk_status':risk['status']}
    for row in f.itertuples():
        key=str(row.trade_id);trade=records.get(key)
        if trade is None or row.symbol!=trade['symbol']:
            errors.append(f'{key} 明细没有对应标的或交易');continue
        if (row.funding_time>now or row.funding_time<trade['entry']-window
                or (trade['exit'] is None and row.funding_time>trade['mark_time'])
                or (trade['exit'] is not None and row.funding_time>trade['exit']+window)):
            errors.append(f'{key} 资金费时间与持仓不匹配');continue
        if not np.isclose(row.qty,trade['qty'],rtol=0,atol=1e-9): errors.append(f'{key} 数量与账本不匹配')
        if schedule is not None and coverage[key]:
            market=market_events[trade['symbol']].get(row.funding_time)
            if market is None or not np.isclose(row.funding_rate,market[0],rtol=0,atol=1e-12) or not np.isclose(row.reference_mark_price,market[1],rtol=0,atol=1e-8):
                errors.append(f'{key} 资金费明细与公开快照不一致')
        expected=float(row.qty*row.reference_mark_price*row.funding_rate)
        if not np.isclose(row.funding_cost,expected,rtol=1e-9,atol=1e-8): errors.append(f'{key} 资金费金额与参考价格、费率和数量不匹配')
        if abs(row.funding_time-trade['entry'])<=window or (trade['exit'] is not None and abs(row.funding_time-trade['exit'])<=window):
            ambiguous.append({'trade_id':key,'funding_time_utc':row.funding_time.isoformat()})
        counts[key]+=1;sums[key]+=float(row.funding_cost)
    no_evidence=[]
    for key,trade in records.items():
        if schedule is not None and coverage[key]:
            recorded=set(f.loc[f.trade_id.astype(str)==key,'funding_time'])
            last=trade['mark_time'] if trade['exit'] is None else trade['exit']
            for stamp in market_events[trade['symbol']]:
                near=(abs(stamp-trade['entry'])<=window or (trade['exit'] is not None and abs(stamp-trade['exit'])<=window)
                      or (trade['exit'] is None and abs(stamp-trade['mark_time'])<=window))
                if near and stamp<=now:
                    item={'trade_id':key,'funding_time_utc':stamp.isoformat()}
                    if item not in ambiguous: ambiguous.append(item)
                elif trade['entry']+window<stamp<last-window and stamp not in recorded:
                    errors.append(f'{key} 缺少快照中的资金费事件 {stamp.isoformat()}')
        if not counts[key]:
            if not coverage[key]: no_evidence.append(key)
            if not np.isclose(trade['funding_cost'],0,rtol=0,atol=1e-8): errors.append(f'{key} 账本有资金费但无明细')
        elif not np.isclose(sums[key],trade['funding_cost'],rtol=1e-9,atol=1e-8):
            errors.append(f'{key} 资金费明细合计与账本不一致')
    uncovered=[key for key in records if schedule is not None and not coverage[key]]
    status=('INVALID' if errors else 'STOP' if risk['status']=='STOP' else 'UNKNOWN' if no_evidence or uncovered
            else 'AMBIGUOUS' if ambiguous else 'STALE' if risk['status']=='STALE'
            else 'AMBIGUOUS_ORDER' if risk['status']=='AMBIGUOUS_ORDER' else 'PARTIAL')
    return {'status':status,'risk_status':risk['status'],
            'risk_equity_context':'ASSUMED_COMPLETE_LEDGER' if verify_flat_equity else 'UNKNOWN_INCOMPLETE_LEDGER',
            'trade_count':len(records),'event_count':len(f),
            'funding_cost_usdt_by_trade':sums,'trade_ids_without_funding_evidence':no_evidence,
            'open_funding_as_of_utc':{key:trade['mark_time'].isoformat() for key,trade in records.items() if trade['mark_time'] is not None},
            'open_after_snapshot_unknown':[key for key,trade in records.items() if trade['mark_time'] is not None and trade['mark_time']<now],
            'schedule_manifest_sha256':schedule_hash,'schedule_uncovered_trade_ids':uncovered,
            'boundary_window_seconds':boundary_seconds,'ambiguous_events':ambiguous,'errors':errors,
            'reason':'仅核对给出的费用明细；未平仓费用核对截止持仓快照时刻，之后至检查时刻 UNKNOWN。不证明结算完整、实际持仓、来源真实性或真实费用。边界区间是研究假设，非交易所统一规则。'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--closed',required=True);p.add_argument('--open',required=True,dest='open_file')
    p.add_argument('--funding',required=True);p.add_argument('--start',required=True);p.add_argument('--as-of',required=True)
    p.add_argument('--schedule',help='可选的公共资金费快照目录，仅作形式覆盖检查')
    args=p.parse_args()
    if not all(Path(x).is_file() for x in (args.closed,args.open_file,args.funding)):
        print(json.dumps({'status':'UNKNOWN','reason':'所需文件不存在，不能当作空记录'},ensure_ascii=False));return
    now=pd.to_datetime(args.as_of,utc=True,errors='coerce')
    if pd.isna(now) or now>pd.Timestamp.now(tz='UTC'):
        print(json.dumps({'status':'INVALID','reason':'检查时间无效或晚于现在'},ensure_ascii=False));return
    print(json.dumps(reconcile(load(args.closed),load(args.open_file),load(args.funding),args.start,args.as_of,schedule=args.schedule),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
