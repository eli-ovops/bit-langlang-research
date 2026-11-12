"""Immutable local scan archive with exact byte deltas; no network or scheduling."""
import argparse
import base64
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import pandas as pd

from .paper_scan_coverage import CONFIG, audit as coverage_audit

SYMBOLS=('BTCUSDT','ETHUSDT')
BLOCK=4096
MAX_BYTES=256*1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()


def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()


def write_new(path,raw):
    with Path(path).open('xb') as out:
        out.write(raw);out.flush();os.fsync(out.fileno())


def sync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def read_public_source(folder):
    """Read a bounded, paired public REST capture; authenticity remains unknown."""
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir():raise ValueError('公开原始响应目录无效')
    paths=list(folder.iterdir())
    pattern=re.compile(r'(server-time|BTCUSDT-\d{3}|ETHUSDT-\d{3})\.(body|request)\.json')
    if not paths or len(paths)>14 or any(p.is_symlink() or not p.is_file() or not pattern.fullmatch(p.name) for p in paths):
        raise ValueError('公开原始响应文件列表无效')
    files={p.name:p.read_bytes() for p in paths}
    if any(len(raw)>MAX_BYTES for raw in files.values()):raise ValueError('公开原始响应过大')
    roots={name.rsplit('.',2)[0] for name in files}
    if 'server-time' not in roots:raise ValueError('缺少服务器时间响应')
    for symbol in SYMBOLS:
        pages=sorted(x for x in roots if x.startswith(symbol+'-'))
        if pages!=[f'{symbol}-{i:03}' for i in range(len(pages))] or not pages:
            raise ValueError('公开 K 线页码缺失或不连续')
    for root in roots:
        body=files.get(root+'.body.json');request=files.get(root+'.request.json')
        if body is None or request is None:raise ValueError('公开请求与响应未成对')
        metadata=json.loads(request);json.loads(body)
        if not isinstance(metadata,dict):raise ValueError('公开请求记录不是对象')
        endpoint='/fapi/v1/time' if root=='server-time' else '/fapi/v1/klines'
        if (metadata.get('endpoint')!=endpoint or metadata.get('body_sha256')!=sha(body)
                or not isinstance(metadata.get('http_status'),int) or not 200<=metadata['http_status']<300
                or not isinstance(metadata.get('local_start_ms'),int) or not isinstance(metadata.get('local_end_ms'),int)
                or metadata['local_start_ms']>metadata['local_end_ms']
                or not isinstance(metadata.get('params'),dict)
                or (root!='server-time' and metadata['params'].get('symbol')!=root.split('-')[0])):
            raise ValueError('公开请求记录或响应哈希不一致')
    return files


def read_initial_source(folder):
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir():raise ValueError('初始基线目录无效')
    paths=list(folder.iterdir())
    if (set(p.name for p in paths)!={f'{s}_5m.csv.gz' for s in SYMBOLS} or
            any(p.is_symlink() or not p.is_file() or p.stat().st_size>MAX_BYTES for p in paths)):
        raise ValueError('初始基线文件列表或大小无效')
    return {s:(folder/f'{s}_5m.csv.gz').read_bytes() for s in SYMBOLS}


def make_delta(previous,current):
    if len(previous)>MAX_BYTES or len(current)>MAX_BYTES:raise ValueError('快照超出字节上限')
    ops=[];literal=bytearray()
    def flush():
        if literal:
            ops.append(['l',base64.b64encode(literal).decode('ascii')]);literal.clear()
    for offset in range(0,len(current),BLOCK):
        piece=current[offset:offset+BLOCK]
        if previous[offset:offset+len(piece)]==piece:
            flush()
            if ops and ops[-1][0]=='c' and ops[-1][1]+ops[-1][2]==offset:ops[-1][2]+=len(piece)
            else:ops.append(['c',offset,len(piece)])
        else:literal.extend(piece)
    flush()
    return encode({'schema':'paper-byte-delta-v1','target_size':len(current),'target_sha256':sha(current),'ops':ops})


