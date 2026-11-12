"""One discrete bid-triggered stop reconciled with paper ledger and funding."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from .paper_closed_audit import audit as audit_closed
from .paper_quote import assess_round_trip

DEFINITION=Path(__file__).resolve().parent.parent/'docs/延迟报价-三类出场批量核对-事前定义-20261030.md'


def deadline_status(entry_time,trigger_time,exit_time):
    deadline=pd.to_datetime(entry_time,utc=True)+pd.Timedelta(days=30)
    trigger_time=pd.to_datetime(trigger_time,utc=True);exit_time=pd.to_datetime(exit_time,utc=True)
    if any(pd.isna(x) for x in (deadline,trigger_time,exit_time)) or trigger_time>exit_time:
        return 'INVALID'
    if trigger_time>deadline:
        return 'EXECUTION_MODEL_MISMATCH'
    if trigger_time==deadline or exit_time>=deadline:
        return 'AMBIGUOUS_ORDER'
    return 'BEFORE_DEADLINE'


def check(signal,entry,entry_quote,mark,trigger_quote,exit_event,exit_quote,ledger,funding,start,as_of,*,schedule=None):
    try:
        now=pd.to_datetime(as_of,utc=True,errors='raise')
        if pd.isna(now) or now>pd.Timestamp.now(tz='UTC') or len(ledger)!=1:
            raise ValueError('检查时间或单笔账本无效')
        row=ledger.iloc[0]
        original=assess_round_trip(signal,entry,entry_quote,mark,trigger_quote,exit_event,exit_quote,
                                   float(row['qty']),float(row['funding_cost']),now)
        if original['status']!='PARTIAL_NOT_REGISTERED':
            return {'status':original['status'],'stop_check':original}
        deadline_check=deadline_status(entry['event_time_utc'],mark['event_time_utc'],exit_event['event_time_utc'])
        if deadline_check!='BEFORE_DEADLINE':
            return {'status':deadline_check,'reason':'止损观察或出场决定与 30 天到期存在次序冲突'}
        result=audit_closed(ledger,entry,exit_event,original['entry_bid'],original['entry_ask'],
                            original['exit_bid'],original['exit_ask'],funding,start,now,schedule=schedule)
        if result['status']!='PARTIAL_NOT_REGISTERED':
            return result
        if abs(result['report']['records'][0]['net_R']-original['net_R'])>1e-6:
            raise ValueError('止损计算与统一账本净 R 不一致')
        return {**result,'exit_kind':'bid_stop','stop_check':original,
                'definition_sha256':hashlib.sha256(DEFINITION.read_bytes()).hexdigest()}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError) as exc:
        return {'status':'INVALID','reason':str(exc)}


def main():
    parser=argparse.ArgumentParser()
    for flag in ('signal','entry','entry-quote','mark','trigger-quote','exit','exit-quote','ledger','funding','start','as-of'):
        parser.add_argument('--'+flag,required=True)
    parser.add_argument('--schedule')
    args=parser.parse_args()
    try:
        paths={'signal':args.signal,'entry':args.entry,'entry_quote':args.entry_quote,'mark':args.mark,
               'trigger_quote':args.trigger_quote,'exit':args.exit,'exit_quote':args.exit_quote,
               'ledger':args.ledger,'funding':args.funding}
        raw={key:Path(path).read_bytes() for key,path in paths.items()}
        objects={key:json.loads(raw[key]) for key in ('signal','entry','entry_quote','mark','trigger_quote','exit','exit_quote')}
        ledger=pd.read_csv(io.BytesIO(raw['ledger']),dtype=str,keep_default_na=False)
        funding=pd.read_csv(io.BytesIO(raw['funding']),dtype=str,keep_default_na=False)
        result=check(objects['signal'],objects['entry'],objects['entry_quote'],objects['mark'],objects['trigger_quote'],
                     objects['exit'],objects['exit_quote'],ledger,funding,args.start,args.as_of,schedule=args.schedule)
        result['input_sha256']={key:hashlib.sha256(value).hexdigest() for key,value in raw.items()}
    except (OSError,KeyError,TypeError,ValueError,OverflowError) as exc:
        result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
