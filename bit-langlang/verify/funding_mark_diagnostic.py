"""Fixed-ledger funding mark-price sensitivity, not an account settlement."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .common import MARKET
from .prove_method import load5

START='2024-07-01T00:00:00Z'
END='2026-10-25T00:00:00Z'
BASE='https://fapi.binance.com/fapi/v1/fundingRate'
LEDGER=Path('data/verify/execution-delay-diagnostic-20261030')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(symbol):
    begin=int(pd.Timestamp(START).timestamp()*1000)
    end=int(pd.Timestamp(END).timestamp()*1000)-1
    cursor=begin; items=[]
    while cursor<=end:
        response=requests.get(BASE,params={'symbol':symbol,'startTime':cursor,'endTime':end,'limit':1000},timeout=20)
        response.raise_for_status(); batch=response.json()
        if not isinstance(batch,list): raise ValueError('unexpected API response')
        if not batch: break
        items.extend(batch)
        next_cursor=int(batch[-1]['fundingTime'])+1
        if next_cursor<=cursor: raise ValueError('API cursor did not advance')
        cursor=next_cursor
    return items


def funding_for_trade(trade, funding):
    """Use recorded entry inclusive, recorded exit exclusive, long position."""
    entry=pd.Timestamp(trade.entry_ts).value//1_000_000
    exit_=pd.Timestamp(trade.exit_ts).value//1_000_000
    events=funding[(funding.ts>=entry)&(funding.ts<exit_)]
    proxy=float((trade.qty*events.funding_rate*events.proxy_price).sum())
    mark=float((trade.qty*events.funding_rate*events.mark_price).sum())
    return len(events),proxy,mark


def main():
    out=Path('data/verify/funding-mark-diagnostic-20261030')
    if out.exists(): raise SystemExit('refusing to overwrite')
    initial=json.loads((LEDGER/'summary.json').read_text())
    data_by_symbol={};api_by_symbol={}
    for sym in ('BTCUSDT','ETHUSDT'):
        paths=[Path(MARKET)/f'{sym}_5m.csv.gz',Path(MARKET)/f'{sym}_funding.csv.gz']
        for p in paths:
            if digest(p)!=initial['inputs'][p.name]: raise ValueError(f'input hash changed: {p.name}')
        raw=download(sym)
        if not raw or any(x.get('symbol')!=sym for x in raw): raise ValueError('empty or wrong symbol')
        fetched=pd.DataFrame([{'ts':int(x['fundingTime']),'funding_rate':float(x['fundingRate']),
                               'mark_price':float(x['markPrice'])} for x in raw])
        if fetched.ts.duplicated().any() or not fetched.ts.is_monotonic_increasing or not np.isfinite(fetched[['funding_rate','mark_price']].to_numpy()).all() or (fetched.mark_price<=0).any():
            raise ValueError('invalid funding response')
        original=pd.read_csv(paths[1]); begin=int(pd.Timestamp(START).timestamp()*1000);end=int(pd.Timestamp(END).timestamp()*1000)
        original=original[(original.ts>=begin)&(original.ts<end)]
        if not np.array_equal(fetched.ts.to_numpy(),original.ts.to_numpy()) or not np.allclose(fetched.funding_rate,original.funding_rate,rtol=0,atol=1e-12):
            raise ValueError(f'{sym} funding times or rates do not match local input')
        candles=load5(sym).set_index('ts')
        candle_times=pd.to_datetime((fetched.ts//300000)*300000,unit='ms',utc=True)
        if not candle_times.isin(candles.index).all(): raise ValueError('missing funding-bar candle')
        fetched['proxy_price']=candles.loc[candle_times,'open'].to_numpy()
        api_by_symbol[sym]=raw;data_by_symbol[sym]=fetched
    scenarios={};details={}
    for name,expected in initial['scenarios'].items():
        symbol='ETHUSDT' if name.startswith('ETH') else 'BTCUSDT'
        path=LEDGER/f'{name}_closed.csv'
        trades=pd.read_csv(path)
        if len(trades)!=expected['closed'] or expected['open']!=0: raise ValueError('ledger mismatch or open trades')
        rows=[]
        for trade in trades.itertuples():
            count,proxy,mark=funding_for_trade(trade,data_by_symbol[symbol])
            if not np.isclose(proxy,trade.funding_paid,rtol=0,atol=1e-7): raise ValueError(f'{name} trade {trade.trade_id} funding mismatch')
            rows.append({'trade_id':int(trade.trade_id),'funding_events':count,'recorded_funding_usdt':trade.funding_paid,
                         'proxy_recomputed_usdt':proxy,'api_mark_estimated_usdt':mark,'mark_minus_proxy_usdt':mark-proxy})
        detail=pd.DataFrame(rows);details[name]=detail
        scenarios[name]={'closed':len(detail),'funding_events_on_trades':int(detail.funding_events.sum()),
                         'proxy_funding_usdt':float(detail.proxy_recomputed_usdt.sum()),
                         'api_mark_funding_usdt':float(detail.api_mark_estimated_usdt.sum()),
                         'mark_minus_proxy_usdt':float(detail.mark_minus_proxy_usdt.sum()),
                         'maximum_trade_difference_usdt':float(detail.mark_minus_proxy_usdt.abs().max()),
                         'max_proxy_reconciliation_error_usdt':float((detail.proxy_recomputed_usdt-detail.recorded_funding_usdt).abs().max()),
                         'closed_ledger_sha256':digest(path)}
    out.mkdir(parents=True,exist_ok=False)
    for sym,raw in api_by_symbol.items(): (out/f'{sym}_api_response.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,detail in details.items(): detail.to_csv(out/f'{name}_funding_comparison.csv',index=False)
    result={'status':'FIXED_LEDGER_SENSITIVITY_NOT_REPLAY_OR_SETTLEMENT', 'interval_utc':[START,END],
            'source':'Binance USD-M public GET /fapi/v1/fundingRate',
            'preregistration_sha256':digest(Path('docs/资金费标记价敏感性-事前定义-20261030.md')),
            'input_summary_sha256':digest(LEDGER/'summary.json'),
            'api_response_sha256':{sym:digest(out/f'{sym}_api_response.json') for sym in api_by_symbol},
            'public_rate_count':{sym:len(frame) for sym,frame in data_by_symbol.items()},'scenarios':scenarios,
            'limitations':['Fixed recorded positions, no cash or position-size re-simulation.',
                           'Funding position timing at settlement and 5m-bar exit ordering are assumptions.',
                           'Public mark is not verified account settlement price; user exchange unknown.',
                           'Same historical data and trade paths as prior research; not out of sample.']}
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
