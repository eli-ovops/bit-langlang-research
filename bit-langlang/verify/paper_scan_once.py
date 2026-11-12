"""One bounded public-data preflight; no accounts, scheduler or order actions."""
import argparse
import gzip
import hashlib
import io
import json
import math
import subprocess
import sys
import time
import zlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import requests

from .forward_scan import closed_snapshot
from .paper_scan_archive import append as archive_append, init as archive_init, status as archive_status
from .paper_scan_receipt import capture as capture_receipt

BASE='https://fapi.binance.com'
SYMBOLS=('BTCUSDT','ETHUSDT')
STEP=300000
MAX_PAGES=3
FIELDS=('ts','open','high','low','close','volume','turnover')


class RevisionError(ValueError):pass


def sha(raw):return hashlib.sha256(raw).hexdigest()


def valid_decimal(value,*,positive=False):
    text=str(value)
    if text!=text.strip() or any(char in text for char in ',\r\n'):
        raise ValueError('K 线数值包含非规范字符')
    try:value=Decimal(text)
    except InvalidOperation as exc:raise ValueError('K 线数值格式无效') from exc
    if not value.is_finite() or (value<=0 if positive else value<0):raise ValueError('K 线数值范围无效')
    return value


def valid_ms(value):
    text=str(value)
    if not text or not text.isascii() or not text.isdecimal():raise ValueError('K 线时间戳不是非负整数')
    return int(text)


