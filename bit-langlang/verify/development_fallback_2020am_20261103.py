"""Check known motivating case only; this is not independent evaluation."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_support_2019on_20261103 import support
from verify.market_support_fallback_2014sp_20261103 import fallback
from verify.audit_fallback_2014sp_20261103 import snapshot_low
BASE=Path('data/verify/market-prior28-2020am-20261103-01');DATA=Path('data/market/btc-2020am-usd-cross-20261102-01');OUT=Path('data/verify/market-fallback-2020am-development-20261103-01')
def main():
    if OUT.exists():raise FileExistsError(OUT)
    flags=json.loads((BASE/'summary.json').read_text())['quality_flags_utc'];assert not flags
    x=pd.read_csv(BASE/'asof.csv');rows=[]
    for name in ('bitstamp','bitfinex'):
        path=DATA/(name+'-4h.csv.gz');d,_=read(path);r=x[(x.source==name)&x.as_of_utc.str.startswith('2020-05-13')].iloc[0].to_dict();t=pd.Timestamp(r['as_of_utc']);old=support(d,t,r);new,method=fallback(d,t,r);b=pd.read_csv(path);b.index=pd.to_datetime(b.ts,unit='ms',utc=True);level,known=snapshot_low(b,t);assert old['support_state']=='WAIT_CONFIRM' and method=='FALLBACK_USED' and np.isclose(new['level'],level) and new['known']==known.isoformat();rows.append({'source':name,'as_of_utc':r['as_of_utc'],'old_state':old['support_state'],'old_level':old['level'],'old_known':old['known'],'new_state':new['support_state'],'new_level':new['level'],'new_known':new['known'],'close':new['close'],'method':method})
    files=[Path(__file__),Path('verify/market_support_fallback_2014sp_20261103.py'),Path('verify/audit_fallback_2014sp_20261103.py'),BASE/'asof.csv',BASE/'summary.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];OUT.mkdir();pd.DataFrame(rows).to_csv(OUT/'motivating_case.csv',index=False);(OUT/'summary.json').write_text(json.dumps({'scope':'Known motivating case: development only, not independent phase or performance validation.','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
