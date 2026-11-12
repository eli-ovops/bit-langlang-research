"""Offline sequence check only; not order-book reconstruction or feed proof."""
import argparse
import hashlib
import json
from pathlib import Path

DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口增量序号-离线检查定义-20261030.md'


def audit(trace):
    prefix=0;discarded=0;previous=None;bridged=False
    try:
        if trace.get('schema')!='paper-depth-sequence-v1' or trace.get('symbol')!='ETHUSDT' or not isinstance(trace.get('events'),list):
            raise ValueError('数据格式或标的不符')
        snapshot=trace['snapshot_last_update_id']
        def valid_id(value):return type(value) is int and value>=0
        if not valid_id(snapshot):raise ValueError('快照序号无效')
        for index,event in enumerate(trace['events']):
            if not isinstance(event,dict) or event.get('e')!='depthUpdate' or event.get('s')!='ETHUSDT':raise ValueError(f'第 {index} 条事件类型或标的无效')
            if 'st' in event and (type(event['st']) is not int or event['st']!=1):raise ValueError(f'第 {index} 条合约类型无效')
            first,last,prev=(event.get(k) for k in ('U','u','pu'))
            if not all(valid_id(x) for x in (first,last,prev)) or first>last:raise ValueError(f'第 {index} 条序号无效')
            if not bridged:
                if last<snapshot:discarded+=1;continue
                if first>snapshot:
                    return {'status':'GAP','index':index,'reason':'首条未覆盖快照序号','discarded':discarded,'valid_prefix':prefix}
                bridged=True;previous=last;prefix+=1;continue
            if prev!=previous or last<=previous:
                return {'status':'GAP','index':index,'reason':'pu 不匹配或末序号未递增','discarded':discarded,
                        'valid_prefix':prefix,'expected_pu':previous,'actual_pu':prev,'current_u':last}
            previous=last;prefix+=1
        if not bridged:return {'status':'UNKNOWN_NO_BRIDGE','discarded':discarded,'valid_prefix':0}
        return {'status':'PARTIAL_CHAIN_UNVERIFIED','discarded':discarded,'valid_prefix':prefix,'last_u':previous,
                'book_reconstruction':'NOT_CHECKED','first_last_coverage':'UNKNOWN','source_authenticity':'UNKNOWN'}
    except (AttributeError,KeyError,TypeError,ValueError) as exc:
        return {'status':'INVALID','reason':str(exc),'valid_prefix':prefix,'discarded':discarded}


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',required=True);args=p.parse_args()
    try:
        raw=Path(args.trace).read_bytes()
        def pairs(seq):
            obj={}
            for key,value in seq:
                if key in obj:raise ValueError('重复 JSON 键')
                obj[key]=value
            return obj
        result=audit(json.loads(raw,object_pairs_hook=pairs));result['input_sha256']=hashlib.sha256(raw).hexdigest()
        result['definition_sha256']=hashlib.sha256(DEFINITION.read_bytes()).hexdigest()
    except (OSError,ValueError,TypeError) as exc:result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
