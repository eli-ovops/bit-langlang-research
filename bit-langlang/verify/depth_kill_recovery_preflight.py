"""One deliberately killed public-only test process and one fresh capture."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path

from .depth_event_archive import inspect,write_new
from .depth_sequence_audit import audit as audit_sequence
from .depth_book_replay import replay as replay_book
from .depth_sessions_audit import audit_session

DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口采样进程中断重建-单次预检定义-20261030.md'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()


def recover(root):
    root=Path(root);state=inspect(root/'event-archive');records=state.get('records',[])
    if state['status'] not in ('INVALID','INCOMPLETE_UNSEALED') or not records:
        raise ValueError('没有可校验的未封存记录前缀')
    raw=(root/'snapshot-response.json').read_bytes();snap=json.loads(raw)
    trace={'schema':'paper-depth-sequence-v1','symbol':'ETHUSDT','snapshot_last_update_id':snap['lastUpdateId'],
           'snapshot_bids':snap['bids'],'snapshot_asks':snap['asks'],
           'events':[json.loads(x['wire_text']) for x in records]}
    sequence=audit_sequence(trace);book=replay_book(trace)
    if sequence['status']!='PARTIAL_CHAIN_UNVERIFIED' or book['status']!='PARTIAL_BOOK_UNVERIFIED':
        raise ValueError('中断前缀无法完成序号和盘口形式核对')
    return {'archive_status':state['status'],'prefix_count':len(records),'prefix_head_sha256':state['head_sha256'],
            'snapshot_sha256':sha(raw),'last_received_utc':records[-1]['received_at_utc'],
            'sequence':sequence,'book_status':book['status']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);args=p.parse_args()
    root=Path(args.outdir);root.mkdir(parents=True,exist_ok=False);first=root/'killed';second=root/'fresh'
    report={'schema':'depth-kill-recovery-v1','status':'FIRST_SEGMENT_FAILED_NO_RESTART','started_at_utc':utc(),
            'definition_sha256':sha(DEFINITION.read_bytes()),'real_position':'NONE_CREATED'}
    started=time.monotonic();child=None;killed=False
    with (root/'first-stdout.txt').open('xb') as stdout,(root/'first-stderr.txt').open('xb') as stderr:
        try:
            child=subprocess.Popen([sys.executable,'-m','verify.depth_capture_preflight','--outdir',str(first),'--journal'],stdout=stdout,stderr=stderr)
            deadline=time.monotonic()+7
            while time.monotonic()<deadline:
                if child.poll() is not None:break
                events=first/'event-archive'/'events'
                if (first/'snapshot-response.json').is_file() and events.is_dir() and len(list(events.glob('*.json')))>=20:
                    child.kill();child.wait(timeout=5);killed=True;break
                time.sleep(.05)
            if not killed:
                if child.poll() is None:child.kill();child.wait(timeout=5)
                raise ValueError('第一段未达到安全中断条件；不执行第二段')
            report['kill_observed_at_utc']=utc();report['kill_after_seconds']=round(time.monotonic()-started,3)
            report['first_returncode']=child.returncode;report['first_prefix']=recover(first)
        except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
            report['error']={'type':type(exc).__name__,'message':str(exc)}
    if killed and 'first_prefix' in report:
        try:
            with (root/'second-stdout.txt').open('xb') as stdout,(root/'second-stderr.txt').open('xb') as stderr:
                result=subprocess.run([sys.executable,'-m','verify.depth_capture_preflight','--outdir',str(second),'--journal'],
                                      stdout=stdout,stderr=stderr,timeout=20,check=False)
            if result.returncode!=0:raise ValueError('第二段进程失败；不再尝试')
            new=audit_session(second)
            if new['status']!='PARTIAL_UNVERIFIED':raise ValueError('第二段文件形式核对未通过: '+new['status'])
            left=datetime.fromisoformat(report['first_prefix']['last_received_utc']);right=datetime.fromisoformat(new['first_received_utc'])
            if left.tzinfo is None or right.tzinfo is None or right<left:raise ValueError('会话时间顺序无效')
            report.update(status='RECOVERED_NEW_SESSION_WITH_UNKNOWN_GAP',second=new,
                          gap={'from_utc':left.isoformat(),'to_utc':right.isoformat(),
                               'local_clock_gap_seconds':(right-left).total_seconds(),'coverage':'UNKNOWN_UNOBSERVED'})
        except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
            report.update(status='SECOND_SEGMENT_FAILED_NO_RETRY',error={'type':type(exc).__name__,'message':str(exc)})
    report['finished_at_utc']=utc()
    report['limitations']=['SIGKILL of own process, not machine power loss or network outage.',
        'New session is not an automatic live trading restart.','Gap, clock, source, actual execution and stop path remain UNKNOWN.']
    write_new(root/'summary.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
