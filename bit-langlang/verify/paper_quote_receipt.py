"""Bind a saved public quote to a local unverified receipt; no monitoring."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from .paper_quote import CONFIG, quote_facts


def capture(quote_path,out):
    raw=Path(quote_path).read_bytes();quote=json.loads(raw);facts=quote_facts(quote)
    captured=pd.Timestamp.now(tz='UTC')
    if not facts['local_completed']<captured<=facts['local_completed']+pd.Timedelta(seconds=2):
        raise ValueError('回执必须在请求完成之后 2 秒内生成')
    receipt={'schema':'paper-quote-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
             'captured_at_utc':captured.isoformat(),'quote_sha256':hashlib.sha256(raw).hexdigest(),
             'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest()}
    encoded=(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    with Path(out).open('xb') as stream:
        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
    return {'status':'RECEIPT_UNVERIFIED','path':str(out),'sha256':hashlib.sha256(encoded).hexdigest(),
            'captured_at_utc':captured.isoformat()}


def record_rejection(quote_path,out):
    """Persist a failed local quote check; never produce an accepted receipt."""
    raw=Path(quote_path).read_bytes();recorded=pd.Timestamp.now(tz='UTC')
    try:
        facts=quote_facts(json.loads(raw))
        if facts['local_completed']<recorded<=facts['local_completed']+pd.Timedelta(seconds=2):
            raise RuntimeError('报价当前符合校验条件，不能记录为拒绝')
        reason='回执必须在请求完成之后 2 秒内生成'
    except (KeyError,TypeError,ValueError,OverflowError,IndexError) as exc:
        reason=str(exc)
    receipt={'schema':'paper-quote-rejection-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
             'recorded_at_utc':recorded.isoformat(),'quote_sha256':hashlib.sha256(raw).hexdigest(),
             'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest(),'reason':reason}
    encoded=(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    with Path(out).open('xb') as stream:
        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
    return {'status':'REJECTION_RECORDED_UNVERIFIED','path':str(out),'sha256':hashlib.sha256(encoded).hexdigest(),
            'recorded_at_utc':recorded.isoformat(),'reason':reason}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--quote',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--reject',action='store_true',help='只记录本机验证失败的报价，不生成有效回执')
    args=parser.parse_args()
    try:result=record_rejection(args.quote,args.out) if args.reject else capture(args.quote,args.out)
    except (KeyError,TypeError,ValueError,OverflowError,IndexError,OSError,RuntimeError) as exc:result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
