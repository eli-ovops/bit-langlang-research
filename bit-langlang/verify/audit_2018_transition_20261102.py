"""Independent raw 4h re-computation of frozen 2018 observations and events."""
from pathlib import Path
import hashlib, json
import pandas as pd
import numpy as np

DATA=Path('data/market/btc-2018-spot-cross-20261102-02')
RESULT=Path('data/verify/market-2018-transitions-20261102-01')
OUT=Path('data/verify/market-2018-transition-independent-20261102-01')

def calc(f,t,days):
    z=f[(f.index>=t-pd.Timedelta(days=days))&(f.index<t)]
    expected=pd.date_range(t-pd.Timedelta(days=days),periods=days*6,freq='4h')
    if not z.index.equals(expected): return None
    v=z[['open','high','low','close']]
    if not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (z.low>v.min(axis=1)).any() or (z.high<v.max(axis=1)).any(): return None
    return z

def rel(z):
    if z is None:return 'UNKNOWN'
    a,b=np.split(z,[len(z)//2]); ah,al,bh,bl=a.high.max(),a.low.min(),b.high.max(),b.low.min()
    if bh>ah and bl>al:return 'UP'
    if bh<ah and bl<al:return 'DOWN'
    if bh<=ah and bl>=al:return 'INSIDE'
    return 'MIXED'

def main():
    if OUT.exists():raise FileExistsError(OUT)
    layers=pd.read_csv(RESULT/'layers.csv');events=pd.read_csv(RESULT/'events.csv'); checked=0; event_checked=0
    for src in ('binance','kucoin'):
        f=pd.read_csv(DATA/(src+'-spot-4h.csv.gz'));f.index=pd.to_datetime(f.ts,unit='ms',utc=True)
        for row in layers[layers.source==src].itertuples():
            t=pd.Timestamp(row.as_of_utc); big,small,long=(calc(f,t,n) for n in (28,8,56));br,sr,lr=map(rel,(big,small,long))
            assert (br,sr,lr)==(row.big_relation,row.small_relation,row.long_relation),(src,t,'relation')
            season='UNKNOWN'
            if big is not None and small is not None:
                if br=='INSIDE' and sr=='UP' and big.close.iloc[-1]>(big.high.max()+big.low.min())/2:season='SPRING'
                elif br=='UP' and sr=='UP':season='SUMMER'
                elif br=='DOWN' and sr=='DOWN':season='WINTER'
            assert season==row.season,(src,t,'season')
            spring=autumn='UNKNOWN'
            if all(x is not None for x in (big,small,long)):
                spring='YES' if season=='SPRING' and lr in ('DOWN','INSIDE') else 'NO'
                recent=big.iloc[-14*6:];mid=(recent.high.max()+recent.low.min())/2
                autumn='YES' if br=='UP' and sr=='DOWN' and lr=='UP' and big.close.iloc[-1]<mid else 'NO'
            assert (spring,autumn)==(row.spring_watch,row.autumn_watch),(src,t,'watch')
            for kind,watch in [('spring',spring),('autumn',autumn)]:
                e=events[(events.source==src)&(events.as_of_utc==row.as_of_utc)&(events.watch==kind)].iloc[0]
                status='NO_WATCH' if watch=='NO' else 'UNKNOWN_INPUT'
                eventtime=None;eventclose=None
                if watch=='YES':
                    hi,lo=big.high.max(),big.low.min()
                    assert np.isclose(hi,e.frozen_upper) and np.isclose(lo,e.frozen_lower)
                    status='UNRESOLVED_28D'
                    for i in range(28):
                        end=t+pd.Timedelta(days=i+1);day=calc(f,end,1)
                        if day is None:status='UNKNOWN_INCOMPLETE';break
                        price=day.close.iloc[-1]
                        if price>hi or price<lo:
                            status='UPPER_BREAK' if price>hi else 'LOWER_BREAK';eventtime=end.isoformat();eventclose=price;break
                    event_checked+=1
                assert status==e.status,(src,t,kind,status,e.status)
                if eventtime:
                    assert eventtime==e.event_time_utc and np.isclose(eventclose,e.event_close)
            checked+=1
    files=[Path(__file__),RESULT/'layers.csv',RESULT/'events.csv',DATA/'binance-spot-4h.csv.gz',DATA/'kucoin-spot-4h.csv.gz',Path('verify/market_2020_cross_20261102.py'),Path('verify/market_multilevel_20261102.py'),Path('verify/market_multilevel_guard_20261102.py'),Path('verify/market_season_research_20261102.py')]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'as_of_source_points_checked':checked,'positive_watch_events_checked':event_checked,'result':'PASS','inputs_sha256':hashes,'scope':'Independently recomputed from source bars; does not validate true season labels or rule selection.'},indent=2)+'\n');print(checked,event_checked,'PASS')
if __name__=='__main__':main()
