"""Prepare as-of price charts; the caller supplies already retrieved source snapshots."""
import argparse,csv,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

R=Path(__file__).resolve().parents[1]
H=3600;D=86400


def valid(v):
    return len(v)==5 and all(math.isfinite(x) and x>0 for x in v) and v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1]


def assemble(t,bitfinex,kraken_daily,kraken_4h):
    if t% D: raise ValueError('asof must be UTC midnight')
    bf={}
    for row in bitfinex:
        raw_ts=int(row[0]);ts=raw_ts//1000;v=tuple(float(row[i]) for i in (1,3,4,2,5))
        if raw_ts%(H*1000):raise ValueError('unaligned Bitfinex timestamp')
        if ts in bf:raise ValueError('duplicate Bitfinex timestamp')
        bf[ts]=v
    kd={}
    for row in kraken_daily:
        ts=int(row[0]);v=tuple(float(row[i]) for i in (1,2,3,4,6))
        if ts%D:raise ValueError('unaligned Kraken daily timestamp')
        if ts in kd:raise ValueError('duplicate Kraken daily timestamp')
        kd[ts]=v
    k4={}
    for row in kraken_4h:
        stamp=datetime.fromisoformat(row['time_utc'])
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds()!=0:raise ValueError('Kraken 4h must specify UTC')
        ts=int(stamp.timestamp());v=tuple(float(row[i]) for i in ('open','high','low','close','volume'))
        if ts%(4*H):raise ValueError('unaligned Kraken 4h timestamp')
        if ts in k4:raise ValueError('duplicate Kraken 4h timestamp')
        k4[ts]=v
    def get(store,key):
        v=store.get(key)
        return v if v is not None and valid(v) else None
    def aggregate(values):
        if any(v is None for v in values):return None
        return (values[0][0],max(v[1] for v in values),min(v[2] for v in values),values[-1][3])
    bd=[aggregate([get(bf,day+i*H) for i in range(24)]) for day in range(t-180*D,t,D)]
    kr=[v[:4] if v is not None else None for v in (get(kd,day) for day in range(t-180*D,t,D))]
    four=[aggregate([get(bf,t4+i*H) for i in range(4)]) for t4 in range(t-42*4*H,t,4*H)]
    krfour=[v[:4] if v is not None else None for v in (get(k4,t4) for t4 in range(t-42*4*H,t,4*H))]
    # Compare every complete Kraken day in the 7-day overlap, not just the last close.
    conflicts=[]
    for i in range(7):
        aggregate4=aggregate(krfour[6*i:6*i+6]);daily=kr[-7+i]
        if aggregate4 is not None and daily is not None and aggregate4!=daily:
            conflicts.append(datetime.fromtimestamp(t-(7-i)*D,timezone.utc).isoformat())
    def panels(daily,four,reason=None):
        groups={'180 daily':daily,'56 daily':daily[-56:],'14 daily':daily[-14:],'42 x 4h':four}
        if reason:return {'panels':{k:None for k in groups},'last_close':None,'reason':reason}
        close=daily[-1][3] if daily[-1] is not None else four[-1][3] if four[-1] is not None else None
        if close is None:return {'panels':{k:None for k in groups},'last_close':None,'reason':'last close unavailable'}
        return {'panels':{k:v if all(x is not None for x in v) else None for k,v in groups.items()},'last_close':close,'reason':None}
    return {'bitfinex':panels(bd,four),'kraken':panels(kr,krfour,('daily/4h OHLC conflict at '+', '.join(conflicts)) if conflicts else None)}


def eligible_sentiment(s,t):
    observed_dt=datetime.fromisoformat(s['response_end_utc']);record_dt=datetime.fromisoformat(s['record_timestamp_utc'])
    if observed_dt.tzinfo is None or record_dt.tzinfo is None:raise ValueError('sentiment timestamps must have timezones')
    observed=observed_dt.timestamp();record=record_dt.timestamp()
    if observed>t or record>t:return None
    if not 0<=int(s['value'])<=100:raise ValueError('invalid sentiment')
    return {'value':s['value'],'classification':s['classification'],'response_end_utc':s['response_end_utc'],'record_timestamp_utc':s['record_timestamp_utc'],'components_asof':s.get('components_asof','UNKNOWN')}


