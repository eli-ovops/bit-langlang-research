"""Link local reports by fields and hashes; never prove authenticity or PASS."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import pandas as pd


def link(coverage, batch, source_check=None):
    if not isinstance(coverage, dict) or not isinstance(batch, dict) or (source_check is not None and not isinstance(source_check,dict)):
        return {'status': 'INVALID', 'reason': '报告必须是对象'}
    statuses = {'coverage': coverage.get('status'), 'batch': batch.get('status'),
                'source_check':source_check.get('status') if source_check is not None else 'UNKNOWN_NOT_PROVIDED'}
    common = {'component_statuses': statuses, 'source_authenticity': 'UNKNOWN',
              'continuous_market_path': 'UNKNOWN', 'actual_fills': 'UNKNOWN', 'unsealed_seconds': None,
              'source_response_crosscheck': 'UNKNOWN_NOT_PROVIDED' if source_check is None else 'UNKNOWN_INCOMPLETE'}
    if 'INVALID' in statuses.values():
        return {**common, 'status': 'INVALID', 'reason': '至少一份报告无效'}
    try:
        interval = batch['observation_interval']
        t = [pd.to_datetime(value, utc=True, errors='raise') for value in
             (coverage['start_utc'], coverage['as_of_utc'], interval['start_utc'], interval['as_of_utc'])]
        if any(pd.isna(x) for x in t) or t[0] > t[1] or t[2] > t[3]:
            raise ValueError('invalid interval')
        cov_events = coverage['event_sha256']
        batch_events = batch['input_sha256']['events']
        scan_hash = batch['input_sha256']['scan']
        scans = coverage['scans']
        archive = coverage['archive']
        unsealed = float(coverage['unsealed_seconds'])
        if not isinstance(cov_events, dict) or not isinstance(batch_events, dict) or not isinstance(scans, list):
            raise ValueError('invalid hashes')
        if not isinstance(archive, dict) or not math.isfinite(unsealed) or unsealed < 0:
            raise ValueError('invalid archive or coverage tail')
        common['unsealed_seconds'] = unsealed
        if not cov_events or not batch_events or not scans:
            return {**common, 'status': 'UNKNOWN_INCOMPLETE', 'reason': '没有事件或扫描证据'}
        valid = lambda value: isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))
        if (not all(isinstance(k, str) and valid(v) for k, v in cov_events.items()) or
                not all(isinstance(k, str) and valid(v) for k, v in batch_events.items()) or
                not valid(scan_hash) or not valid(archive.get('head_sha256')) or
                not all(isinstance(x, dict) and valid(x.get('scan_sha256')) for x in scans)):
            raise ValueError('invalid sha256')
    except (KeyError, TypeError, ValueError, OverflowError):
        return {**common, 'status': 'UNKNOWN_INCOMPLETE', 'reason': '报告缺少可核对的时间或哈希'}
    if t[:2] != t[2:] or cov_events != batch_events or scan_hash not in [x['scan_sha256'] for x in scans]:
        return {**common, 'status': 'INVALID', 'reason': '观察区间、事件文件或扫描内容不一致'}
    source_ok=False
    if source_check is not None:
        source_head=source_check.get('archive_head_sha256')
        if source_head is not None and (not valid(source_head) or source_head!=archive['head_sha256']):
            return {**common,'status':'INVALID','reason':'独立核验与扫描归档头部不一致'}
        transitions=source_check.get('transitions')
        source_ok=(source_check.get('status')=='PARTIAL_INDEPENDENT_CROSSCHECK' and
                   source_head==archive['head_sha256'] and
                   source_check.get('anchor_status')=='MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' and
                   source_check.get('matched_transitions')==len(scans) and
                   source_check.get('unknown_transitions')==0 and isinstance(transitions,list) and
                   len(transitions)==len(scans) and
                   all(isinstance(x,dict) and x.get('sequence')==i and x.get('status')=='MATCHED_UNVERIFIED'
                       for i,x in enumerate(transitions)))
        if source_ok:common['source_response_crosscheck']='MATCHED_UNVERIFIED'
    link_info = {**common, 'formal_link': 'MATCHED_UNVERIFIED', 'event_count': len(cov_events),
                 'matched_scan_sha256': scan_hash,
                 'archive_anchor_status': archive.get('anchor_status'),
                 'public_source_missing_records': archive.get('public_source_missing_records'),
                 'initial_source_status': archive.get('initial_source_status'),
                 'signal_availability_status': coverage.get('signal_availability_status'),
                 'batch_evidence_gaps': batch.get('evidence_gaps')}
    if 'STOP' in statuses.values(): status = 'STOP'
    elif 'EXECUTION_MODEL_MISMATCH' in statuses.values(): status = 'EXECUTION_MODEL_MISMATCH'
    elif (statuses['coverage'] == 'PARTIAL_COVERAGE_UNVERIFIED' and
          statuses['batch'] == 'PARTIAL_NOT_REGISTERED' and
          coverage.get('signal_availability_status') == 'ORDERED_BUT_UNVERIFIED' and
          archive.get('anchor_status') == 'MATCHES_SUPPLIED_UNVERIFIED_ANCHOR' and
          archive.get('fully_reconstructed_records') == len(scans) and
          archive.get('public_source_bound_records') == len(scans) and
          archive.get('public_source_missing_records') == 0 and
          archive.get('initial_source_status') == 'BOUND_UNVERIFIED' and
          archive.get('committed_records') == len(scans) and source_ok and
          batch.get('evidence_gaps') == []):
        status = 'PARTIAL_LINK_UNVERIFIED'
    else: status = 'UNKNOWN_INCOMPLETE'
    return {**link_info, 'status': status,
            'reason': '仅为本地报告的形式关联；未封存时段、信号真实性、连续行情、真实成交与账户完整性均未获证明，不能自动 PASS。'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--coverage', required=True)
    parser.add_argument('--batch', required=True)
    parser.add_argument('--source-check', help='可选独立原始响应交叉核验 JSON 报告')
    args = parser.parse_args()
    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('报告包含重复键: ' + key)
                result[key] = value
            return result
        def reject_constant(value):
            raise ValueError('报告包含非有限数值: ' + value)
        raw_coverage = Path(args.coverage).read_bytes()
        raw_batch = Path(args.batch).read_bytes()
        raw_source = Path(args.source_check).read_bytes() if args.source_check else None
        parse=lambda raw:json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=reject_constant)
        result = link(parse(raw_coverage),parse(raw_batch),parse(raw_source) if raw_source is not None else None)
        result['report_sha256'] = {'coverage': hashlib.sha256(raw_coverage).hexdigest(),
                                   'batch': hashlib.sha256(raw_batch).hexdigest()}
        if raw_source is not None:result['report_sha256']['source_check']=hashlib.sha256(raw_source).hexdigest()
    except (OSError, ValueError) as exc:
        result = {'status': 'INVALID', 'reason': '报告不可读取: ' + str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
