"""Post-hoc two-hour public trade/candle comparison; never asserts true market completeness."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import requests

DATA=Path('data/market/btc-2017sep-usd-cross-20261103-01');OUT=Path('data/verify/market-2017sep-trade-spotcheck-20261103-01');SPEC=Path('docs/2017九月重点小时逐笔-事后定义-20261103.md')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    candles=pd.read_csv(DATA/'bitfinex-1h.csv.gz').set_index('ts');OUT.mkdir();records=[];files=[Path(__file__),SPEC,DATA/'bitfinex-1h.csv.gz']
    for i,date in enumerate(('2017-09-06 23:00','2017-09-13 23:00')):
        start=pd.Timestamp(date,tz='UTC');end=start+pd.Timedelta(hours=1);params={'start':int(start.timestamp()*1000),'end':int(end.timestamp()*1000)-1,'limit':10000,'sort':1};q={'start_utc':start.isoformat(),'end_exclusive_utc':end.isoformat(),'status':'UNKNOWN','source':'Bitfinex public trades'}
        try:
            r=requests.get('https://api-pub.bitfinex.com/v2/trades/tBTCUSD/hist',params=params,timeout=50);q.update(http_status=r.status_code,request_url=r.url);p=OUT/f'trades-{i}.json';p.write_bytes(r.content);files.append(p);r.raise_for_status();z=r.json();assert isinstance(z,list) and (not z or isinstance(z[0],list));tr=pd.DataFrame(z,columns=['id','ts','amount','price']).apply(pd.to_numeric)
            q['rows']=len(tr)
            if tr.empty:q['reason']='EMPTY_RESPONSE'
            elif len(tr)>=10000:q['reason']='POSSIBLY_TRUNCATED'
            elif tr.id.duplicated().any() or not (tr.ts>=params['start']).all() or not (tr.ts<=params['end']).all() or not np.isfinite(tr[['amount','price']].to_numpy()).all() or tr.amount.eq(0).any() or tr.price.le(0).any():q['reason']='INVALID_RECORDS'
            elif params['start'] not in candles.index:q['reason']='CANDLE_MISSING'
            else:
                c=candles.loc[params['start']];vol=float(tr.amount.abs().sum());hi=float(tr.price.max());lo=float(tr.price.min());same_h=bool(np.isclose(hi,c['high'],rtol=0,atol=1e-8));same_l=bool(np.isclose(lo,c['low'],rtol=0,atol=1e-8));same_v=bool(np.isclose(vol,c['volume'],rtol=1e-8,atol=1e-8));q.update(status='REPORTED_RECORDS_MATCH' if same_h and same_l and same_v else 'REPORTED_RECORDS_DIFFER',trade_high=hi,candle_high=float(c['high']),trade_low=lo,candle_low=float(c['low']),trade_abs_volume=vol,candle_volume=float(c['volume']),high_match=same_h,low_match=same_l,volume_match=same_v,same_timestamp_trades=int(tr.ts.duplicated(keep=False).sum()))
        except (requests.RequestException,ValueError,KeyError,AssertionError,TypeError) as exc:q['reason']=type(exc).__name__
        records.append(q)
    (OUT/'summary.json').write_text(json.dumps({'cases':records,'scope':'Post-hoc two single-venue hours; API completeness and true trades remain unverified.','input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print([(q['start_utc'],q['status'],q.get('rows'),q.get('reason')) for q in records])
if __name__=='__main__':main()
