"""Independent CSV/Decimal cross-check of archived response transitions."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import zlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from .paper_scan_archive import market_loaders, read_initial_source, read_public_source, records

STEP=300000
FIELDS=['ts','open','high','low','close','volume','turnover']


def integer(value):
    text=str(value)
    if not text or not text.isascii() or not text.isdecimal():raise ValueError('时间戳无效')
    return int(text)


def number(value,positive):
    text=str(value)
    if text!=text.strip() or any(c in text for c in ',\r\n'):raise ValueError('数字格式无效')
    try:value=Decimal(text)
    except InvalidOperation as exc:raise ValueError('数字无效') from exc
    if not value.is_finite() or (value<=0 if positive else value<0):raise ValueError('数字范围无效')
    return value


def fields(row):
    if len(row)!=7:raise ValueError('CSV 列数无效')
    return (integer(row[0]),*[number(v,i<4) for i,v in enumerate(row[1:])])


def compare(previous,current,files,generated_at):
    """Check uncompressed CSV prefix and closed response rows without collector code."""
    def get(root):return json.loads(files[root+'.request.json']),json.loads(files[root+'.body.json'])
    clock_meta,clock=get('server-time');server=integer(clock['serverTime'])
    if clock_meta['params']!={} or not clock_meta['local_start_ms']-2000<=server<=clock_meta['local_end_ms']+2000:
        raise ValueError('服务器时间不符')
    generated=pd.to_datetime(generated_at,utc=True,errors='raise')
    if pd.isna(generated):raise ValueError('扫描时间无效')
    last_end=clock_meta['local_end_ms'];counts={};last_opens=[]
    for symbol in ('BTCUSDT','ETHUSDT'):
        old=gzip.decompress(previous[symbol]);new=gzip.decompress(current[symbol])
        if not old.endswith(b'\n') or not new.endswith(b'\n') or not old.startswith((','.join(FIELDS)+'\n').encode()) or not new.startswith(old):
            raise ValueError('原始行情前缀不一致')
        last=fields(next(csv.reader([old.rstrip(b'\n').rsplit(b'\n',1)[-1].decode('ascii')],strict=True)))
        last_opens.append(last[0]);expected=last[0];received=[]
        pages=sorted(k[:-len('.body.json')] for k in files if k.startswith(symbol+'-') and k.endswith('.body.json'))
        if not pages or len(pages)>3 or pages!=[f'{symbol}-{i:03}' for i in range(len(pages))]:raise ValueError('分页数无效')
        cursor=last[0]
        for page in pages:
            meta,body=get(page)
            if (meta['local_start_ms']<last_end or meta['local_start_ms']>meta['local_end_ms'] or not isinstance(body,list) or not body or
                    meta['params']!={'symbol':symbol,'interval':'5m','startTime':cursor,'endTime':server,'limit':1000}):
                raise ValueError('请求时序或分页参数无效')
            last_end=meta['local_end_ms']
            for bar in body:
                if not isinstance(bar,list) or len(bar)<8:raise ValueError('K 线字段无效')
                stamp=integer(bar[0]);close=integer(bar[6])
                if stamp!=expected or stamp>server or stamp%STEP or close!=stamp+STEP-1:raise ValueError('K 线时间网格不连续')
                values=fields([bar[0],*bar[1:6],bar[7]])
                op,high,low,closing=values[1:5]
                if low>min(op,high,closing) or high<max(op,low,closing):raise ValueError('OHLC 无效')
                if close<server:received.append(values)
                expected+=STEP
            cursor=integer(body[-1][0])+STEP
        if not received or received[0]!=last:raise ValueError('请求重叠行与基线不一致')
        if received[-1][0]!=(server//STEP)*STEP-STEP:raise ValueError('未覆盖最近已收盘 K 线')
        suffix=new[len(old):].decode('ascii')
        actual=[fields(row) for row in csv.reader(io.StringIO(suffix),strict=True)]
        if not actual or actual!=received[1:]:raise ValueError(symbol+' 新增 CSV 与响应不一致')
        counts[symbol]=len(actual)
    if last_end>generated.value//1_000_000:raise ValueError('请求完成晚于扫描生成')
    if last_opens[0]!=last_opens[1] or counts['BTCUSDT']!=counts['ETHUSDT']:
        raise ValueError('两币起点或新增数量不一致')
    return counts


def audit(root,expected_head=None):
    try:
        items,head,orphans=records(root,expected_head);_,load=market_loaders(items)
        previous=None;results=[];errors=[]
        for i,item in enumerate(items):
            current=load(i)
            if i==0 and item['initial_source_status']=='BOUND_UNVERIFIED':
                previous=read_initial_source(item['run']/'initial-source')
                if {k:hashlib.sha256(v).hexdigest() for k,v in previous.items()}!=item['commit']['initial_source_sha256']:
                    raise ValueError('基线读取期间发生变化')
            if previous is None:
                results.append({'sequence':i,'status':'UNKNOWN_INITIAL_BASELINE'})
            elif item['public_source_status']!='BOUND_UNVERIFIED':
                results.append({'sequence':i,'status':'UNKNOWN_SOURCE_MISSING'})
            else:
                try:
                    source=read_public_source(item['run']/'public-source')
                    if {k:hashlib.sha256(v).hexdigest() for k,v in source.items()}!=item['commit']['public_source_sha256']:
                        raise ValueError('原始响应读取期间发生变化')
                    counts=compare(previous,current,source,item['commit']['generated_at'])
                    results.append({'sequence':i,'status':'MATCHED_UNVERIFIED','added_bars':counts})
                except (KeyError,TypeError,ValueError,OverflowError,OSError,EOFError,zlib.error,csv.Error) as exc:
                    errors.append({'sequence':i,'reason':str(exc)});results.append({'sequence':i,'status':'INVALID'})
            previous=current
        matched=sum(x['status']=='MATCHED_UNVERIFIED' for x in results)
        unknown=sum(x['status'].startswith('UNKNOWN') for x in results)
        status=('INVALID' if errors else 'UNKNOWN_INCOMPLETE' if unknown else 'PARTIAL_INDEPENDENT_CROSSCHECK')
        return {'status':status,'matched_transitions':matched,'unknown_transitions':unknown,'transitions':results,
                'errors':errors,'archive_head_sha256':head,'orphan_run_ids':sorted(orphans),
                'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' if expected_head else 'NO_EXTERNAL_ANCHOR',
                'source_authenticity':'UNKNOWN','clock_trust':'UNKNOWN',
                'reason':'独立 CSV/Decimal 对照；仍复用归档恢复器，不证明来源、时钟或真实成交。'}
    except (KeyError,TypeError,ValueError,OverflowError,OSError,EOFError,zlib.error,csv.Error) as exc:
        return {'status':'INVALID','reason':str(exc)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True);parser.add_argument('--expected-head')
    args=parser.parse_args()
    print(json.dumps(audit(Path(args.archive),args.expected_head),ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
