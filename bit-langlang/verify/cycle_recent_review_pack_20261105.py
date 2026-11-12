"""Build anonymous as-of charts, not independent labels or a trading tool."""
from pathlib import Path
import hashlib
import json
import random
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path('data/verify/cycle-independent-recent-20261105-02')
OUT = Path('data/verify/cycle-recent-review-20261105-01')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    pack = OUT / 'reviewer-pack'
    pack.mkdir()
    f = pd.read_csv(ROOT/'kraken-4h.csv')
    f.index = pd.to_datetime(f.ts, unit='ms', utc=True)
    dates = list(pd.date_range('2026-11-01', '2026-11-05', freq='D', tz='UTC'))
    random.Random(20261105).shuffle(dates)
    mapping, hashes = [], {}
    for i, t in enumerate(dates, 1):
        code = f'R{i:02}'
        past = f.loc[(f.index >= t-pd.Timedelta(days=56)) & (f.index < t)]
        assert len(past) == 336 and past.index.max() == t-pd.Timedelta(hours=4)
        days = past.resample('D').agg(open=('open','first'), high=('high','max'),
                                    low=('low','min'), close=('close','last'))
        short = past.iloc[-48:]
        scale = float(days.close.iloc[0])
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
        for ax, data, label in [(axes[0], days, '56 complete days; each bar = 1 day'),
                                (axes[1], short, '8 complete days; each bar = 4 hours')]:
            x = range(len(data))
            colors = ['#147c54' if c >= o else '#c53a3a' for o, c in zip(data.open, data.close)]
            ax.vlines(x, data.low/scale*100, data.high/scale*100, colors=colors, linewidth=1)
            ax.scatter(list(x), data.close/scale*100, c=colors, s=7)
            ax.set_title(label); ax.set_ylabel('Relative price, first daily close = 100')
            ax.grid(alpha=.18); ax.set_xticks([])
        fig.suptitle(f'{code} | all data ends at observation point')
        path = pack/f'{code}.png'
        fig.savefig(path, dpi=130)
        plt.close(fig)
        hashes[code] = sha(path)
        mapping.append({'id':code,'as_of_utc':t.isoformat()})
    pd.DataFrame(mapping).to_csv(OUT/'private-date-map.csv',index=False)
    pd.DataFrame([{'id':x['id'],'stage':'','evidence':'','alternative':'','confidence':''}
                  for x in mapping]).to_csv(pack/'blank-labels.csv',index=False)
    (pack/'README.md').write_text('''# 匿名判读练习\n\n共五张图，每张只展示判断时刻之前的已完成行情：上图此前 56 个完整日，下图此前 8 个完整日的 4 小时柱。颜色表示该柱收盘相对开盘上/下，点表示收盘；纵轴按首个完整日收归一化，两个面板使用同一比例。图片按 R01–R05 打乱，不显示日期、币价、旧模型结果或后续走势。\n\n根据独立判读标准，在 `blank-labels.csv` 的 stage 中填写“震荡末期 / 启动 / 主升 / 看不清”之一，并记录证据、其他解释与信心；不清楚可留空。判断只代表观察者意见，不是浪浪本人的意见。五张图来自相邻时点，可能高度相似，不能当成五个独立市场周期；一所数据、匿名图形可能被识别，也无法保证严格盲态。\n\n本包用于检查判读过程是否可行，不可用作统计准确率、交易收益或已完成验证。\n''')
    (OUT/'manifest.json').write_text(json.dumps({'source_sha256':sha(ROOT/'kraken-4h.csv'),
        'charts_sha256':hashes,'mapping_sha256':sha(OUT/'private-date-map.csv'),
        'data_rule':'strictly before each observation point'},indent=2))
    print('Created 5 charts, separate date map, blank labels and manifest')


if __name__ == '__main__':
    main()
