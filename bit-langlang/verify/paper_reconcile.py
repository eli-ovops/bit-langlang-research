"""Compare manual paper-entry/exit records against the closed-trade CSV.

This only checks schema, timestamps and matching identifiers. It cannot prove
clock, source, signal completeness, fills or missing trades are authentic.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import pandas as pd
from .forward_report import CFG, load, report


def reconcile(trades, events, start, now, max_lag_seconds=900):
    baseline=report(trades,start,now)
    if baseline['status'] in {'INVALID','NO_DATA'}: return {'status':'INVALID','report_status':baseline['status'],'reason':baseline['reason']}
    expected_hash=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
    index={};errors=[]
    for e in events:
        if not isinstance(e,dict): errors.append('事件必须是对象');continue
        if e.get('schema')!='paper-event-v1' or e.get('verification')!='MANUAL_UNVERIFIED' or e.get('config_sha256')!=expected_hash:
            errors.append('事件格式、状态或冻结参数哈希不匹配');continue
        try:
            observed=pd.to_datetime(e['captured_at_utc'],utc=True,errors='raise')
            occurred=pd.to_datetime(e['event_time_utc'],utc=True,errors='raise')
            if pd.isna(observed) or pd.isna(occurred): raise ValueError('missing time')
            lag=(observed-occurred).total_seconds()
            stated=float(e['capture_lag_seconds'])
            if observed>pd.to_datetime(now,utc=True) or not math.isfinite(stated) or lag<0 or lag>max_lag_seconds or abs(lag-stated)>0.001:
                errors.append('事件采集时间超前、滞后或延迟值不一致');continue
            if e.get('kind')=='entry':
                signal=pd.to_datetime(e['signal_time_utc'],utc=True,errors='raise')
                if pd.isna(signal) or signal.floor('5min')!=signal or occurred<signal+pd.Timedelta(minutes=5):
                    errors.append('入场与信号K线时间不一致');continue
        except (KeyError,TypeError,ValueError):
            errors.append('事件时间无效');continue
        if e.get('kind') in ('entry','exit'):
            key=(str(e.get('trade_id')),e['kind'])
            if key in index: errors.append('同一交易重复入场或出场事件')
            index[key]=e
    for t in trades.itertuples():
        for kind,when in [('entry',t.entry_time),('exit',t.exit_time)]:
            e=index.get((str(t.trade_id),kind))
            if e is None or e.get('symbol')!=t.symbol or pd.to_datetime(e['event_time_utc'],utc=True)!=pd.to_datetime(when,utc=True):
                errors.append(f'交易 {t.trade_id} 的 {kind} 事件缺失或不匹配')
            else:
                try:
                    price=float(e['price'])
                    if not math.isfinite(price) or not math.isclose(price,float(getattr(t,kind)),rel_tol=1e-9,abs_tol=1e-9): raise ValueError('price mismatch')
                except (KeyError,TypeError,ValueError): errors.append(f'交易 {t.trade_id} 的 {kind} 价格不匹配')
    expected={(str(t.trade_id),k) for t in trades.itertuples() for k in ('entry','exit')}
    if set(index)-expected: errors.append('存在没有对应已平仓交易的入场/出场事件（可能为未平仓，需另核）')
    return {'status':'INVALID' if errors else 'PARTIAL','closed_trade_count':len(trades),'event_count':len(events),
            'report_status':baseline['status'],'errors':errors,'reason':'仅验证本地记录的形式一致性；信号覆盖、时钟可信、价格与资金费真实性以及未平仓账户完整性均未验证，不能自动 PASS。'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--trades',required=True);p.add_argument('--events',required=True)
    p.add_argument('--start',required=True);a=p.parse_args()
    folder=Path(a.events)
    if not folder.is_dir(): raise SystemExit('事件目录不存在')
    events=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(folder.glob('*.json'))]
    print(json.dumps(reconcile(load(a.trades),events,a.start,pd.Timestamp.now(tz='UTC')),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
