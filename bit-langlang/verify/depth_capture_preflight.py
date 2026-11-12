"""One bounded public-data sample; no account, order, scheduler or retry."""
import argparse
import hashlib
import json
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path

import requests
import websocket

from .depth_sequence_audit import audit as audit_sequence
from .depth_book_replay import replay as replay_book
from . import depth_event_archive as archive
from . import depth_event_archive_v2 as archive_v2

WS='wss://fstream.binance.com/public/ws/ethusdt@depth@100ms'
REST='https://fapi.binance.com/fapi/v1/depth'
DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口增量-单次公开预检定义-20261030.md'
JOURNAL_DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口逐条归档-单次在线预检定义-20261030.md'
V2_DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口落盘回执-在线预检定义-20261030.md'


def utc():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,raw):
    with path.open('xb') as f:f.write(raw)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True)
    modes=parser.add_mutually_exclusive_group();modes.add_argument('--journal',action='store_true');modes.add_argument('--journal-v2',action='store_true');args=parser.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    journal=out/'event-archive' if args.journal or args.journal_v2 else None
    writer=None;journal_module=archive_v2 if args.journal_v2 else archive
    if journal is not None:journal_module.init(journal);writer=journal_module.NewSessionWriter(journal)
    started=utc();events=[];snapshot=None;ws=None;error=None;http_status=None;request_start=None;request_end=None
    end_reason='UNKNOWN';response_body=None;snapshot_saved=False;write_ms=[]
    try:
        ws=websocket.create_connection(WS,timeout=4,enable_multithread=True)
        deadline=time.monotonic()+8
        def receive():
            remaining=deadline-time.monotonic()
            if remaining<=0:return False
            ws.settimeout(min(remaining,1))
            try:wire=ws.recv()
            except websocket.WebSocketTimeoutException:return False
            if not isinstance(wire,str):raise ValueError('unexpected non-text WebSocket frame')
            received=utc()
            if journal is not None:
                before=time.monotonic();writer.append(wire,received);write_ms.append((time.monotonic()-before)*1000)
            events.append({'received_at_utc':received,'wire_text':wire})
            return True
        while not events and time.monotonic()<deadline:receive()
        if not events:raise TimeoutError('no WebSocket message within preflight window')
        request_start=utc();remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('preflight window elapsed before REST request')
        response=requests.get(REST,params={'symbol':'ETHUSDT','limit':1000},timeout=min(5,remaining))
        request_end=utc();http_status=response.status_code;response_body=response.content
        if journal is not None:
            archive.write_new(out/'snapshot-response.json',response_body);snapshot_saved=True;archive.sync_dir(out)
        if http_status!=200:raise ValueError(f'public REST HTTP {http_status}')
        snapshot=json.loads(response_body)
        while len(events)<500 and time.monotonic()<deadline:receive()
        end_reason='MESSAGE_LIMIT' if len(events)>=500 else 'TIME_LIMIT'
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)};end_reason='ERROR'
    finally:
        if ws is not None:
            try:ws.close()
            except Exception as exc:
                if error is None:error={'type':type(exc).__name__,'message':str(exc)};end_reason='ERROR'
    events_raw=json.dumps(events,ensure_ascii=False,indent=2).encode();save(out/'events.json',events_raw)
    if response_body is not None and not snapshot_saved and not (out/'snapshot-response.json').exists():save(out/'snapshot-response.json',response_body)
    derived=None;sequence=None;book=None
    if error is None and snapshot is not None:
        try:
            decoded=[json.loads(x['wire_text']) for x in events]
            derived={'schema':'paper-depth-sequence-v1','symbol':'ETHUSDT','snapshot_last_update_id':snapshot['lastUpdateId'],
                     'snapshot_bids':snapshot['bids'],'snapshot_asks':snapshot['asks'],'events':decoded}
            sequence=audit_sequence(derived);book=replay_book(derived)
            derived_raw=json.dumps(derived,ensure_ascii=False,indent=2).encode();save(out/'derived-trace.json',derived_raw)
        except (ValueError,KeyError,TypeError) as exc:error={'type':type(exc).__name__,'message':str(exc)};end_reason='ERROR'
    journal_result=None
    if journal is not None:
        state=journal_module.inspect(journal)
        records=state.get('records',[])
        if args.journal_v2:records=[{'received_at_utc':x['received_at_utc'],'wire_text':x['wire_text']} for x in records]
        matches=records==events
        if error is None and (state['status']!='INCOMPLETE_UNSEALED' or not matches):
            error={'type':'ArchiveMismatch','message':'archive invalid or differs from received messages'};end_reason='ERROR'
        if error is None and matches and sequence and sequence['status']=='PARTIAL_CHAIN_UNVERIFIED' and book and book['status']=='PARTIAL_BOOK_UNVERIFIED':
            try:writer.seal();state=journal_module.inspect(journal)
            except (OSError,ValueError) as exc:error={'type':type(exc).__name__,'message':str(exc)};end_reason='ERROR';state=journal_module.inspect(journal)
        journal_result={'status':state['status'],'message_count':state.get('count'),'valid_prefix':state.get('valid_prefix'),
                        'version':'v2' if args.journal_v2 else 'v1',
                        'head_sha256':state.get('event_head_sha256') if args.journal_v2 else state.get('head_sha256'),
                        'receipt_head_sha256':state.get('receipt_head_sha256') if args.journal_v2 else None,
                        'seal_sha256':state.get('seal_sha256'),'matches_events_file':matches,
                        'append_ms_median':statistics.median(write_ms) if write_ms else None,'append_ms_max':max(write_ms) if write_ms else None,
                        'definition_sha256':sha((V2_DEFINITION if args.journal_v2 else JOURNAL_DEFINITION).read_bytes())}
    manifest={'schema':'public-depth-preflight-v1','verification':'PUBLIC_AND_LOCAL_CLOCK_UNVERIFIED',
              'started_at_utc':started,'finished_at_utc':utc(),'source_websocket':WS,'source_rest':REST,
              'rest_symbol':'ETHUSDT','rest_limit':1000,'rest_started_at_utc':request_start,'rest_completed_at_utc':request_end,
              'rest_http_status':http_status,'end_reason':end_reason,'error':error,'message_count':len(events),
              'events_sha256':sha(events_raw),'snapshot_response_sha256':sha(response_body) if response_body is not None else None,
              'snapshot_file_sha256':sha((out/'snapshot-response.json').read_bytes()) if (out/'snapshot-response.json').exists() else None,
              'derived_trace_sha256':sha(derived_raw) if derived is not None and (out/'derived-trace.json').exists() else None,
              'sequence':sequence,'book_status':book['status'] if book is not None else 'UNKNOWN','journal':journal_result,
              'definition_sha256':sha(DEFINITION.read_bytes()),'real_position':'NONE_CREATED',
              'limitations':['No continuous coverage or trading proof.','Clock and source not independently authenticated.','Messages may batch updates.']}
    save(out/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode())
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
