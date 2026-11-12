import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/verify/cycle-fixed-quarter-review-20261105-01'
OLD = ROOT / 'data/verify/cycle-sentiment-2022q4-2023q4-20261105-01/segments-with-prior-funding.csv'
NEW = ROOT / 'data/verify/cycle-sentiment-2024q4-20261105-01/segments-with-prior-funding.csv'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def state(price, low, high):
    return 'ABOVE' if price > high else 'BELOW' if price < low else 'INSIDE'


def main():
    assert [state(x, 10, 20) for x in (9, 10, 15, 20, 21)] == ['BELOW', 'INSIDE', 'INSIDE', 'INSIDE', 'ABOVE']
    OUT.mkdir(parents=True, exist_ok=True)
    output, summaries, inputs = [], [], [OLD, NEW]
    for year, tag in ((2022, 'phase'), (2023, 'phase'), (2024, 'evidence')):
        path = ROOT / f'data/verify/cycle-{year}q4-{tag}-20261104-01/daily.csv'
        inputs.append(path)
        daily, segments = read(path), read(NEW if year == 2024 else OLD)
        start = datetime(year, 10, 1, tzinfo=timezone.utc)
        for source in sorted({r['source'] for r in daily}):
            group = sorted((r for r in daily if r['source'] == source), key=lambda r: r['as_of_utc'])
            assert len(group) == 92
            for i, row in enumerate(group):
                assert datetime.fromisoformat(row['as_of_utc']) == start + timedelta(days=i)
            low, high = float(group[0]['prior28_low']), float(group[0]['prior28_high'])
            assert 0 < low < high and group[0]['range_status'] == 'OK'
            final = [r for r in segments if r['source'] == source and r['start_utc'].startswith(f'{year}-12-31')]
            assert len(final) == 1 and final[0]['status'] == 'COMPLETE' and final[0]['end_utc_exclusive'].startswith(f'{year+1}-01-01')
            end_price = float(final[0].get('last_close') or final[0]['segment_end_close'])
            close_data = [(r['as_of_utc'], float(r['prev_close'])) for r in group]
            close_data.append(((start + timedelta(days=92)).isoformat(), end_price))
            states, changes, last = [], [], None
            for stamp, price in close_data:
                assert price > 0
                current = state(price, low, high)
                if last is not None and current != last:
                    changes.append({'known_utc': stamp, 'from': last, 'to': current, 'close': price})
                states.append(current)
                output.append({'year': year, 'source': source, 'known_utc': stamp, 'close': price, 'frozen_low': low, 'frozen_high': high, 'position': current})
                last = current
            counts = Counter(states[1:])
            assert sum(counts.values()) == 92
            summaries.append({'year': year, 'source': source, 'initial_close': close_data[0][1], 'low': low, 'high': high, 'daily_closes': dict(counts), 'changes': changes})
    path = OUT / 'daily.csv'
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=output[0].keys()); w.writeheader(); w.writerows(output)
    assert len(output) == 558
    evidence = {'note': 'Retrospective, close-only; no stage truth or predictive validation', 'input_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}, 'daily_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'sources': summaries}
    (OUT / 'summary.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
