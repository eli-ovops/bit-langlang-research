"""Raw 4h reconstruction of background, small relations and confirmed swing."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from verify.audit_2018_transition_20261102 import calc,rel

S=Path('data/verify/market-prior28-2017sep-20261103-01');D=Path('data/market/btc-2017sep-usd-cross-20261103-01');O=Path('data/verify/market-layers-2017sep-independent-20261103-01')
def main():
    if O.exists():raise FileExistsError(O)
    rows=pd.read_csv(S/'asof.csv');flags={pd.Timestamp(x).floor('D') for x in json.loads((S/'summary.json').read_text())['quality_flags_utc']};count=0
    for name in ('bitstamp','bitfinex'):
        p=D/(name+'-4h.csv.gz');b=pd.read_csv(p);b.index=pd.to_datetime(b.ts,unit='ms',utc=True);b=b[~b.index.floor('D').isin(flags)]
        for r in rows[rows.source==name].itertuples():
            t=pd.Timestamp(r.as_of_utc);big,small,long=(calc(b,t,n) for n in (28,8,56));br,sr,lr=map(rel,(big,small,long));assert (br,sr,lr)==(r.big,r.small,r.long),(name,t,br,sr,lr,r.big,r.small,r.long)
            swing='UNKNOWN'
            if long is not None:
                days=long.resample('D').agg(high=('high','max'),low=('low','min'));hs=[];ls=[]
                for i in range(2,54):
                    w=days.iloc[i-2:i+3];hi=w.high.iloc[2]>w.high.drop(w.index[2]).max();lo=w.low.iloc[2]<w.low.drop(w.index[2]).min()
                    if hi and not lo:hs.append((w.index[2],w.high.iloc[2]))
                    if lo and not hi:ls.append((w.index[2],w.low.iloc[2]))
                if len(hs)>=2 and len(ls)>=2:
                    swing='SWING_UP' if hs[-1][1]>hs[-2][1] and ls[-1][1]>ls[-2][1] else 'SWING_DOWN' if hs[-1][1]<hs[-2][1] and ls[-1][1]<ls[-2][1] else 'SWING_MIXED'
                    for k,(day,price) in {'h_old':hs[-2],'h_new':hs[-1],'l_old':ls[-2],'l_new':ls[-1]}.items():assert getattr(r,k+'_day')==day.isoformat() and getattr(r,k+'_known')==(day+pd.Timedelta(days=3)).isoformat() and np.isclose(getattr(r,k+'_price'),price)
            assert swing==r.swing,(name,t,swing,r.swing);count+=1
    files=[Path(__file__),S/'asof.csv',S/'summary.json',D/'bitstamp-4h.csv.gz',D/'bitfinex-4h.csv.gz'];O.mkdir();(O/'summary.json').write_text(json.dumps({'status':'PASS','source_points':count,'scope':'raw 4h layers and pivots; relation helper shared with previous independent audits; phase truth not checked','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',count)
if __name__=='__main__':main()
