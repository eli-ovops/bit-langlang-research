"""Audit one position's saved discrete bid samples; never assert continuous coverage."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path

import pandas as pd

from .forward_report import MISSING_TOKENS
from .paper_quote import CONFIG, assess, quote_facts

MAX_GAP=pd.Timedelta(seconds=60)
RECEIPT_LAG=pd.Timedelta(seconds=2)
DEFINITION=Path(__file__).resolve().parent.parent/'docs/纸面持仓离散报价覆盖-事前定义-20261030.md'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    t=pd.to_datetime(value,utc=True,errors='raise')
    if pd.isna(t):raise ValueError('时间缺失')
    return t


def receipt_check(quote_raw,receipt_raw):
    quote=json.loads(quote_raw);receipt=json.loads(receipt_raw);facts=quote_facts(quote)
    cfg=sha(CONFIG.read_bytes())
    if (receipt.get('schema')!='paper-quote-receipt-v1' or receipt.get('verification')!='LOCAL_CLOCK_UNVERIFIED'
            or receipt.get('config_sha256')!=cfg or receipt.get('quote_sha256')!=sha(quote_raw)):
        raise ValueError('报价回执格式或哈希不符')
    captured=timestamp(receipt['captured_at_utc'])
    if not facts['local_completed']<captured<=facts['local_completed']+RECEIPT_LAG:
        raise ValueError('报价回执过早或超过 2 秒')
    return facts,captured


def event_time(event,kind,trade_id,now):
    cfg=sha(CONFIG.read_bytes())
    if (event.get('schema')!='paper-event-v1' or event.get('verification')!='MANUAL_UNVERIFIED'
            or event.get('config_sha256')!=cfg or event.get('kind')!=kind or event.get('symbol')!='ETHUSDT'
            or str(event.get('trade_id'))!=trade_id):raise ValueError('持仓事件类型或交易编号不符')
    happened=timestamp(event['event_time_utc']);captured=timestamp(event['captured_at_utc'])
    lag=float(event['capture_lag_seconds'])
    if (not math.isfinite(lag) or lag<0 or lag>900 or captured<happened or captured>now
            or abs(lag-(captured-happened).total_seconds())>.001):raise ValueError('持仓事件采集时间无效')
    return happened,captured


def audit(signal,entry,entry_quote_raw,entry_receipt_raw,ledger,samples,as_of,*,exit_event=None,mark=None,trigger_quote_raw=None,clock_for_test=None):
    observed_hit=None
    try:
        now=timestamp(as_of)
        clock=pd.Timestamp.now(tz='UTC') if clock_for_test is None else timestamp(clock_for_test)
        if now>clock or len(ledger)!=1 or not isinstance(samples,list):
            raise ValueError('检查时间、单笔账本或报价集合无效')
        row=ledger.iloc[0];qty=float(row['qty']);entry_price=float(entry['price'])
        entry_quote=json.loads(entry_quote_raw)
        entry_check=assess(entry_quote,signal,entry,qty,now)
        if entry_check['status']!='PARTIAL_NOT_REGISTERED':return {'status':entry_check['status'],'entry_check':entry_check}
        entry_facts,entry_receipt_time=receipt_check(entry_quote_raw,entry_receipt_raw)
        if entry_receipt_time>=timestamp(entry['event_time_utc']):raise ValueError('入场决定并未晚于报价保存回执')
        trade_id=str(entry['trade_id']);entered=timestamp(entry['event_time_utc']);entry_captured=timestamp(entry['captured_at_utc'])
        frozen=pd.Timestamp(json.loads(CONFIG.read_text())['frozen_at'],tz='UTC')
        if (timestamp(signal['signal_time_utc'])<frozen or str(row['trade_id'])!=trade_id or row['symbol']!='ETHUSDT'
                or str(row['side']).lower() not in ('long','多') or timestamp(row['entry_time'])!=entered
                or not math.isclose(float(row['entry']),entry_price,rel_tol=1e-9,abs_tol=1e-9)
                or not math.isclose(float(row['stop']),entry_price*.996,rel_tol=1e-9,abs_tol=1e-9)):
            raise ValueError('入场事件与纸面账本或冻结时间不一致')
        if exit_event is None:
            if str(row.get('exit_time','')).strip().upper() not in MISSING_TOKENS:
                raise ValueError('账本含出场时间但未提供出场事件')
            end=now
        else:
            end,_=event_time(exit_event,'exit',trade_id,now)
            if (end<=entry_captured or timestamp(row['exit_time'])!=end
                    or not math.isclose(float(row['exit']),float(exit_event['price']),rel_tol=1e-9,abs_tol=1e-9)):
                raise ValueError('出场事件与账本时间或价格不符')
        if end<entry_captured:raise ValueError('持仓检查区间无效')
        deadline=entered+pd.Timedelta(days=30);overdue=exit_event is None and end>deadline
        entry_capture_lag=(entry_captured-entered).total_seconds()
        if not samples:
            return {'status':'ALERT_OVERDUE' if overdue else 'UNKNOWN_NO_SAMPLES','overdue':overdue,
                    'entry_capture_lag_seconds':entry_capture_lag,
                    'synthetic_clock_used':clock_for_test is not None,
                    'trigger_evidence_provided_unchecked':bool(mark is not None or trigger_quote_raw is not None),
                    'reason':'没有持仓报价样本；不能推断价格或止损是否正常'}
        stop=entry_price*.996;seen=set();previous=entry_captured;coverage_previous=entered;items=[];gaps=[]
        for sample in samples:
            raw=sample['quote_raw'];receipt_raw=sample['receipt_raw'];digest=sha(raw)
            if digest in seen:raise ValueError('重复报价文件')
            seen.add(digest);facts,captured=receipt_check(raw,receipt_raw)
            if not previous<facts['local_start'] or captured>end or (exit_event is not None and captured==end):
                raise ValueError('持仓报价采集顺序或区间无效')
            gap=(captured-coverage_previous).total_seconds();gaps.append(gap)
            items.append({'quote_sha256':digest,'receipt_sha256':sha(receipt_raw),'captured_at_utc':captured.isoformat(),
                          'bid':facts['bid'],'ask':facts['ask'],'observed_stop_hit':facts['bid']<=stop})
            if observed_hit is None and items[-1]['observed_stop_hit']:
                observed_hit=items[-1]
            previous=captured;coverage_previous=captured
        tail=(end-previous).total_seconds();gaps.append(tail)
        hit=next((item for item in items if item['observed_stop_hit']),None)
        gap=any(value>MAX_GAP.total_seconds() for value in gaps)
        trigger_sha=sha(trigger_quote_raw) if trigger_quote_raw is not None else None
        result={'trade_id':trade_id,'stop_unrounded':stop,'sample_count':len(items),'samples':items,
                'max_gap_seconds':max(gaps),'coverage_gap':gap,'tail_gap_seconds':tail,
                'entry_capture_lag_seconds':entry_capture_lag,
                'first_observed_stop_hit':hit,'overdue':overdue,'continuous_price_path':'UNKNOWN',
                'true_stop_trigger':'UNKNOWN','actual_execution':'UNKNOWN',
                'synthetic_clock_used':clock_for_test is not None,
                'definition_sha256':sha(DEFINITION.read_bytes())}
        if hit is not None and exit_event is None:
            return {**result,'status':'ALERT_OBSERVED_STOP',
                    'trigger_evidence_provided_unchecked':bool(mark is not None or trigger_quote_raw is not None),
                    'reason':'已观察 bid 触损；采样间隙内的价格路径仍未知'}
        if overdue:
            return {**result,'status':'ALERT_OVERDUE','reason':'记录的未平仓时间已超过 30 天'}
        if exit_event is None and (mark is not None or trigger_sha is not None):
            return {**result,'status':'UNKNOWN_TRIGGER_SAMPLE','reason':'提供了触发资料，但持仓样本没有观察到触损'}
        if exit_event is not None and hit is not None:
            if mark is None or trigger_sha is None:
                return {**result,'status':'UNKNOWN_TRIGGER_SAMPLE','reason':'已观察触损，但缺少触发事件或对应报价文件'}
            mark_time,mark_captured=event_time(mark,'mark',trade_id,now)
            sample=next((item for item in items if item['quote_sha256']==trigger_sha),None)
            if sample is None:return {**result,'status':'UNKNOWN_TRIGGER_SAMPLE','reason':'触发报价不在提供的持仓样本中'}
            if (mark_time<=timestamp(sample['captured_at_utc']) or mark_captured>=end
                    or not math.isclose(float(mark['price']),sample['bid'],rel_tol=1e-9,abs_tol=1e-9)):
                raise ValueError('止损事件与报价回执或出场时序不一致')
            if trigger_sha!=hit['quote_sha256']:
                return {**result,'status':'MISSED_OBSERVED_STOP','reason':'更早保存的报价已观察到触损'}
        elif exit_event is not None and (mark is not None or trigger_sha is not None):
            return {**result,'status':'UNKNOWN_TRIGGER_SAMPLE','reason':'提供的持仓样本没有可核对的止损触及'}
        if exit_event is not None and end>deadline+pd.Timedelta(minutes=15):
            return {**result,'status':'EXECUTION_MODEL_MISMATCH','reason':'出场记录超过 30 天及其候选宽限'}
        if gap:return {**result,'status':'COVERAGE_GAP','reason':'持仓报价存在超过 60 秒的未观察区间'}
        return {**result,'status':'PARTIAL_DISCRETE_UNVERIFIED',
                'reason':'仅验证离散报价样本；即便间隔达标，样本之间仍可能触损'}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError) as exc:
        return {'status':'INVALID','reason':str(exc),'first_observed_stop_hit':observed_hit,
                'observed_stop_alert':observed_hit is not None,
                'observation_completeness':'UNKNOWN'}


def main():
    parser=argparse.ArgumentParser()
    for flag in ('signal','entry','entry-quote','entry-receipt','ledger','samples','as-of'):
        parser.add_argument('--'+flag,required=True)
    parser.add_argument('--exit');parser.add_argument('--mark');parser.add_argument('--trigger-quote')
    args=parser.parse_args()
    try:
        def unique_pairs(pairs):
            obj={}
            for key,value in pairs:
                if key in obj:raise ValueError('报价清单含重复键')
                obj[key]=value
            return obj
        paths={'signal':args.signal,'entry':args.entry,'entry_quote':args.entry_quote,
               'entry_receipt':args.entry_receipt,'ledger':args.ledger,'samples':args.samples}
        for name,path in (('exit',args.exit),('mark',args.mark),('trigger_quote',args.trigger_quote)):
            if path:paths[name]=path
        raw={key:Path(path).read_bytes() for key,path in paths.items()}
        manifest=json.loads(raw['samples'],object_pairs_hook=unique_pairs)
        if manifest.get('schema')!='paper-position-quotes-v1' or not isinstance(manifest.get('samples'),list):
            raise ValueError('报价清单格式无效')
        root=Path(args.samples).parent;items=[]
        for item in manifest['samples']:
            quote=(root/item['quote']).read_bytes();receipt=(root/item['receipt']).read_bytes()
            items.append({'quote_raw':quote,'receipt_raw':receipt})
        ledger=pd.read_csv(io.BytesIO(raw['ledger']),dtype=str,keep_default_na=False)
        result=audit(json.loads(raw['signal']),json.loads(raw['entry']),raw['entry_quote'],raw['entry_receipt'],ledger,items,args.as_of,
                     exit_event=json.loads(raw['exit']) if 'exit' in raw else None,
                     mark=json.loads(raw['mark']) if 'mark' in raw else None,trigger_quote_raw=raw.get('trigger_quote'))
        result['input_sha256']={key:sha(value) for key,value in raw.items()}
    except (OSError,KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
        result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
