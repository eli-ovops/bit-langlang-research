import csv
import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from cycle_causal_pullback_20261105 import daily
from cycle_pullback_supplement_20261105 import SOURCES

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/verify/cycle-pullback-supplement-20261105-01/segments.csv'
OUT = ROOT/'data/verify/cycle-pullback-review-20261105-02'
DAY = timedelta(days=1)


def chart(ax, candles, start):
    for i, bar in enumerate(candles, start):
        o,h,l,c = bar
        color = '#137a62' if c >= o else '#ba4650'
        ax.vlines(i,l,h,color=color,linewidth=1)
        if o == c:
            ax.hlines(c,i-.30,i+.30,color=color,linewidth=1)
        else:
            ax.add_patch(Rectangle((i-.30,min(o,c)),.6,abs(c-o),facecolor=color,edgecolor=color))
    ax.axhline(100, color='#9aa5b1', linewidth=.7, linestyle=':')
    ax.grid(axis='y',color='#e4e7eb',linewidth=.6)
    ax.set_xlabel('Days before observation')
    ax.set_ylabel('Index (last close = 100)')
    ax.set_xlim(start-.8,start+len(candles)-.2)


def main():
    with SOURCE.open(newline='') as f:
        source = list(csv.DictReader(f))
    assert len(source)==26 and len({(r['quarter'],r['as_of_utc']) for r in source})==26
    random.Random(316751).shuffle(source)
    data = {q:daily(ROOT/p) for q,p in SOURCES.items()}
    OUT.mkdir(parents=True, exist_ok=False)
    pack = OUT/'reviewer-pack'; charts = pack/'charts'; charts.mkdir(parents=True)
    key, points = [], []
    readme = ['# 匿名行情判读包', '', '这些图按观察时刻截断，不展示日期、信号或之后走势。每图左侧为最近 56 个完整日线，右侧为最后 14 日；最后日收标准化为 100。绿色为当日收高于或等于开，红色为收低于开；上下一线是当日高低。横轴 -1 是观察前最后一个完整日。两图是同一行情的不同尺度。', '', '请按[判读标准与记录表](判读表.md)先描述背景、空间、局部变化及竞争解释，再记录候选阶段；不清楚填 UNKNOWN。不提供情绪或新闻，不能从价格直接推断情绪。请记录是否认出行情；这些已见历史不保证盲评或独立样本。', '']
    forms = ['# 判读记录表', '', '逐图记录：大背景（上/下/区间/混合/UNKNOWN）、关键位置及依据、近期变化、阶段候选（震荡末期/启动/主升/其他/UNKNOWN，可多选）、支持与相反解释、是否认出该历史、评审时间。情绪资料未提供，情绪留 UNKNOWN。仅看当时已知盘面，不根据后来结果回填。', '', '候选仅是研究定义：震荡末期需要有已见区间及其平衡可能变化的证据，也可能继续震荡；启动需要有相对既有结构的新推动证据，也可能只是反弹或试探；主升需要已有持续上行结构、推进空间及局部回调描述，也可能是大区间反弹或已到后期。没有充分证据时选 UNKNOWN，不必强行单选。', '', '| 编号 | 大背景 | 关键位置 | 局部变化 | 阶段候选 | 支持与相反解释 | 是否认出 | 评审时间 |', '|---|---|---|---|---|---|---|---|']
    for n,r in enumerate(source,1):
        sample=f'A{n:02d}'; t=datetime.fromisoformat(r['as_of_utc']); candles=[]
        for i in range(56,0,-1):
            day=t-DAY*i; bar=data[r['quarter']].get(day)
            if bar is None:
                raise ValueError(f'incomplete pre-observation candle {sample} {day}')
            assert day+DAY <= t
            candles.append(bar)
        factor=100/candles[-1]['close']
        c=[[x[k]*factor for k in ('open','high','low','close')] for x in candles]
        assert abs(c[-1][-1]-100)<1e-9
        fig,axes=plt.subplots(1,2,figsize=(13,4.4),constrained_layout=True,gridspec_kw={'width_ratios':[2,1]})
        chart(axes[0],c,-56);chart(axes[1],c[-14:],-14)
        axes[0].set_title('56 completed daily candles');axes[1].set_title('Last 14 days')
        fig.suptitle(sample,fontsize=14)
        fig.savefig(charts/f'{sample}.png',dpi=130,metadata={'Software':'Matplotlib'})
        plt.close(fig)
        readme += [f'## {sample}', '', f'![{sample}](charts/{sample}.png)', '']
        forms.append(f'| {sample} |  |  |  |  |  |  |  |')
        key.append({'id':sample, **r})
        points.extend({'id':sample,'offset':-56+i,**dict(zip(('open','high','low','close'),bar))} for i,bar in enumerate(c))
    (pack/'README.md').write_text('\n'.join(readme)+'\n')
    (pack/'判读表.md').write_text('\n'.join(forms)+'\n')
    for name,records in [('private-key.csv',key),('private-normalized-bars.csv',points)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    files=[SOURCE,*(ROOT/x for x in SOURCES.values()),OUT/'private-key.csv',OUT/'private-normalized-bars.csv',*sorted(pack.rglob('*'))]
    files=[p for p in files if p.is_file()]
    audit={'count':len(key),'bars_per_chart':56,'all_dates_strictly_before_observation':True,
           'files_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (OUT/'manifest.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
    print(f'Created {len(key)} charts and {len(points)} normalized bars')


if __name__ == '__main__':
    main()
