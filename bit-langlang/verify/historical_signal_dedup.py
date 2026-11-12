"""Causal per-symbol signal dedup and retrospective entry audit; no platform actions."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forward_scan import read_raw_candles
from .historical_entry_replica import eligible_match
from .historical_ten_replica import COINS

SOURCE=Path('data/verify/historical-pullback-candidate-20261030-01')
LABELS=Path('data/processed/trades_labeled.csv')
CLEAN=Path('data/processed/trades_clean.csv')
PANEL=Path('data/entry_exit/trades_panel.csv')
BEHAVIOR=Path('data/verify/historical-behavior-comparison-20261030-02/records.csv')
DEFINITION=Path('docs/历史入场-信号去重与标注证据-定义-20261030.md')
OFFSETS=(-120,-90,-60,-30,30,60,90,120)
STEP=30*60*1_000_000_000


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def deduplicate(times,interval=STEP):
    """Keep first eligible timestamp and future candidates >=30m after kept one."""
    if interval<=0:raise ValueError('invalid interval')
    previous=None;out=[]
    for raw in times:
        t=int(raw)
        if previous is not None and t<previous:raise ValueError('unsorted signal times')
        previous=t
        if not out or t-out[-1]>=interval:out.append(t)
    return out


def controls(t,coin,market_index,signal_ns):
    hits=[]
    for offset in OFFSETS:
        other=t+pd.Timedelta(minutes=offset)
        if other.floor('D')!=t.floor('D') or other.floor('5min') not in market_index:continue
        hits.append(int(eligible_match(signal_ns,other.value) is not None))
    return {'count':len(hits),'hits':sum(hits),'expected':sum(hits)/len(hits) if hits else None}


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);a=p.parse_args();out=Path(a.outdir)
    if out.exists():raise FileExistsError('refusing overwrite')
    files=(SOURCE/'pullback_delayed_candidate-signal-times.json',SOURCE/'pullback_delayed_candidate-rows.csv',
           SOURCE/'nearby-time-control.json',LABELS,CLEAN,PANEL,BEHAVIOR,DEFINITION,Path(__file__))
    hashes={str(x):sha(x) for x in files}
    source=json.loads(files[0].read_text());dedup={s:deduplicate(v) for s,v in source.items()}
    market={}
    for coin in COINS:
        path=Path('data/market')/f'{coin}USDT_5m.csv.gz';hashes[str(path)]=sha(path)
        market[coin]=read_raw_candles(coin+'USDT').set_index('ts').index
    rows=pd.read_csv(files[1]);valid=rows.status.isin(['SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP']);records=[]
    for row in rows.itertuples(index=False):
        item={'coin':row.coin,'side':row.side,'entry_assumed_utc':row.entry_assumed_utc,
              'old_status':row.status,'new_status':row.status,'stop_order':'UNKNOWN_NOT_RECORDED','target_order':'UNKNOWN_NOT_RECORDED'}
        if row.status in ('SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP'):
            t=pd.to_datetime(row.entry_assumed_utc,utc=True);old=eligible_match(source[row.coin],t.value);new=eligible_match(dedup[row.coin],t.value)
            if (old is not None)!=(row.status=='SIGNAL_OVERLAP') or (new is not None and old is None):raise ValueError('match inconsistency')
            old_ctl=controls(t,row.coin,market[row.coin],source[row.coin]);new_ctl=controls(t,row.coin,market[row.coin],dedup[row.coin])
            item.update(new_status='SIGNAL_OVERLAP' if new is not None else 'NO_SIGNAL_OVERLAP',
                        old_match_ns=old,new_match_ns=new,old_control=old_ctl,new_control=new_ctl)
        records.append(item)
    selected=[r for r in records if r['old_status'] in ('SIGNAL_OVERLAP','NO_SIGNAL_OVERLAP')]
    if len(selected)!=int(valid.sum()):raise ValueError('scope mismatch')
    old_expected=sum(x['old_control']['expected'] for x in selected if x['old_control']['expected'] is not None)
    old_baseline=json.loads(files[2].read_text())['results']['pullback_delayed_candidate']['control_expected_hits']
    if abs(old_expected-old_baseline)>1e-9:raise ValueError('original control baseline differs')
    def summarize(field,control):
        matched=[x for x in selected if x[field]=='SIGNAL_OVERLAP'];year={}
        for period,condition in [('2022_2023',lambda y:y<=2023),('2024',lambda y:y==2024)]:
            group=[x for x in selected if condition(pd.to_datetime(x['entry_assumed_utc'],utc=True).year)]
            year[period]={'rows':len(group),'matches':sum(x[field]=='SIGNAL_OVERLAP' for x in group)}
        return {'matched_rows':len(matched),'unique_matched_signals':len({(x['coin'],x['old_match_ns' if field=='old_status' else 'new_match_ns']) for x in matched}),
                'nearby_control_expected':sum(x[control]['expected'] for x in selected if x[control]['expected'] is not None),
                'without_controls':sum(x[control]['expected'] is None for x in selected),'by_period':year}
    labeled=pd.read_csv(LABELS);clean=pd.read_csv(CLEAN);panel=pd.read_csv(PANEL);behavior=pd.read_csv(BEHAVIOR)
    if len(panel)!=len(rows) or len(behavior)!=len(panel):raise ValueError('panel alignment length mismatch')
    columns=['btc_cycle','btc_cycle_anchor','alt_cycle','pred_entry_type','actual_entry_type','review_note','op_detail']
    labeled=labeled[labeled[columns].notna().any(axis=1)];annotations=[]
    for x in labeled.itertuples(index=False):
        raw=clean[(clean.symbol==x.symbol)&(clean.side==x.side)&(clean.entry_time==x.entry_time)]
        matched=panel[(panel.symbol==x.symbol)&(panel.side==x.side)&(panel.entry_time==x.entry_time)]
        item={'label_id':int(x.id),'symbol':x.symbol,'side':x.side,'entry_original':x.entry_time,
              'btc_cycle':None if pd.isna(x.btc_cycle) else str(x.btc_cycle),
              'review_note':None if pd.isna(x.review_note) else str(x.review_note),
              'clean_matching_rows':len(raw),'panel_matching_rows':len(matched),
              'annotation_author':'UNKNOWN','annotation_recording_time':'UNKNOWN','stop_order':'UNKNOWN_NOT_RECORDED','target_order':'UNKNOWN_NOT_RECORDED'}
        if len(raw)==len(matched)==1:
            ix=int(matched.index[0]);item.update(clean_id=int(raw.iloc[0].id),panel_row=ix,
                 original_candidate_status=records[ix]['old_status'],dedup_candidate_status=records[ix]['new_status'],
                 btc_regime_above_midpoint=None if pd.isna(behavior.iloc[ix].btc_above_midpoint) else bool(behavior.iloc[ix].btc_above_midpoint))
        annotations.append(item)
    if any(sha(x)!=v for x,v in hashes.items()):raise ValueError('input changed')
    report={'status':'POST_HOC_DIAGNOSTIC_NOT_REPLICATION','source_signal_count':sum(len(x) for x in source.values()),
            'dedup_signal_count':sum(len(x) for x in dedup.values()),'evaluable':len(selected),
            'original':summarize('old_status','old_control'),'dedup':summarize('new_status','new_control'),
            'lost_matches':sum(x['old_status']=='SIGNAL_OVERLAP' and x['new_status']!='SIGNAL_OVERLAP' for x in selected),
            'new_matches':sum(x['old_status']!='SIGNAL_OVERLAP' and x['new_status']=='SIGNAL_OVERLAP' for x in selected),
            'labeled_input_rows':len(pd.read_csv(LABELS)),'nonempty_label_rows':len(labeled),'annotations':annotations,
            'input_sha256':hashes,'limitations':['Retrospectively selected 30-minute hypothesis; not a profit test.',
                 'Same-symbol time overlap is not actual entry or account execution.',
                 'Notes are retrospective/unattributed; time, identity and venue unverified.',
                 'Historical stop/target orders are UNKNOWN_NOT_RECORDED.']}
    out.mkdir(parents=True,exist_ok=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (out/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (out/'deduplicated-signals.json').write_text(json.dumps(dedup)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('input_sha256','annotations')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
