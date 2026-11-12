"""Offline finite-depth reconstruction, not a market or execution guarantee."""
import argparse
import hashlib
import json
from decimal import Decimal,InvalidOperation
from pathlib import Path

from .depth_sequence_audit import audit as audit_sequence

DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口有限深度重建-离线定义-20261030.md'


def decimal(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float)):raise ValueError('价量格式无效')
    try:x=Decimal(str(value))
    except InvalidOperation:raise ValueError('价量格式无效')
    if not x.is_finite():raise ValueError('价量必须有限')
    return x


def levels(rows,*,snapshot=False):
    if not isinstance(rows,list):raise ValueError('价量必须为数组')
    parsed=[];seen=set()
    for row in rows:
        if not isinstance(row,list) or len(row)!=2:raise ValueError('价量条目格式无效')
        price,qty=map(decimal,row)
        if price<=0 or qty<0 or (snapshot and qty==0):raise ValueError('价格或数量无效')
        if snapshot and price in seen:raise ValueError('快照价位重复')
        seen.add(price);parsed.append((price,qty))
    return parsed


def replay(trace):
    sequence=audit_sequence(trace);observed=None;states=[]
    try:
        bids=dict(levels(trace['snapshot_bids'],snapshot=True));asks=dict(levels(trace['snapshot_asks'],snapshot=True))
        if not bids or not asks:raise ValueError('快照两侧必须非空')
        bid_floor=min(bids);ask_ceiling=max(asks)
        threshold=decimal(trace['research_bid_threshold']) if 'research_bid_threshold' in trace else None
        if threshold is not None and threshold<=0:raise ValueError('研究阈值必须为正')
        def save(index):
            nonlocal observed
            bid=max(bids) if bids else None;ask=min(asks) if asks else None
            if bid is not None and ask is not None and bid>=ask:raise ValueError('重建盘口交叉或锁定')
            bid_known=bid is not None and bid>=bid_floor;ask_known=ask is not None and ask<=ask_ceiling
            hit=bool(bid<=threshold) if threshold is not None and bid_known else None
            state={'event_index':index,'bid':str(bid) if bid_known else None,'ask':str(ask) if ask_known else None,
                   'bid_within_snapshot_depth':bid_known,'ask_within_snapshot_depth':ask_known,'threshold_hit':hit}
            states.append(state)
            if hit and observed is None:observed=state
        save(None)
        count=sequence.get('valid_prefix',0);discard=sequence.get('discarded',0)
        for index in range(discard,discard+count):
            event=trace['events'][index]
            for book,key in ((bids,'b'),(asks,'a')):
                for price,qty in levels(event[key]):
                    if qty==0:book.pop(price,None)
                    else:book[price]=qty
            save(index)
        uncertain=any(not state['bid_within_snapshot_depth'] or not state['ask_within_snapshot_depth'] for state in states)
        status=sequence['status'] if sequence['status']!='PARTIAL_CHAIN_UNVERIFIED' else ('PARTIAL_DEPTH_UNCERTAIN' if uncertain else 'PARTIAL_BOOK_UNVERIFIED')
        return {'status':status,'sequence':sequence,'states':states,'first_observed_threshold_hit':observed,
                'continuous_path':'UNKNOWN','trade_binding':'UNKNOWN','source_authenticity':'UNKNOWN',
                'reason':'仅对有限快照和已保存增量的最终状态重建；批内价格、时钟及真实成交未知。'}
    except (AttributeError,KeyError,TypeError,ValueError,IndexError,InvalidOperation) as exc:
        return {'status':'INVALID','reason':str(exc),'sequence':sequence,'states':states,
                'first_observed_threshold_hit':observed,'continuous_path':'UNKNOWN'}


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
        result=replay(json.loads(raw,object_pairs_hook=pairs));result['input_sha256']=hashlib.sha256(raw).hexdigest()
        result['definition_sha256']=hashlib.sha256(DEFINITION.read_bytes()).hexdigest()
    except (OSError,ValueError,TypeError) as exc:result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
