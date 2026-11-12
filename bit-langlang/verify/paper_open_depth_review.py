"""Relate saved depth sessions to provided paper positions; no execution claims."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from .depth_book_replay import replay
from .depth_sessions_audit import audit_session,timestamp
from .paper_risk_audit import audit as audit_risk

DEFINITION=Path(__file__).resolve().parent.parent/'docs/未平仓-盘口会话风险核对-事前定义-20261030.md'


def evaluate(closed,opened,start,as_of,session_paths):
    risk=audit_risk(closed,opened,start,as_of);result={'risk':risk,'continuous_price_path':'UNKNOWN',
        'definition_sha256':hashlib.sha256(DEFINITION.read_bytes()).hexdigest()}
    if risk['status']=='INVALID':return {**result,'status':'INVALID','reason':'账本无效，无法绑定观察'}
    now=timestamp(as_of);sessions=[];errors=[];hits=[];observed_counts={str(x):0 for x in opened.trade_id}
    names=[str(Path(x).resolve()) for x in session_paths]
    if len(set(names))!=len(names):errors.append('会话路径重复')
    previous_end=None;gaps=[]
    for path in session_paths:
        info=audit_session(path);sessions.append(info)
        if info['status']!='PARTIAL_UNVERIFIED':errors.append(str(path)+': 会话无效或未封存');continue
        try:
            root=Path(path);manifest=json.loads((root/'manifest.json').read_bytes())
            if timestamp(manifest['finished_at_utc'])>now:raise ValueError('会话结束晚于检查时刻')
            snapshot_response_completed=timestamp(manifest['rest_completed_at_utc'])
            start_time=timestamp(info['first_received_utc']);end_time=timestamp(info['last_received_utc'])
            if previous_end is not None:
                if start_time<previous_end:errors.append('会话顺序倒置或重叠')
                else:gaps.append({'from_utc':previous_end.isoformat(),'to_utc':start_time.isoformat(),
                                  'coverage':'UNKNOWN_UNOBSERVED'})
            previous_end=end_time
            events=json.loads((root/'events.json').read_bytes());trace=json.loads((root/'derived-trace.json').read_bytes())
            for row in opened.itertuples():
                entry=timestamp(str(row.entry_time));copy=dict(trace);copy['research_bid_threshold']=str(row.stop)
                book=replay(copy)
                if book['status']!='PARTIAL_BOOK_UNVERIFIED':raise ValueError('盘口状态不可用')
                for state in book['states']:
                    index=state['event_index']
                    if index is None:continue
                    received=timestamp(events[index]['received_at_utc'])
                    if entry<received<=now and state['bid_within_snapshot_depth']:
                        observed_counts[str(row.trade_id)]+=1
                        if state['threshold_hit']:
                            not_before=max(received,snapshot_response_completed)
                            hits.append({'trade_id':str(row.trade_id),'session':str(root),'event_index':index,
                                         'received_at_utc':received.isoformat(),'book_state_not_before_utc':not_before.isoformat(),
                                         'event_fsync_returned_at_utc':info['event_fsync_returned_at_utc'][index]
                                             if info.get('event_fsync_returned_at_utc') is not None else 'UNKNOWN',
                                         'durably_persisted_at_utc':'UNKNOWN','bid':state['bid'],'stop':str(row.stop)})
                            break
        except (OSError,KeyError,TypeError,ValueError,IndexError,OverflowError) as exc:errors.append(str(path)+': '+str(exc))
    result.update(sessions=sessions,gaps=gaps,events_examined_until_first_hit_by_trade=observed_counts,
                  observed_threshold_hits=hits,errors=errors,
                  reason='消息接收时间不等于盘口状态或文件保存时间；批内路径、源真实性、真实触发及成交未知。')
    if risk['status']=='STOP' or hits:result['status']='STOP'
    elif errors:result['status']='INVALID'
    elif risk['status']=='STALE':result['status']='STALE'
    elif risk['status']=='AMBIGUOUS_ORDER':result['status']='AMBIGUOUS_ORDER'
    elif opened.empty or not sessions or any(v==0 for v in observed_counts.values()):result['status']='UNKNOWN'
    else:result['status']='PARTIAL_DISCRETE_UNKNOWN_PATH'
    return result


def main():
    p=argparse.ArgumentParser()
    for name in ('closed','open','start','as-of'):p.add_argument('--'+name,required=True)
    p.add_argument('--sessions',nargs='*',default=[]);p.add_argument('--out');a=p.parse_args()
    try:
        if timestamp(a.as_of)>pd.Timestamp.now(tz='UTC'):raise ValueError('检查时间晚于现在')
        c=Path(a.closed).read_bytes();o=Path(a.open).read_bytes()
        frame=lambda x:pd.read_csv(io.BytesIO(x),dtype=str,keep_default_na=False)
        result=evaluate(frame(c),frame(o),a.start,a.as_of,a.sessions)
        result['input_sha256']={'closed':hashlib.sha256(c).hexdigest(),'open':hashlib.sha256(o).hexdigest()}
    except (OSError,KeyError,TypeError,ValueError,IndexError,OverflowError) as exc:result={'status':'INVALID','reason':str(exc)}
    raw=(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    if a.out:
        with open(a.out,'xb') as f:f.write(raw)
    print(raw.decode(),end='')


if __name__=='__main__':main()
