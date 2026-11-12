"""One public BTC market snapshot. No account, orders, monitor, or scheduling."""
import argparse
import hashlib
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from .paper_nine_initial_bridge import bridge
from .paper_nine_market import URL, evaluate

ROOT = Path(__file__).resolve().parents[1]
VERIFY_ROOT = (ROOT / 'data/verify').resolve()
INITIAL = ROOT / 'data/verify/langlang-paper-research-20261110-01'


def now_utc():
    return datetime.now(timezone.utc)


def run(outdir, initial=INITIAL):
    initial_result = bridge(initial)
    if initial_result.get('status') != 'UNKNOWN' or initial_result.get('recomputed_market_gate') != 'NO_CANDIDATE':
        return {'status': 'UNKNOWN', 'reason': 'initial paper record not independently reproducible; no request sent'}
    directory = Path(outdir).resolve()
    if directory == VERIFY_ROOT or VERIFY_ROOT not in directory.parents:
        return {'status': 'INVALID', 'reason': 'output must be a new directory under project data/verify'}
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError:
        return {'status': 'INVALID', 'reason': 'output directory unavailable or already exists'}
    started = now_utc()
    try:
        request = urllib.request.Request(URL, headers={'User-Agent': 'local-paper-research/1.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.geturl() != URL:
                raise ValueError('unexpected response URL')
            body = response.read(2_000_001)
            http = response.status
        if len(body) > 2_000_000:
            raise ValueError('response too large')
        received = now_utc()
        receipt = {'url': URL, 'http': http, 'request_utc': started.isoformat(),
                   'received_utc': received.isoformat(), 'sha256': hashlib.sha256(body).hexdigest()}
        (directory / 'response.json').write_bytes(body)
        (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        result = evaluate(body, receipt, received.isoformat())
        initial_day = datetime.fromisoformat(initial_result['observed_utc']).date()
        duplicate = received.date() == initial_day
        result.update({'capture_scope': 'SAME_DAY_DIAGNOSTIC_ONLY' if duplicate else 'MARKET_OBSERVATION_ONLY',
                       'paper_decision': 'NONE', 'paper_entry': 'NONE', 'ranked_coins': 'NONE',
                       'ledger_modified': False, 'continuous_coverage': 'UNKNOWN',
                       'initial_record_utc': initial_result['observed_utc'],
                       'caution': 'v0.1 pullback semantics unresolved; no trading or entry from this output'})
    except Exception as exc:
        # Only a fixed public unauthenticated endpoint is used; never load or log credentials.
        result = {'status': 'UNKNOWN', 'reason': type(exc).__name__, 'request_utc': started.isoformat(),
                  'failure_observed_utc': now_utc().isoformat(), 'paper_decision': 'NONE',
                  'paper_entry': 'NONE', 'ledger_modified': False}
        if isinstance(exc, urllib.error.URLError):
            # Report only the underlying error type; never print request or exception text.
            result['underlying_error_type'] = type(exc.reason).__name__
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', required=True, help='new path under project data/verify')
    args = parser.parse_args()
    print(json.dumps(run(args.outdir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
