"""Record local scan-file availability; not a trusted timestamp or monitor."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

CONFIG=Path(__file__).with_name('frozen_config.json')


def capture(scan_path,market_dir,out):
    raw=Path(scan_path).read_bytes();snapshot=json.loads(raw)
    cfg=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    generated=pd.to_datetime(snapshot['generated_at'],utc=True,errors='raise')
    if pd.isna(generated) or snapshot['config_sha256']!=cfg:raise ValueError('扫描时间或配置无效')
    hashes={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        data=(Path(market_dir)/f'{symbol}_5m.csv.gz').read_bytes()
        hashes[symbol]=hashlib.sha256(data).hexdigest()
        if snapshot['symbols'][symbol]['data_sha256']!=hashes[symbol]:raise ValueError('扫描与行情哈希不一致')
    captured=pd.Timestamp.now(tz='UTC')
    if captured<generated:raise ValueError('扫描生成时间晚于本机回执时间')
    receipt={'schema':'paper-scan-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
             'captured_at_utc':captured.isoformat(),'scan_sha256':hashlib.sha256(raw).hexdigest(),
             'config_sha256':cfg,'market_sha256':hashes}
    encoded=(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    with Path(out).open('xb') as stream:
        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
    return {'status':'RECEIPT_UNVERIFIED','path':str(out),'sha256':hashlib.sha256(encoded).hexdigest(),
            'captured_at_utc':captured.isoformat()}


def main():
    parser=argparse.ArgumentParser()
    for flag in ('scan','market-dir','out'):parser.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    try:result=capture(args.scan,args.market_dir,args.out)
    except (KeyError,TypeError,ValueError,OverflowError,OSError) as exc:result={'status':'INVALID','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
