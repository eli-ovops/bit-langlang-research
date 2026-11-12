"""Plot pre-existing anonymous cases with complete as-of OHLC candles."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path('data/verify')
OUT = ROOT/'cycle-review-candles-20261105-01'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def window(df, t, periods, freq):
    step = pd.Timedelta(freq)
    expected = pd.date_range(t-periods*step, periods=periods, freq=step)
    z = df.loc[(df.index >= t-periods*step) & (df.index < t)]
    if not z.index.equals(expected) or not z.good.all():
        return None
    return z


def candles(ax, data, title):
    scale = float(data.close.iloc[0]); w = .65
    for i, r in enumerate(data.itertuples()):
        o, h, l, c = (float(v)/scale*100 for v in (r.open,r.high,r.low,r.close))
        color = '#147c54' if c >= o else '#c53a3a'
        ax.vlines(i, l, h, color=color, linewidth=.75)
        height = abs(c-o)
        if height:
            ax.add_patch(Rectangle((i-w/2,min(o,c)),w,height,facecolor=color,edgecolor=color,linewidth=.3))
        else:
            ax.hlines(o,i-w/2,i+w/2,color=color,linewidth=1)
    ax.autoscale_view();ax.set_xlim(-1,len(data));ax.grid(alpha=.16)
    ax.set_title(title);ax.set_ylabel('Relative price, first close = 100');ax.set_xticks([])


def main():
    OUT.mkdir(parents=True, exist_ok=False);pack=OUT/'reviewer-pack';pack.mkdir()
    dayfile=ROOT/'cycle-review-context-20261105-01/bitfinex-1d-raw.json'
    hourfile=ROOT/'cycle-independent-recent-20261105-02/kraken-4h.csv'
    mappingfile=ROOT/'cycle-recent-review-20261105-01/private-date-map.csv'
    daily=pd.DataFrame(json.loads(dayfile.read_text()),columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric)
    hourly=pd.read_csv(hourfile)
    for f in (daily,hourly):
        f.sort_values('ts',inplace=True);assert not f.ts.duplicated().any()
        f.index=pd.to_datetime(f.ts,unit='ms',utc=True)
        v=f[['open','high','low','close','volume']]
        f['good']=np.isfinite(v).all(axis=1)&(v>0).all(axis=1)&\
            (f.high>=f[['open','close','low']].max(axis=1))&\
            (f.low<=f[['open','close','high']].min(axis=1))
    rows=[];hashes={}
    for m in pd.read_csv(mappingfile).itertuples(index=False):
        t=pd.Timestamp(m.as_of_utc)
        d=window(daily,t,120,'1d');h=window(hourly,t,84,'4h')
        record={'id':m.id,'as_of_utc':t.isoformat(),'daily_ok':d is not None,'fourhour_ok':h is not None}
        for frame,n,freq,expected in [(daily,120,'1d',d),(hourly,84,'4h',h)]:
            changed=frame.copy();changed.loc[changed.index>=t,['open','high','low','close']]*=2
            updated=window(changed,t,n,freq)
            assert (expected is None and updated is None) or expected.equals(updated)
            if expected is not None:
                assert len(expected)==n and expected.index[-1]+pd.Timedelta(freq)==t
        if d is not None and h is not None:
            fig,axes=plt.subplots(2,1,figsize=(12,8),constrained_layout=True)
            candles(axes[0],d,'120 completed daily candles | Bitfinex BTC/USD')
            candles(axes[1],h,'14 days of completed 4-hour candles | Kraken BTC/USD')
            fig.suptitle(f'{m.id} | no candles after observation point')
            p=pack/f'{m.id}-candles.png';fig.savefig(p,dpi=140);plt.close(fig);hashes[m.id]=sha(p)
        rows.append(record)
    (pack/'README.md').write_text('# 裸 K 补充材料\n\n'
      '这是旧匿名盘面的事后补充；同一编号对应同一观察点，不是新增独立案例。'
      '各图上方是此前 120 个完整日 Bitfinex 现货日 K，下方是此前 14 个完整日 Kraken 现货 4 小时 K；'
      '每根均画出开、高、低、收：绿色收盘不低于开盘，红色收盘低于开盘。'
      '两图分别按自身首根收盘归一化，数值不能直接比较；来源不同，不互相补价。'
      '均只含观察点之前已完成的 K 线。120/14 日是展示范围，不是浪浪规则。\n\n'
      '结合[原一年背景与情绪说明](../../cycle-review-context-20261105-01/reviewer-pack/README.md)及原判断表记录事实和竞争解释；'
      '看不清留空。匿名并不保证无法识别日期，五个相近时点不能当作五个市场周期。\n\n'+
      '\n'.join(f'- [{k} 图]({k}-candles.png)' for k in hashes)+'\n')
    (OUT/'private-quality.json').write_text(json.dumps(rows,indent=2))
    (OUT/'manifest.json').write_text(json.dumps({'images':hashes,'raw_daily_sha256':sha(dayfile),
        'raw_4h_sha256':sha(hourfile),'map_sha256':sha(mappingfile),'script_sha256':sha(Path(__file__)),
        'protocol_sha256':sha(Path('docs/独立判读-裸K材料事后修订定义-20261105.md')),
        'future_mutation_checks':len(rows)*2},indent=2))
    print(json.dumps({'quality':rows,'images':len(hashes)},indent=2))


if __name__ == '__main__':
    main()
