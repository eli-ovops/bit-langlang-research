"""Audit saved paper scan cadence and sealed signals, not an observation service."""
import argparse
import hashlib
import io
import json
import math
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_report import MISSING_TOKENS, valid_trade_id
from .forward_scan import closed_snapshot, signal_records
from .signal_reconcile import reconcile as reconcile_signals
from .tph_frozen_audit import signals

CONFIG=Path(__file__).with_name('frozen_config.json')
DEFINITION=Path(__file__).resolve().parent.parent/'docs/纸面信号连续覆盖核验-事前定义-20261030.md'
CADENCE=pd.Timedelta(minutes=6)
GRACE=pd.Timedelta(minutes=15)
BAR=pd.Timedelta(minutes=5)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    result=pd.to_datetime(value,utc=True,errors='raise')
    if pd.isna(result):raise ValueError('时间缺失')
    return result


def audit(scans,events,start,as_of):
    """scans contain snapshot, file hash, market directory and local receipt."""
    try:
        start=timestamp(start);now=timestamp(as_of);real_now=pd.Timestamp.now(tz='UTC')
        frozen=pd.Timestamp(json.loads(CONFIG.read_text())['frozen_at'],tz='UTC')
        if start<frozen or start.floor('5min')!=start or now<start or now>real_now:
            raise ValueError('起点、终点或 5 分钟网格无效')
        if not isinstance(scans,list) or not isinstance(events,list):raise ValueError('扫描或事件集合类型无效')
        if not scans:return {'status':'UNKNOWN_NO_SCANS','reason':'没有已保存扫描；不能推断没有信号'}
        generated=[timestamp(item['snapshot']['generated_at']) for item in scans]
        captured_times=[timestamp(item['receipt']['captured_at_utc']) for item in scans]
        if (any(g>c or c>now for g,c in zip(generated,captured_times))
                or any(a>=b for a,b in zip(generated,generated[1:]))
                or any(a>=b for a,b in zip(captured_times,captured_times[1:]))):
            raise ValueError('扫描时间重复、倒序或晚于检查时刻')
        intervals=[b-a for a,b in zip(captured_times,captured_times[1:])]
        if not BAR<=captured_times[0]-start<=CADENCE or any(x>CADENCE for x in intervals) or now-captured_times[-1]>CADENCE:
            return {'status':'COVERAGE_GAP','first_scan_utc':captured_times[0].isoformat(),'last_scan_utc':captured_times[-1].isoformat(),
                    'max_inter_scan_seconds':max([x.total_seconds() for x in intervals],default=0),
                    'reason':'首条、相邻扫描或末尾检查间隔超过预定范围'}
        cfg=digest(CONFIG.read_bytes());relevant=[];counts={};entry_ids=set()
        for event in events:
            if not isinstance(event,dict):raise ValueError('事件不是对象')
            kind=event.get('kind')
            if kind not in ('signal','skip','entry'):continue
            signal=timestamp(event['signal_time_utc']);happened=timestamp(event['event_time_utc']);captured=timestamp(event['captured_at_utc'])
            lag=float(event['capture_lag_seconds']);close=signal+BAR
            if (event.get('schema')!='paper-event-v1' or event.get('verification')!='MANUAL_UNVERIFIED'
                    or event.get('config_sha256')!=cfg or event.get('symbol')!='ETHUSDT'
                    or signal<start or signal.floor('5min')!=signal or happened<close or captured>now
                    or captured<happened or captured-close>GRACE or not math.isfinite(lag)
                    or abs(lag-(captured-happened).total_seconds())>.001
                    or (kind=='skip' and str(event.get('description','')).strip().upper() in MISSING_TOKENS)
                    or (kind=='entry' and not valid_trade_id(event.get('trade_id')))):
                raise ValueError('信号事件格式或采集时序无效')
            if kind=='entry':
                price=float(event['price']);trade_id=str(event['trade_id'])
                if not math.isfinite(price) or price<=0 or trade_id in entry_ids:
                    raise ValueError('入场价格无效或跨扫描交易编号重复')
                entry_ids.add(trade_id)
            key=(event['symbol'],signal.isoformat());bucket='signal' if kind=='signal' else 'decision'
            counts[(key,bucket)]=counts.get((key,bucket),0)+1
            if counts[(key,bucket)]>1:raise ValueError('信号或决定重复')
            relevant.append((key,signal,captured,event))
        previous=None;previous_watermark=start;first_seen={};sealed_count=matched_signals=matched_decisions=0
        delayed=ambiguous=pending_refs=0;results=[]
        for item,generated_at,captured_at in zip(scans,generated,captured_times):
            snapshot=item['snapshot'];loader=item.get('_load_market');folder=Path(item['market_dir']) if loader is None else None
            source=loader() if loader is not None else {s:(folder/f'{s}_5m.csv.gz').read_bytes() for s in ('BTCUSDT','ETHUSDT')}
            frames={};file_hashes={}
            receipt=item['receipt']
            if (receipt.get('schema')!='paper-scan-receipt-v1' or receipt.get('verification')!='LOCAL_CLOCK_UNVERIFIED'
                    or receipt.get('scan_sha256')!=item['scan_sha256'] or receipt.get('config_sha256')!=cfg):
                raise ValueError('扫描文件保存回执无效')
            if snapshot['config_sha256']!=cfg or snapshot['btc_data_status']['status']!='FRESH':
                raise ValueError('扫描配置或 BTC 状态无效')
            for symbol in ('BTCUSDT','ETHUSDT'):
                metadata=snapshot['symbols'][symbol]
                if metadata['data_status']['status']!='FRESH':raise ValueError('扫描行情状态不是 FRESH')
                raw=source[symbol];file_hashes[symbol]=digest(raw)
                if file_hashes[symbol]!=metadata['data_sha256'] or receipt['market_sha256'][symbol]!=file_hashes[symbol]:
                    raise ValueError('行情或回执哈希不匹配')
                data=pd.read_csv(io.BytesIO(raw),usecols=['ts','open','high','low','close'],compression='gzip')
                data['ts']=pd.to_datetime(data.ts,unit='ms',utc=True,errors='coerce')
                if data.empty or data.ts.isna().any() or data.ts.iloc[-1]+BAR>generated_at:
                    raise ValueError('行情包含未收盘或未来 K 线')
                frame,state=closed_snapshot(data,generated_at,minimum_bars=205*288)
                if frame is None or state['status']!='FRESH':raise ValueError('行情缺口、过期或预热不足')
                if captured_at-(frame.ts.iloc[-1]+BAR)>CADENCE:
                    raise ValueError('最近已收盘 K 线距扫描超过 6 分钟')
                frames[symbol]=frame.reset_index(drop=True)
                if previous is not None:
                    old=previous[symbol]
                    prefix=frames[symbol].iloc[:len(old)].reset_index(drop=True)
                    if (len(frame)<len(old) or not prefix.ts.equals(old.ts)
                            or not np.array_equal(prefix[['open','high','low','close']].to_numpy(dtype=float),
                                                  old[['open','high','low','close']].to_numpy(dtype=float))):
                        raise ValueError('相邻快照的历史 K 线被修改、删除或重排')
            if not frames['BTCUSDT'].ts.equals(frames['ETHUSDT'].ts):raise ValueError('BTC 与 ETH 网格不一致')
            for symbol,frame in frames.items():
                metadata=snapshot['symbols'][symbol];cutoff=timestamp(metadata['candidate_window_start'])
                if cutoff>previous_watermark or cutoff>frame.ts.iloc[-1]:raise ValueError('候选窗口未覆盖封存范围')
                hit,_,_=signals(frames['BTCUSDT'],frame)
                actual=signal_records(frame,hit,cutoff);saved=metadata['signals_recent']
                if metadata['candidate_count']!=len(saved):raise ValueError('候选数量不符')
                def indexed(rows):
                    out={}
                    for row in rows:
                        stamp=timestamp(row['ts']);key=(symbol,stamp.isoformat())
                        if key in out or stamp+BAR>generated_at:raise ValueError('候选重复或未收盘')
                        out[key]={k:row[k] for k in ('entry_next_open','reference_stop_on_open','historical_only')}
                    return out
                observed=indexed(saved);expected=indexed(actual)
                if observed!=expected:raise ValueError('全部候选与当时行情重算不一致')
                for key in observed:
                    if timestamp(key[1])>=start:first_seen.setdefault(key,captured_at)
            seal=(generated_at-GRACE).floor('5min')
            segment=[event for _,signal,captured,event in relevant
                     if previous_watermark<=signal and signal+BAR<=seal and captured<=generated_at]
            checked=reconcile_signals(snapshot,segment,folder,CONFIG,previous_watermark,sealed_close=seal,source_bytes=source)
            if checked['status']=='INVALID':return {'status':'INVALID','scan_sha256':item['scan_sha256'],'signal_check':checked}
            if checked['status']=='AMBIGUOUS_ORDER':ambiguous+=1
            elif checked['status']=='EXECUTION_MODEL_MISMATCH':delayed+=checked['delayed_entry_count']
            elif checked['status'] not in ('PARTIAL','PENDING_REFERENCE'):raise ValueError('未知信号检查状态')
            pending_refs+=checked['pending_reference_count'];sealed_count+=checked['candidate_count']
            matched_signals+=checked['matched_signal_count'];matched_decisions+=checked['matched_decision_count']
            for key in first_seen:
                close=timestamp(key[1])+BAR
                if previous_watermark<=timestamp(key[1]) and close<=seal and first_seen[key]>close+CADENCE:
                    raise ValueError('已封存信号未在收盘后 6 分钟内出现')
            for symbol in frames:
                if loader is None and digest((folder/f'{symbol}_5m.csv.gz').read_bytes())!=file_hashes[symbol]:
                    raise ValueError('核查期间行情文件发生变化')
            previous=frames;previous_watermark=max(previous_watermark,seal)
            results.append({'scan_sha256':item['scan_sha256'],'generated_at':generated_at.isoformat(),
                            'receipt_sha256':item['receipt_sha256'],'captured_at_utc':captured_at.isoformat(),
                            'sealed_close_utc':seal.isoformat(),'sealed_candidates':checked['candidate_count'],
                            'status':checked['status'],'market_sha256':file_hashes})
        pending=[{'symbol':key[0],'signal_time_utc':key[1]} for key in first_seen if timestamp(key[1])+BAR>previous_watermark]
        pending_events=[{'symbol':key[0],'signal_time_utc':key[1],'kind':event['kind']}
                        for key,signal,_,event in relevant if signal+BAR>previous_watermark]
        pending_unseen=sorted({key for key,signal,_,_ in relevant if signal+BAR>previous_watermark and key not in first_seen})
        pending_delayed=sum(event['kind']=='entry' and signal+BAR>previous_watermark
                            and timestamp(event['event_time_utc'])>signal+BAR for _,signal,_,event in relevant)
        # A retrospective scan match does not establish that its saved signal
        # was available when the manually recorded signal was observed.
        unavailable=[]
        for key,signal,_,event in relevant:
            if event['kind']!='signal' or key not in first_seen:
                continue
            happened=timestamp(event['event_time_utc'])
            if happened<=first_seen[key]:
                unavailable.append({'symbol':key[0],'signal_time_utc':key[1],
                                    'signal_event_utc':happened.isoformat(),
                                    'first_saved_scan_receipt_utc':first_seen[key].isoformat(),
                                    'window':'SEALED' if signal+BAR<=previous_watermark else 'PENDING'})
        status=('PENDING_NO_SEALED_WINDOW' if previous_watermark<=start else 'AMBIGUOUS_ORDER' if ambiguous
                else 'EXECUTION_MODEL_MISMATCH' if delayed or pending_delayed
                else 'UNKNOWN_SIGNAL_AVAILABILITY' if unavailable else 'PARTIAL_COVERAGE_UNVERIFIED')
        return {'status':status,'coverage_status':'PENDING' if previous_watermark<=start else 'PARTIAL_COVERAGE_UNVERIFIED',
                'start_utc':start.isoformat(),'as_of_utc':now.isoformat(),'scan_count':len(scans),
                'first_scan_utc':captured_times[0].isoformat(),'last_scan_utc':captured_times[-1].isoformat(),
                'max_inter_scan_seconds':max([x.total_seconds() for x in intervals],default=0),
                'sealed_close_watermark_utc':previous_watermark.isoformat(),
                'unsealed_seconds':max(0,(now-previous_watermark).total_seconds()),'sealed_candidates':sealed_count,
                'matched_signals':matched_signals,'matched_decisions':matched_decisions,'pending_candidates':pending,
                'pending_events':pending_events,'pending_event_keys_not_yet_seen_in_scans':
                    [{'symbol':key[0],'signal_time_utc':key[1]} for key in pending_unseen],
                'signal_availability_status':('UNKNOWN' if unavailable or pending_unseen else
                    'NO_SIGNAL_EVENTS' if not any(event['kind']=='signal' for _,_,_,event in relevant)
                    else 'ORDERED_BUT_UNVERIFIED'),
                'signal_events_not_after_first_scan_receipt':unavailable,
                'delayed_entry_count':delayed,'pending_delayed_entry_count':pending_delayed,
                'ambiguous_segment_count':ambiguous,'pending_open_references':pending_refs,
                'scans':results,'definition_sha256':digest(DEFINITION.read_bytes()),
                'reason':'仅为已保存离散扫描的条件性核对，最新时段未封存；不证明时钟、来源、连续盘口或真实成交。'}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError,EOFError,zlib.error) as exc:
        return {'status':'INVALID','reason':str(exc)}


