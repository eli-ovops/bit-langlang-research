import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .paper_evidence_link import link


class EvidenceLinkTest(unittest.TestCase):
    def setUp(self):
        self.coverage = {'status': 'PARTIAL_COVERAGE_UNVERIFIED',
                         'start_utc': '2026-10-30T00:00:00Z', 'as_of_utc': '2026-10-30T01:00:00Z',
                         'event_sha256': {'a.json': 'a'*64}, 'scans': [{'scan_sha256': 'b'*64}],
                         'archive': {'head_sha256': 'c'*64, 'fully_reconstructed_records': 1,'committed_records':1,
                                     'public_source_bound_records': 1,'public_source_missing_records': 0,
                                     'initial_source_status':'BOUND_UNVERIFIED',
                                     'anchor_status': 'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR'},
                         'unsealed_seconds': 900, 'signal_availability_status': 'ORDERED_BUT_UNVERIFIED'}
        self.batch = {'status': 'PARTIAL_NOT_REGISTERED', 'evidence_gaps': [],
                      'observation_interval': {'start_utc': '2026-10-30T08:00:00+08:00',
                                               'as_of_utc': '2026-10-30T09:00:00+08:00'},
                      'input_sha256': {'events': {'a.json': 'a'*64}, 'scan': 'b'*64}}
        self.source = {'status':'PARTIAL_INDEPENDENT_CROSSCHECK','archive_head_sha256':'c'*64,
                       'anchor_status':'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR','matched_transitions':1,
                       'unknown_transitions':0,'transitions':[{'sequence':0,'status':'MATCHED_UNVERIFIED'}]}

    def test_formal_link_keeps_limits(self):
        result = link(self.coverage, self.batch, self.source)
        self.assertEqual(result['status'], 'PARTIAL_LINK_UNVERIFIED')
        self.assertEqual(result['source_authenticity'], 'UNKNOWN')
        self.assertEqual(result['source_response_crosscheck'], 'MATCHED_UNVERIFIED')
        self.assertEqual(result['unsealed_seconds'], 900)
        self.assertEqual(result['event_count'], 1)
        self.assertEqual(link(self.coverage,self.batch)['status'],'UNKNOWN_INCOMPLETE')

    def test_source_head_and_transition_completeness(self):
        changed=copy.deepcopy(self.source);changed['archive_head_sha256']='d'*64
        self.assertEqual(link(self.coverage,self.batch,changed)['status'],'INVALID')
        changed=copy.deepcopy(self.source);changed['unknown_transitions']=1
        self.assertEqual(link(self.coverage,self.batch,changed)['status'],'UNKNOWN_INCOMPLETE')
        changed=copy.deepcopy(self.source);changed['transitions'][0]['status']='UNKNOWN_INITIAL_BASELINE'
        self.assertEqual(link(self.coverage,self.batch,changed)['status'],'UNKNOWN_INCOMPLETE')
        changed=copy.deepcopy(self.source);changed['status']='INVALID'
        self.assertEqual(link(self.coverage,self.batch,changed)['status'],'INVALID')

    def test_different_interval_events_and_scan_fail(self):
        changed = copy.deepcopy(self.batch)
        changed['observation_interval']['as_of_utc'] = '2026-10-30T01:00:01Z'
        self.assertEqual(link(self.coverage, changed)['status'], 'INVALID')
        changed = copy.deepcopy(self.batch)
        changed['input_sha256']['events']['a.json'] = 'c'*64
        self.assertEqual(link(self.coverage, changed)['status'], 'INVALID')
        changed = copy.deepcopy(self.batch)
        changed['input_sha256']['scan'] = 'c'*64
        self.assertEqual(link(self.coverage, changed)['status'], 'INVALID')

    def test_missing_evidence_and_component_statuses_are_not_pass(self):
        changed = copy.deepcopy(self.batch)
        changed['input_sha256']['events'] = {}
        self.assertEqual(link(self.coverage, changed)['status'], 'UNKNOWN_INCOMPLETE')
        coverage = copy.deepcopy(self.coverage)
        coverage['archive']['fully_reconstructed_records'] = 0
        self.assertEqual(link(coverage, self.batch)['status'], 'UNKNOWN_INCOMPLETE')
        coverage['archive']['fully_reconstructed_records'] = 1
        coverage['archive']['anchor_status'] = 'NO_EXTERNAL_ANCHOR'
        self.assertEqual(link(coverage, self.batch)['status'], 'UNKNOWN_INCOMPLETE')
        coverage['archive']['anchor_status'] = 'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR'
        coverage['archive']['public_source_missing_records'] = 1
        self.assertEqual(link(coverage, self.batch)['status'], 'UNKNOWN_INCOMPLETE')
        coverage['archive']['public_source_missing_records'] = 0
        coverage['archive']['initial_source_status'] = 'UNKNOWN_NOT_CAPTURED'
        self.assertEqual(link(coverage, self.batch)['status'], 'UNKNOWN_INCOMPLETE')
        changed = copy.deepcopy(self.batch)
        del changed['observation_interval']
        self.assertEqual(link(self.coverage, changed)['status'], 'UNKNOWN_INCOMPLETE')
        changed = {**self.batch, 'status': 'UNKNOWN_POSITION_PATH', 'evidence_gaps': ['CLOSED_POSITION_PATH']}
        self.assertEqual(link(self.coverage, changed)['status'], 'UNKNOWN_INCOMPLETE')
        self.coverage['status'] = 'EXECUTION_MODEL_MISMATCH'
        self.assertEqual(link(self.coverage, changed)['status'], 'EXECUTION_MODEL_MISMATCH')
        changed['status'] = 'STOP'
        self.assertEqual(link(self.coverage, changed)['status'], 'STOP')

    def test_cli_reports_input_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            cov = Path(directory)/'coverage.json'; cov.write_text(json.dumps(self.coverage))
            batch = Path(directory)/'batch.json'; batch.write_text(json.dumps(self.batch))
            source = Path(directory)/'source.json'; source.write_text(json.dumps(self.source))
            result = subprocess.run([sys.executable, '-m', 'verify.paper_evidence_link',
                                     '--coverage', str(cov), '--batch', str(batch),'--source-check',str(source)],
                                    capture_output=True, text=True, check=True)
            out = json.loads(result.stdout)
            self.assertEqual(out['status'], 'PARTIAL_LINK_UNVERIFIED')
            self.assertEqual(len(out['report_sha256']['coverage']), 64)
            self.assertEqual(len(out['report_sha256']['source_check']), 64)
            cov.write_text('{"status":"STOP","status":"PARTIAL_COVERAGE_UNVERIFIED"}')
            result = subprocess.run([sys.executable, '-m', 'verify.paper_evidence_link',
                                     '--coverage', str(cov), '--batch', str(batch)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['status'], 'INVALID')


if __name__ == '__main__':
    unittest.main()
