"""Count historical entries compatible with phase/strength gates; no orders inferred."""
import argparse
import json
from pathlib import Path

import pandas as pd

from .forward_scan import read_raw_candles
from .historical_ten_replica import COINS,BEGIN,END,PANEL,sha

SOURCE=Path('data/verify/historical-pullback-candidate-20261030-01/pullback_delayed_candidate-rows.csv')
DEFINITION=Path('docs/历史入场-周期强势覆盖-补充定义-20261030.md')


def run():
    idx=pd.date_range(BEGIN,END-pd.Timedelta(minutes=5),freq='5min');daily={};hashes={}
    for coin in sorted(COINS):
        path=Path('data/market')/f'{coin}USDT_5m.csv.gz';hashes[str(path)]=sha(path)
        frame=read_raw_candles(coin+'USDT').set_index('ts')
        if frame.index.duplicated().any() or not frame.index.is_monotonic_increasing:raise ValueError('invalid timestamp ordering')
        frame=frame.reindex(idx);daily[coin]=frame.resample('1D').agg({'high':'max','low':'min','close':'last','open':'count'})
    btc=daily['BTC'];regime=(btc.close>(btc.high.rolling(20,min_periods=20).max()+btc.low.rolling(20,min_periods=20).min())/2).shift(1,fill_value=False)
    bret=btc.close.pct_change(7,fill_method=None);scores={}
    for coin,dd in daily.items():
        warm=dd.open.eq(288).shift(1,fill_value=False).rolling(30,min_periods=30).sum().eq(30)
        scores[coin]=(dd.close.pct_change(7,fill_method=None)-bret).shift(1).where(warm)
    scores=pd.DataFrame(scores);ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first')
    panel=pd.read_csv(PANEL);source=pd.read_csv(SOURCE)
    if len(panel)!=len(source):raise ValueError('panel/source mismatch')
    rows=[]
    for i,(row,prior) in enumerate(zip(panel.itertuples(index=False),source.itertuples(index=False))):
        if prior.status not in ('SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'):continue
        coin=row.coin;t=pd.to_datetime(row.entry_utc,utc=True);day=t.floor('D')
        if coin!=prior.coin or str(row.side)!=str(prior.side):raise ValueError('panel row mismatch')
        on=bool(regime.loc[day]);rs=scores.loc[day,coin];rank=ranks.loc[day,coin]
        if coin=='BTC':
            if pd.notna(rs) and abs(rs)>1e-12:raise ValueError('BTC self score changed')
            positive=None;top_two=None;joint=on
        else:
            if pd.isna(rs):raise ValueError('missing required prior strength')
            positive=bool(rs>0);top_two=bool(pd.notna(rank) and rank<=2);joint=on and positive and top_two
        rows.append({'row_number':i,'coin':coin,'entry_assumed_utc':t.isoformat(),'regime_on':on,
                     'relative_to_btc':float(rs) if pd.notna(rs) else None,'positive_relative':positive,
                     'rank':int(rank) if pd.notna(rank) else None,'top_two':top_two,'joint_pass':joint,
                     'eligible_positive_coins':int(scores.loc[day].gt(0).sum())})
    for path,digest in hashes.items():
        if sha(path)!=digest:raise ValueError('market changed')
    return rows,hashes


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();out=Path(a.outdir)
    if out.exists():raise FileExistsError('output exists')
    inputs={str(p):sha(p) for p in (PANEL,SOURCE,DEFINITION,Path(__file__))};rows,hashes=run()
    if any(sha(p)!=v for p,v in inputs.items()):raise ValueError('input changed')
    df=pd.DataFrame(rows);df['year']=pd.to_datetime(df.entry_assumed_utc,utc=True).dt.year
    groups={}
    for name,frame in [('all',df),('BTC',df[df.coin=='BTC']),('non_BTC',df[df.coin!='BTC']),
                       ('non_BTC_2022_2023',df[(df.coin!='BTC')&(df.year<=2023)]),('non_BTC_2024',df[(df.coin!='BTC')&(df.year==2024)])]:
        groups[name]={'rows':len(frame),'regime_on':int(frame.regime_on.sum()),'positive_relative':int(frame.positive_relative.fillna(False).sum()) if name!='BTC' else None,
                      'top_two':int(frame.top_two.fillna(False).sum()) if name!='BTC' else None,'joint_pass':int(frame.joint_pass.sum()),
                      'entry_days':int(pd.to_datetime(frame.entry_assumed_utc,utc=True).dt.floor('D').nunique())}
    out.mkdir(parents=True,exist_ok=False);df.to_csv(out/'rows.csv',index=False)
    result={'status':'POST_HOC_GATE_COVERAGE_NOT_CAUSAL','groups':groups,'inputs_sha256':{**inputs,**hashes},
            'limitations':['Retrospective ten-coin subset and unverified account/time/venue.',
                           'Necessary gate compatibility is not signal, execution or profitability.',
                           'BTC positive relative is undefined rather than an automatic rejection.']}
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(groups,indent=2))


if __name__=='__main__':main()
