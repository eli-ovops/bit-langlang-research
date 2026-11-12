import gzip
import hashlib
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from .paper_scan_archive import status as archive_status
from .paper_scan_archive import records, market_loaders
from .paper_scan_once import STEP, RevisionError, advance, run
from .paper_scan_receipt import CONFIG


class FakeResponse:
    def __init__(self,body,status=200):
        self.content=json.dumps(body).encode();self.status_code=status
    def raise_for_status(self):
        if self.status_code>=400:
            import requests
            raise requests.HTTPError(f'{self.status_code} synthetic')


class FakeSession:
    def __init__(self,now_ms,*,revision=False,gap=False,status=200,clock_offset=0):
        self.now_ms=now_ms;self.revision=revision;self.gap=gap;self.status=status;self.clock_offset=clock_offset;self.calls=[]
    def get(self,url,params,timeout):
        self.calls.append((url,dict(params)))
        if url.endswith('/time'):return FakeResponse({'serverTime':self.now_ms+self.clock_offset},self.status)
        first=params['startTime'];end=params['endTime'];rows=[]
        for index,stamp in enumerate(range(first,end+1,STEP)):
            if self.gap and index==1:continue
            close='100.01' if self.revision and index==0 else '100'
            rows.append([stamp,'100','101','99',close,'10',stamp+STEP-1,'1000',1,'0','0','0'])
        return FakeResponse(rows,self.status)


class ScanOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.now_ms=(time.time_ns()//1_000_000)//1000*1000
        last_open=(self.now_ms//STEP)*STEP-2*STEP
        ts=pd.date_range(end=pd.to_datetime(last_open,unit='ms',utc=True),periods=205*288,freq='5min')
        frame=pd.DataFrame({'ts':ts.astype('int64')//10**6,'open':'100','high':'101','low':'99',
                            'close':'100','volume':'10','turnover':'1000'})
        self.source=self.root/'source';self.source.mkdir()
        for symbol in ('BTCUSDT','ETHUSDT'):
            frame.to_csv(self.source/f'{symbol}_5m.csv.gz',index=False,compression='gzip')

    def tearDown(self):self.tmp.cleanup()

    def test_overlap_append_and_unclosed_exclusion(self):
        base=b'ts,open,high,low,close,volume,turnover\n300000,100,101,99,100,10,1000\n'
        last=['300000','100','101','99','100','10','1000']
        def row(ts):return [ts,'100','101','99','100','10',ts+STEP-1,'1000']
        updated,count,end=advance(base,last,[row(300000),row(600000),row(900000)],900001)
        self.assertEqual((count,end),(1,600000))
        self.assertTrue(updated.startswith(base));self.assertNotIn(b'900000,',updated)
        changed=row(300000);changed[5]='11'
        with self.assertRaises(RevisionError):advance(base,last,[changed],900001)
        with self.assertRaises(ValueError):advance(base,last,[row(300000),row(900000)],1200000)
        fractional=row(300000);fractional[0]=300000.5
        with self.assertRaises(ValueError):advance(base,last,[fractional],900001)
        injected=row(300000);injected[1]='100\n'
        with self.assertRaises(ValueError):advance(base,last,[injected],900001)

    def test_one_shot_archive_no_new_and_no_overwrite(self):
        fake=FakeSession(self.now_ms);archive=self.root/'archive'
        with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
            result=run(self.source,self.root/'run-1',3,session=fake,archive=archive)
        self.assertEqual(result['status'],'PREFLIGHT_SNAPSHOT_SAVED',result)
        self.assertEqual(result['mode'],'SYNTHETIC_SESSION_NOT_FORWARD')
        self.assertGreaterEqual(result['added_bars']['ETHUSDT'],1)
        self.assertEqual(result['validation_status'],'INVALID')
        self.assertEqual(result['archive']['public_source_status'],'BOUND_UNVERIFIED')
        self.assertEqual(result['archive']['initial_source_status'],'BOUND_UNVERIFIED')
        self.assertEqual(len(fake.calls),3)
        self.assertEqual(archive_status(archive)['committed_records'],1)
        self.assertEqual(archive_status(archive)['public_source_bound_records'],1)
        self.assertEqual(archive_status(archive)['initial_source_status'],'BOUND_UNVERIFIED')
        head=result['archive']['head_sha256']
        with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
            no_new=run(self.root/'run-1'/'market',self.root/'run-2',3,session=FakeSession(self.now_ms),
                       archive=archive,previous_seq=0,previous_head=head)
        self.assertEqual(no_new['status'],'NO_NEW_CLOSED_BAR',no_new)
        self.assertFalse((self.root/'run-2'/'scan.json').exists())
        wrong=FakeSession(self.now_ms)
        with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
            failed=run(self.root/'run-1'/'market',self.root/'wrong-head',3,session=wrong,
                       archive=archive,previous_seq=0,previous_head='0'*64)
        self.assertEqual(failed['status'],'FAILED_READ_ONLY')
        self.assertEqual(len(wrong.calls),0)
        with self.assertRaises(FileExistsError):run(self.source,self.root/'run-1',3,session=FakeSession(self.now_ms))

    def test_revision_gap_clock_and_rejection_are_preserved_without_archive(self):
        cases=[('revision',{'revision':True},'SOURCE_REVISION'),('gap',{'gap':True},'FAILED_READ_ONLY'),
               ('clock',{'clock_offset':5000},'FAILED_READ_ONLY'),('denied',{'status':403},'FAILED_READ_ONLY')]
        for name,flags,expected in cases:
            with self.subTest(name=name):
                fake=FakeSession(self.now_ms,**flags);out=self.root/name
                with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
                    result=run(self.source,out,3,session=fake,archive=self.root/(name+'-archive'))
                self.assertEqual(result['status'],expected,result)
                self.assertTrue((out/'result.json').is_file())
                self.assertTrue((out/'raw'/'server-time.body.json').is_file())
                self.assertFalse((self.root/(name+'-archive')).exists())
                if name in ('clock','denied'):self.assertEqual(len(fake.calls),1)

    def test_misaligned_symbol_history_rejected_before_kline_requests(self):
        path=self.source/'ETHUSDT_5m.csv.gz';frame=pd.read_csv(path)
        extra=frame.head(1).copy();extra.loc[extra.index[0],'ts']-=STEP
        pd.concat([extra,frame],ignore_index=True).to_csv(path,index=False,compression='gzip')
        fake=FakeSession(self.now_ms)
        with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
            result=run(self.source,self.root/'unequal-history',3,session=fake)
        self.assertEqual(result['status'],'FAILED_READ_ONLY',result)
        self.assertIn('时间网格不一致',result['reason'])
        self.assertEqual(len(fake.calls),1)

    def test_candidate_window_covers_explicit_start_and_rejects_short_warmup(self):
        now=pd.to_datetime(self.now_ms,unit='ms',utc=True)
        cover=now.floor('5min')-pd.Timedelta(days=90)
        short=FakeSession(self.now_ms)
        with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
            result=run(self.source,self.root/'short-prewarm',3,session=short,cover_since=cover)
        self.assertEqual(result['status'],'FAILED_READ_ONLY',result)
        self.assertIn('205 天历史预热',result['reason'])
        self.assertEqual(len(short.calls),1)
        first=pd.read_csv(self.source/'BTCUSDT_5m.csv.gz').iloc[0].ts
        ts=pd.date_range(end=pd.to_datetime(int(first)-STEP,unit='ms',utc=True),periods=90*288,freq='5min')
        extra=pd.DataFrame({'ts':ts.astype('int64')//10**6,'open':'100','high':'101','low':'99',
                            'close':'100','volume':'10','turnover':'1000'})
        longer=self.root/'longer-source';longer.mkdir()
        for symbol in ('BTCUSDT','ETHUSDT'):
            old=pd.read_csv(self.source/f'{symbol}_5m.csv.gz')
            pd.concat([extra,old],ignore_index=True).to_csv(longer/f'{symbol}_5m.csv.gz',index=False,compression='gzip')
        with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000):
            good=run(longer,self.root/'cover-start',3,session=FakeSession(self.now_ms),cover_since=cover)
        self.assertEqual(good['status'],'PREFLIGHT_SNAPSHOT_NOT_ARCHIVED',good)
        self.assertGreaterEqual(good['candidate_days_effective'],90)
        snapshot=json.loads((self.root/'cover-start'/'scan.json').read_text())
        for symbol in ('BTCUSDT','ETHUSDT'):
            self.assertLessEqual(pd.Timestamp(snapshot['symbols'][symbol]['candidate_window_start']),cover)
        self.assertEqual(good['mode'],'SYNTHETIC_SESSION_NOT_FORWARD')
        real_run=subprocess.run
        for name,value in (('late-window',(cover+pd.Timedelta(minutes=5)).isoformat()),('missing-window','NaT')):
            def altered_window(command,**kwargs):
                result=real_run(command,**kwargs)
                path=Path(command[command.index('--out')+1]);data=json.loads(path.read_text())
                data['symbols']['ETHUSDT']['candidate_window_start']=value
                path.write_text(json.dumps(data))
                return result
            with patch('verify.paper_scan_once.time.time_ns',return_value=self.now_ms*1_000_000), \
                 patch('verify.paper_scan_once.subprocess.run',side_effect=altered_window):
                bad=run(longer,self.root/name,3,session=FakeSession(self.now_ms),cover_since=cover)
            self.assertEqual(bad['status'],'FAILED_READ_ONLY',bad)
            self.assertIn('扫描候选窗口未覆盖指定起点',bad['reason'])
            self.assertFalse((self.root/name/'receipt.json').exists())

    def test_synthetic_resume_checks_published_head_before_retry(self):
        source=self.root/'older-source';source.mkdir()
        for symbol in ('BTCUSDT','ETHUSDT'):
            frame=pd.read_csv(self.source/f'{symbol}_5m.csv.gz');frame['ts']-=600000
            frame.to_csv(source/f'{symbol}_5m.csv.gz',index=False,compression='gzip')
        state={'now_ms':self.now_ms-600000}
        config_hash=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        def fake_scan(command,**_):
            folder=Path(command[command.index('--market-dir')+1]);out=Path(command[command.index('--out')+1])
            data={'generated_at':pd.to_datetime(state['now_ms'],unit='ms',utc=True).isoformat(),
                  'config_sha256':config_hash,'btc_data_status':{'status':'FRESH'},'validation_status':'INVALID','symbols':{}}
            for symbol in ('BTCUSDT','ETHUSDT'):
                raw=(folder/f'{symbol}_5m.csv.gz').read_bytes()
                data['symbols'][symbol]={'data_status':{'status':'FRESH'},'data_sha256':hashlib.sha256(raw).hexdigest(),'candidate_count':0}
            out.write_text(json.dumps(data))
            return SimpleNamespace(returncode=0,stdout='synthetic',stderr='')
        def fake_receipt(scan,folder,out):
            raw=Path(scan).read_bytes();snapshot=json.loads(raw)
            captured=pd.to_datetime(state['now_ms']+1000,unit='ms',utc=True).isoformat()
            body={'schema':'paper-scan-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                  'captured_at_utc':captured,'scan_sha256':hashlib.sha256(raw).hexdigest(),
                  'config_sha256':config_hash,'market_sha256':{s:snapshot['symbols'][s]['data_sha256'] for s in ('BTCUSDT','ETHUSDT')}}
            encoded=json.dumps(body).encode();Path(out).write_bytes(encoded)
            return {'sha256':hashlib.sha256(encoded).hexdigest(),'captured_at_utc':captured}
        archive=self.root/'resume-archive'
        with patch('verify.paper_scan_once.subprocess.run',side_effect=fake_scan), \
             patch('verify.paper_scan_once.capture_receipt',side_effect=fake_receipt), \
             patch('verify.paper_scan_once.time.time_ns',side_effect=lambda:state['now_ms']*1_000_000):
            first=run(source,self.root/'resume-1',3,session=FakeSession(state['now_ms']),archive=archive)
            self.assertEqual(first['status'],'PREFLIGHT_SNAPSHOT_SAVED',first)
            state['now_ms']+=STEP;head=first['archive']['head_sha256'];previous=self.root/'resume-1'/'market'
            with patch('verify.paper_scan_archive.os.link',side_effect=InterruptedError('synthetic process interruption')):
                interrupted=run(previous,self.root/'resume-interrupted',3,session=FakeSession(state['now_ms']),
                                archive=archive,previous_seq=0,previous_head=head)
            self.assertEqual(interrupted['status'],'ARCHIVE_RESULT_UNKNOWN',interrupted)
            self.assertEqual(interrupted['archive_status']['last_sequence'],0)
            self.assertEqual(archive_status(archive,head)['last_sequence'],0)
            resumed=run(previous,self.root/'resume-2',3,session=FakeSession(state['now_ms']),
                        archive=archive,previous_seq=0,previous_head=head)
        self.assertEqual(resumed['status'],'PREFLIGHT_SNAPSHOT_SAVED',resumed)
        self.assertEqual(resumed['archive']['sequence'],1)
        self.assertLess(resumed['archive']['stored_market_bytes'],resumed['archive']['market_raw_bytes'])
        items,_,orphans=records(archive,resumed['archive']['head_sha256']);_,load=market_loaders(items)
        load(0);restored=load(1)
        for symbol in ('BTCUSDT','ETHUSDT'):
            self.assertEqual(restored[symbol],(self.root/'resume-2'/'market'/f'{symbol}_5m.csv.gz').read_bytes())
        self.assertEqual(len(orphans),1)


if __name__=='__main__':unittest.main()
