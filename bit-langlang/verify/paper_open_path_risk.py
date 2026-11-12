"""Combine recorded open-position risk and discrete quote observations; no PASS."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from .paper_position_quotes import audit as audit_position
from .paper_risk_audit import audit as audit_risk

DEFINITION=Path(__file__).resolve().parent.parent/'docs/未平仓联合风险与持仓报价-核对定义-20261030.md'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def evaluate(closed,opened,start,as_of,evidence=None):
    risk=audit_risk(closed,opened,start,as_of)
    result={'risk':risk,'definition_sha256':digest(DEFINITION.read_bytes()),'continuous_price_path':'UNKNOWN'}
    if risk['status']=='INVALID':return {**result,'status':'INVALID','reason':'联合账本无效，无法可靠绑定报价'}
    if evidence is not None and (not isinstance(evidence,dict) or not set(evidence).issubset(set(opened.trade_id.astype(str)))):
        return {**result,'status':'INVALID','reason':'持仓观察清单编号无效'}
    observations={}
    for trade_id in opened.trade_id.astype(str):
        if evidence is None or trade_id not in evidence:
            observations[trade_id]={'status':'UNKNOWN_NOT_PROVIDED'};continue
        try:
            ev=evidence[trade_id]
            if 'load_error' in ev:raise ValueError('证据加载失败: '+ev['load_error'])
            observations[trade_id]=audit_position(ev['signal'],ev['entry'],ev['entry_quote_raw'],ev['entry_receipt_raw'],
                opened.loc[opened.trade_id.astype(str)==trade_id],ev['samples'],as_of)
        except (KeyError,TypeError,ValueError,IndexError,OverflowError,OSError) as exc:
            observations[trade_id]={'status':'INVALID','reason':str(exc)}
    observed_alert=any(x.get('observed_stop_alert') or x['status'] in ('ALERT_OBSERVED_STOP','ALERT_OVERDUE') for x in observations.values())
    invalid=any(x['status']=='INVALID' for x in observations.values())
    incomplete=any(x['status']!='PARTIAL_DISCRETE_UNVERIFIED' for x in observations.values())
    if risk['status']=='STOP' or observed_alert:status='STOP'
    elif invalid:status='INVALID'
    elif risk['status']=='STALE':status='STALE'
    elif not observations or incomplete:status='UNKNOWN_OBSERVATION'
    elif risk['status']=='AMBIGUOUS_ORDER':status='AMBIGUOUS_ORDER'
    else:status='REVIEW'
    return {**result,'status':status,'observations':observations,'observed_stop_or_overdue':observed_alert,
            'invalid_observation_present':invalid,'incomplete_observation_present':incomplete,
            'reason':'离散观察不证明连续价格、真实触发或成交；只审所给账本，不能证明账户完整性或强平。'}


def main():
    p=argparse.ArgumentParser()
    for flag in ('closed','open','start','as-of'):p.add_argument('--'+flag,required=True)
    p.add_argument('--manifest');args=p.parse_args()
    try:
        now=pd.to_datetime(args.as_of,utc=True,errors='raise')
        if pd.isna(now) or now>pd.Timestamp.now(tz='UTC'):raise ValueError('检查时间无效或晚于现在')
        raw_closed=Path(args.closed).read_bytes();raw_open=Path(args.open).read_bytes()
        frame=lambda raw:pd.read_csv(io.BytesIO(raw),dtype=str,keep_default_na=False)
        hashes={'closed':digest(raw_closed),'open':digest(raw_open)};evidence=None
        if args.manifest:
            path=Path(args.manifest);manifest_raw=path.read_bytes();hashes['manifest']=digest(manifest_raw)
            def pairs(seq):
                obj={}
                for k,v in seq:
                    if k in obj:raise ValueError('清单含重复键')
                    obj[k]=v
                return obj
            manifest=json.loads(manifest_raw,object_pairs_hook=pairs)
            if manifest.get('schema')!='paper-open-risk-paths-v1' or not isinstance(manifest.get('positions'),dict):
                raise ValueError('持仓观察清单格式无效')
            files={};evidence={}
            def read(name):
                if not isinstance(name,str) or not name:raise ValueError('证据路径无效')
                if name not in files:files[name]=(path.parent/name).read_bytes()
                return files[name]
            for key,item in manifest['positions'].items():
                try:
                    if not isinstance(item,dict) or not isinstance(item.get('samples'),list):raise ValueError('持仓样本格式无效')
                    ev={'signal':json.loads(read(item['signal'])),'entry':json.loads(read(item['entry'])),
                        'entry_quote_raw':read(item['entry_quote']),'entry_receipt_raw':read(item['entry_receipt']),
                        'samples':[{'quote_raw':read(x['quote']),'receipt_raw':read(x['receipt'])} for x in item['samples']]}
                    evidence[key]=ev
                except (OSError,KeyError,TypeError,ValueError) as exc:evidence[key]={'load_error':str(exc)}
            hashes['evidence']={name:digest(raw) for name,raw in files.items()}
        result=evaluate(frame(raw_closed),frame(raw_open),args.start,args.as_of,evidence);result['input_sha256']=hashes
    except (OSError,KeyError,TypeError,ValueError,IndexError,OverflowError) as exc:
        result={'status':'INVALID','reason':str(exc)}
    try:encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    except (ValueError,TypeError):encoded=json.dumps({'status':'INVALID','reason':'报告含无法序列化或非有限数值'},ensure_ascii=False)
    print(encoded)


if __name__=='__main__':main()
