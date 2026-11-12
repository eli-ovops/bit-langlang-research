"""Reconcile provided closed/open paper positions to local manual events."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from .forward_report import load, valid_trade_id
from .paper_reconcile import reconcile as reconcile_closed
from .paper_risk_audit import audit as risk_audit

CONFIG=Path(__file__).with_name('frozen_config.json')


def reconcile(closed,opened,events,start,as_of,max_lag_seconds=900):
    risk=risk_audit(closed,opened,start,as_of)
    if risk['status']=='INVALID': return {'status':'INVALID','reason':'已平仓或未平仓账本无效','risk_status':'INVALID'}
    now=pd.to_datetime(as_of,utc=True);begin=pd.to_datetime(start,utc=True)
    cfg=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    records={}
    for is_open,frame in ((False,closed),(True,opened)):
        for row in frame.itertuples():
            records[str(row.trade_id)]={'row':row,'open':is_open,'marks':[],'entries':[],'exits':[]}
    errors=[];closed_events=[];ambiguous_order=[]
    for e in events:
        if not isinstance(e,dict): errors.append('事件必须为对象');continue
        kind=e.get('kind')
        if kind in ('signal','skip'): continue
        if kind not in ('entry','exit','mark'): errors.append('事件类型无效');continue
        key=e.get('trade_id')
        if not valid_trade_id(key) or str(key) not in records: errors.append('持仓事件没有对应交易编号');continue
        key=str(key);rec=records[key];row=rec['row']
        try:
            if e.get('schema')!='paper-event-v1' or e.get('verification')!='MANUAL_UNVERIFIED' or e.get('config_sha256')!=cfg: raise ValueError('invalid metadata')
            when=pd.to_datetime(e['event_time_utc'],utc=True,errors='raise')
            observed=pd.to_datetime(e['captured_at_utc'],utc=True,errors='raise')
            lag=float(e['capture_lag_seconds']);price=float(e['price'])
            if pd.isna(when) or pd.isna(observed) or not math.isfinite(lag) or not math.isfinite(price) or price<=0: raise ValueError('invalid value')
            if observed>now or when<begin or lag<0 or lag>max_lag_seconds or abs((observed-when).total_seconds()-lag)>.001: raise ValueError('invalid capture time')
            if e.get('symbol')!=row.symbol: raise ValueError('wrong symbol')
            entry=pd.to_datetime(row.entry_time,utc=True)
            if kind=='entry':
                signal=pd.to_datetime(e['signal_time_utc'],utc=True,errors='raise')
                if pd.isna(signal) or signal.floor('5min')!=signal or when<signal+pd.Timedelta(minutes=5): raise ValueError('invalid signal timing')
                rec['entries'].append((when,price,observed))
            elif kind=='exit':
                if rec['open']: raise ValueError('open position has exit event')
                rec['exits'].append((when,price,observed))
            else:
                if when<entry or (not rec['open'] and when>pd.to_datetime(row.exit_time,utc=True)): raise ValueError('mark outside recorded holding')
                rec['marks'].append((when,price,observed))
            if not rec['open'] and kind in ('entry','exit'): closed_events.append(e)
        except (KeyError,TypeError,ValueError,OverflowError): errors.append(f'{key} {kind} 事件格式、价格或时间无效')
    for key,rec in records.items():
        row=rec['row'];entries=rec['entries'];exits=rec['exits'];marks=rec['marks']
        if len(entries)!=1 or entries[0][0]!=pd.to_datetime(row.entry_time,utc=True) or not math.isclose(entries[0][1],float(row.entry),rel_tol=1e-9,abs_tol=1e-9):
            errors.append(f'{key} 入场事件缺失、重复或与账本不匹配')
        if len({item[0] for item in marks})!=len(marks): errors.append(f'{key} 估值事件时间重复')
        chain=sorted(marks,key=lambda item:item[0])
        if len(entries)==1: chain=[entries[0]]+chain
        if len(exits)==1: chain=chain+[exits[0]]
        for before,after in zip(chain,chain[1:]):
            if before[2]>after[2]: errors.append(f'{key} 入场、估值或出场的采集顺序相反')
            elif before[0]==after[0] or before[2]==after[2]: ambiguous_order.append(key)
        if rec['open']:
            if not marks: errors.append(f'{key} 未平仓缺少估值事件')
            else:
                last=max(marks,key=lambda item:item[0])
                if last[0]!=pd.to_datetime(row.mark_time,utc=True) or not math.isclose(last[1],float(row.mark_price),rel_tol=1e-9,abs_tol=1e-9):
                    errors.append(f'{key} 最新估值事件与未平仓快照不匹配')
        elif len(exits)!=1 or exits[0][0]!=pd.to_datetime(row.exit_time,utc=True) or not math.isclose(exits[0][1],float(row.exit),rel_tol=1e-9,abs_tol=1e-9):
            errors.append(f'{key} 出场事件缺失、重复或与账本不匹配')
    closed_check=reconcile_closed(closed,closed_events,start,as_of) if not closed.empty else {'status':'NO_DATA'}
    if closed_check['status']=='INVALID': errors.append('已平仓账本与事件核对无效')
    status=('INVALID' if errors else 'STOP' if risk['status']=='STOP' else 'STALE' if risk['status']=='STALE'
            else 'UNKNOWN' if not records else 'AMBIGUOUS_ORDER' if ambiguous_order or risk['status']=='AMBIGUOUS_ORDER' else 'PARTIAL')
    return {'status':status,'risk_status':risk['status'],'closed_event_check_status':closed_check['status'],
            'closed_positions':len(closed),'open_positions':len(opened),'ambiguous_order_trade_ids':sorted(set(ambiguous_order)),'errors':errors,
            'reason':'仅核对提供的记录，未证明信号完整、持仓快照完整、时钟、行情、实际成交或资金费。未平仓估值后至检查时刻的状态仍须核实。'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--closed',required=True);parser.add_argument('--open',required=True,dest='open_file')
    parser.add_argument('--events',required=True);parser.add_argument('--start',required=True);parser.add_argument('--as-of',required=True)
    args=parser.parse_args();folder=Path(args.events)
    if not Path(args.closed).is_file() or not Path(args.open_file).is_file() or not folder.is_dir():
        print(json.dumps({'status':'UNKNOWN','reason':'账本或事件目录不存在'},ensure_ascii=False));return
    now=pd.to_datetime(args.as_of,utc=True,errors='coerce')
    if pd.isna(now) or now>pd.Timestamp.now(tz='UTC'):
        print(json.dumps({'status':'INVALID','reason':'检查时间无效或晚于现在'},ensure_ascii=False));return
    try:
        events=[json.loads(path.read_text(encoding='utf-8')) for path in sorted(folder.glob('*.json'))]
        result=reconcile(load(args.closed),load(args.open_file),events,args.start,args.as_of)
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        result={'status':'INVALID','reason':'事件或账本不可读取：'+str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
