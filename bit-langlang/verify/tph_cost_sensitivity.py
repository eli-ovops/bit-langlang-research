"""Compare fixed fee plus slippage assumptions; no strategy parameter search."""
import json
from pathlib import Path
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals
from .tph_ledger import replay


def main():
    out = Path('data/verify/cost-sensitivity-20261030.json')
    if out.exists(): raise SystemExit('refusing to overwrite existing results')
    btc, eth = load5('BTCUSDT'), load5('ETHUSDT')
    funding = pd.read_csv(Path(MARKET) / 'ETHUSDT_funding.csv.gz')
    hit, _, ema20 = signals(btc, eth)
    result = {'status':'EXPLORATORY_NOT_VALIDATED', 'interval_utc':['2024-07-01','2026-10-25'],
              'note':'Same frozen signal; zero BTC; 5m close equity; fee 5bp per side; assumed slippage per side, not observed execution costs; liquidation uses last-price proxy; no mark prices, book depth or liquidation fee.', 'scenarios':[]}
    for slippage_bps in (0,2,5):
        metrics, rows, opened = replay(eth, hit, ema20, funding, '2024-07-01', '2026-10-25', slip=slippage_bps/10000)
        pnl = pd.Series([row['net_pnl'] for row in rows], dtype=float)
        winners = pnl[pnl > 0].sort_values(ascending=False)
        result['scenarios'].append({'slippage_bps_per_side':slippage_bps, **metrics,
            'net_pnl_closed':float(pnl.sum()), 'positive_trade_count':int(len(winners)),
            'top_1_profit':float(winners.head(1).sum()), 'top_3_profit':float(winners.head(3).sum()),
            'top_5_profit':float(winners.head(5).sum()),
            'net_pnl_less_top_3_static':float(pnl.sum()-winners.head(3).sum()),
            'top_trade_note':'Subtraction is descriptive, not a rerun of sizing or portfolio performance.'})
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__ == '__main__': main()
