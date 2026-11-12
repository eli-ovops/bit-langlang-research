"""Create a local, timestamped observation record; never submits orders.

The timestamp is the local system clock. A hash proves later byte changes,
not truth, completeness, independent timing, or absence of earlier edits.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4
from .forward_report import valid_trade_id

CONFIG=Path(__file__).with_name('frozen_config.json')
KINDS={'signal','skip','entry','exit','mark'}


def capture(directory, kind, symbol, event_time, description, trade_id=None, signal_time=None, price=None):
    if kind not in KINDS or symbol != 'ETHUSDT' or not description.strip():
        raise ValueError('事件类型、标的或描述无效；当前冻结条件仅 ETH 可入场')
    if kind in {'entry','exit','mark'} and not valid_trade_id(trade_id):
        raise ValueError('入场、出场和持仓观察必须提供交易编号')
    if kind in {'entry','exit','mark'} and (price is None or not math.isfinite(price) or price<=0):
        raise ValueError('入场、出场和持仓观察必须提供有限的正价格')
    event=datetime.fromisoformat(event_time.replace('Z','+00:00'))
    if event.tzinfo is None: raise ValueError('事件时间必须带 UTC 偏移')
    event=event.astimezone(timezone.utc); now=datetime.now(timezone.utc)
    frozen=datetime.fromisoformat(json.loads(CONFIG.read_text())['frozen_at']).replace(tzinfo=timezone.utc)
    if event<frozen: raise ValueError('事件时间早于策略冻结日期')
    if event>now: raise ValueError('事件时间晚于采集时间')
    signal=None
    if kind in {'signal','skip','entry'}:
        if not signal_time: raise ValueError('信号、跳过和入场必须提供信号 K 线开盘时间')
        signal=datetime.fromisoformat(signal_time.replace('Z','+00:00'))
        if signal.tzinfo is None: raise ValueError('信号时间必须带 UTC 偏移')
        signal=signal.astimezone(timezone.utc)
        if signal<frozen or signal.second or signal.microsecond or signal.minute%5 or (event-signal).total_seconds()<300:
            raise ValueError('信号 K 线未收盘或不对齐 5 分钟')
    folder=Path(directory); folder.mkdir(parents=True,exist_ok=True)
    payload={'schema':'paper-event-v1','kind':kind,'symbol':symbol,'event_time_utc':event.isoformat(),
             'captured_at_utc':now.isoformat(),'capture_lag_seconds':(now-event).total_seconds(),
             'trade_id':trade_id,
             'price':price,
             'signal_time_utc':signal.isoformat() if signal else None,
             'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
             'description':description,'verification':'MANUAL_UNVERIFIED'}
    encoded=(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    path=folder/f'{now.strftime("%Y%m%dT%H%M%S%fZ")}-{uuid4().hex}.json'
    with open(path,'xb') as f:
        f.write(encoded); f.flush(); os.fsync(f.fileno())
    return {'path':str(path),'sha256':hashlib.sha256(encoded).hexdigest(),'captured_at_utc':payload['captured_at_utc'],
            'capture_lag_seconds':payload['capture_lag_seconds'],'verification':payload['verification']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--kind',choices=sorted(KINDS),required=True)
    p.add_argument('--symbol',required=True);p.add_argument('--event-time',required=True);p.add_argument('--description',required=True)
    p.add_argument('--trade-id',help='entry/exit/mark must match the paper CSV trade_id')
    p.add_argument('--signal-time',help='signal/skip/entry require signal candle open time with UTC offset')
    p.add_argument('--price',type=float,help='required for entry/exit/mark; manually supplied USDT price')
    a=p.parse_args();print(json.dumps(capture(a.directory,a.kind,a.symbol,a.event_time,a.description,a.trade_id,a.signal_time,a.price),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
