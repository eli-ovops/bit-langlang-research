"""Replay archived public responses into snapshots; no network or authenticity claim."""
import argparse
import gzip
import hashlib
import json
import zlib
from pathlib import Path

import pandas as pd

from .paper_scan_archive import market_loaders, read_initial_source, read_public_source, records
from .paper_scan_once import MAX_PAGES, STEP, advance, load_base, valid_ms


def transition(previous, current, files, generated_at):
    """Replay one transition; this deliberately reuses the collector parser."""
    def request(root):
        return json.loads(files[root+'.request.json']),json.loads(files[root+'.body.json'])
    server_meta,clock=request('server-time')
    server=valid_ms(clock['serverTime'])
    if (server_meta['params']!={} or
            not server_meta['local_start_ms']-2000<=server<=server_meta['local_end_ms']+2000):
        raise ValueError('服务器时间与本机请求记录不一致')
    last_request_end=server_meta['local_end_ms']
    generated=pd.to_datetime(generated_at,utc=True,errors='raise')
    if pd.isna(generated):raise ValueError('扫描时间无效')
    counts={};grids=[]
    for symbol in ('BTCUSDT','ETHUSDT'):
        csv_raw,last,grid=load_base(previous[symbol],server)
        grids.append(grid)
        cursor=valid_ms(last[0]);rows=[]
        pages=sorted(name[:-len('.body.json')] for name in files
                     if name.startswith(symbol+'-') and name.endswith('.body.json'))
        if not pages or len(pages)>MAX_PAGES:raise ValueError('K 线页数无效')
        for name in pages:
            meta,body=request(name)
            if (meta['local_start_ms']<last_request_end or not isinstance(body,list) or not body or
                    meta['params']!={'symbol':symbol,'interval':'5m','startTime':cursor,'endTime':server,'limit':1000}):
                raise ValueError('K 线请求顺序、分页参数或响应无效')
            last_request_end=meta['local_end_ms']
            rows.extend(body);cursor=valid_ms(body[-1][0])+STEP
        rebuilt,count,end=advance(csv_raw,last,rows,server)
        latest=(server//STEP)*STEP-STEP
        if count<1 or end!=latest or rebuilt!=gzip.decompress(current[symbol]):
            raise ValueError(symbol+' 公开响应重放结果与归档行情不一致')
        counts[symbol]=count
    if last_request_end>generated.value//1_000_000:
        raise ValueError('请求完成晚于扫描生成时间')
    if counts['BTCUSDT']!=counts['ETHUSDT'] or grids[0]!=grids[1]:
        raise ValueError('两币历史网格或新增根数不一致')
    return counts


def audit(root, expected_head=None):
    try:
        items,head,orphans=records(root,expected_head)
        state,load=market_loaders(items)
        previous=None;results=[];errors=[]
        for index,item in enumerate(items):
            current=load(index)
            if index==0 and item['initial_source_status']=='BOUND_UNVERIFIED':
                previous=read_initial_source(item['run']/'initial-source')
                if {k:hashlib.sha256(v).hexdigest() for k,v in previous.items()}!=item['commit']['initial_source_sha256']:
                    raise ValueError('读取期间初始基线与提交哈希不一致')
            if previous is None:
                results.append({'sequence':index,'status':'UNKNOWN_INITIAL_BASELINE',
                                'public_source_status':item['public_source_status']})
            elif item['public_source_status']!='BOUND_UNVERIFIED':
                results.append({'sequence':index,'status':'UNKNOWN_SOURCE_MISSING'})
            else:
                try:
                    source=read_public_source(item['run']/'public-source')
                    if {k:hashlib.sha256(v).hexdigest() for k,v in source.items()}!=item['commit']['public_source_sha256']:
                        raise ValueError('读取期间原始响应与提交哈希不一致')
                    added=transition(previous,current,source,item['commit']['generated_at'])
                    results.append({'sequence':index,'status':'MATCHED_UNVERIFIED','added_bars':added})
                except (KeyError,TypeError,ValueError,OverflowError,OSError,EOFError,zlib.error) as exc:
                    errors.append({'sequence':index,'reason':str(exc)})
                    results.append({'sequence':index,'status':'INVALID'})
            previous=current
        missing=sum(x['public_source_status']=='UNKNOWN_NOT_CAPTURED' for x in items)
        matched=sum(x['status']=='MATCHED_UNVERIFIED' for x in results)
        status=('INVALID' if errors else 'UNKNOWN_SOURCE_MISSING' if missing else
                'PARTIAL_SOURCE_REPLAY' if matched else 'UNKNOWN_NO_TRANSITIONS')
        return {'status':status,'archive_head_sha256':head,
                'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' if expected_head else 'NO_EXTERNAL_ANCHOR',
                'records':len(items),'matched_transitions':matched,'missing_source_records':missing,
                'initial_baseline':('MATCHED_UNVERIFIED' if results[0]['status']=='MATCHED_UNVERIFIED' else 'UNKNOWN'),
                'transitions':results,'errors':errors,'orphan_run_ids':sorted(orphans),
                'source_authenticity':'UNKNOWN','clock_trust':'UNKNOWN',
                'reason':'复用采集器解析代码的本地字节重放；缺失基线、来源真实性、时钟和连续成交均未获证明。'}
    except (KeyError,TypeError,ValueError,OverflowError,OSError,EOFError,zlib.error) as exc:
        return {'status':'INVALID','reason':str(exc)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',required=True)
    parser.add_argument('--expected-head')
    args=parser.parse_args()
    print(json.dumps(audit(Path(args.archive),args.expected_head),ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
