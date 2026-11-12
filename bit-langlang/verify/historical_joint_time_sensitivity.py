"""Post-hoc match-window sensitivity; no signal thresholds change."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .historical_entry_replica import eligible_match
from .historical_pullback_candidate import COINS, sha
from .historical_signal_dedup import OFFSETS
from .forward_scan import read_raw_candles

BASE=Path('data/verify/historical-joint-filter-20261030-01')
OUT=Path('data/verify/historical-joint-time-sensitivity-20261030-01')
DEFINITION=Path('docs/历史入场-匹配窗口敏感性定义-20261030.md')

def main():
    if OUT.exists():raise FileExistsError('refuse overwrite')
    files=[BASE/'signals.json',BASE/'rows.csv',BASE/'summary.json',DEFINITION,Path(__file__)]
    hashes={str(p):sha(p) for p in files};signals=json.loads(files[0].read_text());rows=pd.read_csv(files[1]);prior=json.loads(files[2].read_text())
    signals={v:{c:np.asarray(a,dtype=np.int64) for c,a in per.items()} for v,per in signals.items()}
    market={c:read_raw_candles(c+'USDT').set_index('ts').index for c in COINS};results={};records=[]
    for row in rows.itertuples(index=False):
        t=pd.Timestamp(row.entry_assumed_utc);result={'panel_row':row.panel_row,'coin':row.coin,'entry_assumed_utc':row.entry_assumed_utc}
        for minutes in (5,10,15):
            window=minutes*60*10**9
            for v,per in signals.items():
                arr=per[row.coin];match=eligible_match(arr,t.value,window_ns=window);checks=[]
                for offset in OFFSETS:
                    other=t+pd.Timedelta(minutes=offset)
                    if other.floor('D')==t.floor('D') and other.floor('5min') in market[row.coin]:checks.append(eligible_match(arr,other.value,window_ns=window) is not None)
                result[f'{v}_{minutes}_match']=match is not None;result[f'{v}_{minutes}_control']=float(np.mean(checks)) if checks else None
        records.append(result)
    df=pd.DataFrame(records)
    for minutes in (5,10,15):
        results[str(minutes)]={}
        for v in signals:
            matches=int(df[f'{v}_{minutes}_match'].sum());expected=float(df[f'{v}_{minutes}_control'].sum());results[str(minutes)][v]={'matches':matches,'control_expected':expected}
            if minutes==15:
                prev=prior['groups']['all'][v];assert matches==prev['matches'] and abs(expected-prev['control_expected'])<1e-8
    assert all(sha(p)==v for p,v in hashes.items())
    OUT.mkdir(parents=True);df.to_csv(OUT/'rows.csv',index=False);(OUT/'summary.json').write_text(json.dumps({'status':'POST_HOC_WINDOW_SENSITIVITY','results':results,'input_sha256':hashes,'limitations':['Time overlap is not proof of same signal or executable trade.','Controls are descriptive and not independent.']},ensure_ascii=False,indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
