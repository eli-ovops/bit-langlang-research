"""Compare fixed ETH and BTC research signals in predefined time windows."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals
from .btc_h1_historical import btc_eligible_signals
from .tph_ledger import replay


def main():
    out=Path('data/verify/fixed-period-audit-20261030');out.mkdir(parents=True,exist_ok=False)
    btc=load5('BTCUSDT');eth=load5('ETHUSDT')
    eb,_,ee=signals(btc,eth);bb,be=btc_eligible_signals(btc)
    inputs=[Path(MARKET)/n for n in ['BTCUSDT_5m.csv.gz','ETHUSDT_5m.csv.gz','BTCUSDT_funding.csv.gz','ETHUSDT_funding.csv.gz']]
    result={'status':'EXPLORATORY_NOT_VALIDATED','definition_sha256':hashlib.sha256(Path('docs/固定规则分时段检验-事前定义-20261030.md').read_bytes()).hexdigest(),
            'config_sha256':hashlib.sha256(Path('verify/frozen_config.json').read_bytes()).hexdigest(),
            'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            'warning':'Previously studied historical windows, independently reset accounts; not independent OOS or a joint BTC/ETH portfolio. Close-price drawdown and liquidation proxy; cost assumptions are not actual fills.',
            'windows':{}}
    windows=[('prior','2022-05-01','2024-07-01'),('later_a','2024-07-01','2025-10-01'),('later_b','2025-10-01','2026-10-25')]
    for label,d,hit,ema in [('ETH_frozen',eth,eb,ee),('BTC_H1',btc,bb,be)]:
        fund=pd.read_csv(Path(MARKET)/f'{"ETHUSDT" if label=="ETH_frozen" else "BTCUSDT"}_funding.csv.gz')
        result['windows'][label]={}
        for name,start,end in windows:
            metrics,closed,opened=replay(d,hit,ema,fund,start,end,slip=.0002)
            c=pd.DataFrame(closed);o=pd.DataFrame(opened)
            c.to_csv(out/f'{label}_{name}_closed.csv',index=False);o.to_csv(out/f'{label}_{name}_open.csv',index=False)
            next_open=d.ts+pd.Timedelta(minutes=5)
            mask=(next_open>=pd.Timestamp(start,tz='UTC'))&(next_open<pd.Timestamp(end,tz='UTC'))
            summary={'start_utc':start,'end_exclusive_utc':end,'candidate_count':int((hit&mask.to_numpy()).sum()),
                     'positive_closed_count':int((c.net_pnl>0).sum()) if len(c) else 0,
                     'realized_net_pnl_usdt':float(c.net_pnl.sum()) if len(c) else 0.,**metrics}
            result['windows'][label][name]=summary
            print(label,name,'candidates',summary['candidate_count'],'trades',metrics['closed'],'open',metrics['open'],
                  'cagr',round(metrics['cagr_pct'],2) if metrics['cagr_pct'] is not None else None,
                  'drawdown',round(metrics['mdd_close_5m_pct'],2),flush=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
