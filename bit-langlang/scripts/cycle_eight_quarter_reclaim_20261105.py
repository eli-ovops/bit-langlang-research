import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
paths = {
    'seg_a': base/'cycle-2022q1-2024q2-segments-20261105-01/asof-segments.csv',
    'seg_b': base/'cycle-2022-2024-segments-20261105-01/asof-segments.csv',
    'seg_c': base/'cycle-two-regime-segments-20261105-01/asof-segments.csv',
    'seg_d': base/'cycle-2025q3-2026q1-segments-20261105-01/asof-segments.csv',
    'rebound': base/'cycle-rebound-full-quarters-20261105-01/daily.csv',
    'recent25': base/'cycle-2025q3-continuous-20261104-01/daily.csv',
    'recent26': base/'cycle-2026q1-phase-20261104-01/daily.csv',
    'daily_a': base/'cycle-2022q1-2024q2-segments-20261105-01/daily-fixed.csv',
    'daily_b': base/'cycle-fixed-quarter-review-20261105-01/daily.csv',
    'daily_25q3': base/'cycle-fixed-2025q3-20261105-01/daily.csv',
    'daily_25q4': base/'cycle-fixed-2025q4-20261105-01/daily.csv',
    'daily_26q1': base/'cycle-fixed-2026q1-20261105-01/daily.csv',
}
out = base/'cycle-eight-quarter-reclaim-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def numeric(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def main():
    d = {key:read(path) for key,path in paths.items()}
    segments = [r for key in ('seg_a','seg_b','seg_c','seg_d') for r in d[key]]
    assert len(segments) == 109 and len({(r['quarter'],r['start_utc']) for r in segments}) == 109
    daily = {}
    for r in d['daily_a']:
        daily[(r['quarter'],r['known_utc'])] = r
    for r in d['daily_b']:
        if r['source'] == 'bitstamp': daily[(r['year']+'Q4',r['known_utc'])] = r
    for key,quarter in (('daily_25q3','2025Q3'),('daily_25q4','2025Q4'),('daily_26q1','2026Q1')):
        for r in d[key]:
            if r['source'] == 'bitstamp': daily[(quarter,r['known_utc'])] = r
    rebound = {(r['quarter'],r['as_of_utc']):r for r in d['rebound']}
    recent = {(q,r['as_of_utc']):r for key,q in (('recent25','2025Q3'),('recent26','2026Q1')) for r in d[key] if r['source'] == 'bitstamp'}
    results = []
    for s in sorted(segments,key=lambda x:(x['start_utc'],x['quarter'])):
        q,tstamp = s['quarter'],s['start_utc']; t=datetime.fromisoformat(tstamp)
        d0 = daily[(q,tstamp)]; price=numeric(d0['close'])
        prior = s.get('past7_futures_pct')
        if prior is None:
            prior = rebound[(q,tstamp)]['past7_pct']
        prior=numeric(prior)
        prior90 = s.get('past90_futures_pct')
        if prior90 is None:
            prior90 = rebound[(q,tstamp)]['past90_pct']
        prior90 = numeric(prior90)
        history_quality = s.get('past_quality') or (rebound.get((q,tstamp),{}).get('prior_quality')) or ('API_SAVED' if prior90 is not None else 'UNKNOWN')
        high=numeric(s.get('recent28_high'))
        if high is None and (q,tstamp) in recent:
            item=recent[(q,tstamp)]
            if item['range_status'] == 'OK': high=numeric(item['prior28_high'])
        assert price is None or math.isclose(price,float(s['close']),rel_tol=0,abs_tol=1e-8)
        qualified = 'UNKNOWN' if price is None or high is None or prior is None or d0['position']=='UNKNOWN' else 'ELIGIBLE' if prior<0 and price<=high else 'NOT_ELIGIBLE'
        row={'quarter':q,'as_of_utc':tstamp,'spot_close':price,'fixed_position':d0['position'],'long':s['long'],'medium':s['medium'],'short':s['short'],'past7_futures_pct':prior,'past90_futures_pct':prior90,'past_quality':history_quality,'recent28_high':high,'funding_pos':s['funding_pos'],'funding_neg':s['funding_neg'],'eligibility':qualified,'observed_days':0,'reclaim':'NOT_APPLICABLE','reclaim_known_utc':'','reclaim_close':'','return7':'NOT_APPLICABLE','return7_known_utc':'','future28_pct':'','phase':'UNKNOWN','sentiment':'UNKNOWN'}
        if qualified == 'ELIGIBLE':
            observed=[]
            for i in range(1,29):
                item=daily.get((q,(t+timedelta(days=i)).isoformat()))
                if item is None: break
                p=numeric(item['close']); observed.append((t+timedelta(days=i),p if item['position']!='UNKNOWN' else None))
            row['observed_days']=len(observed)
            cross = next((i for i,(_,p) in enumerate(observed) if p is not None and p>high),None)
            if cross is not None and all(p is not None for _,p in observed[:cross+1]):
                cross_t,cross_price=observed[cross]
                row.update({'reclaim':'RECLAIM','reclaim_known_utc':cross_t.isoformat(),'reclaim_close':cross_price})
                after=[]
                for i in range(1,8):
                    item=daily.get((q,(cross_t+timedelta(days=i)).isoformat()))
                    if item is None: break
                    p=numeric(item['close']); after.append((cross_t+timedelta(days=i),p if item['position']!='UNKNOWN' else None))
                hit=next(((date,p) for date,p in after if p is not None and p<=high),None)
                if hit: row.update({'return7':'RETURN_WITHIN_7','return7_known_utc':hit[0].isoformat()})
                elif len(after)==7 and all(p is not None for _,p in after): row['return7']='NO_RETURN_7'
                else: row['return7']='UNKNOWN'
            elif cross is not None:
                row['reclaim']='CROSS_FIRST_UNKNOWN'
            elif len(observed)==28 and all(p is not None for _,p in observed):
                row['reclaim']='NO_RECLAIM'
            else:
                row['reclaim']='INCOMPLETE'
            if len(observed)==28 and all(p is not None for _,p in observed): row['future28_pct']=100*(observed[-1][1]/price-1)
        results.append(row)
    assert len(results)==109
    out.mkdir(parents=True,exist_ok=True)
    target=out/'segments.csv'
    with target.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=results[0]);w.writeheader();w.writerows(results)
    (out/'summary.json').write_text(json.dumps({'rows':len(results),'eligibility':dict(Counter(r['eligibility'] for r in results)),'reclaim_for_eligible':dict(Counter(r['reclaim'] for r in results if r['eligibility']=='ELIGIBLE')),'sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list(paths.values())+[target]}},indent=2)+'\n')
    for q in sorted({r['quarter'] for r in results}):
        group=[r for r in results if r['quarter']==q];eligible=[r for r in group if r['eligibility']=='ELIGIBLE']
        print(q,'segments',len(group),'eligible',len(eligible),'outcomes',dict(Counter(r['reclaim'] for r in eligible)))
        for r in eligible:
            print(' ',r['as_of_utc'][:10],r['past7_futures_pct'],r['recent28_high'],r['reclaim'],r['reclaim_known_utc'][:10],r['return7'],r['future28_pct'])


if __name__ == '__main__':
    main()
