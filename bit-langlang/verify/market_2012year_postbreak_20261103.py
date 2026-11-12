"""Post-hoc description of all frozen-support breaks followed by 7d return."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2023_return_28d_20261102 import returned
DATA=Path('data/market/btc-2012year-usd-cross-20261103-01');SRC=Path('data/verify/market-support-fallback-2012year-20261103-01');OUT=Path('data/verify/market-support-2012year-postbreak-20261103-01')
def main():
    if OUT.exists():raise FileExistsError(OUT)
    assert not json.loads(Path('data/verify/market-prior28-2012year-20261103-01/summary.json').read_text())['quality_flags_utc']
    a=pd.read_csv(SRC/'asof_and_future.csv');records=[]
    for name in ('bitstamp','bitfinex'):
        path=DATA/(name+'-4h.csv.gz');d,h=read(path)
        for r in a[(a.source==name)&(a.event_7=='BREAK')].itertuples():
            start=pd.Timestamp(r.event_time);level=float(r.new_level);status,when,price=returned(d,start,'LOWER_BREAK',level,7)
            audit='NO_RETURN';independent_time=None
            for i in range(7):
                end=start+pd.Timedelta(days=i);z=h.reindex(pd.date_range(end,periods=6,freq='4h'))
                if z[['open','high','low','close']].isna().any().any() or not z.good.fillna(False).all():audit='UNKNOWN_INCOMPLETE';break
                close=float(z.close.iloc[-1])
                if close>level:audit='RETURN';independent_time=(end+pd.Timedelta(days=1)).isoformat();assert np.isclose(close,price);break
            assert status==audit and when==independent_time
            records.append({'source':name,'as_of_utc':r.as_of_utc,'focus':r.focus,'support':level,'break_time':r.event_time,'return_7_after_break':status,'return_time':when,'return_close':price})
    x=pd.DataFrame(records,columns=['source','as_of_utc','focus','support','break_time','return_7_after_break','return_time','return_close']);files=[Path(__file__),SRC/'asof_and_future.csv',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];OUT.mkdir();x.to_csv(OUT/'postbreak.csv',index=False);(OUT/'summary.json').write_text(json.dumps({'scope':'Post-hoc, all previously identified BREAK rows, not phase truth or independent events.','rows':len(x),'distinct_break_times':int(x.break_time.nunique()),'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS rows',len(x),'distinct_break_times',x.break_time.nunique())
if __name__=='__main__':main()
