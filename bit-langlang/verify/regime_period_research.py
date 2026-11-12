"""Descriptive post-selection replay across previously examined windows."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .regime_dynamic_research import ROOT,allowed_by_prior_day,load_checked,sha
from .tph_frozen_audit import signals
from .tph_ledger import replay

DEFINITION=ROOT/'docs/周期筛选-分段动态对照-事后探索定义-20261030.md'
WINDOWS=[('prior','2022-05-01','2024-07-01'),('middle','2024-07-01','2025-10-01'),('late','2025-10-01','2026-10-25')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);args=p.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    btc=load_checked('BTCUSDT');eth=load_checked('ETHUSDT');fund=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    if fund.ts.duplicated().any() or not fund.ts.is_monotonic_increasing or not np.isfinite(fund[['ts','funding_rate']].to_numpy(dtype=float)).all():
        raise ValueError('资金费数据无效')
    end=pd.Timestamp(WINDOWS[-1][2],tz='UTC')
    btc=btc[btc.ts<end].reset_index(drop=True);eth=eth[eth.ts<end].reset_index(drop=True)
    hit,_,ema=signals(btc,eth);allowed,returns=allowed_by_prior_day(eth)
    entry=eth.ts+pd.Timedelta(minutes=5);rows={}
    for name,start,finish in WINDOWS:
        select=hit&((entry>=pd.Timestamp(start,tz='UTC'))&(entry<pd.Timestamp(finish,tz='UTC'))).to_numpy()
        rows[name]={'start':start,'end_exclusive':finish,'candidates':int(select.sum()),
                    'kept':int((select&allowed).sum()),'missing_prior':int((select&~np.isfinite(returns)).sum()),'results':{}}
        for variant,mask in [('baseline',hit),('filtered',hit&allowed)]:
            result,closed,opened=replay(eth,mask,ema,fund,start,finish,fee=.0005,slip=.0002)
            if abs(result['ledger_reconciliation_error'])>1e-7:raise ValueError('账本权益不一致')
            for label,records in [('closed',closed),('open',opened)]:
                pd.DataFrame(records).to_csv(out/f'{name}_{variant}_{label}.csv',index=False)
            rows[name]['results'][variant]=result
    summary={'status':'POST_SELECTION_EXPLORATORY_NOT_OOS','windows':rows,
             'inputs':{'btc':sha(Path(MARKET)/'BTCUSDT_5m.csv.gz'),'eth':sha(Path(MARKET)/'ETHUSDT_5m.csv.gz'),
                       'funding':sha(Path(MARKET)/'ETHUSDT_funding.csv.gz'),'definition':sha(DEFINITION),
                       'code':sha(Path(__file__)),'filter':sha(ROOT/'verify/regime_dynamic_research.py'),
                       'signals':sha(ROOT/'verify/tph_frozen_audit.py'),'replay':sha(ROOT/'verify/tph_ledger.py')}}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
