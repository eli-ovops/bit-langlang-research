"""One synthetic scan-to-EMA-exit chain; never prospective or venue evidence."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .forward_open import FIELDS as OPEN_FIELDS
from .forward_scan import signal_records
from .funding_reconcile import FIELDS as FUNDING_FIELDS
from .paper_delayed_signal_reconcile import reconcile as reconcile_entry
from .paper_exit_batch import reconcile as reconcile_batch
from .paper_evidence_link import link as link_reports
from .paper_timed_exit import check, make_observation
from .tph_frozen_audit import signals
from . import test_depth_sessions_audit as depth_fixtures


class DelayedExitIntegration(unittest.TestCase):
    def test_scan_to_ema_exit_and_funding_is_only_partial(self):
        ts=pd.date_range(end='2026-10-29T23:55:00Z',periods=230*288,freq='5min')
        generated=ts[-1]+pd.Timedelta(minutes=6)
        cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);frames={};hashes={}
            for symbol,step in (('BTCUSDT',.00001),('ETHUSDT',.00005)):
                values=100+pd.RangeIndex(len(ts))*step
                frame=pd.DataFrame({'ts':ts,'open':values,'high':values+.02,'low':values-.02,'close':values})
                if symbol=='ETHUSDT':
                    frame.loc[len(frame)-1,'low']=frame.iloc[-1].open-.3
                    frame.loc[len(frame)-1,'close']=frame.iloc[-1].open-.3
                frames[symbol]=frame
                saved=frame.copy();saved.ts=saved.ts.astype('int64')//10**6
                path=root/f'{symbol}_5m.csv.gz';saved.to_csv(path,index=False,compression='gzip')
                hashes[symbol]=hashlib.sha256(path.read_bytes()).hexdigest()
            cutoff=ts[-5]
            snapshot={'generated_at':generated.isoformat(),'config_sha256':cfg,'btc_data_status':{'status':'FRESH'},'symbols':{}}
            for symbol,frame in frames.items():
                hit,_,_=signals(frames['BTCUSDT'],frame)
                rows=signal_records(frame,hit,cutoff)
                snapshot['symbols'][symbol]={'data_status':{'status':'FRESH'},'data_sha256':hashes[symbol],
                    'candidate_count':len(rows),'candidate_window_start':cutoff.isoformat(),'signals_recent':rows}
            candidates=snapshot['symbols']['ETHUSDT']['signals_recent']
            self.assertGreater(len(candidates),0)
            common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,'symbol':'ETHUSDT'}
            events=[];first_entry=None;first_signal=None
            def quote(start,bid,ask):
                ms=lambda n:int((start+pd.Timedelta(milliseconds=n)).timestamp()*1000)
                return {'schema':'paper-quote-research-v1','source':'Binance USD-M public REST',
                    'verification':'PUBLIC_UNVERIFIED','config_sha256':cfg,
                    'requests':[{'local_start_ms':ms(0),'local_end_ms':ms(20),'body':{'serverTime':ms(10)}},
                                {'local_start_ms':ms(100),'local_end_ms':ms(200),'body':{'symbol':'ETHUSDT','time':ms(150),
                                 'bidPrice':str(bid),'askPrice':str(ask),'bidQty':'3','askQty':'3'}},
                                {'local_start_ms':ms(300),'local_end_ms':ms(320),'body':{'serverTime':ms(310)}}]}
            for index,row in enumerate(candidates):
                close=pd.Timestamp(row['ts'])+pd.Timedelta(minutes=5)
                signal={**common,'kind':'signal','signal_time_utc':pd.Timestamp(row['ts']).isoformat(),
                        'event_time_utc':close.isoformat(),'captured_at_utc':(close+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1}
                decision={**common,'kind':'entry' if index==0 else 'skip','signal_time_utc':signal['signal_time_utc'],
                          'event_time_utc':(close+pd.Timedelta(seconds=3)).isoformat(),
                          'captured_at_utc':(close+pd.Timedelta(seconds=4)).isoformat(),'capture_lag_seconds':1}
                if index==0:
                    ask=row['entry_next_open'];decision.update(trade_id='e1',price=ask*1.0002)
                    first_signal,first_entry=signal,decision
                    entry_quote=quote(close+pd.Timedelta(seconds=2),ask-.01,ask)
                events.extend([signal,decision])
            entry_raw=json.dumps(first_entry).encode();scan_raw=json.dumps(snapshot).encode()
            market_raw=(root/'ETHUSDT_5m.csv.gz').read_bytes()
            observed=generated+pd.Timedelta(seconds=1)
            observation=make_observation('ema20',first_entry,entry_raw,observed,signal_day='2026-10-29',
                                         scan_raw=scan_raw,market_raw=market_raw)
            bid=first_entry['price']+.1;exit_quote=quote(observed+pd.Timedelta(seconds=1),bid,bid+.01)
            exit_time=observed+pd.Timedelta(seconds=2)
            exit_event={**common,'kind':'exit','trade_id':'e1','price':bid*.9998,
                        'event_time_utc':exit_time.isoformat(),'captured_at_utc':(exit_time+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1}
            qty=2;price=first_entry['price']
            ledger=pd.DataFrame([{'trade_id':'e1','entry_time':first_entry['event_time_utc'],'exit_time':exit_event['event_time_utc'],
                'symbol':'ETHUSDT','side':'long','entry':price,'stop':price*.996,'exit':exit_event['price'],'qty':qty,
                'equity_at_entry':2000,'fee_cost':qty*(price+exit_event['price'])*.0005,'funding_cost':0,
                'five_q_pass':'1','stop_placed':'1','added':'0','reversed':'0','plan_deviation':'0',
                'reference_entry':ask,'reference_exit':bid,'reference_source':'synthetic quote', 'margin_at_entry':qty*price/5}])
            now=exit_time+pd.Timedelta(seconds=100);all_events=events+[exit_event]
            entry_result=reconcile_entry(snapshot,all_events,root,ledger,pd.DataFrame(columns=OPEN_FIELDS),
                                         {'e1':{'quote':entry_quote,'sha256':'synthetic'}},cutoff,now)
            self.assertEqual(entry_result['status'],'PARTIAL_CANDIDATE_NOT_REGISTERED',entry_result)
            self.assertEqual(entry_result['original_signal_status'],'EXECUTION_MODEL_MISMATCH')
            schedule=root/'funding';schedule.mkdir();end=exit_time+pd.Timedelta(seconds=61)
            manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
                      'start_utc':(pd.Timestamp(first_entry['event_time_utc'])-pd.Timedelta(minutes=2)).isoformat(),
                      'end_utc_exclusive':end.isoformat(),'captured_at_utc':(end+pd.Timedelta(seconds=1)).isoformat(),
                      'query_server_time_ms':int(end.timestamp()*1000),'server_time_ms':int((end+pd.Timedelta(seconds=1)).timestamp()*1000),'symbols':{}}
            for symbol in ('BTCUSDT','ETHUSDT'):
                raw=b'[]';(schedule/(symbol+'.json')).write_bytes(raw)
                manifest['symbols'][symbol]={'file':symbol+'.json','sha256':hashlib.sha256(raw).hexdigest(),'count':0}
            (schedule/'manifest.json').write_text(json.dumps(manifest))
            result=check(first_signal,first_entry,entry_raw,entry_quote,observation,exit_event,exit_quote,ledger,
                         pd.DataFrame(columns=FUNDING_FIELDS),cutoff,now,schedule=schedule,scan_raw=scan_raw,market_raw=market_raw)
            self.assertEqual(result['status'],'PARTIAL_NOT_REGISTERED',result)
            self.assertEqual(result['report']['n'],1)
            self.assertEqual(result['funding_check']['status'],'PARTIAL')
            self.assertAlmostEqual(result['report']['net_pnl_usdt'],result['costs_vs_mid_unverified']['net_pnl_reconciled_usdt'])
            self.assertGreaterEqual(len(candidates),2)
            signal2=events[2];close2=pd.Timestamp(signal2['event_time_utc']);ask2=candidates[1]['entry_next_open']
            entry2={**events[3],'kind':'entry','trade_id':'e2','price':ask2*1.0002}
            entry_quote2=quote(close2+pd.Timedelta(seconds=2),ask2-.01,ask2)
            trigger_bid=entry2['price']*.996-.01
            trigger_quote2=quote(close2+pd.Timedelta(seconds=10),trigger_bid,trigger_bid+.01)
            mark2={**common,'kind':'mark','trade_id':'e2','price':trigger_bid,
                   'event_time_utc':(close2+pd.Timedelta(seconds=11)).isoformat(),
                   'captured_at_utc':(close2+pd.Timedelta(seconds=12)).isoformat(),'capture_lag_seconds':1}
            exit_quote2=quote(close2+pd.Timedelta(seconds=13),trigger_bid-.01,trigger_bid)
            exit2={**common,'kind':'exit','trade_id':'e2','price':(trigger_bid-.01)*.9998,
                   'event_time_utc':(close2+pd.Timedelta(seconds=14)).isoformat(),
                   'captured_at_utc':(close2+pd.Timedelta(seconds=15)).isoformat(),'capture_lag_seconds':1}
            row2=ledger.iloc[0].to_dict();row2.update(trade_id='e2',entry_time=entry2['event_time_utc'],
                exit_time=exit2['event_time_utc'],entry=entry2['price'],stop=entry2['price']*.996,exit=exit2['price'],qty=1,
                fee_cost=(entry2['price']+exit2['price'])*.0005,reference_entry=ask2,reference_exit=trigger_bid-.01,
                margin_at_entry=entry2['price']/5)
            mixed=pd.concat([ledger,pd.DataFrame([row2])],ignore_index=True)
            mixed_events=events.copy();mixed_events[3]=entry2;mixed_events.extend([exit_event,mark2,exit2])
            raw_quote1=json.dumps(entry_quote).encode()
            quotes={'e1':{'quote':entry_quote,'sha256':hashlib.sha256(raw_quote1).hexdigest()},
                    'e2':{'quote':entry_quote2,'sha256':hashlib.sha256(json.dumps(entry_quote2).encode()).hexdigest()}}
            bundles={'e1':{'kind':'ema20','signal':first_signal,'entry':first_entry,'entry_raw':entry_raw,
                           'observation':observation,'exit':exit_event,'exit_quote':exit_quote,
                           'scan_raw':scan_raw,'market_raw':market_raw},
                     'e2':{'kind':'bid_stop','signal':signal2,'entry':entry2,'mark':mark2,'trigger_quote':trigger_quote2,
                           'exit':exit2,'exit_quote':exit_quote2}}
            batch=reconcile_batch(snapshot,mixed_events,root,mixed,pd.DataFrame(columns=OPEN_FIELDS),
                                  pd.DataFrame(columns=FUNDING_FIELDS),quotes,bundles,cutoff,now,schedule=schedule)
            self.assertEqual(batch['status'],'UNKNOWN_POSITION_PATH',batch)
            self.assertEqual(batch['evidence_gaps'],['CLOSED_POSITION_PATH'])
            self.assertEqual(batch['signal_scan_coverage'],'UNKNOWN_NOT_CHECKED')
            self.assertEqual(pd.Timestamp(batch['observation_interval']['start_utc']),pd.Timestamp(cutoff))
            self.assertEqual(pd.Timestamp(batch['observation_interval']['as_of_utc']),pd.Timestamp(now))
            self.assertEqual(batch['position_path_check']['status'],'UNKNOWN_NOT_PROVIDED')
            self.assertEqual(batch['position_path_check']['scope'],'CLOSED_ONLY')
            self.assertEqual(batch['open_position_path_check'],'NO_OPEN_RECORDS_SUPPLIED')
            self.assertEqual(batch['position_definition_sha256'],hashlib.sha256(
                (Path(__file__).parent.parent/'docs/批量出场-持仓观察交叉核对-事前定义-20261030.md').read_bytes()).hexdigest())
            self.assertEqual(batch['totals']['closed_trades'],2)
            raw_net=[];raw_r=[]
            for item in mixed.itertuples():
                net=(item.exit-item.entry)*item.qty-item.fee_cost-item.funding_cost
                raw_net.append(net);raw_r.append(net/((item.entry-item.stop)*item.qty))
            self.assertAlmostEqual(batch['totals']['net_pnl_usdt'],sum(raw_net),places=6)
            self.assertAlmostEqual(batch['totals']['mean_net_R'],sum(raw_r)/2,places=6)
            self.assertNotAlmostEqual(batch['totals']['mean_net_R'],sum(raw_net)/sum((x.entry-x.stop)*x.qty for x in mixed.itertuples()),places=3)
            def receipt(raw,at):
                return json.dumps({'schema':'paper-quote-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
                    'captured_at_utc':at.isoformat(),'quote_sha256':hashlib.sha256(raw).hexdigest(),'config_sha256':cfg}).encode()
            entry_start=pd.Timestamp(first_entry['event_time_utc'])
            entry_receipt=receipt(raw_quote1,entry_start-pd.Timedelta(seconds=.5))
            hit_start=entry_start+pd.Timedelta(seconds=5)
            hit_quote=quote(hit_start,first_entry['price']*.996-.01,first_entry['price']*.996+.01)
            hit_raw=json.dumps(hit_quote).encode();hit_receipt=receipt(hit_raw,hit_start+pd.Timedelta(seconds=.5))
            position_evidence={'e1':{'entry_quote_raw':raw_quote1,'entry_receipt_raw':entry_receipt,
                'samples':[{'quote_raw':hit_raw,'receipt_raw':hit_receipt}]}}
            conflict=reconcile_batch(snapshot,mixed_events,root,mixed,pd.DataFrame(columns=OPEN_FIELDS),
                pd.DataFrame(columns=FUNDING_FIELDS),quotes,bundles,cutoff,now,schedule=schedule,
                position_evidence=position_evidence)
            self.assertEqual(conflict['status'],'EXECUTION_MODEL_MISMATCH',conflict)
            self.assertEqual(conflict['position_path_check']['trades']['e2']['status'],'UNKNOWN_NOT_PROVIDED')
            incomplete=reconcile_batch(snapshot,mixed_events,root,mixed,pd.DataFrame(columns=OPEN_FIELDS),
                                       pd.DataFrame(columns=FUNDING_FIELDS),quotes,{'e1':bundles['e1']},cutoff,now,schedule=schedule)
            self.assertEqual(incomplete['status'],'INVALID')
            bad=mixed.copy();bad.loc[1,'fee_cost']=0
            failed=reconcile_batch(snapshot,mixed_events,root,bad,pd.DataFrame(columns=OPEN_FIELDS),
                                   pd.DataFrame(columns=FUNDING_FIELDS),quotes,bundles,cutoff,now,schedule=schedule)
            self.assertEqual(failed['status'],'INVALID',failed)
            insolvent=mixed.copy();insolvent.loc[0,'funding_cost']=5000
            negative_equity=reconcile_batch(snapshot,mixed_events,root,insolvent,pd.DataFrame(columns=OPEN_FIELDS),
                                           pd.DataFrame(columns=FUNDING_FIELDS),quotes,bundles,cutoff,now,schedule=schedule)
            self.assertEqual(negative_equity['status'],'STOP',negative_equity)
            self.assertEqual(negative_equity['equity_check']['status'],'STOP')
            event_dir=root/'batch-events';event_dir.mkdir();event_paths={}
            for n,event in enumerate(mixed_events):
                name=f'{n:03}.json';(event_dir/name).write_text(json.dumps(event))
                event_paths[json.dumps(event,sort_keys=True)]='batch-events/'+name
            event_path=lambda value:event_paths[json.dumps(value,sort_keys=True)]
            for name,value in (('entry1',entry_quote),('entry2',entry_quote2),('exit1',exit_quote),
                               ('exit2',exit_quote2),('trigger2',trigger_quote2),('observation',observation)):
                (root/(name+'.json')).write_text(json.dumps(value))
            (root/'batch-scan.json').write_bytes(scan_raw)
            mixed.to_csv(root/'batch-closed.csv',index=False)
            pd.DataFrame(columns=OPEN_FIELDS).to_csv(root/'batch-open.csv',index=False)
            pd.DataFrame(columns=FUNDING_FIELDS).to_csv(root/'batch-funding.csv',index=False)
            manifest={'schema':'paper-exit-batch-v1','entries':{'e1':'entry1.json','e2':'entry2.json'},
                'exits':{'e1':{'kind':'ema20','signal':event_path(first_signal),'entry':event_path(first_entry),
                    'exit':event_path(exit_event),'exit_quote':'exit1.json','observation':'observation.json',
                    'scan':'batch-scan.json','market':'ETHUSDT_5m.csv.gz'},
                    'e2':{'kind':'bid_stop','signal':event_path(signal2),'entry':event_path(entry2),
                    'exit':event_path(exit2),'exit_quote':'exit2.json','mark':event_path(mark2),'trigger_quote':'trigger2.json'}}}
            (root/'batch-manifest.json').write_text(json.dumps(manifest))
            cmd=[sys.executable,'-m','verify.paper_exit_batch','--scan',str(root/'batch-scan.json'),
                 '--events',str(event_dir),'--market-dir',str(root),'--closed',str(root/'batch-closed.csv'),
                 '--open',str(root/'batch-open.csv'),'--funding',str(root/'batch-funding.csv'),
                 '--manifest',str(root/'batch-manifest.json'),'--schedule',str(schedule),
                 '--start',cutoff.isoformat(),'--as-of',now.isoformat()]
            cli=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(cli['status'],'UNKNOWN_POSITION_PATH',cli)
            self.assertEqual(cli['totals'],batch['totals'])
            self.assertEqual(cli['input_sha256']['manifest'],hashlib.sha256((root/'batch-manifest.json').read_bytes()).hexdigest())
            # Synthetic coverage stub: exercises the real batch CLI output's
            # interval and hashes; it does not claim a real archive audit.
            coverage_stub={'status':'PARTIAL_COVERAGE_UNVERIFIED','start_utc':cutoff.isoformat(),
                'as_of_utc':now.isoformat(),'event_sha256':cli['input_sha256']['events'],
                'scans':[{'scan_sha256':cli['input_sha256']['scan']}], 'unsealed_seconds':900,
                'signal_availability_status':'ORDERED_BUT_UNVERIFIED',
                'archive':{'head_sha256':'a'*64,'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR',
                           'fully_reconstructed_records':1,'public_source_bound_records':1,
                           'public_source_missing_records':0,'initial_source_status':'BOUND_UNVERIFIED'}}
            linked=link_reports(coverage_stub,cli)
            self.assertEqual(linked['formal_link'],'MATCHED_UNVERIFIED')
            self.assertEqual(linked['status'],'UNKNOWN_INCOMPLETE')
            self.assertEqual(linked['batch_evidence_gaps'],['CLOSED_POSITION_PATH'])
            (root/'entry-receipt.json').write_bytes(entry_receipt)
            (root/'hit.json').write_bytes(hit_raw);(root/'hit-receipt.json').write_bytes(hit_receipt)
            manifest['positions']={'e1':{'entry_quote':'entry1.json','entry_receipt':'entry-receipt.json',
                                       'samples':[{'quote':'hit.json','receipt':'hit-receipt.json'}]}}
            (root/'batch-manifest.json').write_text(json.dumps(manifest))
            conflict_cli=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(conflict_cli['status'],'EXECUTION_MODEL_MISMATCH',conflict_cli)
            self.assertEqual(conflict_cli['position_path_check']['trades']['e2']['status'],'UNKNOWN_NOT_PROVIDED')
            manifest['positions']['e2']={'entry_quote':'missing.json','entry_receipt':'entry-receipt.json','samples':[]}
            (root/'batch-manifest.json').write_text(json.dumps(manifest))
            conflict_missing=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(conflict_missing['status'],'EXECUTION_MODEL_MISMATCH',conflict_missing)
            self.assertEqual(conflict_missing['position_path_check']['trades']['e2']['status'],'INVALID')
            manifest['positions']={'e1':[]}
            (root/'batch-manifest.json').write_text(json.dumps(manifest))
            invalid_cli=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(invalid_cli['status'],'INVALID',invalid_cli)
            # One trade remains open: include its mark, equity and funding only
            # through the snapshot, never count it as a closed result.
            mark_time=now-pd.Timedelta(seconds=61)
            open_mark={**common,'kind':'mark','trade_id':'e2','price':entry2['price']+.01,
                       'event_time_utc':mark_time.isoformat(),
                       'captured_at_utc':(mark_time+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1}
            open_row={'trade_id':'e2','entry_time':entry2['event_time_utc'],'symbol':'ETHUSDT','side':'long',
                      'entry':entry2['price'],'stop':entry2['price']*.996,'qty':1,'equity_at_entry':2000,
                      'mark_price':open_mark['price'],'mark_time':mark_time.isoformat(),'mark_source':'synthetic',
                      'entry_fee':entry2['price']*.0005,'funding_cost':0,'margin_at_entry':entry2['price']/5}
            open_schedule=root/'funding-open';open_schedule.mkdir()
            open_manifest=json.loads((schedule/'manifest.json').read_text());open_manifest.update(end_utc_exclusive=now.isoformat(),captured_at_utc=now.isoformat(),
                query_server_time_ms=int(now.timestamp()*1000),server_time_ms=int(now.timestamp()*1000))
            for symbol in ('BTCUSDT','ETHUSDT'):(open_schedule/(symbol+'.json')).write_bytes(b'[]')
            (open_schedule/'manifest.json').write_text(json.dumps(open_manifest))
            open_events=events.copy();open_events[3]=entry2;open_events.extend([exit_event,open_mark])
            partial=reconcile_batch(snapshot,open_events,root,ledger,pd.DataFrame([open_row]),
                                    pd.DataFrame(columns=FUNDING_FIELDS),quotes,{'e1':bundles['e1']},cutoff,now,schedule=open_schedule)
            self.assertEqual(partial['status'],'UNKNOWN_POSITION_PATH',partial)
            self.assertEqual(partial['evidence_gaps'],['CLOSED_POSITION_PATH','OPEN_POSITION_PATH'])
            self.assertEqual(partial['open_position_path_check']['status'],'UNKNOWN_OBSERVATION')
            self.assertEqual(partial['totals']['closed_trades'],1)
            self.assertEqual(partial['totals']['open_positions'],1)
            self.assertEqual(partial['funding_check']['open_after_snapshot_unknown'],['e2'])
            raw2=json.dumps(entry_quote2).encode();enter2=pd.Timestamp(entry2['event_time_utc'])
            receipt2=receipt(raw2,enter2-pd.Timedelta(seconds=.5))
            open_hit_start=enter2+pd.Timedelta(seconds=5)
            open_hit=json.dumps(quote(open_hit_start,entry2['price']*.996-.01,entry2['price']*.996+.01)).encode()
            open_hit_receipt=receipt(open_hit,open_hit_start+pd.Timedelta(seconds=.5))
            open_evidence={'e2':{'signal':signal2,'entry':entry2,'entry_quote_raw':raw2,
                'entry_receipt_raw':receipt2,'samples':[{'quote_raw':open_hit,'receipt_raw':open_hit_receipt}]}}
            stop=reconcile_batch(snapshot,open_events,root,ledger,pd.DataFrame([open_row]),pd.DataFrame(columns=FUNDING_FIELDS),
                                 quotes,{'e1':bundles['e1']},cutoff,now,schedule=open_schedule,open_position_evidence=open_evidence)
            self.assertEqual(stop['status'],'STOP',stop)
            self.assertTrue(stop['open_position_path_check']['observed_stop_or_overdue'])
            self.assertIn('avg_net_R',stop['risk_check']['closed'])
            altered=copy.deepcopy(open_evidence);altered['e2']['entry']['capture_lag_seconds']=2
            invalid=reconcile_batch(snapshot,open_events,root,ledger,pd.DataFrame([open_row]),pd.DataFrame(columns=FUNDING_FIELDS),
                                    quotes,{'e1':bundles['e1']},cutoff,now,schedule=open_schedule,open_position_evidence=altered)
            self.assertEqual(invalid['status'],'INVALID',invalid)
            depth_path=depth_fixtures.DepthSessionsTests().session(root/'depth-session',
                (enter2+pd.Timedelta(seconds=10)).isoformat(),(enter2+pd.Timedelta(seconds=11)).isoformat())
            joint=reconcile_batch(snapshot,open_events,root,ledger,pd.DataFrame([open_row]),pd.DataFrame(columns=FUNDING_FIELDS),
                                  quotes,{'e1':bundles['e1']},cutoff,now,schedule=open_schedule,
                                  open_position_evidence=altered,depth_session_paths=[depth_path])
            self.assertEqual(joint['status'],'STOP',joint)
            self.assertEqual(joint['open_position_path_check']['status'],'INVALID')
            self.assertEqual(joint['open_depth_session_check']['status'],'STOP')
            self.assertIn('avg_net_R',joint['risk_check']['closed'])
            open_dir=root/'open-events';open_dir.mkdir()
            for index,event in enumerate(open_events):(open_dir/f'{index:03}.json').write_text(json.dumps(event))
            ledger.to_csv(root/'open-closed.csv',index=False);pd.DataFrame([open_row]).to_csv(root/'open-snapshot.csv',index=False)
            (root/'open-entry2.json').write_text(json.dumps(entry2));(root/'open-receipt2.json').write_bytes(receipt2)
            (root/'open-hit.json').write_bytes(open_hit);(root/'open-hit-receipt.json').write_bytes(open_hit_receipt)
            combined={'schema':'paper-exit-batch-v1','entries':{'e1':'entry1.json','e2':'entry2.json'},
                      'exits':{'e1':manifest['exits']['e1']},
                      'open_positions':{'e2':{'signal':event_path(signal2),'entry':'open-entry2.json',
                          'entry_quote':'entry2.json','entry_receipt':'open-receipt2.json',
                          'samples':[{'quote':'open-hit.json','receipt':'open-hit-receipt.json'}]}}}
            (root/'open-batch-manifest.json').write_text(json.dumps(combined))
            open_cmd=[sys.executable,'-m','verify.paper_exit_batch','--scan',str(root/'batch-scan.json'),
                '--events',str(open_dir),'--market-dir',str(root),'--closed',str(root/'open-closed.csv'),
                '--open',str(root/'open-snapshot.csv'),'--funding',str(root/'batch-funding.csv'),
                '--manifest',str(root/'open-batch-manifest.json'),'--schedule',str(open_schedule),
                '--start',cutoff.isoformat(),'--as-of',now.isoformat()]
            cli_open=json.loads(subprocess.run(open_cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(cli_open['status'],'STOP',cli_open)
            self.assertTrue(cli_open['open_position_path_check']['observed_stop_or_overdue'])
            self.assertEqual(cli_open['input_sha256']['evidence']['open-hit.json'],hashlib.sha256(open_hit).hexdigest())
            (root/'open-invalid-entry2.json').write_text(json.dumps(altered['e2']['entry']))
            combined['open_positions']['e2']['entry']='open-invalid-entry2.json'
            combined['depth_sessions']=['depth-session']
            (root/'open-batch-manifest.json').write_text(json.dumps(combined))
            cli_joint=json.loads(subprocess.run(open_cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(cli_joint['status'],'STOP',cli_joint)
            self.assertEqual(cli_joint['open_position_path_check']['status'],'INVALID')
            self.assertEqual(cli_joint['open_depth_session_check']['status'],'STOP')


if __name__ == '__main__':
    unittest.main()