def apply_delta(previous,patch):
    item=json.loads(patch)
    if item.get('schema')!='paper-byte-delta-v1' or not isinstance(item.get('ops'),list):raise ValueError('差量格式无效')
    size=item['target_size']
    if not isinstance(size,int) or isinstance(size,bool) or size<0 or size>MAX_BYTES or len(item['ops'])>100000:
        raise ValueError('差量大小或操作数量无效')
    result=bytearray()
    for op in item['ops']:
        if not isinstance(op,list) or not op:raise ValueError('差量操作无效')
        if op[0]=='c' and len(op)==3:
            offset,length=op[1:]
            if (not isinstance(offset,int) or isinstance(offset,bool) or not isinstance(length,int) or isinstance(length,bool)
                    or offset<0 or length<=0 or offset+length>len(previous)):
                raise ValueError('差量复制范围无效')
            part=previous[offset:offset+length]
        elif op[0]=='l' and len(op)==2 and isinstance(op[1],str):
            part=base64.b64decode(op[1],validate=True)
        else:raise ValueError('差量操作类型无效')
        if len(result)+len(part)>size:raise ValueError('差量输出超过声明长度')
        result.extend(part)
    raw=bytes(result)
    if len(raw)!=size or sha(raw)!=item['target_sha256']:raise ValueError('差量还原哈希或长度不符')
    return raw


