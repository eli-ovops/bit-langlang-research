"""Public quote research evidence, not an order or registered paper strategy."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests
from .forward_report import valid_trade_id

BASE='https://fapi.binance.com'
CONFIG=Path(__file__).with_name('frozen_config.json')
MAX_CLOCK_SKEW_MS=2000
MAX_QUOTE_AGE_MS=2000


def fetch_quote(session):
    """One bounded public snapshot; local and venue clocks remain untrusted."""
    responses=[]
    for path,params in (('/fapi/v1/time',{}),('/fapi/v1/ticker/bookTicker',{'symbol':'ETHUSDT'}),('/fapi/v1/time',{})):
        start=time.time_ns()//1_000_000
        response=session.get(BASE+path,params=params,timeout=15)
        end=time.time_ns()//1_000_000
        response.raise_for_status()
        responses.append({'local_start_ms':start,'local_end_ms':end,'body':response.json()})
    return {'schema':'paper-quote-research-v1','source':'Binance USD-M public REST',
            'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
            'requests':responses,'verification':'PUBLIC_UNVERIFIED'}


def _millis(value):
    text=str(value)
    if not text or not text.isascii() or not text.isdecimal():raise ValueError('报价时间戳不是非负整数')
    return int(text)


def quote_facts(quote):
    """Validate quote and request clocks without inventing a decision event."""
    if quote['schema']!='paper-quote-research-v1' or quote['verification']!='PUBLIC_UNVERIFIED' or quote['source']!='Binance USD-M public REST':
        raise ValueError('报价记录格式或来源无效')
    cfg=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    if quote['config_sha256']!=cfg: raise ValueError('报价配置哈希不匹配')
    req=quote['requests']
    if len(req)!=3: raise ValueError('报价请求数无效')
    times=[_millis(x[k]) for x in req for k in ('local_start_ms','local_end_ms')]
    if any(a>b for a,b in zip(times,times[1:])): raise ValueError('本机请求顺序倒置')
    completed=pd.to_datetime(times[-1],unit='ms',utc=True)
    first=_millis(req[0]['body']['serverTime']);last=_millis(req[2]['body']['serverTime'])
    book=req[1]['body'];quote_time=_millis(book['time'])
    if first>last or not first<quote_time<=last or last-quote_time>MAX_QUOTE_AGE_MS:
        raise ValueError('报价 time 字段不满足预定时序或 2 秒门槛')
    for r,server_time in ((req[0],first),(req[2],last)):
        if not _millis(r['local_start_ms'])-MAX_CLOCK_SKEW_MS<=server_time<=_millis(r['local_end_ms'])+MAX_CLOCK_SKEW_MS:
            raise ValueError('本机与服务器时间偏差过大')
    bid=float(book['bidPrice']);ask=float(book['askPrice']);bid_qty=float(book['bidQty']);ask_qty=float(book['askQty'])
    if book['symbol']!='ETHUSDT' or not all(math.isfinite(x) and x>0 for x in (bid,ask,bid_qty,ask_qty)) or bid>ask:
        raise ValueError('报价或数量无效')
    return {'bid':bid,'ask':ask,'bid_qty':bid_qty,'ask_qty':ask_qty,'age_ms':last-quote_time,
            'local_start':pd.to_datetime(times[0],unit='ms',utc=True),'local_completed':completed,
            'server_quote_ms':quote_time}


def checked_book(quote,after,before):
    facts=quote_facts(quote)
    if not after<facts['local_start'] or not facts['local_completed']<before:
        raise ValueError('前序记录、报价采集和决定的先后顺序无法确认')
    if before-facts['local_completed']>pd.Timedelta(milliseconds=MAX_QUOTE_AGE_MS):
        raise ValueError('报价完成至决定的间隔超过研究时效')
    return facts['bid'],facts['ask'],facts['bid_qty'],facts['ask_qty'],facts['age_ms']


def assess(quote,signal,entry,qty,as_of):
    """Validate captured timing and hypothetical price; no claim of a fill."""
    try:
        cfg=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        for event,kind in ((signal,'signal'),(entry,'entry')):
            if event['schema']!='paper-event-v1' or event['verification']!='MANUAL_UNVERIFIED' or event['config_sha256']!=cfg or event['kind']!=kind or event['symbol']!='ETHUSDT':
                raise ValueError('事件类型、来源或配置无效')
        if not valid_trade_id(entry.get('trade_id')): raise ValueError('入场交易编号无效')
        if pd.to_datetime(signal['signal_time_utc'],utc=True)!=pd.to_datetime(entry['signal_time_utc'],utc=True):
            raise ValueError('信号编号不一致')
        signal_time=pd.to_datetime(signal['signal_time_utc'],utc=True,errors='raise')
        signal_event=pd.to_datetime(signal['event_time_utc'],utc=True,errors='raise')
        observed=pd.to_datetime(signal['captured_at_utc'],utc=True,errors='raise')
        decision=pd.to_datetime(entry['event_time_utc'],utc=True,errors='raise')
        entry_captured=pd.to_datetime(entry['captured_at_utc'],utc=True,errors='raise')
        now=pd.to_datetime(as_of,utc=True,errors='raise')
        if any(pd.isna(x) for x in (signal_time,signal_event,observed,decision,entry_captured,now)):
            raise ValueError('事件时间缺失')
        if signal_time.floor('5min')!=signal_time or signal_event<signal_time+pd.Timedelta(minutes=5) or signal_event>observed or decision>entry_captured or entry_captured>now:
            raise ValueError('事件时间不合规')
        for event,event_time,captured in ((signal,signal_event,observed),(entry,decision,entry_captured)):
            lag=float(event['capture_lag_seconds'])
            if not math.isfinite(lag) or lag<0 or lag>900 or abs(lag-(captured-event_time).total_seconds())>.001 or captured-signal_time-pd.Timedelta(minutes=5)>pd.Timedelta(minutes=15):
                raise ValueError('采集延迟不合规')
        bid,ask,bid_qty,ask_qty,age=checked_book(quote,observed,decision);qty=float(qty)
        price=float(entry['price'])
        if not all(math.isfinite(x) and x>0 for x in (qty,price)): raise ValueError('数量或价格无效')
        expected=ask*1.0002
        if not math.isclose(price,expected,rel_tol=1e-9,abs_tol=1e-9): raise ValueError('入场价与假设 ask 加 2bp 不一致')
        return {'status':'UNKNOWN_DEPTH' if qty>ask_qty else 'PARTIAL_NOT_REGISTERED',
                'ask':ask,'bid':bid,'ask_qty':ask_qty,'requested_qty':qty,'assumed_entry':expected,
                'assumed_entry_fee_usdt':round(qty*expected*.0005,6),
                'spread_bps':round((ask-bid)/((ask+bid)/2)*10000,6),'quote_age_ms':age,
                'quote_age_ms_semantics':'后一次 serverTime 减接口 time 字段；不是已证明的实际报价年龄',
                'reason':'仅为手工事件和公开一级报价的形式检查；不是实际成交、账本完整性或已注册前瞻的证明。'}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
        return {'status':'INVALID','reason':str(exc)}


def assess_round_trip(signal,entry,entry_quote,mark,trigger_quote,exit_event,exit_quote,qty,funding_cost,as_of):
    """Conditional bid-triggered paper stop; does not prove a real fill."""
    entry_check=assess(entry_quote,signal,entry,qty,as_of)
    if entry_check['status']!='PARTIAL_NOT_REGISTERED': return entry_check
    try:
        now=pd.to_datetime(as_of,utc=True,errors='raise');cfg=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        trade_id=str(entry['trade_id']);times=[]
        for event,kind in ((mark,'mark'),(exit_event,'exit')):
            if event['schema']!='paper-event-v1' or event['verification']!='MANUAL_UNVERIFIED' or event['config_sha256']!=cfg or event['kind']!=kind or event['symbol']!='ETHUSDT' or str(event['trade_id'])!=trade_id:
                raise ValueError('出场事件类型、配置或交易编号不一致')
            happened=pd.to_datetime(event['event_time_utc'],utc=True,errors='raise')
            captured=pd.to_datetime(event['captured_at_utc'],utc=True,errors='raise')
            lag=float(event['capture_lag_seconds'])
            if pd.isna(happened) or pd.isna(captured) or captured<happened or captured>now or not math.isfinite(lag) or lag<0 or lag>900 or abs(lag-(captured-happened).total_seconds())>.001:
                raise ValueError('出场事件采集时间无效')
            times.append((happened,captured))
        entry_captured=pd.to_datetime(entry['captured_at_utc'],utc=True)
        trigger_bid,_,_,_,_=checked_book(trigger_quote,entry_captured,times[0][0])
        exit_bid,exit_ask,exit_bid_qty,_,_=checked_book(exit_quote,times[0][1],times[1][0])
        entry_price=float(entry['price']);stop=entry_price*.996;mark_price=float(mark['price']);exit_price=float(exit_event['price'])
        qty=float(qty);funding=float(funding_cost)
        if not all(math.isfinite(x) for x in (mark_price,exit_price,qty,funding)) or qty<=0:
            raise ValueError('止损观察、出场价或资金费无效')
        if not math.isclose(mark_price,trigger_bid,rel_tol=1e-9,abs_tol=1e-9) or trigger_bid>stop:
            raise ValueError('bid 观察与触发报价不符或未达到模拟止损')
        if not math.isclose(exit_price,exit_bid*.9998,rel_tol=1e-9,abs_tol=1e-9):
            raise ValueError('出场价与假设 bid 减 2bp 不一致')
        if qty>exit_bid_qty:
            return {'status':'UNKNOWN_DEPTH','reason':'出场数量超过可见一级 bid 数量；不推断成交价'}
        entry_fee=qty*entry_price*.0005;exit_fee=qty*exit_price*.0005
        gross=(exit_price-entry_price)*qty;net=gross-entry_fee-exit_fee-funding;risk=(entry_price-stop)*qty
        if not all(math.isfinite(x) for x in (entry_fee,exit_fee,gross,net,risk)) or risk<=0:
            raise ValueError('计算金额无效')
        return {'status':'PARTIAL_NOT_REGISTERED','trade_id':trade_id,'stop_price':stop,'trigger_bid':trigger_bid,
                'exit_bid':exit_bid,'exit_ask':exit_ask,'entry_bid':entry_check['bid'],'entry_ask':entry_check['ask'],
                'entry_price':entry_price,'exit_price':exit_price,'qty':qty,
                'gross_pnl_usdt':round(gross,6),'entry_fee_usdt':round(entry_fee,6),'exit_fee_usdt':round(exit_fee,6),
                'funding_cost_usdt':funding,'funding_verification':'UNKNOWN','net_pnl_usdt':round(net,6),
                'initial_price_risk_usdt':round(risk,6),'net_R':round(net/risk,6),
                'reason':'仅为离散 bid 触发与假设成交的条件性核对；缺少连续行情、资金费完整性、真实止损和成交证据。'}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
        return {'status':'INVALID','reason':str(exc)}


def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    cap=sub.add_parser('capture');cap.add_argument('--out',required=True)
    paired=sub.add_parser('capture-with-receipt');paired.add_argument('--out',required=True);paired.add_argument('--receipt-out',required=True)
    check=sub.add_parser('check');check.add_argument('--quote',required=True);check.add_argument('--signal',required=True)
    check.add_argument('--entry',required=True);check.add_argument('--qty',required=True,type=float);check.add_argument('--as-of')
    trip=sub.add_parser('check-round-trip')
    for flag in ('signal','entry','entry-quote','mark','trigger-quote','exit','exit-quote'):
        trip.add_argument('--'+flag,required=True)
    trip.add_argument('--qty',required=True,type=float);trip.add_argument('--funding-cost',required=True,type=float);trip.add_argument('--as-of')
    args=parser.parse_args()
    if args.command in ('capture','capture-with-receipt'):
        path=Path(args.out)
        if path.exists() or (args.command=='capture-with-receipt' and Path(args.receipt_out).exists()):
            raise SystemExit('拒绝覆盖已有报价或回执文件')
        quote=fetch_quote(requests.Session())
        raw=(json.dumps(quote,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
        with path.open('xb') as f: f.write(raw)
        result={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),
                'status':'PREFLIGHT_UNVERIFIED','note':'一次只读快照，不是前瞻信号或成交'}
        if args.command=='capture-with-receipt':
            from .paper_quote_receipt import capture as capture_receipt, record_rejection
            try:
                result['receipt']=capture_receipt(path,args.receipt_out)
                result['status']='SAMPLE_AND_RECEIPT_UNVERIFIED'
            except (KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
                try:
                    result['rejection']=record_rejection(path,args.receipt_out)
                    result.update(status='QUOTE_SAVED_REJECTED',receipt_error=str(exc))
                except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError,RuntimeError) as failure:
                    result.update(status='QUOTE_SAVED_RECEIPT_MISSING',receipt_error=str(exc),rejection_error=str(failure))
            except OSError as exc:
                result.update(status='QUOTE_SAVED_RECEIPT_MISSING',receipt_error=str(exc))
    else:
        now=pd.to_datetime(args.as_of,utc=True,errors='coerce') if args.as_of else pd.Timestamp.now(tz='UTC')
        if pd.isna(now) or now>pd.Timestamp.now(tz='UTC'):
            raise SystemExit('检查时间无效或晚于现在')
        if args.command=='check':
            raw=Path(args.quote).read_bytes()
            result=assess(json.loads(raw),json.loads(Path(args.signal).read_text()),
                          json.loads(Path(args.entry).read_text()),args.qty,now)
            result['quote_sha256']=hashlib.sha256(raw).hexdigest()
        else:
            paths=[args.signal,args.entry,args.entry_quote,args.mark,args.trigger_quote,args.exit,args.exit_quote]
            raw=[Path(p).read_bytes() for p in paths]
            values=[json.loads(x) for x in raw]
            result=assess_round_trip(*values,args.qty,args.funding_cost,now)
            result['input_sha256']={name:hashlib.sha256(data).hexdigest()
                                    for name,data in zip(('signal','entry','entry_quote','mark','trigger_quote','exit','exit_quote'),raw)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