def main():
    ap=argparse.ArgumentParser()
    for name in ('asof','bitfinex','kraken_daily','kraken_4h','output'):ap.add_argument('--'+name.replace('_','-'),required=True)
    ap.add_argument('--sentiment');ap.add_argument('--sentiment-raw')
    args=ap.parse_args();dt=datetime.fromisoformat(args.asof.replace('Z','+00:00'))
    if dt.tzinfo is None or dt.utcoffset().total_seconds()!=0 or dt.microsecond:raise ValueError('asof must specify whole-second UTC')
    t=int(dt.timestamp())
    if t>datetime.now(timezone.utc).timestamp():raise ValueError('asof is in the future')
    paths=[Path(args.bitfinex),Path(args.kraken_daily),Path(args.kraken_4h)]
    bit=json.loads(paths[0].read_text());kr=json.loads(paths[1].read_text())['result']['XXBTZUSD']
    with paths[2].open() as f:four=list(csv.DictReader(f))
    data=assemble(t,bit,kr,four)
    sentiment=None
    if bool(args.sentiment)!=bool(args.sentiment_raw):raise ValueError('sentiment summary and raw response must be supplied together')
    if args.sentiment:
        p=Path(args.sentiment);raw=Path(args.sentiment_raw);paths.extend((p,raw));summary=json.loads(p.read_text());body=raw.read_bytes()
        if hashlib.sha256(body).hexdigest()!=summary['response_sha256']:raise ValueError('sentiment response hash mismatch')
        item=json.loads(body)['data'][0]
        if int(item['value'])!=int(summary['value']) or item['value_classification']!=summary['classification'] or int(item['timestamp'])!=int(datetime.fromisoformat(summary['record_timestamp_utc']).timestamp()) or summary.get('http')!=200:raise ValueError('sentiment summary disagrees with response')
        sentiment=eligible_sentiment(summary,t)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    lines=['# 截点行情观察材料','','这是人工描述材料；不展示旧量化触发、未来走势或盈利。窗口用于展示，不是浪浪的公式。两所独立绘图，不混价。','',f'观察截止：{dt.isoformat()}。图中只包含此前完整日线及四小时柱。','',f'情绪代理：{json.dumps(sentiment,ensure_ascii=False) if sentiment else "UNKNOWN：未提供或获取时间晚于观察点"}。代理不等于真实情绪。','','请分别记录大背景、参考区域及其依据、局部变化、情绪线索、候选阶段和竞争解释；看不清留 UNKNOWN。是否认出行情也应记录。','']
    figures=[]
    for name,source in data.items():
        fig,axes=plt.subplots(2,2,figsize=(14,9),constrained_layout=True);close=source['last_close']
        availability={}
        for ax,(title,series) in zip(axes.flat,source['panels'].items()):
            availability[title]='READY' if series is not None else 'UNKNOWN'
            if series is None:
                ax.text(.5,.5,'UNKNOWN: missing, invalid, or conflicting data',ha='center',va='center',transform=ax.transAxes)
            else:
                chart(ax,[[z*100/close for z in x] for x in series],-len(series))
                if title.endswith('4h'):ax.set_xlabel('4h bars before observation')
            ax.set_title(title)
        fig.suptitle(name+' BTC/USD as of '+dt.isoformat());p=out/(name+'.png');fig.savefig(p,dpi=130);plt.close(fig)
        figures.append({'source':name,'last_close':close,'panels':availability,'reason':source['reason'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});lines += [f'## {name}','',f'可用性：{json.dumps(availability,ensure_ascii=False)}；原因：{source["reason"] or "缺失面板分别标 UNKNOWN"}。','',f'![{name}]({name}.png)','']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    (out/'manifest.json').write_text(json.dumps({'asof':dt.isoformat(),'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'figures':figures,'sentiment':sentiment,'phase':'UNKNOWN','reviewer':'UNKNOWN'},indent=2,ensure_ascii=False))
    print(json.dumps({'asof':dt.isoformat(),'figures':figures,'sentiment':sentiment},ensure_ascii=False))

if __name__=='__main__':main()