def init(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    (root/'runs').mkdir();(root/'commits').mkdir()
    metadata={'schema':'paper-scan-archive-v1','archive_id':uuid.uuid4().hex,
              'config_sha256':sha(CONFIG.read_bytes())}
    write_new(root/'archive.json',encode(metadata))
    return {'status':'ARCHIVE_CREATED','archive_id':metadata['archive_id'],'previous_seq':-1,'previous_head':'GENESIS'}


def archive_meta(root):
    raw=(Path(root)/'archive.json').read_bytes();data=json.loads(raw)
    if (data.get('schema')!='paper-scan-archive-v1' or not re.fullmatch('[0-9a-f]{32}',str(data.get('archive_id','')))
            or data.get('config_sha256')!=sha(CONFIG.read_bytes())):raise ValueError('归档标识或冻结配置无效')
    return data,sha(raw)


def append(root,scan_path,receipt_path,market_dir,previous_seq,previous_head,previous_market_dir=None,source_evidence_dir=None,initial_source=None):
    root=Path(root);meta,archive_hash=archive_meta(root)
    if not isinstance(previous_seq,int) or previous_seq < -1:raise ValueError('前一序号无效')
    sequence=previous_seq+1;target=root/'commits'/f'{sequence:08d}.json'
    if target.exists():raise FileExistsError('目标序号已有提交，拒绝覆盖')
    before=None;previous_market={}
    if previous_seq==-1:
        if previous_head!='GENESIS' or previous_market_dir is not None:raise ValueError('初始头部或前一行情参数无效')
    else:
        if initial_source is not None:raise ValueError('初始基线只能在首条提交中保存')
        old_raw=(root/'commits'/f'{previous_seq:08d}.json').read_bytes();before=json.loads(old_raw)
        if sha(old_raw)!=previous_head or before['sequence']!=previous_seq or before['archive_sha256']!=archive_hash:
            raise ValueError('前一提交哈希或归档不符')
        if previous_market_dir is None:raise ValueError('追加时必须提供前一行情目录')
        for symbol in SYMBOLS:
            raw=(Path(previous_market_dir)/f'{symbol}_5m.csv.gz').read_bytes()
            if sha(raw)!=before['markets'][symbol]['target_sha256']:raise ValueError('前一行情哈希不符')
            previous_market[symbol]=raw
    scan_raw=Path(scan_path).read_bytes();receipt_raw=Path(receipt_path).read_bytes()
    scan=json.loads(scan_raw);receipt=json.loads(receipt_raw)
    generated=pd.to_datetime(scan['generated_at'],utc=True,errors='raise');captured=pd.to_datetime(receipt['captured_at_utc'],utc=True,errors='raise')
    if (pd.isna(generated) or pd.isna(captured) or captured<generated or captured>pd.Timestamp.now(tz='UTC')
            or scan['config_sha256']!=meta['config_sha256'] or receipt.get('config_sha256')!=meta['config_sha256']
            or receipt.get('schema')!='paper-scan-receipt-v1' or receipt.get('verification')!='LOCAL_CLOCK_UNVERIFIED'
            or receipt.get('scan_sha256')!=sha(scan_raw)):
        raise ValueError('扫描与本机回执不一致')
    if before is not None and (generated<=pd.to_datetime(before['generated_at'],utc=True) or captured<=pd.to_datetime(before['captured_at_utc'],utc=True)):
        raise ValueError('扫描或回执时间未递增')
    current={}
    for symbol in SYMBOLS:
        raw=(Path(market_dir)/f'{symbol}_5m.csv.gz').read_bytes()
        if len(raw)>MAX_BYTES or sha(raw)!=scan['symbols'][symbol]['data_sha256'] or sha(raw)!=receipt['market_sha256'][symbol]:
            raise ValueError('原始行情与扫描/回执哈希不匹配')
        current[symbol]=raw
    if initial_source is not None and (not isinstance(initial_source,dict) or set(initial_source)!=set(SYMBOLS)
            or any(not isinstance(raw,bytes) or len(raw)>MAX_BYTES for raw in initial_source.values())):
        raise ValueError('初始行情基线无效')
    source_files=read_public_source(source_evidence_dir) if source_evidence_dir is not None else None
    run_id=uuid.uuid4().hex;run=root/'runs'/run_id;run.mkdir()
    write_new(run/'scan.json',scan_raw);write_new(run/'receipt.json',receipt_raw)
    if source_files is not None:
        source_dir=run/'public-source';source_dir.mkdir()
        for name,raw in sorted(source_files.items()):write_new(source_dir/name,raw)
        sync_dir(source_dir)
    if initial_source is not None:
        initial_dir=run/'initial-source';initial_dir.mkdir()
        for symbol,raw in sorted(initial_source.items()):write_new(initial_dir/f'{symbol}_5m.csv.gz',raw)
        sync_dir(initial_dir)
    markets={}
    for symbol in SYMBOLS:
        raw=current[symbol];patch=make_delta(previous_market[symbol],raw) if before is not None else b''
        kind='delta' if before is not None and len(patch)<len(raw) else 'full'
        payload=patch if kind=='delta' else raw
        write_new(run/(symbol+'.'+kind),payload)
        markets[symbol]={'kind':kind,'payload_sha256':sha(payload),'payload_size':len(payload),
                         'target_sha256':sha(raw),'target_size':len(raw)}
    commit={'schema':'paper-scan-commit-v1','sequence':sequence,'previous_sha256':previous_head,'archive_sha256':archive_hash,
            'run_id':run_id,'generated_at':generated.isoformat(),'captured_at_utc':captured.isoformat(),
            'scan_sha256':sha(scan_raw),'receipt_sha256':sha(receipt_raw),'markets':markets}
    if source_files is not None:
        commit['public_source_sha256']={name:sha(raw) for name,raw in sorted(source_files.items())}
    if initial_source is not None:
        commit['initial_source_sha256']={symbol:sha(raw) for symbol,raw in sorted(initial_source.items())}
    commit_raw=encode(commit);write_new(run/'commit.json',commit_raw)
    sync_dir(run);sync_dir(root/'runs')
    os.link(run/'commit.json',target)  # Atomic exclusive publication, no replace.
    try:
        sync_dir(root/'commits')
        status='COMMITTED'
    except OSError:
        status='COMMIT_PUBLISHED_DURABILITY_UNKNOWN'
    return {'status':status,'sequence':sequence,'head_sha256':sha(commit_raw),'run_id':run_id,
            'market_raw_bytes':sum(len(x) for x in current.values()),
            'stored_market_bytes':sum(x['payload_size'] for x in markets.values()),
            'public_source_status':'BOUND_UNVERIFIED' if source_files is not None else 'UNKNOWN_NOT_CAPTURED',
            'initial_source_status':'BOUND_UNVERIFIED' if initial_source is not None else 'UNKNOWN_NOT_CAPTURED',
            'prior_chain_verification':'NOT_RECHECKED' if before is not None else 'GENESIS'}


def records(root,expected_head=None):
    root=Path(root);metadata,archive_hash=archive_meta(root)
    paths=sorted((root/'commits').glob('*.json'))
    if [p.name for p in paths]!=[f'{i:08d}.json' for i in range(len(paths))]:raise ValueError('提交序号缺失或不连续')
    if not paths:raise ValueError('归档没有已提交快照')
    items=[];prior='GENESIS';run_ids=set();previous_gen=previous_cap=None
    for i,path in enumerate(paths):
        raw=path.read_bytes();commit=json.loads(raw);run_id=commit['run_id']
        if (commit.get('schema')!='paper-scan-commit-v1' or commit['sequence']!=i or commit['previous_sha256']!=prior
                or commit['archive_sha256']!=archive_hash or not re.fullmatch('[0-9a-f]{32}',str(run_id)) or run_id in run_ids):
            raise ValueError('提交链、序号或运行标识无效')
        run_ids.add(run_id);run=root/'runs'/run_id
        scan_raw=(run/'scan.json').read_bytes();receipt_raw=(run/'receipt.json').read_bytes()
        if sha(scan_raw)!=commit['scan_sha256'] or sha(receipt_raw)!=commit['receipt_sha256']:
            raise ValueError('扫描或回执文件哈希不符')
        scan=json.loads(scan_raw);receipt=json.loads(receipt_raw)
        if (scan.get('config_sha256')!=metadata['config_sha256'] or receipt.get('config_sha256')!=metadata['config_sha256']
                or receipt.get('schema')!='paper-scan-receipt-v1' or receipt.get('verification')!='LOCAL_CLOCK_UNVERIFIED'
                or receipt.get('scan_sha256')!=sha(scan_raw)):
            raise ValueError('原始扫描与回执不一致')
        source_hashes=commit.get('public_source_sha256')
        if source_hashes is not None:
            if not isinstance(source_hashes,dict):raise ValueError('公开响应哈希清单无效')
            source_files=read_public_source(run/'public-source')
            if {name:sha(value) for name,value in source_files.items()}!=source_hashes:
                raise ValueError('归档公开响应与提交哈希不一致')
        initial_hashes=commit.get('initial_source_sha256')
        if initial_hashes is not None:
            if i!=0 or not isinstance(initial_hashes,dict):raise ValueError('初始行情基线只允许首条提交')
            initial=read_initial_source(run/'initial-source')
            if {symbol:sha(raw) for symbol,raw in initial.items()}!=initial_hashes:
                raise ValueError('初始行情基线与提交哈希不一致')
        for symbol in SYMBOLS:
            info=commit['markets'][symbol]
            if (not re.fullmatch('[0-9a-f]{64}',str(info.get('target_sha256','')))
                    or scan['symbols'][symbol]['data_sha256']!=info['target_sha256']
                    or receipt['market_sha256'][symbol]!=info['target_sha256']):
                raise ValueError('原始行情、扫描与回执哈希不一致')
        gen=pd.to_datetime(commit['generated_at'],utc=True,errors='raise');cap=pd.to_datetime(commit['captured_at_utc'],utc=True,errors='raise')
        if (pd.isna(gen) or pd.isna(cap) or gen!=pd.to_datetime(scan['generated_at'],utc=True)
                or cap!=pd.to_datetime(receipt['captured_at_utc'],utc=True) or cap<gen or cap>pd.Timestamp.now(tz='UTC')
                or (previous_gen is not None and (gen<=previous_gen or cap<=previous_cap))):
            raise ValueError('提交时间与原始文件不一致')
        previous_gen,previous_cap=gen,cap
        items.append({'commit':commit,'run':run,'snapshot':scan,'scan_sha256':sha(scan_raw),
                      'public_source_status':'BOUND_UNVERIFIED' if source_hashes is not None else 'UNKNOWN_NOT_CAPTURED',
                      'initial_source_status':'BOUND_UNVERIFIED' if initial_hashes is not None else 'UNKNOWN_NOT_CAPTURED',
                      'receipt':receipt,'receipt_sha256':sha(receipt_raw),'scan_raw':scan_raw,'receipt_raw':receipt_raw})
        prior=sha(raw)
    if expected_head is not None and expected_head!=prior:raise ValueError('预期头部不匹配，可能截断或修改')
    orphan=[p.name for p in (root/'runs').iterdir() if p.is_dir() and p.name not in run_ids]
    return items,prior,orphan


def market_loaders(items):
    state={'sequence':-1,'markets':{}}
    def load(index):
        if index!=state['sequence']+1:raise ValueError('行情只能按提交顺序恢复')
        item=items[index];result={}
        for symbol in SYMBOLS:
            info=item['commit']['markets'][symbol];kind=info['kind']
            if kind not in ('full','delta') or (index==0 and kind!='full'):raise ValueError('行情存储类型无效')
            payload=(item['run']/(symbol+'.'+kind)).read_bytes()
            if len(payload)!=info['payload_size'] or sha(payload)!=info['payload_sha256']:raise ValueError('行情差量文件哈希不符')
            raw=payload if kind=='full' else apply_delta(state['markets'][symbol],payload)
            if len(raw)>MAX_BYTES or len(raw)!=info['target_size'] or sha(raw)!=info['target_sha256']:
                raise ValueError('恢复行情文件与原始文件不一致')
            result[symbol]=raw
        state['markets']=result;state['sequence']=index
        return result
    return state,load


def status(root,expected_head=None):
    root=Path(root);archive_meta(root)
    commits=root/'commits'
    if not commits.is_dir() or not (root/'runs').is_dir():raise ValueError('归档目录不完整')
    if not list(commits.glob('*.json')):
        if expected_head not in (None,'GENESIS'):raise ValueError('预期头部不匹配，可能截断或修改')
        orphan=[p.name for p in (root/'runs').iterdir() if p.is_dir()]
        return {'status':'EMPTY_METADATA_ONLY','committed_records':0,'last_sequence':-1,'head_sha256':'GENESIS',
                'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' if expected_head else 'NO_EXTERNAL_ANCHOR',
                'orphan_run_ids':sorted(orphan),'market_payloads':'NOT_RECONSTRUCTED_OR_CHECKED'}
    items,head,orphan=records(root,expected_head)
    return {'status':'METADATA_ONLY_UNVERIFIED','committed_records':len(items),'last_sequence':len(items)-1,
            'head_sha256':head,'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' if expected_head else 'NO_EXTERNAL_ANCHOR',
            'orphan_run_ids':sorted(orphan),'market_payloads':'NOT_RECONSTRUCTED_OR_CHECKED',
            'public_source_bound_records':sum(x['public_source_status']=='BOUND_UNVERIFIED' for x in items),
            'public_source_missing_records':sum(x['public_source_status']=='UNKNOWN_NOT_CAPTURED' for x in items),
            'initial_source_status':items[0]['initial_source_status']}


def verify_coverage(root,events,start,as_of,expected_head=None):
    items,head,orphan=records(root,expected_head);state,load=market_loaders(items)
    scans=[{'snapshot':item['snapshot'],'scan_sha256':item['scan_sha256'],'receipt':item['receipt'],
            'receipt_sha256':item['receipt_sha256'],'_load_market':(lambda i=i:load(i))} for i,item in enumerate(items)]
    result=coverage_audit(scans,events,start,as_of)
    result['archive']={'head_sha256':head,'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' if expected_head else 'NO_EXTERNAL_ANCHOR',
                       'committed_records':len(items),'fully_reconstructed_records':state['sequence']+1,
                       'public_source_bound_records':sum(x['public_source_status']=='BOUND_UNVERIFIED' for x in items),
                       'public_source_missing_records':sum(x['public_source_status']=='UNKNOWN_NOT_CAPTURED' for x in items),
                       'initial_source_status':items[0]['initial_source_status'],
                       'orphan_run_ids':sorted(orphan)}
    return result


def restore(root,sequence,out,expected_head=None):
    items,head,orphan=records(root,expected_head)
    if not isinstance(sequence,int) or sequence<0 or sequence>=len(items):raise ValueError('恢复序号超出范围')
    _,load=market_loaders(items)
    for index in range(sequence+1):markets=load(index)
    source_files=None;initial_source=None
    if items[sequence]['public_source_status']=='BOUND_UNVERIFIED':
        source_files=read_public_source(items[sequence]['run']/'public-source')
        if {name:sha(raw) for name,raw in source_files.items()}!=items[sequence]['commit']['public_source_sha256']:
            raise ValueError('恢复期间公开响应与提交哈希不一致')
    if items[sequence]['initial_source_status']=='BOUND_UNVERIFIED':
        initial_source=read_initial_source(items[sequence]['run']/'initial-source')
        if {symbol:sha(raw) for symbol,raw in initial_source.items()}!=items[sequence]['commit']['initial_source_sha256']:
            raise ValueError('恢复期间初始基线与提交哈希不一致')
    output=Path(out);output.mkdir(parents=True,exist_ok=False)
    for symbol,raw in markets.items():write_new(output/f'{symbol}_5m.csv.gz',raw)
    write_new(output/'scan.json',items[sequence]['scan_raw']);write_new(output/'receipt.json',items[sequence]['receipt_raw'])
    if source_files is not None:
        restored_source=output/'public-source';restored_source.mkdir()
        for name,raw in sorted(source_files.items()):write_new(restored_source/name,raw)
    if initial_source is not None:
        restored_initial=output/'initial-source';restored_initial.mkdir()
        for symbol,raw in sorted(initial_source.items()):write_new(restored_initial/f'{symbol}_5m.csv.gz',raw)
    return {'status':'RESTORED_BYTES_VERIFIED','sequence':sequence,'head_sha256':head,
            'public_source_status':items[sequence]['public_source_status'],
            'initial_source_status':items[sequence]['initial_source_status'],
            'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' if expected_head else 'NO_EXTERNAL_ANCHOR',
            'market_sha256':{s:sha(raw) for s,raw in markets.items()},'orphan_run_ids':sorted(orphan)}


def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    create=sub.add_parser('init');create.add_argument('--archive',required=True)
    inspect=sub.add_parser('status');inspect.add_argument('--archive',required=True);inspect.add_argument('--expected-head')
    add=sub.add_parser('append')
    for flag in ('archive','scan','receipt','market-dir','previous-seq','previous-head'):add.add_argument('--'+flag,required=True)
    add.add_argument('--previous-market-dir')
    add.add_argument('--source-evidence-dir',help='公开请求与原始响应目录，缺省时标记未知')
    check=sub.add_parser('audit')
    for flag in ('archive','events','start','as-of'):check.add_argument('--'+flag,required=True)
    check.add_argument('--expected-head')
    recover=sub.add_parser('restore')
    for flag in ('archive','sequence','out'):recover.add_argument('--'+flag,required=True)
    recover.add_argument('--expected-head')
    args=parser.parse_args()
    try:
        if args.command=='init':result=init(args.archive)
        elif args.command=='status':result=status(args.archive,args.expected_head)
        elif args.command=='append':result=append(args.archive,args.scan,args.receipt,args.market_dir,int(args.previous_seq),args.previous_head,args.previous_market_dir,args.source_evidence_dir)
        elif args.command=='restore':result=restore(args.archive,int(args.sequence),args.out,args.expected_head)
        else:
            directory=Path(args.events)
            if not directory.is_dir():raise ValueError('事件目录不存在')
            paths=sorted(directory.glob('*.json'));raw_events=[p.read_bytes() for p in paths]
            result=verify_coverage(args.archive,[json.loads(raw) for raw in raw_events],args.start,args.as_of,args.expected_head)
            result['event_sha256']={p.name:sha(raw) for p,raw in zip(paths,raw_events)}
    except (OSError,KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
