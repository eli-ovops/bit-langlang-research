"""Offline unregistered OHLC proxy replay; never an order or forward proof."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .execution_delay_diagnostic import candidates_with_entry_in_window, delay_one_bar
from .forward_scan import closed_snapshot, read_raw_candles
from .funding_reconcile import read_schedule
from .tph_frozen_audit import signals
from .tph_ledger import replay


BASE_HASH='a15b84d37e30f7ac8024e031512026168b45c967104f92899c850909289495c3'
DEFINITION=Path('docs/五分钟双延迟影子研究候选-v0.1.md')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(market_dir,funding_path,start,end,*,now=None,schedule_path=None):
    """Recompute only completed bars; funding coverage and authenticity remain unknown."""
    start=pd.to_datetime(start,utc=True,errors='raise');end=pd.to_datetime(end,utc=True,errors='raise')
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.to_datetime(now,utc=True,errors='raise')
    if (any(pd.isna(x) for x in (start,end,now)) or start.floor('5min')!=start or end.floor('5min')!=end
            or start>=end or end>now):raise ValueError('研究区间必须是过去的 UTC 5 分钟网格')
    if sha('verify/frozen_config.json')!=BASE_HASH:raise ValueError('原冻结配置已改变，不能沿用候选版本')
    frames={};hashes={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        path=Path(market_dir)/f'{symbol}_5m.csv.gz';hashes[symbol]=sha(path)
        frame,state=closed_snapshot(read_raw_candles(symbol,market_dir),end,minimum_bars=205*288)
        if (frame is None or state['status']!='FRESH' or frame.ts.iloc[-1]!=end-pd.Timedelta(minutes=5)
                or start-frame.ts.iloc[0]<pd.Timedelta(days=205)):
            raise ValueError('行情不完整、缺尾柱或起点前预热不足')
        frames[symbol]=frame.reset_index(drop=True)
    btc,eth=frames['BTCUSDT'],frames['ETHUSDT']
    if not btc.ts.equals(eth.ts):raise ValueError('BTC/ETH 已收盘时间网格不一致')
    funding_hash=sha(funding_path)
    funding=pd.read_csv(funding_path,usecols=['ts','funding_rate'])
    for key in ('ts','funding_rate'):funding[key]=pd.to_numeric(funding[key],errors='coerce')
    values=funding[['ts','funding_rate']].to_numpy(dtype=float)
    if (not np.isfinite(values).all() or (funding.ts<0).any() or (funding.ts>pd.Timestamp.max.value//1_000_000).any() or
            (funding.ts%1!=0).any() or funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing):
        raise ValueError('资金费时间或费率无效')
    funding['ts']=funding.ts.astype('int64')
    coverage='UNKNOWN';snapshot_hashes=None
    if schedule_path is not None:
        folder=Path(schedule_path)
        snapshot_hashes={name:sha(folder/name) for name in ('manifest.json','BTCUSDT.json','ETHUSDT.json')}
        begin,finish,events,manifest_hash,server_ms,captured=read_schedule(folder)
        if manifest_hash!=snapshot_hashes['manifest.json']:raise ValueError('读取期间资金费快照发生变化')
        if captured>now or server_ms*1_000_000>now.value:raise ValueError('资金费快照采集晚于检查时间')
        if begin<=start and finish>=end:
            supplied={int(row.ts):float(row.funding_rate) for row in funding.itertuples()
                      if start.value<=int(row.ts)*1_000_000<end.value}
            expected={stamp.value//1_000_000:rate_price[0] for stamp,rate_price in events['ETHUSDT'].items()
                      if start<=stamp<end}
            if set(supplied)!=set(expected) or any(not np.isclose(supplied[t],expected[t],rtol=0,atol=1e-12) for t in expected):
                raise ValueError('资金费 CSV 与覆盖快照不一致')
            coverage='PARTIAL_PUBLIC_RATE_COVERAGE_UNVERIFIED'
        else:
            coverage='UNKNOWN_INCOMPLETE_SNAPSHOT'
    hit,_,ema=signals(btc,eth)
    hit=np.asarray(hit,dtype=bool)&(eth.ts>=start).to_numpy()
    delayed=delay_one_bar(hit)
    metrics,closed,opened=replay(eth,delayed,ema,funding,start.isoformat(),end.isoformat(),
                                 fee=.0005,slip=.0002,delayed_stop=True)
    candidates=candidates_with_entry_in_window(eth,delayed,start.isoformat(),end.isoformat())
    if candidates!=len(closed)+len(opened)+metrics['skipped'] or abs(metrics['ledger_reconciliation_error'])>1e-7:
        raise ValueError('候选数量或权益对账不一致')
    for row in closed:
        risk=(row['entry']-row['stop'])*row['qty']
        net=row['gross_pnl']-row['entry_fee']-row['exit_fee']-row['funding_paid']
        if not np.isfinite([risk,net]).all() or risk<=0 or abs(net-row['net_pnl'])>1e-8:
            raise ValueError('平仓风险或成本对账无效')
        ratio=net/risk
        if not np.isfinite(ratio):raise ValueError('平仓净 R 非有限值')
        row['initial_price_risk_usdt']=risk;row['net_R']=ratio
    for row in opened:
        risk=(row['entry']-row['stop'])*row['qty']
        if not np.isfinite([risk,row['net_pnl_to_date']]).all() or risk<=0:raise ValueError('未平仓风险无效')
        ratio=row['net_pnl_to_date']/risk
        if not np.isfinite(ratio):raise ValueError('未平仓净 R 非有限值')
        row['initial_price_risk_usdt']=risk;row['net_R_to_date_unrealized']=ratio
    if any(sha(Path(market_dir)/f'{symbol}_5m.csv.gz')!=digest for symbol,digest in hashes.items()) or sha(funding_path)!=funding_hash:
        raise ValueError('研究期间输入文件发生变化')
    if snapshot_hashes is not None and any(sha(Path(schedule_path)/name)!=digest for name,digest in snapshot_hashes.items()):
        raise ValueError('研究期间资金费快照发生变化')
    return {'status':'SHADOW_NOT_REGISTERED','execution':'5m OHLC proxy; not an executable price or actual fill',
            'observation_interval':{'start_utc':start.isoformat(),'end_utc_exclusive':end.isoformat()},
            'candidates':candidates,'metrics':metrics,'closed':closed,'open':opened,
            'funding_coverage':coverage,'source_authenticity':'UNKNOWN','clock_trust':'UNKNOWN',
            'input_sha256':{'markets':hashes,'funding':funding_hash,'funding_snapshot':snapshot_hashes},'base_config_sha256':BASE_HASH,
            'definition_sha256':sha(DEFINITION),'code_sha256':{p:sha(p) for p in
                ('verify/shadow_5m_candidate.py','verify/tph_ledger.py','verify/tph_frozen_audit.py','verify/execution_delay_diagnostic.py')},
            'limitations':['Not registered or prospective proof; inputs may be retrospectively edited.',
                'Proxy open fills, stop lows and liquidation are not venue mark prices or fills.',
                'Funding completeness and actual costs are unknown; account and liquidation are modeled.',
                '5m close drawdown excludes intrabar risk; no automatic strategy decision.']}


def main():
    parser=argparse.ArgumentParser()
    for flag in ('market-dir','funding','start','end','out'):parser.add_argument('--'+flag,required=True)
    parser.add_argument('--funding-snapshot',help='可选公开资金费快照目录；只核对覆盖与费率')
    args=parser.parse_args();path=Path(args.out)
    if path.exists():raise SystemExit('refusing to overwrite output')
    result=evaluate(args.market_dir,args.funding,args.start,args.end,schedule_path=args.funding_snapshot)
    encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    with path.open('x') as file:file.write(encoded)
    print(json.dumps({'status':result['status'],'candidates':result['candidates'],
                      'metrics':result['metrics'],'funding_coverage':result['funding_coverage'],'out':str(path)},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
