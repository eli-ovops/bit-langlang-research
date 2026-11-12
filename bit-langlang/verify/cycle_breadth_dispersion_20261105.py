"""Describe already-seen aggregate breadth and dispersion, no phase labels."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path('data/verify')
OUT = ROOT/'cycle-breadth-dispersion-20261105-01'
NAMES = ['2022nov-2023nov','2024nov-2026jan','2024q2','2025aug','2025q4']
PREFIX = 'cycle-breadth-binance-archive-'
SUFFIX = '-20261105-01'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manual_quantile(values, q):
    a = sorted(values); pos = (len(a)-1)*q; lo = int(pos); hi = min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(pos-lo)


def summarize(g):
    good = g[g.quality.eq('OK')]
    r={'known':len(good),'unknown':len(g)-len(good)}
    for period in (7,28):
        z=good[f'return{period}_pct'].to_numpy(dtype=float)
        assert np.isfinite(z).all()
        r[f'up{period}']=int((z>0).sum())
        for q in (10,50,90):
            r[f'p{q}_{period}']=float(np.quantile(z,q/100,method='linear')) if len(z) else None
            if len(z):assert np.isclose(r[f'p{q}_{period}'],manual_quantile(z,q/100),rtol=1e-12,atol=1e-12)
        if len(z):
            r[f'top_gap_{period}']=r[f'p90_{period}']-r[f'p50_{period}']
            r[f'bottom_gap_{period}']=r[f'p50_{period}']-r[f'p10_{period}']
    return r


def main():
    OUT.mkdir(parents=True,exist_ok=False);rows=[];inputs={}
    for name in NAMES:
        directory=ROOT/(PREFIX+name+SUFFIX)
        source=directory/'contract-daily-asof.csv';existing=directory/'archive-daily-asof.csv'
        inputs[str(source)]=digest(source);inputs[str(existing)]=digest(existing)
        df=pd.read_csv(source);ref=pd.read_csv(existing).set_index('as_of_utc')
        assert set(df.quality.unique()) <= {'OK','UNKNOWN'}
        assert not df.duplicated(['as_of_utc','contract']).any()
        for day,g in df.groupby('as_of_utc',sort=True):
            s=summarize(g);r=ref.loc[day]
            assert all(int(s[x])==int(r[x]) for x in ['known','unknown','up7','up28'])
            rows.append({'as_of_utc':day,**s})
    result=pd.DataFrame(rows).sort_values('as_of_utc')
    assert len(result)==335 and not result.as_of_utc.duplicated().any()
    result.to_csv(OUT/'daily-dispersion.csv',index=False)
    source=ROOT/(PREFIX+'2022nov-2023nov'+SUFFIX)/'contract-daily-asof.csv'
    differences=ROOT/(PREFIX+'2022nov-2023nov'+SUFFIX)/'2023-api-archive-differences.csv'
    inputs[str(differences)]=digest(differences)
    exclude=set(pd.read_csv(differences).symbol);assert len(exclude)==6
    df=pd.read_csv(source);g=df[df.as_of_utc.str.startswith('2023-11-17')]
    s=summarize(g[~g.contract.isin(exclude)])
    (OUT/'2023-exclusion-sensitivity.json').write_text(json.dumps(s,indent=2))
    report={'rows':len(result),'inputs_sha256':inputs,
       'protocol_sha256':digest(Path('docs/浪浪周期-广度与分化事实检验定义-20261105.md')),
       'script_sha256':digest(Path(__file__)),
       'checks':'all daily counts vs stored archive; linear quantiles independently recomputed',
       'limits':'already-seen historical data, no true phase, not out-of-sample'}
    (OUT/'summary.json').write_text(json.dumps(report,indent=2))
    print(result[result.as_of_utc.str[:10].isin(['2023-11-17','2024-11-19','2025-08-05','2026-01-16'])].to_string(index=False))


if __name__=='__main__':
    main()
