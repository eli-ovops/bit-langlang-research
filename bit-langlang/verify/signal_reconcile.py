"""Offline completeness check for one captured scan window and manual events.

Historical consistency only: does not prove source authenticity, clock, timely
capture, overlapping window coverage, order fills or actual exchange exposure.
"""
import argparse
import hashlib
import io
import json
import zlib
from pathlib import Path
import pandas as pd
import numpy as np
from .forward_scan import closed_snapshot, signal_records, stop_for_entry
from .tph_frozen_audit import signals
from .forward_report import valid_trade_id


def reconcile(snapshot, events, market_dir, config_file, start, *, sealed_close=None, source_bytes=None, evidence_as_of=None):
    errors=[];expected={};candles={}
    try:
        cfg_hash=hashlib.sha256(Path(config_file).read_bytes()).hexdigest()
        if snapshot['config_sha256']!=cfg_hash: errors.append('冻结配置哈希不一致')
        generated=pd.to_datetime(snapshot['generated_at'],utc=True,errors='raise')
        if pd.isna(generated) or generated>pd.Timestamp.now(tz='UTC'): raise ValueError('invalid generated_at')
        evidence_time=pd.to_datetime(evidence_as_of,utc=True,errors='raise') if evidence_as_of is not None else generated
        if pd.isna(evidence_time) or evidence_time<generated or evidence_time>pd.Timestamp.now(tz='UTC'):
            raise ValueError('invalid evidence as-of time')
        start=pd.to_datetime(start,utc=True,errors='raise')
        frozen=pd.Timestamp(json.loads(Path(config_file).read_text())['frozen_at'],tz='UTC')
        if pd.isna(start) or start<frozen or start>generated: raise ValueError('invalid prospective start')
        seal=pd.to_datetime(sealed_close,utc=True,errors='raise') if sealed_close is not None else generated
        if pd.isna(seal) or seal>generated: raise ValueError('invalid sealed close time')
        if snapshot['btc_data_status']['status']!='FRESH': errors.append('BTC 快照采集时不新鲜')
        for sym in ('BTCUSDT','ETHUSDT'):
            value=snapshot['symbols'][sym]
            if value['data_status']['status']!='FRESH': errors.append(f'{sym} 快照采集时不新鲜');continue
            if source_bytes is None:
                path=Path(market_dir)/f'{sym}_5m.csv.gz';raw=path.read_bytes()
            else: raw=source_bytes[sym]
            if hashlib.sha256(raw).hexdigest()!=value['data_sha256']: errors.append(f'{sym} 行情快照哈希不一致')
            loaded=pd.read_csv(io.BytesIO(raw),usecols=['ts','open','high','low','close'],compression='gzip')
            loaded['ts']=pd.to_datetime(loaded.ts,unit='ms',utc=True,errors='coerce')
            data, state=closed_snapshot(loaded,generated,minimum_bars=205*288)
            if data is None or state['status']!='FRESH': errors.append(f'{sym} 行情在快照时无效或过期');continue
            candles[sym]=data.reset_index(drop=True)
            rows=value['signals_recent']
            if value['candidate_count']!=len(rows): errors.append(f'{sym} 候选数与记录数不一致')
            source_start=pd.to_datetime(value['candidate_window_start'],utc=True,errors='raise')
            if pd.isna(source_start) or source_start>start or data.ts.iloc[0]>start:
                errors.append(f'{sym} 扫描窗口未覆盖前瞻起点')
            for x in rows:
                stamp=pd.to_datetime(x['ts'],utc=True,errors='raise')
                if pd.isna(stamp) or stamp+pd.Timedelta(minutes=5)>generated: raise ValueError('invalid signal time')
                if stamp<start or stamp+pd.Timedelta(minutes=5)>seal: continue
                key=(sym,stamp.isoformat())
                if key in expected: errors.append('快照内候选重复')
                expected[key]=x
        if set(candles)=={'BTCUSDT','ETHUSDT'}:
            if candles['BTCUSDT'].ts.iloc[-1]!=candles['ETHUSDT'].ts.iloc[-1]: errors.append('BTC/ETH 快照时间不一致')
            for sym,data in candles.items():
                hit,_,_=signals(candles['BTCUSDT'],data)
                cutoff=max(pd.to_datetime(snapshot['symbols'][sym]['candidate_window_start'],utc=True,errors='raise'),start)
                if pd.isna(cutoff) or cutoff>data.ts.iloc[-1]: raise ValueError('invalid candidate window')
                recomputed={(sym,data.ts.iloc[i].isoformat()) for i in np.flatnonzero(hit)
                            if data.ts.iloc[i]>=cutoff and data.ts.iloc[i]+pd.Timedelta(minutes=5)<=seal}
                recorded={key for key in expected if key[0]==sym}
                if recomputed!=recorded: errors.append(f'{sym} 保存的候选与冻结公式重算不一致')
                actual={(sym,pd.Timestamp(row['ts']).isoformat()):row for row in signal_records(data,hit,cutoff)}
                for key in recorded & recomputed:
                    for field in ('entry_next_open','reference_stop_on_open','historical_only'):
                        if field not in expected[key] or expected[key][field]!=actual[key][field]: errors.append(f'{sym} 候选 {field} 与源行情重算不一致（旧 stop 字段不是成交止损）')
    except (KeyError,TypeError,ValueError,OSError,EOFError,zlib.error) as e:
        return {'status':'INVALID','reason':'快照无效或文件不可读取：'+str(e)}
    signal_count={};decisions={};signal_timing={};decision_timing={};entry_ids=set();entry_slippage=[];pending_references=0;ambiguous_order=0;delayed_entries=0
    for event in events:
        if not isinstance(event,dict): errors.append('事件必须是对象');continue
        if event.get('kind') not in ('signal','skip','entry'): continue
        try:
            signal=pd.to_datetime(event['signal_time_utc'],utc=True,errors='raise')
            observed=pd.to_datetime(event['captured_at_utc'],utc=True,errors='raise')
            happened=pd.to_datetime(event['event_time_utc'],utc=True,errors='raise')
            if any(pd.isna(t) for t in (signal,observed,happened)): raise ValueError('invalid event time')
            lag=(observed-happened).total_seconds()
            stated=float(event['capture_lag_seconds'])
            if event.get('schema')!='paper-event-v1' or event.get('verification')!='MANUAL_UNVERIFIED' or event.get('config_sha256')!=cfg_hash or observed>evidence_time or not np.isfinite(stated) or lag<0 or lag>900 or abs(lag-stated)>.001:
                raise ValueError('event metadata or lag invalid')
            close=signal+pd.Timedelta(minutes=5)
            if happened<close or observed-close>pd.Timedelta(minutes=15):
                raise ValueError('invalid event/signal timing')
            if event['kind']=='entry' and not valid_trade_id(event.get('trade_id')): raise ValueError('missing trade_id')
            key=(event['symbol'],signal.isoformat())
            if signal<start or signal+pd.Timedelta(minutes=5)>seal: continue
            if key not in expected: errors.append('信号事件不在该扫描窗口内');continue
            if event['kind']=='entry':
                if happened>close: delayed_entries+=1
                price=float(event['price']); reference=expected[key]['entry_next_open']
                if not np.isfinite(price) or price<=0: raise ValueError('invalid entry')
                if str(event['trade_id']) in entry_ids: errors.append('不同信号使用了重复交易编号')
                entry_ids.add(str(event['trade_id']))
                if reference is None: pending_references+=1
                entry_slippage.append({'trade_id':str(event['trade_id']),'symbol':key[0],'signal_time_utc':key[1],
                                       'reference_open':reference,'recorded_entry':price,
                                       'stop_on_recorded_entry_unrounded':stop_for_entry(price),
                                       'reference_status':'PENDING_NEXT_CLOSED_BAR' if reference is None else 'HISTORICAL_OPEN_UNVERIFIED',
                                       'price_difference_bps':round((price/reference-1)*10000,4) if reference is not None else None})
            bucket=signal_count if event['kind']=='signal' else decisions
            bucket[key]=bucket.get(key,0)+1
            timing=signal_timing if event['kind']=='signal' else decision_timing
            timing[key]=(happened,observed)
        except (KeyError,TypeError,ValueError): errors.append('信号事件格式、配置或时间无效')
    for key in expected:
        if signal_count.get(key,0)!=1: errors.append(f'{key[0]} {key[1]} 缺失或重复信号记录')
        if decisions.get(key,0)!=1: errors.append(f'{key[0]} {key[1]} 缺失或重复入场/跳过决定')
        if signal_count.get(key,0)==decisions.get(key,0)==1:
            signal_time,signal_capture=signal_timing[key]
            decision_time,decision_capture=decision_timing[key]
            if signal_time>decision_time or signal_capture>decision_time or signal_capture>decision_capture:
                errors.append(f'{key[0]} {key[1]} 信号记录晚于入场或跳过决定')
            elif signal_capture==decision_time or signal_capture==decision_capture:
                ambiguous_order+=1
    return {'status':'INVALID' if errors else ('AMBIGUOUS_ORDER' if ambiguous_order else 'EXECUTION_MODEL_MISMATCH' if delayed_entries else 'PENDING_REFERENCE' if pending_references else 'PARTIAL'),
            'ambiguous_order_count':ambiguous_order,'pending_reference_count':pending_references,'candidate_count':len(expected),'matched_signal_count':sum(v==1 for v in signal_count.values()),
            'delayed_entry_count':delayed_entries,
            'matched_decision_count':sum(v==1 for v in decisions.values()),'entry_price_differences':entry_slippage,'errors':errors,
            'evidence_as_of_utc':evidence_time.isoformat(),
            'reason':'信号采集须先于决定；延迟入场与冻结的下一根开盘模型不同，需另行定义并验证，不得当作原规则通过。仅核对形式一致性，不证明连续覆盖、真实捕获或成交。'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',required=True);p.add_argument('--events',required=True);p.add_argument('--market-dir',required=True);p.add_argument('--start',required=True);a=p.parse_args()
    folder=Path(a.events)
    if not folder.is_dir(): raise SystemExit('事件目录不存在')
    events=[json.loads(f.read_text()) for f in sorted(folder.glob('*.json'))]
    result=reconcile(json.loads(Path(a.scan).read_text()),events,a.market_dir,Path(__file__).with_name('frozen_config.json'),a.start)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
