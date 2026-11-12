"""As-of conflict facts; no phase labels and no trading decisions."""
from pathlib import Path
import hashlib
import json
import pandas as pd
from verify.market_2018_transition_20261102 import read

BASE = Path('data/verify/market-2016q4-position-20261102-01')
DATA = Path('data/market/btc-2016q4-usd-cross-20261102-01')
OUT = Path('data/verify/market-conflicts-2016q4-20261103-01')

def relation(big, small):
    if 'UNKNOWN' in (big, small):
        return 'UNKNOWN'
    if big not in ('UP', 'DOWN') or small not in ('UP', 'DOWN'):
        return 'NON_DIRECTIONAL'
    return 'ALIGNED' if big == small else 'OPPOSING'

def location(position, price, low, high):
    if position == 'UNKNOWN' or pd.isna(price) or pd.isna(low) or pd.isna(high) or high <= low:
        return 'UNKNOWN'
    if price < low or price > high:
        return 'LARGE_OUTSIDE'
    return 'SMALL_OUTSIDE_LARGE_INSIDE' if position in ('ABOVE', 'BELOW') else 'INSIDE_BOTH'

def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    a = pd.read_csv(BASE/'asof.csv'); f = pd.read_csv(BASE/'future.csv')
    flags = [pd.Timestamp(x).floor('D') for x in json.loads((BASE/'summary.json').read_text())['results']['bitstamp_bitfinex']['flags_utc']]
    rows = []
    for venue in ('bitstamp', 'bitfinex'):
        d, _ = read(DATA/(venue+'-4h.csv.gz'))
        d.loc[d.index.isin(flags), 'good'] = False
        for r in a[a.source == venue].itertuples():
            t = pd.Timestamp(r.as_of_utc); prev = t-pd.Timedelta(days=1)
            price = float(d.loc[prev, 'close']) if prev in d.index and d.loc[prev, 'good'] else float('nan')
            q = f[(f.source == venue) & (f.as_of_utc == r.as_of_utc)].iloc[0]
            rows.append({'source':venue, 'as_of_utc':r.as_of_utc, 'long':r.long_relation, 'big':r.big_relation, 'small':r.small_relation, 'layers':relation(r.big_relation, r.small_relation), 'position':r.position, 'price':price, 'fixed_low':q.fixed_lower, 'fixed_high':q.fixed_upper, 'position_context':location(r.position, price, q.fixed_lower, q.fixed_upper), 'spring':r.spring_watch, 'autumn':r.autumn_watch, 'future_fixed_status':q.fixed_status, 'future_fixed_follow':q.fixed_follow})
    table = pd.DataFrame(rows); OUT.mkdir(); table.to_csv(OUT/'conflicts.csv', index=False)
    inputs = [Path(__file__), BASE/'asof.csv', BASE/'future.csv', BASE/'summary.json', DATA/'bitstamp-4h.csv.gz', DATA/'bitfinex-4h.csv.gz']
    summary = {'points':len(table), 'by_source':{v:{'layers':x.layers.value_counts().to_dict(),'position_context':x.position_context.value_counts().to_dict()} for v,x in table.groupby('source')}, 'limitations':['28-day range contains latest close: large-outside is impossible for valid input.', 'No independent phase labels or actual missed-event rates.'], 'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary['by_source'],indent=2))

if __name__ == '__main__':
    main()
