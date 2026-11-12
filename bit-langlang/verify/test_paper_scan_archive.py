import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from .paper_scan_archive import (CONFIG, append, apply_delta, init, make_delta,
                                 records, restore, status)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.archive=self.root/'archive';self.initial=init(self.archive)
        self.config=hashlib.sha256(CONFIG.read_bytes()).hexdigest()

    def tearDown(self):self.tmp.cleanup()

    def input(self,index,data):
        folder=self.root/f'input-{index}';folder.mkdir();market=folder/'market';market.mkdir()
        hashes={}
        for symbol,raw in data.items():
            (market/f'{symbol}_5m.csv.gz').write_bytes(raw);hashes[symbol]=hashlib.sha256(raw).hexdigest()
        generated=pd.Timestamp('2026-10-29T23:35:00Z')+pd.Timedelta(minutes=5*index)
        scan={'generated_at':generated.isoformat(),'config_sha256':self.config,
              'symbols':{symbol:{'data_sha256':digest} for symbol,digest in hashes.items()}}
        scan_raw=json.dumps(scan).encode();(folder/'scan.json').write_bytes(scan_raw)
        receipt={'schema':'paper-scan-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                 'captured_at_utc':(generated+pd.Timedelta(seconds=1)).isoformat(),
                 'config_sha256':self.config,'scan_sha256':hashlib.sha256(scan_raw).hexdigest(),'market_sha256':hashes}
        (folder/'receipt.json').write_text(json.dumps(receipt))
        return folder/'scan.json',folder/'receipt.json',market

    def test_block_delta_exact_and_defensive(self):
        previous=os.urandom(100000);current=bytearray(previous);current[:4]=b'1234';current.extend(b'new-tail')
        delta=make_delta(previous,bytes(current))
        self.assertLess(len(delta),len(current)//4)
        self.assertEqual(apply_delta(previous,delta),bytes(current))
        self.assertEqual(apply_delta(previous,make_delta(previous,previous)),previous)
        self.assertEqual(apply_delta(previous,make_delta(previous,os.urandom(1000))).__len__(),1000)
        broken=json.loads(delta);broken['target_sha256']='0'*64
        with self.assertRaises(ValueError):apply_delta(previous,json.dumps(broken).encode())
        broken=json.loads(delta);broken['ops']=[['c',len(previous),4]]
        with self.assertRaises(ValueError):apply_delta(previous,json.dumps(broken).encode())

    def test_commit_recovery_and_tamper_detection(self):
        self.assertEqual(status(self.archive,'GENESIS')['status'],'EMPTY_METADATA_ONLY')
        first={'BTCUSDT':os.urandom(50000),'ETHUSDT':os.urandom(50000)}
        second={key:raw[:-10]+b'changed-end' for key,raw in first.items()}
        scan0,receipt0,market0=self.input(0,first);scan1,receipt1,market1=self.input(1,second)
        a=append(self.archive,scan0,receipt0,market0,-1,'GENESIS')
        self.assertIn(a['status'],('COMMITTED','COMMIT_PUBLISHED_DURABILITY_UNKNOWN'))
        with self.assertRaises(ValueError):append(self.archive,scan1,receipt1,market1,0,'wrong',market0)
        with patch('verify.paper_scan_archive.os.link',side_effect=InterruptedError('synthetic interruption')):
            with self.assertRaises(InterruptedError):append(self.archive,scan1,receipt1,market1,0,a['head_sha256'],market0)
        self.assertFalse((self.archive/'commits'/'00000001.json').exists())
        b=append(self.archive,scan1,receipt1,market1,0,a['head_sha256'],market0)
        self.assertLess(b['stored_market_bytes'],b['market_raw_bytes']//4)
        items,head,orphans=records(self.archive,b['head_sha256'])
        self.assertEqual((len(items),head,len(orphans)),(2,b['head_sha256'],1))
        cmd=[sys.executable,'-m','verify.paper_scan_archive','status','--archive',str(self.archive),'--expected-head',head]
        cli=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
        self.assertEqual(cli['status'],'METADATA_ONLY_UNVERIFIED')
        self.assertEqual(cli['market_payloads'],'NOT_RECONSTRUCTED_OR_CHECKED')
        self.assertEqual(cli['public_source_missing_records'],2)
        self.assertEqual(cli['initial_source_status'],'UNKNOWN_NOT_CAPTURED')
        restored=self.root/'restored';out=restore(self.archive,1,restored,b['head_sha256'])
        self.assertEqual(out['status'],'RESTORED_BYTES_VERIFIED')
        for symbol,raw in second.items():self.assertEqual((restored/f'{symbol}_5m.csv.gz').read_bytes(),raw)
        with self.assertRaises(FileExistsError):restore(self.archive,1,restored,b['head_sha256'])
        with self.assertRaises(FileExistsError):append(self.archive,scan1,receipt1,market1,0,a['head_sha256'],market0)
        with self.assertRaises(ValueError):records(self.archive,'0'*64)
        last=self.archive/'commits'/'00000001.json';saved=self.root/'saved-commit.json';last.rename(saved)
        with self.assertRaises(ValueError):records(self.archive,b['head_sha256'])
        unanchored,_,_=records(self.archive)
        self.assertEqual(len(unanchored),1)  # Without an external head, truncation is indistinguishable.
        saved.rename(last)
        item=items[1];path=item['run']/('BTCUSDT.'+item['commit']['markets']['BTCUSDT']['kind'])
        raw=path.read_bytes();path.write_bytes(raw+b'corruption')
        self.assertEqual(status(self.archive,b['head_sha256'])['market_payloads'],'NOT_RECONSTRUCTED_OR_CHECKED')
        with self.assertRaises(ValueError):restore(self.archive,1,self.root/'must-not-exist',b['head_sha256'])
        self.assertFalse((self.root/'must-not-exist').exists())
        self.assertEqual((market1/'BTCUSDT_5m.csv.gz').read_bytes(),second['BTCUSDT'])

    def test_wrong_previous_market_and_receipt_fail_closed(self):
        data={'BTCUSDT':b'first-btc','ETHUSDT':b'first-eth'}
        scan0,receipt0,market0=self.input(0,data);scan1,receipt1,market1=self.input(1,data)
        head=append(self.archive,scan0,receipt0,market0,-1,'GENESIS')['head_sha256']
        (market0/'BTCUSDT_5m.csv.gz').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'前一行情'):append(self.archive,scan1,receipt1,market1,0,head,market0)
        self.assertFalse((self.archive/'commits'/'00000001.json').exists())
        (market0/'BTCUSDT_5m.csv.gz').write_bytes(data['BTCUSDT'])
        receipt=json.loads(receipt1.read_text());receipt['scan_sha256']='wrong';receipt1.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'回执不一致'):append(self.archive,scan1,receipt1,market1,0,head,market0)

    def test_public_source_saved_restored_and_tamper_detected(self):
        scan,receipt,market=self.input(0,{'BTCUSDT':b'btc','ETHUSDT':b'eth'})
        rawdir=self.root/'public';rawdir.mkdir()
        for root in ('server-time','BTCUSDT-000','ETHUSDT-000'):
            body=json.dumps({'synthetic':root}).encode();(rawdir/(root+'.body.json')).write_bytes(body)
            metadata={'endpoint':'/fapi/v1/time' if root=='server-time' else '/fapi/v1/klines',
                      'params':{} if root=='server-time' else {'symbol':root.split('-')[0]},
                      'body_sha256':hashlib.sha256(body).hexdigest(),'http_status':200,
                      'local_start_ms':10,'local_end_ms':11}
            (rawdir/(root+'.request.json')).write_text(json.dumps(metadata))
        initial={'BTCUSDT':b'before-btc','ETHUSDT':b'before-eth'}
        saved=append(self.archive,scan,receipt,market,-1,'GENESIS',source_evidence_dir=rawdir,initial_source=initial)
        self.assertEqual(saved['public_source_status'],'BOUND_UNVERIFIED')
        self.assertEqual(saved['initial_source_status'],'BOUND_UNVERIFIED')
        self.assertEqual(status(self.archive,saved['head_sha256'])['public_source_bound_records'],1)
        restored=self.root/'raw-restored'
        result=restore(self.archive,0,restored,saved['head_sha256'])
        self.assertEqual(result['public_source_status'],'BOUND_UNVERIFIED')
        self.assertEqual(result['initial_source_status'],'BOUND_UNVERIFIED')
        for path in rawdir.iterdir():self.assertEqual((restored/'public-source'/path.name).read_bytes(),path.read_bytes())
        for symbol,raw in initial.items():self.assertEqual((restored/'initial-source'/f'{symbol}_5m.csv.gz').read_bytes(),raw)
        items,_,_=records(self.archive,saved['head_sha256'])
        initial_path=items[0]['run']/'initial-source'/'BTCUSDT_5m.csv.gz'
        initial_path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'初始行情基线'):records(self.archive,saved['head_sha256'])
        initial_path.write_bytes(initial['BTCUSDT'])
        damaged=items[0]['run']/'public-source'/'ETHUSDT-000.body.json'
        damaged.write_bytes(b'{"modified":true}')
        with self.assertRaisesRegex(ValueError,'哈希'):records(self.archive,saved['head_sha256'])

    def test_public_source_missing_pair_fails_before_commit(self):
        scan,receipt,market=self.input(0,{'BTCUSDT':b'btc','ETHUSDT':b'eth'})
        rawdir=self.root/'incomplete';rawdir.mkdir()
        (rawdir/'server-time.body.json').write_text('{}')
        with self.assertRaises(ValueError):append(self.archive,scan,receipt,market,-1,'GENESIS',source_evidence_dir=rawdir)
        self.assertFalse((self.archive/'commits'/'00000000.json').exists())

    def test_cli_init_append_restore(self):
        root=self.root/'cli-archive';output=self.root/'cli-restored'
        data={'BTCUSDT':b'synthetic btc bytes','ETHUSDT':b'synthetic eth bytes'}
        scan,receipt,market=self.input(0,data)
        def run(*args):
            command=[sys.executable,'-m','verify.paper_scan_archive',*map(str,args)]
            return json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout)
        self.assertEqual(run('init','--archive',root)['status'],'ARCHIVE_CREATED')
        saved=run('append','--archive',root,'--scan',scan,'--receipt',receipt,'--market-dir',market,
                  '--previous-seq','-1','--previous-head','GENESIS')
        self.assertIn(saved['status'],('COMMITTED','COMMIT_PUBLISHED_DURABILITY_UNKNOWN'))
        restored=run('restore','--archive',root,'--sequence','0','--out',output,'--expected-head',saved['head_sha256'])
        self.assertEqual(restored['status'],'RESTORED_BYTES_VERIFIED')
        for symbol,raw in data.items():self.assertEqual((output/f'{symbol}_5m.csv.gz').read_bytes(),raw)


if __name__=='__main__':unittest.main()