def load_base(raw,server_ms):
    csv_raw=gzip.decompress(raw)
    if not csv_raw.endswith(b'\n') or csv_raw.split(b'\n',1)[0]!=','.join(FIELDS).encode():
        raise ValueError('基线 CSV 字段或行尾无效')
    last=csv_raw.rstrip(b'\n').rsplit(b'\n',1)[-1].decode('ascii').split(',')
    if len(last)!=len(FIELDS):raise ValueError('基线最后一行字段无效')
    frame=pd.read_csv(io.BytesIO(raw),usecols=['ts','open','high','low','close'],compression='gzip')
    frame['ts']=pd.to_datetime(frame.ts,unit='ms',utc=True,errors='coerce')
    data,state=closed_snapshot(frame,pd.to_datetime(server_ms,unit='ms',utc=True),minimum_bars=205*288)
    if data is None or state['status']=='INVALID' or len(data)!=len(frame):
        raise ValueError('基线行情无效、预热不足或含未收盘数据')
    if valid_ms(last[0])!=int(data.ts.iloc[-1].value//1_000_000):raise ValueError('基线最后时间不一致')
    for value in last[1:5]:valid_decimal(value,positive=True)
    for value in last[5:]:valid_decimal(value)
    return csv_raw,last,(int(data.ts.iloc[0].value//1_000_000),len(data))


def advance(csv_raw,last,klines,server_ms):
    """Validate overlap and append only closed bars, preserving original CSV bytes."""
    if not isinstance(klines,list) or not klines:raise ValueError('K 线响应为空或格式无效')
    expected=valid_ms(last[0]);rows=[]
    for item in klines:
        if not isinstance(item,list) or len(item)<8:raise ValueError('K 线字段不足')
        ts=valid_ms(item[0]);close_ts=valid_ms(item[6])
        if ts!=expected or ts%STEP or close_ts!=ts+STEP-1:raise ValueError('K 线时间缺口、重复或未对齐')
        expected+=STEP
        values=[valid_decimal(x,positive=True) for x in item[1:5]]
        valid_decimal(item[5]);valid_decimal(item[7])
        op,high,low,close=values
        if low>min(op,high,close) or high<max(op,low,close):raise ValueError('K 线 OHLC 无效')
        if close_ts>=server_ms:continue
        rendered=[str(ts),*(str(x) for x in item[1:6]),str(item[7])]
        if not rows:
            if ts!=valid_ms(last[0]) or any(valid_decimal(a,positive=i<4)!=valid_decimal(b,positive=i<4)
                    for i,(a,b) in enumerate(zip(last[1:],rendered[1:]))):
                raise RevisionError('基线最后一根 K 线与公开响应不一致')
        rows.append(rendered)
    if not rows:raise ValueError('未能验证最后一根已收盘 K 线')
    appended=rows[1:]
    return csv_raw+b''.join((','.join(row)+'\n').encode('ascii') for row in appended),len(appended),int(rows[-1][0])


def request(session,out,name,path,params):
    local_start=time.time_ns()//1_000_000
    response=session.get(BASE+path,params=params,timeout=20)
    local_end=time.time_ns()//1_000_000
    raw=response.content
    with (out/(name+'.body.json')).open('xb') as f:f.write(raw)
    metadata={'endpoint':path,'params':params,'http_status':response.status_code,'local_start_ms':local_start,
              'local_end_ms':local_end,'body_sha256':sha(raw)}
    with (out/(name+'.request.json')).open('x') as f:json.dump(metadata,f,indent=2)
    if local_end<local_start:raise ValueError('本机请求时钟倒退')
    response.raise_for_status()
    return json.loads(raw),metadata


def run(source,out,days,*,session=None,archive=None,previous_seq=-1,previous_head='GENESIS',cover_since=None):
    source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    rawdir=out/'raw';rawdir.mkdir();simulated=session is not None;session=session or requests.Session()
    result={'status':'INCOMPLETE','mode':'SYNTHETIC_SESSION_NOT_FORWARD' if simulated else 'PREFLIGHT_NOT_FORWARD','source':'Binance USD-M public REST',
            'no_account_no_orders':True,'source_files':{},'outdir':str(out)}
    try:
        if days<=0:raise ValueError('days 必须为正整数')
        base_raw={s:(source/f'{s}_5m.csv.gz').read_bytes() for s in SYMBOLS}
        result['source_files']={s:sha(raw) for s,raw in base_raw.items()}
        if archive is None:
            if previous_seq!=-1 or previous_head!='GENESIS':raise ValueError('未指定归档却提供了历史头部')
        elif previous_seq==-1:
            if previous_head!='GENESIS' or Path(archive).exists():raise ValueError('新归档路径已存在或初始头部无效')
        else:
            current=archive_status(archive,previous_head)
            if current['last_sequence']!=previous_seq:raise ValueError('指定序号不是归档当前头部')
            commit=json.loads((Path(archive)/'commits'/f'{previous_seq:08d}.json').read_text())
            if any(commit['markets'][s]['target_sha256']!=result['source_files'][s] for s in SYMBOLS):
                raise ValueError('当前基线不匹配归档头部行情')
            result['archive_precheck']=current
        clock,clock_req=request(session,rawdir,'server-time','/fapi/v1/time',{})
        server_ms=valid_ms(clock['serverTime'])
        if not clock_req['local_start_ms']-2000<=server_ms<=clock_req['local_end_ms']+2000:
            raise ValueError('本机与公开服务器时间差超过 2 秒')
        base={s:load_base(raw,server_ms) for s,raw in base_raw.items()}
        if valid_ms(base[SYMBOLS[0]][1][0])!=valid_ms(base[SYMBOLS[1]][1][0]):raise ValueError('两币基线末根时间不一致')
        if base[SYMBOLS[0]][2]!=base[SYMBOLS[1]][2]:raise ValueError('两币基线历史时间网格不一致')
        last_ts=valid_ms(base[SYMBOLS[0]][1][0]);latest_closed=(server_ms//STEP)*STEP-STEP
        if latest_closed<last_ts:raise ValueError('基线晚于服务器最近收盘 K 线')
        if cover_since is not None:
            cover_since=pd.to_datetime(cover_since,utc=True,errors='raise')
            if (pd.isna(cover_since) or cover_since.floor('5min')!=cover_since or
                    cover_since>pd.to_datetime(server_ms,unit='ms',utc=True)):
                raise ValueError('候选覆盖起点无效或晚于服务器时间')
            first=pd.to_datetime(base[SYMBOLS[0]][2][0],unit='ms',utc=True)
            if cover_since-first<pd.Timedelta(days=205):
                raise ValueError('候选覆盖起点之前不足 205 天历史预热')
            latest=pd.to_datetime(latest_closed,unit='ms',utc=True)
            days=max(days,int((latest-cover_since)//pd.Timedelta(days=1))+1)
            result['candidate_cover_since_utc']=cover_since.isoformat()
        result['candidate_days_effective']=days
        if (latest_closed-last_ts)//STEP>=1000*MAX_PAGES:raise ValueError('增量超过单次公开请求上限')
        updates={};last_times={}
        for symbol in SYMBOLS:
            rows=[];cursor=last_ts
            for page in range(MAX_PAGES):
                body,_=request(session,rawdir,f'{symbol}-{page:03d}','/fapi/v1/klines',
                               {'symbol':symbol,'interval':'5m','startTime':cursor,'endTime':server_ms,'limit':1000})
                if not isinstance(body,list) or not body:raise ValueError(f'{symbol} K 线响应为空')
                rows.extend(body);last_returned=valid_ms(body[-1][0])
                if last_returned<cursor:raise ValueError('分页未前进')
                if last_returned>=latest_closed:break
                cursor=last_returned+STEP
            else:raise ValueError('超过单次请求分页上限')
            updated,count,end=advance(*base[symbol][:2],rows,server_ms)
            updates[symbol]=(updated,count);last_times[symbol]=end
        if len(set(last_times.values()))!=1 or next(iter(last_times.values()))!=latest_closed:
            raise ValueError('两币更新未覆盖同一最近收盘时间')
        result.update(server_time_ms=server_ms,last_closed_open_ms=latest_closed,
                      added_bars={s:updates[s][1] for s in SYMBOLS})
        if all(updates[s][1]==0 for s in SYMBOLS):
            result['status']='NO_NEW_CLOSED_BAR';return result
        market=out/'market';market.mkdir()
        for symbol in SYMBOLS:
            with (market/f'{symbol}_5m.csv.gz').open('xb') as f:
                with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:z.write(updates[symbol][0])
        if any(sha((source/f'{s}_5m.csv.gz').read_bytes())!=result['source_files'][s] for s in SYMBOLS):
            raise ValueError('运行期间基线文件发生变化')
        scan_path=out/'scan.json'
        process=subprocess.run([sys.executable,'-m','verify.forward_scan','--json','--days',str(days),
                                '--market-dir',str(market),'--out',str(scan_path)],capture_output=True,text=True)
        (out/'scan.stdout.txt').write_text(process.stdout);(out/'scan.stderr.txt').write_text(process.stderr)
        if process.returncode!=0:raise ValueError('扫描进程失败，保留输出供核查')
        snapshot=json.loads(scan_path.read_bytes())
        if any(snapshot['symbols'][s]['data_status']['status']!='FRESH' for s in SYMBOLS):raise ValueError('扫描行情过期或无效')
        if cover_since is not None:
            windows=[pd.to_datetime(snapshot['symbols'][s]['candidate_window_start'],utc=True,errors='raise') for s in SYMBOLS]
            if any(pd.isna(t) or t>cover_since for t in windows):
                raise ValueError('扫描候选窗口未覆盖指定起点')
        receipt_path=out/'receipt.json';receipt=capture_receipt(scan_path,market,receipt_path)
        captured=pd.to_datetime(receipt['captured_at_utc'],utc=True)
        if (captured-pd.to_datetime(latest_closed+STEP,unit='ms',utc=True)).total_seconds()>360:
            raise ValueError('保存回执距最近收盘超过 6 分钟')
        result.update(scan_sha256=sha(scan_path.read_bytes()),receipt_sha256=receipt['sha256'],
                      captured_at_utc=receipt['captured_at_utc'],candidate_counts={s:snapshot['symbols'][s]['candidate_count'] for s in SYMBOLS},
                      validation_status=snapshot['validation_status'])
        if archive is not None:
            archive=Path(archive)
            if previous_seq==-1:archive_init(archive)
            try:committed=archive_append(archive,scan_path,receipt_path,market,previous_seq,previous_head,
                                         source if previous_seq>=0 else None,source_evidence_dir=rawdir,
                                         initial_source=base_raw if previous_seq==-1 else None)
            except (OSError,KeyError,TypeError,ValueError) as exc:
                try:current=archive_status(archive)
                except (OSError,KeyError,TypeError,ValueError):current={'status':'UNKNOWN'}
                result.update(status='ARCHIVE_RESULT_UNKNOWN',archive_reason=str(exc),archive_status=current)
                return result
            result['archive']=committed
            if committed['status']!='COMMITTED':
                result['status']='ARCHIVE_RESULT_UNKNOWN';return result
        result['status']='PREFLIGHT_SNAPSHOT_SAVED' if archive is not None else 'PREFLIGHT_SNAPSHOT_NOT_ARCHIVED'
        return result
    except RevisionError as exc:
        result.update(status='SOURCE_REVISION',reason=str(exc));return result
    except (OSError,KeyError,TypeError,ValueError,InvalidOperation,OverflowError,requests.RequestException,EOFError,zlib.error) as exc:
        result.update(status='FAILED_READ_ONLY',reason=str(exc));return result
    finally:
        with (out/'result.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True);parser.add_argument('--out',required=True);parser.add_argument('--days',type=int,default=3)
    parser.add_argument('--archive');parser.add_argument('--previous-seq',type=int,default=-1);parser.add_argument('--previous-head',default='GENESIS')
    parser.add_argument('--cover-since',help='UTC 候选覆盖起点；自动扩大扫描天数并要求起点之前至少 205 天历史')
    args=parser.parse_args()
    try:result=run(args.source,args.out,args.days,archive=args.archive,previous_seq=args.previous_seq,previous_head=args.previous_head,cover_since=args.cover_since)
    except (OSError,ValueError) as exc:result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
