# -*- coding: utf-8 -*-
import csv,gzip,hashlib,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

ROOT=Path(__file__).resolve().parents[1]
KEY=ROOT/'data/verify/cycle-pullback-review-20261105-02/private-key.csv'
MARKET=ROOT/'data/verify/cycle-market-archive-corrected-20261109-01/summary.json'
GROUPS={'2023Q1':['data/market/btc-2022nine-usd-cross-20261104-01/bitstamp-4h.csv.gz','data/market/btc-2022q4-usd-cross-20261103-01/bitstamp-4h.csv.gz','data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv'],'2025Q2':['data/market/btc-2024q4-usd-cross-20261104-01/bitstamp-4h.csv.gz','data/market/btc-2025q1-usd-cross-20261104-01/bitstamp-4h.csv.gz','data/market/btc-2025q2-usd-cross-20261104-01/bitstamp-4h.csv.gz']}
OUT=ROOT/'data/verify/cycle-multiscale-review-20261109-01'


def load(paths):
    bars={};overlap=0
    for path in paths:
        seen=set()
        with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as f:
            for r in csv.DictReader(f):
                t=datetime.fromtimestamp(int(r['ts'])/1000,timezone.utc)
                if t in seen:raise ValueError('DUPLICATE_4H')
                seen.add(t);v=tuple(float(r[k]) for k in ('open','high','low','close','volume'));o,h,l,c,vol=v
                if not(all(math.isfinite(x) and x>0 for x in v) and l<=min(o,c)<=max(o,c)<=h):raise ValueError('INVALID_4H')
                if t in bars:
                    overlap+=1
                    if bars[t]!=v:raise ValueError('OVERLAP_MISMATCH')
                bars[t]=v
    return bars,overlap


def main():
    with KEY.open(newline='') as f:keys=[{k:r[k] for k in ('id','quarter','as_of_utc')} for r in csv.DictReader(f)]
    market=json.loads(MARKET.read_text());lookup={(r['quarter'],r['as_of_utc']):r for r in market}
    assert len(keys)==len(market)==len(lookup)>0 and len({x['id'] for x in keys})==len(keys)
    datasets={q:load([ROOT/x for x in paths]) for q,paths in GROUPS.items()}
    OUT.mkdir(parents=True,exist_ok=False);pub=OUT/'reviewer-pack';charts=pub/'charts';charts.mkdir(parents=True)
    forms=[];audit=[]
    for key in keys:
        idx=key['id'];q=key['quarter'];t=datetime.fromisoformat(key['as_of_utc']);assert t.utcoffset()==timedelta(0) and t.hour==t.minute==t.second==0
        days=[]
        for i in range(180,0,-1):
            dt=t-timedelta(days=i);b=[datasets[q][0].get(dt+timedelta(hours=4*j)) for j in range(6)]
            if any(x is None for x in b):days=[];break
            days.append([b[0][0],max(x[1] for x in b),min(x[2] for x in b),b[-1][3]])
        status='OK' if len(days)==180 else 'UNKNOWN_INCOMPLETE_BTC'
        if days:
            scale=100/days[-1][3];cs=[[v*scale for v in x] for x in days];fig,axes=plt.subplots(3,1,figsize=(13,9),constrained_layout=True)
            for ax,n in zip(axes,(180,56,14)):chart(ax,cs[-n:],-n);ax.set_title(f'Last {n} completed daily candles')
            fig.suptitle(idx);fig.savefig(charts/f'{idx}.png',dpi=110,metadata={'Software':'Matplotlib'});plt.close(fig)
        m=lookup[(q,key['as_of_utc'])];good=m['status']=='DATA_READY';age='UNKNOWN'
        if good:
            cap=datetime.fromisoformat(m['capture_utc']);assert cap<t and cap.date()==(t-timedelta(days=1)).date();age=f'{(t-cap).total_seconds()/3600:.2f}'
        forms.append({'编号':idx,'BTC图状态':status,'样本页面状态':'有前30行' if good else 'UNKNOWN','快照距观察小时':age,'7d上涨':m['count_up'] if good else 'UNKNOWN','7d下跌':m['count_down'] if good else 'UNKNOWN','7d显示零':m['count_zero'] if good else 'UNKNOWN','大背景':'','关键位置':'','局部变化':'','BTC阶段候选':'','支持与反证':'','整体市场阶段':'UNKNOWN','情绪':'UNKNOWN','是否认出':'','评审时间':''})
        audit.append({'id':idx,'quarter':q,'as_of_utc':t.isoformat(),'price_status':status,'bars':len(days),'market_status':m['status'],'market_capture_utc':m.get('capture_utc','') if good else '','market_error':m.get('error','')})
    with (pub/'判读表.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(forms[0]));w.writeheader();w.writerows(forms)
    lines=['# 匿名市场阶段练习','', '本包使用已被项目研究的历史，不能称样本外或盲测。图只含观察时刻以前完整日线，按最后日收归一化为100；-1 是此前最后完整日。每张图的 100 不是相同真实价格。','', '先看180天背景，再看56天和14天的局部变化。图中没有真实情绪；市场前30行数字是观察前更早时刻的一份第三方页面，截图内部数据时间未知，样本含BTC、稳定币及包装资产，不能代表全市场。页面观察后仍可能发生价格变化。','', '在判读表写大背景、关键位置、局部变化、支持与相反解释，再考虑 BTC 结构的阶段候选；不清楚或缺信息就写 UNKNOWN。整体市场阶段和真实情绪默认 UNKNOWN，若修改需明确提供依据。不能从涨跌直接断定真实情绪。','', '如果认出行情请记下。独立于旧量化计算不等于独立历史，也不能用来证明复刻或盈利。','', '[打开判读表](判读表.csv)','']
    for r in forms:
        idx=r['编号'];lines += [f'## {idx}', '', f"市场页面：{r['样本页面状态']}；距观察点 {r['快照距观察小时']} 小时；前30行7d显示上涨/下跌/零：{r['7d上涨']}/{r['7d下跌']}/{r['7d显示零']}。",'',f'![{idx}](charts/{idx}.png)' if r['BTC图状态']=='OK' else 'BTC 图 UNKNOWN','']
    (pub/'README.md').write_text('\n'.join(lines)+'\n')
    private={'records':audit,'overlap_4h':{k:v[1] for k,v in datasets.items()},'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [KEY,MARKET,*[ROOT/x for g in GROUPS.values() for x in g]]}}
    (OUT/'private-audit.json').write_text(json.dumps(private,ensure_ascii=False,indent=2)+'\n')
    print('charts',sum(x['price_status']=='OK' for x in audit),'of',len(audit),'market_data',sum(x['market_status']=='DATA_READY' for x in audit))

if __name__=='__main__':main()