def main():
    parser=argparse.ArgumentParser()
    for flag in ('manifest','events','start','as-of'):parser.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    try:
        def unique_pairs(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('扫描清单存在重复键')
                result[key]=value
            return result
        manifest_path=Path(args.manifest);manifest_raw=manifest_path.read_bytes();manifest=json.loads(manifest_raw,object_pairs_hook=unique_pairs)
        if manifest['schema']!='paper-scan-coverage-v1' or not isinstance(manifest['scans'],list):raise ValueError('清单格式无效')
        scans=[]
        for item in manifest['scans']:
            raw=(manifest_path.parent/item['scan']).read_bytes()
            receipt_raw=(manifest_path.parent/item['receipt']).read_bytes()
            scans.append({'snapshot':json.loads(raw),'market_dir':manifest_path.parent/item['market_dir'],
                          'scan_sha256':digest(raw),'receipt':json.loads(receipt_raw),'receipt_sha256':digest(receipt_raw)})
        folder=Path(args.events)
        if not folder.is_dir():raise ValueError('事件目录不存在')
        paths=sorted(folder.glob('*.json'));raw_events=[path.read_bytes() for path in paths]
        result=audit(scans,[json.loads(raw) for raw in raw_events],args.start,args.as_of)
        result['input_sha256']={'manifest':digest(manifest_raw),'events':{p.name:digest(raw) for p,raw in zip(paths,raw_events)}}
    except (KeyError,TypeError,ValueError,OverflowError,OSError) as exc:
        result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
