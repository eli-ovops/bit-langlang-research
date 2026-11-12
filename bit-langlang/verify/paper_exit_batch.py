"""Combine three paper exit types, signal evidence and portfolio checks; never PASS."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path

import pandas as pd

from .forward_report import report
from .funding_reconcile import reconcile as reconcile_funding
from .paper_delayed_signal_reconcile import reconcile as reconcile_entries
from .paper_equity import evaluate as evaluate_equity
from .paper_risk_audit import audit as audit_risk
from .paper_position_quotes import audit as audit_position
from .paper_open_path_risk import evaluate as evaluate_open_paths
from .paper_open_depth_review import evaluate as evaluate_open_depth
from .paper_stop_exit import check as check_stop
from .paper_timed_exit import check as check_timed

DEFINITION=Path(__file__).resolve().parent.parent/'docs/延迟报价-三类出场批量核对-事前定义-20261030.md'
POSITION_DEFINITION=Path(__file__).resolve().parent.parent/'docs/批量出场-持仓观察交叉核对-事前定义-20261030.md'
DEPTH_DEFINITION=Path(__file__).resolve().parent.parent/'docs/批量对账-盘口会话未平仓联检定义-20261030.md'


def position_paths(closed,quote_records,bundles,evidence,as_of):
    """Cross-check actual raw files; missing path evidence never implies no stop."""
    if evidence is None:
        return {'status':'UNKNOWN_NOT_PROVIDED','scope':'CLOSED_ONLY','trades':{}}
    if not isinstance(evidence,dict) or not set(evidence).issubset(set(closed.trade_id.astype(str))):
        raise ValueError('持仓观察证据编号无效')
    checks={}
    for trade_id in closed.trade_id.astype(str):
        if trade_id not in evidence:
            checks[trade_id]={'status':'UNKNOWN_NOT_PROVIDED'}
            continue
        try:
            ev=evidence[trade_id]
            if isinstance(ev,dict) and 'load_error' in ev:raise ValueError('持仓证据加载失败: '+ev['load_error'])
            raw=ev['entry_quote_raw'];record=quote_records[trade_id];bundle=bundles[trade_id]
            if (hashlib.sha256(raw).hexdigest()!=record['sha256'] or json.loads(raw)!=record['quote']):
                raise ValueError('持仓观察入场报价与批量入场报价不一致: '+trade_id)
            kwargs={'exit_event':bundle['exit']}
            if bundle['kind']=='bid_stop':
                trigger=ev['trigger_quote_raw']
                if json.loads(trigger)!=bundle['trigger_quote']:
                    raise ValueError('止损触发原始报价与批量证据不一致: '+trade_id)
                kwargs.update(mark=bundle['mark'],trigger_quote_raw=trigger)
            checks[trade_id]=audit_position(bundle['signal'],bundle['entry'],raw,ev['entry_receipt_raw'],
                                 closed.loc[closed.trade_id.astype(str)==trade_id],ev['samples'],as_of,**kwargs)
        except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError) as exc:
            checks[trade_id]={'status':'INVALID','reason':str(exc)}
    invalid=any(value['status']=='INVALID' for value in checks.values())
    mismatch=any(value['status']=='MISSED_OBSERVED_STOP' or
                 (bundles[key]['kind'] in ('ema20','max_30d') and value.get('first_observed_stop_hit') is not None)
                 for key,value in checks.items())
    status=('EXECUTION_MODEL_MISMATCH' if mismatch else 'INVALID' if invalid else
            'PARTIAL_DISCRETE_UNVERIFIED' if all(value['status']=='PARTIAL_DISCRETE_UNVERIFIED' for value in checks.values())
            else 'UNKNOWN_INCOMPLETE')
    return {'status':status,'scope':'CLOSED_ONLY','trades':checks,'continuous_price_path':'UNKNOWN'}


def reconcile(snapshot,events,market_dir,closed,opened,funding,quote_records,bundles,start,as_of,*,schedule=None,position_evidence=None,open_position_evidence=None,depth_session_paths=None):
    """Caller provides already loaded raw evidence; all results remain unverified."""
    try:
        if not isinstance(bundles,dict) or not isinstance(events,list):
            raise ValueError('交易证据或事件集合格式无效')
        begin=pd.to_datetime(start,utc=True,errors='raise')
        now=pd.to_datetime(as_of,utc=True,errors='raise')
        if pd.isna(begin) or pd.isna(now) or begin>now or now>pd.Timestamp.now(tz='UTC'):
            raise ValueError('观察起点或检查时间无效')
        entry_result=reconcile_entries(snapshot,events,market_dir,closed,opened,quote_records,start,as_of)
        base={'entry_check':entry_result,'definition_sha256':hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
              'observation_interval':{'start_utc':begin.isoformat(),'as_of_utc':now.isoformat()},
              'position_definition_sha256':hashlib.sha256(POSITION_DEFINITION.read_bytes()).hexdigest(),
              'depth_definition_sha256':hashlib.sha256(DEPTH_DEFINITION.read_bytes()).hexdigest()}
        if entry_result['status']!='PARTIAL_CANDIDATE_NOT_REGISTERED':
            return {**base,'status':entry_result['status']}
        ids=closed.trade_id.astype(str)
        if ids.duplicated().any() or set(ids)!=set(bundles):
            return {**base,'status':'INVALID','reason':'已平仓账本与出场证据编号不一一对应'}
        risk=audit_risk(closed,opened,start,as_of);base['risk_check']=risk
        if opened.empty and open_position_evidence:
            return {**base,'status':'INVALID','reason':'无未平仓记录却提供未平仓观察证据'}
        if opened.empty and depth_session_paths:
            return {**base,'status':'INVALID','reason':'无未平仓记录却提供盘口会话证据'}
        if not opened.empty:
            open_evidence=None
            if open_position_evidence is not None:
                if not isinstance(open_position_evidence,dict):raise ValueError('未平仓观察证据格式无效')
                open_evidence={}
                for key,ev in open_position_evidence.items():
                    try:
                        if 'load_error' in ev:raise ValueError(ev['load_error'])
                        if ev['signal'] not in events or ev['entry'] not in events:raise ValueError('未平仓信号或入场不在共同事件中')
                        raw=ev['entry_quote_raw'];record=quote_records[key]
                        if hashlib.sha256(raw).hexdigest()!=record['sha256'] or json.loads(raw)!=record['quote']:
                            raise ValueError('未平仓观察与入场报价不一致')
                        open_evidence[key]=ev
                    except (KeyError,TypeError,ValueError,IndexError,OverflowError) as exc:
                        open_evidence[key]={'load_error':str(exc)}
            open_paths=evaluate_open_paths(closed,opened,start,as_of,open_evidence);base['open_position_path_check']=open_paths
            depth_paths=None
            if depth_session_paths is not None:
                if not isinstance(depth_session_paths,list):raise ValueError('盘口会话清单格式无效')
                depth_paths=evaluate_open_depth(closed,opened,start,str(as_of),depth_session_paths)
                base['open_depth_session_check']=depth_paths
            else:base['open_depth_session_check']={'status':'UNKNOWN_NOT_PROVIDED'}
            checks=[open_paths['status']]+([depth_paths['status']] if depth_paths is not None else [])
            if 'STOP' in checks:return {**base,'status':'STOP'}
            if 'INVALID' in checks:return {**base,'status':'INVALID'}
        equity=evaluate_equity(closed,opened,start,as_of);base['equity_check']=equity
        if equity['status'] in ('STOP','INVALID','STALE','AMBIGUOUS_ORDER'):
            return {**base,'status':equity['status']}
        if schedule is None:
            funding_result=reconcile_funding(closed,opened,funding,start,as_of)
            base['funding_check']=funding_result
            return {**base,'status':funding_result['status'] if funding_result['status'] in ('INVALID','STOP') else 'UNKNOWN_FUNDING'}
        funding_result=reconcile_funding(closed,opened,funding,start,as_of,schedule=schedule)
        base['funding_check']=funding_result
        if funding_result['status']!='PARTIAL':
            return {**base,'status':'UNKNOWN_FUNDING' if funding_result['status']=='UNKNOWN' else funding_result['status']}
        if closed.empty:
            return {**base,'status':'NO_CLOSED_TRADE_EVIDENCE','reason':'没有已平仓交易，不能评估净 R 或出场'}
        checks={};observations={}
        for key, record in quote_records.items():
            quote=record['quote']
            fp=tuple((int(r['local_start_ms']),int(r['local_end_ms'])) for r in quote['requests'])
            if fp in observations and observations[fp]!=key:
                raise ValueError('不同交易复用一次报价观测')
            observations[fp]=key
        for trade_id in ids:
            bundle=bundles[trade_id];kind=bundle['kind'];entry=bundle['entry'];signal=bundle['signal'];exit_event=bundle['exit']
            if any(event not in events for event in (signal,entry,exit_event)):
                raise ValueError('交易事件未包含在共同事件目录: '+trade_id)
            if str(entry.get('trade_id'))!=trade_id or str(exit_event.get('trade_id'))!=trade_id:
                raise ValueError('出场证据交易编号不匹配: '+trade_id)
            entry_quote=quote_records[trade_id]['quote'];exit_quote=bundle['exit_quote']
            relevant=[exit_quote]
            if kind=='bid_stop':
                if bundle['mark'] not in events:
                    raise ValueError('止损观察不在共同事件目录: '+trade_id)
                relevant.append(bundle['trigger_quote'])
            for quote in relevant:
                fp=tuple((int(r['local_start_ms']),int(r['local_end_ms'])) for r in quote['requests'])
                if fp in observations and observations[fp]!=trade_id:
                    raise ValueError('不同交易复用一次报价观测')
                observations[fp]=trade_id
            row=closed.loc[closed.trade_id.astype(str)==trade_id].copy()
            subset=funding.loc[funding.trade_id.astype(str)==trade_id].copy()
            if kind=='bid_stop':
                result=check_stop(signal,entry,entry_quote,bundle['mark'],bundle['trigger_quote'],exit_event,exit_quote,
                                  row,subset,start,as_of,schedule=schedule)
            elif kind in ('ema20','max_30d'):
                if bundle['observation'].get('kind')!=kind:
                    raise ValueError('出场观察类型与索引不符: '+trade_id)
                result=check_timed(signal,entry,bundle['entry_raw'],entry_quote,bundle['observation'],exit_event,exit_quote,
                                   row,subset,start,as_of,schedule=schedule,scan_raw=bundle.get('scan_raw'),market_raw=bundle.get('market_raw'))
            else:
                raise ValueError('未知出场类型: '+trade_id)
            checks[trade_id]=result
        base['trade_checks']=checks
        position_check=position_paths(closed,quote_records,bundles,position_evidence,as_of)
        base['position_path_check']=position_check
        if opened.empty:base['open_position_path_check']='NO_OPEN_RECORDS_SUPPLIED'
        if position_check['status'] in ('INVALID','EXECUTION_MODEL_MISMATCH'):
            return {**base,'status':position_check['status'],'reason':'持仓离散观察与出场证据不一致或无效'}
        bad=[(key,value['status']) for key,value in checks.items() if value['status']!='PARTIAL_NOT_REGISTERED']
        if bad:
            priority=('STOP','INVALID','EXECUTION_MODEL_MISMATCH','AMBIGUOUS_ORDER','AMBIGUOUS','STALE',
                      'UNKNOWN_DEPTH','UNKNOWN_MARGIN','UNKNOWN_FUNDING')
            status=next((item for item in priority if any(x[1]==item for x in bad)),'UNKNOWN')
            return {**base,'status':status,'incomplete_trades':[{'trade_id':key,'status':status_} for key,status_ in bad]}
        gross_positive=cost_total=net_total=sum_r=0.0
        for row in closed.itertuples(index=False):
            key=str(row.trade_id);q1=quote_records[key]['quote']['requests'][1]['body'];q2=bundles[key]['exit_quote']['requests'][1]['body']
            qty=float(row.qty);e=float(row.entry);x=float(row.exit);fee=float(row.fee_cost);fund=float(row.funding_cost)
            entry_mid=(float(q1['bidPrice'])+float(q1['askPrice']))/2
            exit_mid=(float(q2['bidPrice'])+float(q2['askPrice']))/2
            gross=qty*(exit_mid-entry_mid);net=qty*(x-e)-fee-fund
            gross_positive+=max(gross,0);cost_total+=gross-net;net_total+=net
            sum_r+=net/((e-float(row.stop))*qty)
        ledger_result=report(closed,start,as_of)
        if (not math.isclose(net_total,ledger_result['net_pnl_usdt'],rel_tol=0,abs_tol=1e-6)
                or not math.isclose(sum_r/len(closed),ledger_result['avg_net_R'],rel_tol=0,abs_tol=1e-6)):
            raise ValueError('批量净盈亏或等权净 R 与全账本报告不一致')
        totals={'closed_trades':len(closed),'open_positions':len(opened),'net_pnl_usdt':round(net_total,6),
                'mean_net_R':round(sum_r/len(closed),6),'total_cost_vs_mid_usdt':round(cost_total,6),
                'sum_positive_mid_reference_gross_usdt':round(gross_positive,6),
                'cost_over_positive_mid_gross_pct':round(cost_total/gross_positive*100,4) if gross_positive>0 else None}
        gaps=[]
        if position_check['status']!='PARTIAL_DISCRETE_UNVERIFIED':
            gaps.append('CLOSED_POSITION_PATH')
        if not opened.empty and base['open_position_path_check']['status']!='REVIEW':
            gaps.append('OPEN_POSITION_PATH')
        status=('UNKNOWN_POSITION_PATH' if 'CLOSED_POSITION_PATH' in gaps else
                'PARTIAL_WITH_OPEN_UNKNOWN' if not opened.empty else 'PARTIAL_NOT_REGISTERED')
        return {**base,'status':status,'totals':totals,'evidence_gaps':gaps,
                'signal_scan_coverage':'UNKNOWN_NOT_CHECKED',
                'reason':'仅核对提供的离散资料；缺少已平仓持仓路径时顶层为 UNKNOWN_POSITION_PATH。持续扫描、离散样本间价格、来源真实性、真实成交及账户状态均未获证。'}
    except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError) as exc:
        return {'status':'INVALID','reason':str(exc)}


def main():
    parser=argparse.ArgumentParser()
    for flag in ('scan','events','market-dir','closed','open','funding','manifest','start','as-of'):
        parser.add_argument('--'+flag,required=True)
    parser.add_argument('--schedule')
    args=parser.parse_args()
    try:
        def unique_pairs(pairs):
            result={}
            for key,value in pairs:
                if key in result: raise ValueError('清单包含重复键: '+key)
                result[key]=value
            return result
        manifest_path=Path(args.manifest);manifest_raw=manifest_path.read_bytes()
        manifest=json.loads(manifest_raw,object_pairs_hook=unique_pairs)
        if manifest.get('schema')!='paper-exit-batch-v1' or not isinstance(manifest.get('entries'),dict) or not isinstance(manifest.get('exits'),dict):
            raise ValueError('批量清单格式无效')
        evidence={}
        def read(path):
            if not isinstance(path,str) or not path: raise ValueError('证据路径无效')
            if path not in evidence: evidence[path]=(manifest_path.parent/path).read_bytes()
            return evidence[path]
        quotes={key:{'quote':json.loads(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                for key,path in manifest['entries'].items() for raw in (read(path),)}
        bundles={}
        for key,item in manifest['exits'].items():
            kind=item['kind']
            bundle={'kind':kind}
            for name in ('signal','entry','exit','exit_quote'):
                raw=read(item[name]);bundle[name]=json.loads(raw)
                if name=='entry':bundle['entry_raw']=raw
            if kind=='bid_stop':
                for name in ('mark','trigger_quote'):bundle[name]=json.loads(read(item[name]))
            elif kind in ('ema20','max_30d'):
                bundle['observation']=json.loads(read(item['observation']))
                if kind=='ema20':bundle['scan_raw']=read(item['scan']);bundle['market_raw']=read(item['market'])
            else: raise ValueError('未知出场类型: '+str(kind))
            bundles[key]=bundle
        positions=None
        if 'positions' in manifest:
            if not isinstance(manifest['positions'],dict):raise ValueError('持仓观察清单格式无效')
            positions={}
            for key,item in manifest['positions'].items():
                try:
                    if not isinstance(item,dict) or not isinstance(item.get('samples'),list):raise ValueError('持仓报价样本格式无效')
                    if any(not isinstance(sample,dict) for sample in item['samples']):raise ValueError('持仓报价样本格式无效')
                    ev={'entry_quote_raw':read(item['entry_quote']),'entry_receipt_raw':read(item['entry_receipt']),
                        'samples':[{'quote_raw':read(sample['quote']),'receipt_raw':read(sample['receipt'])} for sample in item['samples']]}
                    if 'trigger_quote' in item:ev['trigger_quote_raw']=read(item['trigger_quote'])
                    positions[key]=ev
                except (OSError,KeyError,TypeError,ValueError) as exc:
                    positions[key]={'load_error':str(exc)}
        open_positions=None
        if 'open_positions' in manifest:
            if not isinstance(manifest['open_positions'],dict):raise ValueError('未平仓观察清单格式无效')
            open_positions={}
            for key,item in manifest['open_positions'].items():
                try:
                    if not isinstance(item,dict) or not isinstance(item.get('samples'),list):raise ValueError('未平仓样本格式无效')
                    open_positions[key]={'signal':json.loads(read(item['signal'])),'entry':json.loads(read(item['entry'])),
                        'entry_quote_raw':read(item['entry_quote']),'entry_receipt_raw':read(item['entry_receipt']),
                        'samples':[{'quote_raw':read(sample['quote']),'receipt_raw':read(sample['receipt'])} for sample in item['samples']]}
                except (OSError,KeyError,TypeError,ValueError) as exc:open_positions[key]={'load_error':str(exc)}
        depth_sessions=None
        if 'depth_sessions' in manifest:
            if not isinstance(manifest['depth_sessions'],list) or any(not isinstance(x,str) or not x for x in manifest['depth_sessions']):
                raise ValueError('盘口会话清单格式无效')
            depth_sessions=[str(manifest_path.parent/x) for x in manifest['depth_sessions']]
        event_dir=Path(args.events)
        if not event_dir.is_dir():raise ValueError('事件目录不存在')
        event_paths=sorted(event_dir.glob('*.json'));event_raw=[p.read_bytes() for p in event_paths]
        events=[json.loads(raw) for raw in event_raw]
        scan_raw=Path(args.scan).read_bytes()
        closed_raw=Path(args.closed).read_bytes();open_raw=Path(args.open).read_bytes();funding_raw=Path(args.funding).read_bytes()
        frame=lambda raw:pd.read_csv(io.BytesIO(raw),dtype=str,keep_default_na=False)
        result=reconcile(json.loads(scan_raw),events,args.market_dir,frame(closed_raw),frame(open_raw),frame(funding_raw),
                         quotes,bundles,args.start,args.as_of,schedule=args.schedule,position_evidence=positions,
                         open_position_evidence=open_positions,depth_session_paths=depth_sessions)
        result['input_sha256']={'manifest':hashlib.sha256(manifest_raw).hexdigest(),
            'scan':hashlib.sha256(scan_raw).hexdigest(),'closed':hashlib.sha256(closed_raw).hexdigest(),
            'open':hashlib.sha256(open_raw).hexdigest(),'funding':hashlib.sha256(funding_raw).hexdigest(),
            'events':{p.name:hashlib.sha256(raw).hexdigest() for p,raw in zip(event_paths,event_raw)},
            'evidence':{path:hashlib.sha256(raw).hexdigest() for path,raw in evidence.items()}}
    except (OSError,KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
        result={'status':'INVALID','reason':'输入不可读取或无效：'+str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
