"""Independent 4h reconstruction of all 29-day boundaries and seven-day returns."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

DATA=Path('data/market/btc-2017nd-usd-cross-20261102-01')
SRC=Path('data/verify/market-prior28-2017nd-20261103-01')
OUT=Path('data/verify/market-prior28-2017nd-independent-20261103-01')

def main():
    if OUT.exists():raise FileExistsError(OUT)
    x=pd.read_csv(SRC/'asof.csv');joint=pd.read_csv(SRC/'joint.csv');meta=json.loads((SRC/'summary.json').read_text());flags={pd.Timestamp(f).floor('D') for f in meta['quality_flags_utc']}; states={};checked=returns=0
    for source in ('bitstamp','bitfinex'):
        p=DATA/(source+'-4h.csv.gz');bars=pd.read_csv(p);bars.index=pd.to_datetime(bars.ts,unit='ms',utc=True);bars=bars[~bars.index.floor('D').isin(flags)]
        for row in x[x.source==source].itertuples():
            t=pd.Timestamp(row.as_of_utc);q=bars.reindex(pd.date_range(t-pd.Timedelta(days=29),periods=174,freq='4h'))
            if q[['high','low','close']].isna().any().any():state='UNKNOWN';status='UNKNOWN'
            else:
                hi=q.high.iloc[:168].max();lo=q.low.iloc[:168].min();c=q.close.iloc[-1]
                if hi<=lo:state='UNKNOWN';status='UNKNOWN'
                else:
                    state='ABOVE' if c>hi else 'BELOW' if c<lo else 'INSIDE'
                    assert np.isclose(hi,row.ref_high) and np.isclose(lo,row.ref_low) and np.isclose(c,row.current_close)
                    status='NOT_APPLICABLE'
                    if state!='INSIDE':
                        status='NO_RETURN';level=hi if state=='ABOVE' else lo
                        for n in range(7):
                            day=t+pd.Timedelta(days=n);z=bars.reindex(pd.date_range(day,periods=6,freq='4h'))
                            if z[['high','low','close']].isna().any().any():status='UNKNOWN_INCOMPLETE';break
                            close=z.close.iloc[-1]
                            if (state=='ABOVE' and close<level) or (state=='BELOW' and close>level):
                                status='RETURN';assert row.return_time==(day+pd.Timedelta(days=1)).isoformat() and np.isclose(row.return_close,close);break
                        returns+=1
            assert row.range_state==state and row.return_7==status,(source,t,state,status,row.range_state,row.return_7)
            states[(source,row.as_of_utc)]=state;checked+=1
    for r in joint.itertuples():
        a=states[('bitstamp',r.as_of_utc)];b=states[('bitfinex',r.as_of_utc)]
        expected='UNKNOWN' if 'UNKNOWN' in (a,b) else 'JOINT_'+a if a==b else 'DISAGREE'
        assert r.joint==expected
    files=[Path(__file__),SRC/'asof.csv',SRC/'joint.csv',SRC/'summary.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz']
    OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','source_points':checked,'seven_day_checks':returns,'joint_points':len(joint),'scope':'independent 4h price boundaries and returns; flags shared, not phase truth or venue price certification','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',checked,returns,len(joint))
if __name__=='__main__':main()
