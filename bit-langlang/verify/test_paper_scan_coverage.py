import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .forward_scan import signal_records
from .paper_scan_coverage import audit
from .paper_scan_receipt import capture as capture_receipt
from .paper_scan_archive import append as archive_append, init as archive_init, verify_coverage
from .tph_frozen_audit import signals


class ScanCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.start=pd.Timestamp('2026-10-29T23:30:00Z');cls.asof=cls.start+pd.Timedelta(minutes=35,seconds=40)
        ts=pd.date_range(end=cls.start+pd.Timedelta(minutes=30),periods=206*288,freq='5min')
        master={}
        for symbol,step in (('BTCUSDT',.00001),('ETHUSDT',.00005)):
            values=100+pd.RangeIndex(len(ts))*step
            master[symbol]=pd.DataFrame({'ts':ts,'open':values,'high':values+.02,'low':values-.02,'close':values})
        cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        cls.cfg=cfg;cls.scans=[]
        for index in range(7):
            generated=cls.start+pd.Timedelta(minutes=5*(index+1),seconds=30)
            folder=cls.root/f'market-{index}';folder.mkdir();frames={};hashes={}
            for symbol in master:
                frame=master[symbol].loc[master[symbol].ts+pd.Timedelta(minutes=5)<=generated].reset_index(drop=True)
                frames[symbol]=frame;saved=frame.copy();saved['ts']=saved.ts.astype('int64')//10**6
                path=folder/f'{symbol}_5m.csv.gz';saved.to_csv(path,index=False,compression='gzip')
                hashes[symbol]=hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot={'generated_at':generated.isoformat(),'config_sha256':cfg,'btc_data_status':{'status':'FRESH'},'symbols':{}}
            for symbol,frame in frames.items():
                hit,_,_=signals(frames['BTCUSDT'],frame);rows=signal_records(frame,hit,cls.start-pd.Timedelta(minutes=5))
                snapshot['symbols'][symbol]={'data_status':{'status':'FRESH'},'data_sha256':hashes[symbol],
                    'candidate_count':len(rows),'candidate_window_start':(cls.start-pd.Timedelta(minutes=5)).isoformat(),'signals_recent':rows}
            scan_hash=hashlib.sha256(json.dumps(snapshot).encode()).hexdigest()
            receipt={'schema':'paper-scan-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                     'captured_at_utc':(generated+pd.Timedelta(seconds=2)).isoformat(),
                     'scan_sha256':scan_hash,'config_sha256':cfg,'market_sha256':hashes}
            cls.scans.append({'snapshot':snapshot,'market_dir':folder,'scan_sha256':scan_hash,
                              'receipt':receipt,'receipt_sha256':hashlib.sha256(json.dumps(receipt).encode()).hexdigest()})
        cls.events=[]
        for row in cls.scans[-1]['snapshot']['symbols']['ETHUSDT']['signals_recent']:
            signal=pd.Timestamp(row['ts'])
            if signal<cls.start:continue
            close=signal+pd.Timedelta(minutes=5)
            for kind,happen,capture in (('signal',close+pd.Timedelta(seconds=33),close+pd.Timedelta(seconds=34)),
                                         ('skip',close+pd.Timedelta(seconds=36),close+pd.Timedelta(seconds=37))):
                cls.events.append({'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                    'symbol':'ETHUSDT','kind':kind,'signal_time_utc':signal.isoformat(),
                    'event_time_utc':happen.isoformat(),'captured_at_utc':capture.isoformat(),
                    'capture_lag_seconds':(capture-happen).total_seconds(),
                    'description':'synthetic skip: test only' if kind=='skip' else 'synthetic signal'})

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    @staticmethod
    def refresh(item, captured=None):
        item['scan_sha256']=hashlib.sha256(json.dumps(item['snapshot']).encode()).hexdigest()
        item['receipt']['scan_sha256']=item['scan_sha256']
        item['receipt']['market_sha256']={s:item['snapshot']['symbols'][s]['data_sha256'] for s in ('BTCUSDT','ETHUSDT')}
        if captured is not None:item['receipt']['captured_at_utc']=pd.Timestamp(captured).isoformat()

    def test_sealed_coverage_and_unsealed_tail(self):
        result=audit(self.scans,self.events,self.start,self.asof)
        self.assertEqual(result['status'],'PARTIAL_COVERAGE_UNVERIFIED',result)
        self.assertEqual(result['sealed_candidates'],4)
        self.assertEqual(result['matched_signals'],4)
        self.assertEqual(result['matched_decisions'],4)
        self.assertEqual(result['signal_availability_status'],'ORDERED_BUT_UNVERIFIED')
        self.assertEqual(len(result['pending_candidates']),3)
        self.assertEqual(len(result['pending_events']),6)
        self.assertEqual(result['pending_event_keys_not_yet_seen_in_scans'],[])
        self.assertEqual(pd.Timestamp(result['sealed_close_watermark_utc']),self.start+pd.Timedelta(minutes=20))
        pending=audit(self.scans[:2],self.events[:4],self.start,self.start+pd.Timedelta(minutes=10,seconds=40))
        self.assertEqual(pending['status'],'PENDING_NO_SEALED_WINDOW',pending)

    def test_signal_before_or_at_first_scan_receipt_is_not_proven_available(self):
        early=copy.deepcopy(self.events)
        first_receipt=pd.Timestamp(self.scans[0]['receipt']['captured_at_utc'])
        for when in (first_receipt-pd.Timedelta(seconds=1),first_receipt):
            early[0]['event_time_utc']=when.isoformat()
            early[0]['captured_at_utc']=(when+pd.Timedelta(seconds=1)).isoformat()
            early[0]['capture_lag_seconds']=1
            result=audit(self.scans,early,self.start,self.asof)
            self.assertEqual(result['status'],'UNKNOWN_SIGNAL_AVAILABILITY',result)
            self.assertEqual(result['signal_availability_status'],'UNKNOWN')
            self.assertEqual(result['signal_events_not_after_first_scan_receipt'][0]['window'],'SEALED')
        early[1].update(kind='entry',trade_id='d1',price=100.0)
        result=audit(self.scans,early,self.start,self.asof)
        self.assertEqual(result['status'],'EXECUTION_MODEL_MISMATCH')
        self.assertEqual(result['signal_availability_status'],'UNKNOWN')

    def test_missing_late_duplicate_and_delayed_entry(self):
        missing=audit(self.scans,self.events[1:],self.start,self.asof)
        self.assertEqual(missing['status'],'INVALID')
        duplicate=audit(self.scans,self.events+[self.events[0]],self.start,self.asof)
        self.assertEqual(duplicate['status'],'INVALID')
        no_reason=copy.deepcopy(self.events);no_reason[1]['description']='UNKNOWN'
        self.assertEqual(audit(self.scans,no_reason,self.start,self.asof)['status'],'INVALID')
        repeated_id=copy.deepcopy(self.events)
        for index in (1,3):repeated_id[index].update(kind='entry',trade_id='same',price=100.0)
        self.assertEqual(audit(self.scans,repeated_id,self.start,self.asof)['status'],'INVALID')
        late=copy.deepcopy(self.events);close=pd.Timestamp(late[0]['event_time_utc'])
        late[0]['captured_at_utc']=(close+pd.Timedelta(minutes=16)).isoformat();late[0]['capture_lag_seconds']=960
        self.assertEqual(audit(self.scans,late,self.start,self.asof)['status'],'INVALID')
        delayed=copy.deepcopy(self.events);delayed[1].update(kind='entry',trade_id='d1',price=100.0)
        result=audit(self.scans,delayed,self.start,self.asof)
        self.assertEqual(result['status'],'EXECUTION_MODEL_MISMATCH',result)
        self.assertEqual(result['coverage_status'],'PARTIAL_COVERAGE_UNVERIFIED')
        pending_entry=copy.deepcopy(self.events);pending_entry[-1].update(kind='entry',trade_id='pending',price=100.0)
        result=audit(self.scans,pending_entry,self.start,self.asof)
        self.assertEqual(result['status'],'EXECUTION_MODEL_MISMATCH',result)
        self.assertEqual(result['pending_delayed_entry_count'],1)

    def test_gaps_future_and_omitted_unsealed_candidate_fail(self):
        gap=copy.deepcopy(self.scans);gap.pop(2)
        self.assertEqual(audit(gap,self.events,self.start,self.asof)['status'],'COVERAGE_GAP')
        duplicate=copy.deepcopy(self.scans);duplicate[1]['snapshot']['generated_at']=duplicate[0]['snapshot']['generated_at']
        self.assertEqual(audit(duplicate,self.events,self.start,self.asof)['status'],'INVALID')
        backdated=copy.deepcopy(self.scans);backdated[0]['receipt']['captured_at_utc']=(pd.Timestamp(backdated[0]['snapshot']['generated_at'])-pd.Timedelta(seconds=1)).isoformat()
        self.assertEqual(audit(backdated,self.events,self.start,self.asof)['status'],'INVALID')
        wrong_receipt=copy.deepcopy(self.scans);wrong_receipt[0]['receipt']['scan_sha256']='wrong'
        self.assertEqual(audit(wrong_receipt,self.events,self.start,self.asof)['status'],'INVALID')
        omitted=copy.deepcopy(self.scans);rows=omitted[0]['snapshot']['symbols']['ETHUSDT']['signals_recent']
        rows.pop();omitted[0]['snapshot']['symbols']['ETHUSDT']['candidate_count']=len(rows)
        self.refresh(omitted[0])
        result=audit(omitted,self.events,self.start,self.asof)
        self.assertEqual(result['status'],'INVALID')
        self.assertIn('全部候选',result['reason'])

    def test_late_detection_and_revised_or_future_candles_fail(self):
        delayed=copy.deepcopy(self.scans)
        earlier=copy.deepcopy(delayed[0]['snapshot'])
        earlier['generated_at']=(self.start+pd.Timedelta(minutes=10,seconds=58)).isoformat()
        delayed[1]['snapshot']=earlier;delayed[1]['market_dir']=delayed[0]['market_dir']
        self.refresh(delayed[1],self.start+pd.Timedelta(minutes=11))
        delayed[2]['snapshot']['generated_at']=(self.start+pd.Timedelta(minutes=16,seconds=58)).isoformat()
        self.refresh(delayed[2],self.start+pd.Timedelta(minutes=17))
        result=audit(delayed,self.events,self.start,self.asof)
        self.assertEqual(result['status'],'INVALID',result)
        self.assertIn('已封存信号未在',result['reason'])
        stale=copy.deepcopy(self.scans)
        for index in (1,2):
            earlier=copy.deepcopy(stale[0]['snapshot']);earlier['generated_at']=stale[index]['snapshot']['generated_at']
            stale[index]['snapshot']=earlier;stale[index]['market_dir']=stale[0]['market_dir']
            self.refresh(stale[index])
        result=audit(stale,self.events,self.start,self.asof)
        self.assertEqual(result['status'],'INVALID',result)
        self.assertIn('最近已收盘',result['reason'])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);original=Path(self.scans[1]['market_dir'])
            for symbol in ('BTCUSDT','ETHUSDT'):
                shutil.copy2(original/f'{symbol}_5m.csv.gz',folder/f'{symbol}_5m.csv.gz')
            changed=folder/'BTCUSDT_5m.csv.gz';frame=pd.read_csv(changed)
            frame.loc[0,'close']=frame.loc[0,'close']+.001
            frame.to_csv(changed,index=False,compression='gzip')
            revised=copy.deepcopy(self.scans);revised[1]['market_dir']=folder
            revised[1]['snapshot']['symbols']['BTCUSDT']['data_sha256']=hashlib.sha256(changed.read_bytes()).hexdigest()
            self.refresh(revised[1])
            result=audit(revised,self.events,self.start,self.asof)
            self.assertEqual(result['status'],'INVALID')
            self.assertIn('历史 K 线',result['reason'])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);original=Path(self.scans[0]['market_dir'])
            for symbol in ('BTCUSDT','ETHUSDT'):
                shutil.copy2(original/f'{symbol}_5m.csv.gz',folder/f'{symbol}_5m.csv.gz')
            changed=folder/'ETHUSDT_5m.csv.gz';frame=pd.read_csv(changed)
            later=pd.read_csv(Path(self.scans[1]['market_dir'])/'ETHUSDT_5m.csv.gz').tail(1)
            pd.concat([frame,later],ignore_index=True).to_csv(changed,index=False,compression='gzip')
            future=copy.deepcopy(self.scans);future[0]['market_dir']=folder
            future[0]['snapshot']['symbols']['ETHUSDT']['data_sha256']=hashlib.sha256(changed.read_bytes()).hexdigest()
            self.refresh(future[0])
            result=audit(future,self.events,self.start,self.asof)
            self.assertEqual(result['status'],'INVALID')
            self.assertIn('未收盘',result['reason'])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);original=Path(self.scans[0]['market_dir'])
            for symbol in ('BTCUSDT','ETHUSDT'):
                shutil.copy2(original/f'{symbol}_5m.csv.gz',folder/f'{symbol}_5m.csv.gz')
            changed=folder/'BTCUSDT_5m.csv.gz';raw=changed.read_bytes();changed.write_bytes(raw[:len(raw)//2])
            corrupt=copy.deepcopy(self.scans);corrupt[0]['market_dir']=folder
            corrupt[0]['snapshot']['symbols']['BTCUSDT']['data_sha256']=hashlib.sha256(changed.read_bytes()).hexdigest()
            self.refresh(corrupt[0])
            self.assertEqual(audit(corrupt,self.events,self.start,self.asof)['status'],'INVALID')

    def test_cli_preserves_scan_and_event_hashes(self):
        event_dir=self.root/'events';event_dir.mkdir(exist_ok=True)
        for n,event in enumerate(self.events):(event_dir/f'{n:03}.json').write_text(json.dumps(event))
        indexes=[]
        for index,item in enumerate(self.scans):
            path=self.root/f'scan-{index}.json';path.write_text(json.dumps(item['snapshot']))
            receipt=self.root/f'receipt-{index}.json';receipt.write_text(json.dumps(item['receipt']))
            indexes.append({'scan':path.name,'market_dir':Path(item['market_dir']).name,'receipt':receipt.name})
        manifest={'schema':'paper-scan-coverage-v1','scans':indexes}
        manifest_path=self.root/'coverage-manifest.json';manifest_path.write_text(json.dumps(manifest))
        command=[sys.executable,'-m','verify.paper_scan_coverage','--manifest',str(manifest_path),'--events',str(event_dir),
                 '--start',self.start.isoformat(),'--as-of',self.asof.isoformat()]
        result=json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout)
        self.assertEqual(result['status'],'PARTIAL_COVERAGE_UNVERIFIED',result)
        self.assertEqual(result['input_sha256']['manifest'],hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        self.assertEqual(len(result['input_sha256']['events']),len(self.events))

    def test_local_receipt_is_non_overwriting_and_binds_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);scan=root/'scan.json';scan.write_text(json.dumps(self.scans[0]['snapshot']))
            output=root/'receipt.json'
            result=capture_receipt(scan,self.scans[0]['market_dir'],output)
            self.assertEqual(result['status'],'RECEIPT_UNVERIFIED')
            receipt=json.loads(output.read_text())
            self.assertEqual(receipt['scan_sha256'],hashlib.sha256(scan.read_bytes()).hexdigest())
            self.assertEqual(receipt['market_sha256'],self.scans[0]['receipt']['market_sha256'])
            with self.assertRaises(FileExistsError):capture_receipt(scan,self.scans[0]['market_dir'],output)

    def test_incremental_archive_reproduces_full_snapshot_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'archive';archive_init(archive)
            head='GENESIS';previous=None;stored=total=0
            for index,item in enumerate(self.scans):
                scan=root/f'scan-{index}.json';scan.write_text(json.dumps(item['snapshot']))
                receipt=root/f'receipt-{index}.json';receipt.write_text(json.dumps(item['receipt']))
                saved=archive_append(archive,scan,receipt,item['market_dir'],index-1,head,previous)
                self.assertIn(saved['status'],('COMMITTED','COMMIT_PUBLISHED_DURABILITY_UNKNOWN'))
                head=saved['head_sha256'];previous=item['market_dir']
                stored+=saved['stored_market_bytes'];total+=saved['market_raw_bytes']
            self.assertLessEqual(stored,total)
            result=verify_coverage(archive,self.events,self.start,self.asof,head)
            self.assertEqual(result['status'],'PARTIAL_COVERAGE_UNVERIFIED',result)
            self.assertEqual(result['archive']['fully_reconstructed_records'],len(self.scans))
            self.assertEqual(result['archive']['anchor_status'],'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR')
            self.assertEqual(result['sealed_candidates'],4)
            self.assertEqual(len(result['pending_candidates']),3)
            with self.assertRaises(ValueError):verify_coverage(archive,self.events,self.start,self.asof,'0'*64)
            commit=json.loads((archive/'commits'/'00000006.json').read_text())
            info=commit['markets']['BTCUSDT'];payload=archive/'runs'/commit['run_id']/('BTCUSDT.'+info['kind'])
            saved=payload.with_name(payload.name+'.preserved');payload.rename(saved)
            broken=verify_coverage(archive,self.events,self.start,self.asof,head)
            self.assertEqual(broken['status'],'INVALID')
            self.assertLess(broken['archive']['fully_reconstructed_records'],len(self.scans))
            saved.rename(payload)


if __name__=='__main__':unittest.main()
