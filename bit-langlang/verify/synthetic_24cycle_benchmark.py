"""Bounded offline synthetic rehearsal; no scheduler, account or real forward."""
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from .common import MARKET
from .forward_scan import build_snapshot
from .paper_scan_archive import verify_coverage
from .paper_scan_once import STEP, run


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_size(root):
    files = [p for p in Path(root).rglob('*') if p.is_file()]
    return {'files': len(files), 'logical_bytes': sum(p.stat().st_size for p in files),
            'allocated_bytes': sum(p.stat().st_blocks * 512 for p in files)}


class Response:
    def __init__(self, body):
        self.content = json.dumps(body).encode()
        self.status_code = 200

    def raise_for_status(self):
        pass


class Market:
    def __init__(self, state, last):
        self.state, self.last = state, last

    def get(self, url, params, timeout):
        if url.endswith('/time'):
            return Response({'serverTime': self.state['ms']})
        original = self.last[params['symbol']]
        rows = []
        for stamp in range(params['startTime'], params['endTime']+1, STEP):
            fields = ([original[k] for k in ('open','high','low','close','volume','turnover')]
                      if stamp == int(original['ts']) else [original['close']]*4+['0','0'])
            rows.append([stamp, *fields[:5], stamp+STEP-1, fields[5], 1, '0', '0', '0'])
        return Response(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise SystemExit('refusing to overwrite output')
    definition = Path('docs/二十四周期合成扫描归档-测量定义-20261030.md')
    reference = json.loads(Path('data/verify/fixed-notional-20261030-01/summary.json').read_text())
    config_path = Path('verify/frozen_config.json')
    config_hash = sha(config_path)
    if config_hash != reference['config_sha256']:
        raise ValueError('config mismatch')
    for symbol in ('BTCUSDT','ETHUSDT'):
        name=symbol+'_5m.csv.gz'
        if sha(Path(MARKET)/name) != reference['inputs'][name]:
            raise ValueError('historical input mismatch')
    start_ms = ((time.time_ns()//1_000_000)//STEP)*STEP-4*60*60*1000
    start = pd.to_datetime(start_ms, unit='ms', utc=True)
    state={'ms':start_ms};times=[];stored=[];events=[];last={}
    with tempfile.TemporaryDirectory(prefix='paper-24cycle-', dir=output.parent) as folder:
        root=Path(folder);source=root/'source';source.mkdir();archive=root/'archive'
        for symbol in ('BTCUSDT','ETHUSDT'):
            original=Path(MARKET)/(symbol+'_5m.csv.gz')
            frame=pd.read_csv(original,dtype=str,usecols=['ts','open','high','low','close','volume','turnover']).tail(295*288).copy()
            if len(frame)!=295*288:raise ValueError('insufficient source history')
            frame['ts']=(frame.ts.astype('int64')+(start_ms-STEP-int(frame.ts.iloc[-1]))).astype(str)
            if not (frame.ts.astype('int64').diff().dropna()==STEP).all():raise ValueError('source grid gap')
            frame.to_csv(source/(symbol+'_5m.csv.gz'),index=False,compression='gzip')
            last[symbol]=frame.iloc[-1].to_dict()
        input_size=tree_size(source);source_hashes={s:sha(source/(s+'_5m.csv.gz')) for s in last}
        def scan(command,**_):
            market=Path(command[command.index('--market-dir')+1]);path=Path(command[command.index('--out')+1])
            days=int(command[command.index('--days')+1])
            snapshot=build_snapshot(market,days,pd.to_datetime(state['ms'],unit='ms',utc=True))
            path.write_text(json.dumps(snapshot))
            return SimpleNamespace(returncode=0,stdout='synthetic offline scan',stderr='')
        def receipt(scan_path,market,out):
            raw=Path(scan_path).read_bytes();snapshot=json.loads(raw)
            captured=pd.to_datetime(state['ms']+1000,unit='ms',utc=True).isoformat()
            body={'schema':'paper-scan-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                  'captured_at_utc':captured,'scan_sha256':hashlib.sha256(raw).hexdigest(),
                  'config_sha256':config_hash,'market_sha256':{s:snapshot['symbols'][s]['data_sha256'] for s in last}}
            encoded=json.dumps(body).encode()
            with Path(out).open('xb') as file:
                file.write(encoded);file.flush()
                import os
                os.fsync(file.fileno())
            return {'sha256':hashlib.sha256(encoded).hexdigest(),'captured_at_utc':captured}
        head='GENESIS';seq=-1
        with patch('verify.paper_scan_once.subprocess.run',side_effect=scan), \
             patch('verify.paper_scan_once.capture_receipt',side_effect=receipt), \
             patch('verify.paper_scan_once.time.time_ns',side_effect=lambda:state['ms']*1_000_000):
            for i in range(24):
                state['ms']=start_ms+(i+1)*STEP+10000
                destination=root/f'cycle-{i:02}'
                began=time.perf_counter()
                result=run(source,destination,90,session=Market(state,last),archive=archive,
                           previous_seq=seq,previous_head=head,cover_since=start)
                times.append(time.perf_counter()-began)
                if result['status']!='PREFLIGHT_SNAPSHOT_SAVED':raise ValueError(str(result))
                seq=i;head=result['archive']['head_sha256'];stored.append(result['archive']['stored_market_bytes'])
                snapshot=json.loads((destination/'scan.json').read_text())
                signal_open=start+pd.Timedelta(minutes=5*i)
                matches=[x for x in snapshot['symbols']['ETHUSDT']['signals_recent'] if pd.Timestamp(x['ts'])==signal_open]
                if len(matches)>1:raise ValueError('duplicate signal')
                if matches:
                    observed=pd.Timestamp(result['captured_at_utc'])+pd.Timedelta(seconds=1)
                    common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':config_hash,
                            'symbol':'ETHUSDT','signal_time_utc':signal_open.isoformat()}
                    events.extend([{**common,'kind':'signal','event_time_utc':observed.isoformat(),
                        'captured_at_utc':(observed+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1},
                        {**common,'kind':'skip','event_time_utc':(observed+pd.Timedelta(seconds=2)).isoformat(),
                        'captured_at_utc':(observed+pd.Timedelta(seconds=3)).isoformat(),'capture_lag_seconds':1,
                        'description':'synthetic observation only'}])
                source=destination/'market'
        as_of=pd.to_datetime(state['ms']+10000,unit='ms',utc=True)
        began=time.perf_counter();audit=verify_coverage(archive,events,start,as_of,head);audit_seconds=time.perf_counter()-began
        if audit['status'] not in ('PARTIAL_COVERAGE_UNVERIFIED','PENDING_NO_SEALED_WINDOW'):
            raise ValueError('coverage audit failed: '+str(audit))
        result={'status':'SYNTHETIC_OFFLINE_NOT_FORWARD','cycles':24,'cycle_seconds':times,
                'cycle_median_seconds':float(pd.Series(times).median()),'cycle_max_seconds':max(times),
                'audit_seconds':audit_seconds,'coverage_status':audit['status'],'sealed_candidates':audit['sealed_candidates'],
                'unsealed_seconds':audit['unsealed_seconds'],'reconstructed_records':audit['archive']['fully_reconstructed_records'],
                'initial_source':input_size,'all_cycles':tree_size(root),'archive':tree_size(archive),
                'stored_market_bytes_by_cycle':stored,'synthetic_source_sha256':source_hashes,
                'definition_sha256':sha(definition),'code_sha256':sha(__file__),
                'limits':['synthetic clock and response; no network','not a 90-day reliability measurement',
                          'temporary full outputs included in all_cycles','no account, fill or trade evidence']}
    with output.open('x') as file:
        json.dump(result,file,ensure_ascii=False,indent=2,allow_nan=False);file.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
