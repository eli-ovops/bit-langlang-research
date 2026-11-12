"""Verify later candle perturbations cannot alter earlier signals and risk inputs."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from . import nine_futures_compound_20261031 as model

STAGE=Path('data/market/nine-futures-stage-20261031-01');OUT=Path('data/verify/nine-futures-compound-20261031-01')
def main():
    model.SYMBOLS=tuple(json.loads((STAGE/'manifest.json').read_text())['symbols']);idx,baseline=model.prepare(STAGE)
    original=model.read_raw_candles;cut=pd.Timestamp('2026-03-01T00:00:00Z')
    def changed(symbol,*args,**kwargs):
        f=original(symbol,*args,**kwargs).copy();f.loc[f.ts>=cut,['open','high','low','close']]*=1.71;return f
    model.read_raw_candles=changed
    try:idx2,other=model.prepare(STAGE)
    finally:model.read_raw_candles=original
    assert idx.equals(idx2);prior=idx<cut
    for s in model.SYMBOLS:
        for k in ('signal','rank','relative_strength','stop'):
            assert np.array_equal(baseline[s][k][prior],other[s][k][prior],equal_nan=True),(s,k)
    result={'result':'PASS','cutoff':cut.isoformat(),'perturbation':'multiply all later OHLC by 1.71 for all assets and BTC','checked_symbols':list(model.SYMBOLS),'limitations':'single cutoff; checks signal/rank/stop arrays only, not execution or market authenticity'}
    (OUT/'prefix-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
