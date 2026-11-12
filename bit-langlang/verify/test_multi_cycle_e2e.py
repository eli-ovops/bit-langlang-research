"""Synthetic multi-cycle rehearsal; no real monitoring or prospective records."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from .forward_scan import build_snapshot
from .forward_open import FIELDS as OPEN_FIELDS
from .forward_report import REQUIRED as CLOSED_FIELDS
from .funding_reconcile import FIELDS as FUNDING_FIELDS
from .paper_evidence_link import link as link_reports
from .paper_scan_archive import status, records, verify_coverage
from .paper_scan_source_reconcile import audit as audit_source
from .paper_scan_source_independent import audit as audit_independent_source
from .paper_scan_coverage import audit as audit_coverage
from .paper_scan_once import STEP, run
from .paper_scan_receipt import CONFIG
from .test_paper_scan_once import FakeResponse


class SyntheticMarket:
    def __init__(self,now_ms,origin_ms):self.now_ms=now_ms;self.origin_ms=origin_ms
    def get(self,url,params,timeout):
        if url.endswith('/time'):return FakeResponse({'serverTime':self.now_ms})
        symbol=params['symbol'];rows=[]
        for stamp in range(params['startTime'],params['endTime']+1,STEP):
            rows.append(self.row(symbol,stamp))
        return FakeResponse(rows)
    def row(self,symbol,stamp):
        step=Decimal('0.00001') if symbol=='BTCUSDT' else Decimal('0.00005')
        price=Decimal('100')+Decimal((stamp-self.origin_ms)//STEP)*step
        return [stamp,str(price),str(price+Decimal('.02')),str(price-Decimal('.02')),str(price),
                '10',stamp+STEP-1,'1000',1,'0','0','0']


class MultiCycleE2E(unittest.TestCase):
    def test_seven_cycles_resume_then_detect_gap_missing_and_corruption(self):
        start=pd.Timestamp('2026-10-29T23:30:00Z');start_ms=int(start.timestamp()*1000)
        count=205*288;origin_ms=start_ms-count*STEP
        cfg=hashlib.sha256(CONFIG.read_bytes()).hexdigest();state={'ms':0}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'base';source.mkdir();archive=root/'archive'
            market=SyntheticMarket(0,origin_ms)
            for symbol in ('BTCUSDT','ETHUSDT'):
                rows=[]
                for index in range(count):
                    raw=market.row(symbol,origin_ms+index*STEP)
                    rows.append([raw[0],*raw[1:6],raw[7]])
                pd.DataFrame(rows,columns=['ts','open','high','low','close','volume','turnover']).to_csv(
                    source/f'{symbol}_5m.csv.gz',index=False,compression='gzip')
            def actual_scan(command,**_):
                folder=Path(command[command.index('--market-dir')+1]);out=Path(command[command.index('--out')+1])
                days=int(command[command.index('--days')+1])
                snapshot=build_snapshot(folder,days,pd.to_datetime(state['ms'],unit='ms',utc=True))
                out.write_text(json.dumps(snapshot))
                return SimpleNamespace(returncode=0,stdout='synthetic actual scan',stderr='')
            def synthetic_receipt(scan,folder,out):
                raw=Path(scan).read_bytes();snapshot=json.loads(raw)
                captured=pd.to_datetime(state['ms']+1000,unit='ms',utc=True).isoformat()
                receipt={'schema':'paper-scan-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                         'captured_at_utc':captured,'scan_sha256':hashlib.sha256(raw).hexdigest(),
                         'config_sha256':cfg,'market_sha256':{s:snapshot['symbols'][s]['data_sha256'] for s in ('BTCUSDT','ETHUSDT')}}
                encoded=json.dumps(receipt).encode();Path(out).write_bytes(encoded)
                return {'sha256':hashlib.sha256(encoded).hexdigest(),'captured_at_utc':captured}
            previous_seq=-1;head='GENESIS';events=[]
            with patch('verify.paper_scan_once.subprocess.run',side_effect=actual_scan), \
                 patch('verify.paper_scan_once.capture_receipt',side_effect=synthetic_receipt), \
                 patch('verify.paper_scan_once.time.time_ns',side_effect=lambda:state['ms']*1_000_000):
                for index in range(7):
                    state['ms']=start_ms+(index+1)*STEP+10000
                    if index==3:
                        with patch('verify.paper_scan_archive.os.link',side_effect=InterruptedError('synthetic interruption')):
                            interrupted=run(source,root/'interrupted',3,session=SyntheticMarket(state['ms'],origin_ms),
                                            archive=archive,previous_seq=previous_seq,previous_head=head,cover_since=start)
                        self.assertEqual(interrupted['status'],'ARCHIVE_RESULT_UNKNOWN',interrupted)
                        checked=status(archive,head)
                        self.assertEqual(checked['last_sequence'],previous_seq)
                        self.assertEqual(len(checked['orphan_run_ids']),1)
                    output=root/f'cycle-{index}'
                    result=run(source,output,3,session=SyntheticMarket(state['ms'],origin_ms),
                               archive=archive,previous_seq=previous_seq,previous_head=head,cover_since=start)
                    self.assertEqual(result['status'],'PREFLIGHT_SNAPSHOT_SAVED',result)
                    self.assertEqual(result['mode'],'SYNTHETIC_SESSION_NOT_FORWARD')
                    self.assertEqual(result['added_bars'],{'BTCUSDT':1,'ETHUSDT':1})
                    self.assertEqual(pd.Timestamp(result['candidate_cover_since_utc']),start)
                    self.assertEqual(result['archive']['sequence'],index)
                    snapshot=json.loads((output/'scan.json').read_text())
                    expected_open=start+pd.Timedelta(minutes=5*index)
                    hits=[r for r in snapshot['symbols']['ETHUSDT']['signals_recent'] if pd.Timestamp(r['ts'])==expected_open]
                    self.assertEqual(len(hits),1,'合成行情应产生一条新 ETH 候选')
                    observed=pd.Timestamp(result['captured_at_utc'])+pd.Timedelta(seconds=1)
                    common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                            'symbol':'ETHUSDT','signal_time_utc':expected_open.isoformat()}
                    events.extend([{**common,'kind':'signal','event_time_utc':observed.isoformat(),
                        'captured_at_utc':(observed+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1,'description':'synthetic signal'},
                        {**common,'kind':'skip','event_time_utc':(observed+pd.Timedelta(seconds=2)).isoformat(),
                        'captured_at_utc':(observed+pd.Timedelta(seconds=3)).isoformat(),'capture_lag_seconds':1,'description':'synthetic skip'}])
                    previous_seq=index;head=result['archive']['head_sha256'];source=output/'market'
            asof=pd.to_datetime(state['ms']+5000,unit='ms',utc=True)
            checked=verify_coverage(archive,events,start,asof,head)
            self.assertEqual(checked['status'],'PARTIAL_COVERAGE_UNVERIFIED',checked)
            self.assertEqual((checked['sealed_candidates'],checked['matched_signals'],checked['matched_decisions']),(4,4,4))
            self.assertEqual(len(checked['pending_candidates']),3)
            self.assertEqual(checked['archive']['fully_reconstructed_records'],7)
            self.assertEqual(checked['archive']['public_source_bound_records'],7)
            self.assertEqual(checked['archive']['public_source_missing_records'],0)
            self.assertEqual(checked['archive']['initial_source_status'],'BOUND_UNVERIFIED')
            source_check=audit_source(archive,head)
            self.assertEqual(source_check['status'],'PARTIAL_SOURCE_REPLAY',source_check)
            self.assertEqual(source_check['initial_baseline'],'MATCHED_UNVERIFIED')
            self.assertEqual(source_check['matched_transitions'],7)
            independent=audit_independent_source(archive,head)
            self.assertEqual(independent['status'],'PARTIAL_INDEPENDENT_CROSSCHECK',independent)
            self.assertEqual(independent['matched_transitions'],7)
            self.assertEqual(independent['unknown_transitions'],0)
            self.assertEqual(len(checked['archive']['orphan_run_ids']),1)
            # Link actual outputs from both CLIs using the same synthetic
            # event directory and archived scan. No trades are fabricated.
            event_dir=root/'linked-events';event_dir.mkdir()
            for i,event in enumerate(events):
                (event_dir/f'{i:03}.json').write_text(json.dumps(event))
            coverage_cli=json.loads(subprocess.run([sys.executable,'-m','verify.paper_scan_archive','audit',
                '--archive',str(archive),'--events',str(event_dir),'--start',start.isoformat(),
                '--as-of',asof.isoformat(),'--expected-head',head],check=True,capture_output=True,text=True).stdout)
            pd.DataFrame(columns=CLOSED_FIELDS).to_csv(root/'linked-closed.csv',index=False)
            pd.DataFrame(columns=OPEN_FIELDS).to_csv(root/'linked-open.csv',index=False)
            pd.DataFrame(columns=FUNDING_FIELDS).to_csv(root/'linked-funding.csv',index=False)
            (root/'linked-manifest.json').write_text(json.dumps({'schema':'paper-exit-batch-v1','entries':{},'exits':{}}))
            last=root/'cycle-6'
            batch_cli=json.loads(subprocess.run([sys.executable,'-m','verify.paper_exit_batch',
                '--scan',str(last/'scan.json'),'--events',str(event_dir),'--market-dir',str(last/'market'),
                '--closed',str(root/'linked-closed.csv'),'--open',str(root/'linked-open.csv'),
                '--funding',str(root/'linked-funding.csv'),'--manifest',str(root/'linked-manifest.json'),
                '--start',start.isoformat(),'--as-of',asof.isoformat()],check=True,capture_output=True,text=True).stdout)
            self.assertEqual(batch_cli['status'],'NO_ENTRY_EVIDENCE',batch_cli)
            linked=link_reports(coverage_cli,batch_cli,independent)
            self.assertEqual(linked['formal_link'],'MATCHED_UNVERIFIED',linked)
            self.assertEqual(linked['status'],'UNKNOWN_INCOMPLETE')
            self.assertGreater(linked['unsealed_seconds'],0)
            # Add one synthetic delayed entry, observed stop and exit, then
            # rerun both real audit CLIs over exactly the same event files.
            signal=events[0];signal_capture=pd.Timestamp(signal['captured_at_utc'])
            common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                    'symbol':'ETHUSDT','trade_id':'paper-1'}
            def quote(at,bid,ask):
                ms=lambda delta:int((at+pd.Timedelta(milliseconds=delta)).timestamp()*1000)
                return {'schema':'paper-quote-research-v1','source':'Binance USD-M public REST',
                    'verification':'PUBLIC_UNVERIFIED','config_sha256':cfg,
                    'requests':[{'local_start_ms':ms(0),'local_end_ms':ms(20),'body':{'serverTime':ms(10)}},
                        {'local_start_ms':ms(100),'local_end_ms':ms(200),'body':{'symbol':'ETHUSDT',
                         'time':ms(150),'bidPrice':str(bid),'askPrice':str(ask),'bidQty':'3','askQty':'3'}},
                        {'local_start_ms':ms(300),'local_end_ms':ms(320),'body':{'serverTime':ms(310)}}]}
            def event(kind,at,price,**extra):
                return {**common,'kind':kind,'event_time_utc':at.isoformat(),
                    'captured_at_utc':(at+pd.Timedelta(milliseconds=100)).isoformat(),
                    'capture_lag_seconds':.1,'price':price,**extra}
            entry_quote_time=signal_capture+pd.Timedelta(seconds=1)
            entry_quote=quote(entry_quote_time,100,100.1);entry_at=entry_quote_time+pd.Timedelta(milliseconds=600)
            entry=event('entry',entry_at,100.1*1.0002,signal_time_utc=signal['signal_time_utc'])
            trigger_time=pd.Timestamp(entry['captured_at_utc'])+pd.Timedelta(seconds=1)
            trigger=quote(trigger_time,99.6,99.7);mark_at=trigger_time+pd.Timedelta(milliseconds=600)
            mark=event('mark',mark_at,99.6)
            exit_quote_time=pd.Timestamp(mark['captured_at_utc'])+pd.Timedelta(seconds=1)
            exit_quote=quote(exit_quote_time,99.5,99.6);exit_at=exit_quote_time+pd.Timedelta(milliseconds=600)
            exit_event=event('exit',exit_at,99.5*.9998)
            trade_events=[events[0],entry]+events[2:]+[mark,exit_event]
            trade_dir=root/'trade-events';trade_dir.mkdir()
            for i,item in enumerate(trade_events):(trade_dir/f'{i:03}.json').write_text(json.dumps(item))
            evidence=root/'trade-evidence';evidence.mkdir()
            def save(name,obj):
                path=evidence/name;path.write_text(json.dumps(obj));return path
            entry_q=save('entry-quote.json',entry_quote);trigger_q=save('trigger.json',trigger)
            exit_q=save('exit-quote.json',exit_quote)
            def receipt(name,path,at):
                return save(name,{'schema':'paper-quote-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                    'config_sha256':cfg,'quote_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'captured_at_utc':(at+pd.Timedelta(milliseconds=420)).isoformat()})
            entry_receipt=receipt('entry-receipt.json',entry_q,entry_quote_time)
            trigger_receipt=receipt('trigger-receipt.json',trigger_q,trigger_time)
            funding_dir=root/'trade-funding';funding_dir.mkdir()
            funding_end=exit_at+pd.Timedelta(seconds=61)
            funding_manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
                'start_utc':(entry_at-pd.Timedelta(minutes=2)).isoformat(),'end_utc_exclusive':funding_end.isoformat(),
                'captured_at_utc':(funding_end+pd.Timedelta(seconds=1)).isoformat(),
                'query_server_time_ms':int(funding_end.timestamp()*1000),
                'server_time_ms':int((funding_end+pd.Timedelta(seconds=1)).timestamp()*1000),'symbols':{}}
            for symbol in ('BTCUSDT','ETHUSDT'):
                data=b'[]';(funding_dir/(symbol+'.json')).write_bytes(data)
                funding_manifest['symbols'][symbol]={'file':symbol+'.json','sha256':hashlib.sha256(data).hexdigest(),'count':0}
            (funding_dir/'manifest.json').write_text(json.dumps(funding_manifest))
            fee=(entry['price']+exit_event['price'])*.0005
            row={'trade_id':'paper-1','entry_time':entry['event_time_utc'],'exit_time':exit_event['event_time_utc'],
                 'symbol':'ETHUSDT','side':'long','entry':entry['price'],'stop':entry['price']*.996,
                 'exit':exit_event['price'],'qty':1,'equity_at_entry':2000,'fee_cost':fee,'funding_cost':0,
                 'five_q_pass':'1','stop_placed':'1','added':'0','reversed':'0','plan_deviation':'0',
                 'reference_entry':100.1,'reference_exit':99.5,'reference_source':'synthetic',
                 'margin_at_entry':entry['price']/5}
            pd.DataFrame([row]).to_csv(root/'trade-closed.csv',index=False)
            relative=lambda p:str(p.relative_to(root))
            manifest={'schema':'paper-exit-batch-v1','entries':{'paper-1':relative(entry_q)},
                'exits':{'paper-1':{'kind':'bid_stop','signal':relative(trade_dir/'000.json'),
                    'entry':relative(trade_dir/'001.json'),'mark':relative(trade_dir/f'{len(trade_events)-2:03}.json'),
                    'trigger_quote':relative(trigger_q),'exit':relative(trade_dir/f'{len(trade_events)-1:03}.json'),
                    'exit_quote':relative(exit_q)}},
                'positions':{'paper-1':{'entry_quote':relative(entry_q),'entry_receipt':relative(entry_receipt),
                    'samples':[{'quote':relative(trigger_q),'receipt':relative(trigger_receipt)}],
                    'trigger_quote':relative(trigger_q)}}}
            (root/'trade-manifest.json').write_text(json.dumps(manifest))
            coverage_trade=json.loads(subprocess.run([sys.executable,'-m','verify.paper_scan_archive','audit',
                '--archive',str(archive),'--events',str(trade_dir),'--start',start.isoformat(),
                '--as-of',asof.isoformat(),'--expected-head',head],check=True,capture_output=True,text=True).stdout)
            batch_trade=json.loads(subprocess.run([sys.executable,'-m','verify.paper_exit_batch',
                '--scan',str(last/'scan.json'),'--events',str(trade_dir),'--market-dir',str(last/'market'),
                '--closed',str(root/'trade-closed.csv'),'--open',str(root/'linked-open.csv'),
                '--funding',str(root/'linked-funding.csv'),'--manifest',str(root/'trade-manifest.json'),
                '--schedule',str(funding_dir),'--start',start.isoformat(),'--as-of',asof.isoformat()],
                check=True,capture_output=True,text=True).stdout)
            self.assertEqual(batch_trade['status'],'PARTIAL_NOT_REGISTERED',batch_trade)
            self.assertEqual(batch_trade['funding_check']['status'],'PARTIAL')
            self.assertEqual(batch_trade['position_path_check']['status'],'PARTIAL_DISCRETE_UNVERIFIED')
            expected_net=exit_event['price']-entry['price']-fee
            expected_r=expected_net/(entry['price']-row['stop'])
            self.assertAlmostEqual(batch_trade['totals']['net_pnl_usdt'],expected_net,places=6)
            self.assertAlmostEqual(batch_trade['totals']['mean_net_R'],expected_r,places=6)
            linked_trade=link_reports(coverage_trade,batch_trade,independent)
            self.assertEqual(linked_trade['formal_link'],'MATCHED_UNVERIFIED',linked_trade)
            self.assertEqual(linked_trade['source_response_crosscheck'],'MATCHED_UNVERIFIED')
            self.assertEqual(linked_trade['status'],'EXECUTION_MODEL_MISMATCH',linked_trade)
            self.assertGreater(linked_trade['unsealed_seconds'],0)
            missing=verify_coverage(archive,events[1:],start,asof,head)
            self.assertEqual(missing['status'],'INVALID')
            items,_,_=records(archive,head)
            summaries=[{'snapshot':x['snapshot'],'receipt':x['receipt']} for x in items]
            summaries.pop(2)
            self.assertEqual(audit_coverage(summaries,events,start,asof)['status'],'COVERAGE_GAP')
            item=items[-1];info=item['commit']['markets']['BTCUSDT']
            path=item['run']/('BTCUSDT.'+info['kind']);raw=path.read_bytes();path.write_bytes(raw+b'corrupt')
            corrupt=verify_coverage(archive,events,start,asof,head)
            self.assertEqual(corrupt['status'],'INVALID')
            self.assertLess(corrupt['archive']['fully_reconstructed_records'],7)


if __name__=='__main__':unittest.main()
