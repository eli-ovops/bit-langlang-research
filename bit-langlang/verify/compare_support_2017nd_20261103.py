"""Post-hoc comparison on the two cases that motivated this idea, not holdout."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_support_2019on_20261103 import support
BASE=Path('data/verify/market-prior28-2017nd-20261103-01');DATA=Path('data/market/btc-2017nd-usd-cross-20261102-01');OUT=Path('data/verify/market-support-2017nd-development-20261103-01')
def main():
    if OUT.exists():raise FileExistsError(OUT)
    x=pd.read_csv(BASE/'asof.csv');rows=[]
    for name in ('bitstamp','bitfinex'):
        d,_=read(DATA/(name+'-4h.csv.gz'))
        for date in ('2017-11-13','2017-12-22'):
            r=x[(x.source==name)&(x.as_of_utc.str.startswith(date))].iloc[0].to_dict();t=pd.Timestamp(r['as_of_utc']);z=support(d,t,r);w=d[(d.index>=t)&(d.index<t+pd.Timedelta(days=7))];assert len(w)==7 and w.good.all();z.update(source=name,as_of_utc=r['as_of_utc'],long=r['long'],big=r['big'],small=r['small'],future_7_pct=(float(w.close.iloc[-1])/float(d.loc[t-pd.Timedelta(days=1),'close'])-1)*100);rows.append(z)
    paths=[Path(__file__),Path('verify/market_support_2019on_20261103.py'),BASE/'asof.csv',BASE/'summary.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];OUT.mkdir();pd.DataFrame(rows).to_csv(OUT/'development_cases.csv',index=False);(OUT/'summary.json').write_text(json.dumps({'scope':'Selected after seeing these historical cases; development only, not independent evidence.','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2)+'\n');print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
