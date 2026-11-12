"""Four selected-history fill assumptions; not a live execution model."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .execution_delay_diagnostic import delay_one_bar,candidates_with_entry_in_window
from .regime_dynamic_research import ROOT,load_checked,sha
from .tph_frozen_audit import signals
from .tph_ledger import replay

START='2024-07-01';END='2026-10-25'
DEFINITION=ROOT/'docs/入场止损双延迟-事后探索定义-20261030.md'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--outdir',required=True);args=ap.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=False)
    btc=load_checked('BTCUSDT');eth=load_checked('ETHUSDT');fund=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    if fund.ts.duplicated().any() or not fund.ts.is_monotonic_increasing or not np.isfinite(fund[['ts','funding_rate']].to_numpy(dtype=float)).all():
        raise ValueError('资金费数据无效')
    end=pd.Timestamp(END,tz='UTC');btc=btc[btc.ts<end].reset_index(drop=True);eth=eth[eth.ts<end].reset_index(drop=True)
    hit,_,ema=signals(btc,eth);report={}
    for entry,mask in [('next_open',hit),('extra_5m',delay_one_bar(hit))]:
        for exit_delay in (False,True):
            name=entry+('_stop_next_open' if exit_delay else '_stop_same_bar')
            result,closed,opened=replay(eth,mask,ema,fund,START,END,fee=.0005,slip=.0002,delayed_stop=exit_delay)
            candidates=candidates_with_entry_in_window(eth,mask,START,END)
            if candidates!=len(closed)+len(opened)+result['skipped'] or abs(result['ledger_reconciliation_error'])>1e-7:
                raise ValueError('候选或权益对账失败')
            pd.DataFrame(closed).to_csv(out/(name+'_closed.csv'),index=False)
            pd.DataFrame(opened).to_csv(out/(name+'_open.csv'),index=False)
            report[name]={'candidates':candidates,**result}
    summary={'status':'POST_SELECTION_EXPLORATORY_NOT_OOS','scenarios':report,
             'inputs':{'btc':sha(Path(MARKET)/'BTCUSDT_5m.csv.gz'),'eth':sha(Path(MARKET)/'ETHUSDT_5m.csv.gz'),
                       'funding':sha(Path(MARKET)/'ETHUSDT_funding.csv.gz'),'definition':sha(DEFINITION),
                       'code':sha(Path(__file__)),'replay':sha(ROOT/'verify/tph_ledger.py'),
                       'signals':sha(ROOT/'verify/tph_frozen_audit.py'),'delay':sha(ROOT/'verify/execution_delay_diagnostic.py')}}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
