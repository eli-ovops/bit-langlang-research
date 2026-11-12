"""Supplement the existing review with strictly as-of 365-day context."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = Path('data/verify/cycle-review-context-20261105-01')
OLD = Path('data/verify/cycle-recent-review-20261105-01')
PROTOCOL = Path('docs/独立判读材料-大背景与情绪补充定义-20261105.md')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calc(frame, t):
    z = frame.loc[(frame.index >= t-pd.Timedelta(days=365)) & (frame.index < t)]
    expected = pd.date_range(t-pd.Timedelta(days=365), periods=365, freq='D')
    if not z.index.equals(expected) or not z.good.all():
        return None, z
    lo, hi, last = float(z.low.min()), float(z.high.max()), float(z.close.iloc[-1])
    if hi <= lo:
        return None, z
    return {'low': lo, 'high': hi, 'last': last, 'position': (last-lo)/(hi-lo)}, z


def main():
    pack = BASE/'reviewer-pack'
    pack.mkdir(exist_ok=False)
    raw = json.loads((BASE/'bitfinex-1d-raw.json').read_text())
    df = pd.DataFrame(raw, columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric)
    df = df.sort_values('ts'); assert not df.ts.duplicated().any()
    assert (df.ts % 86400000 == 0).all()
    df.index = pd.to_datetime(df.ts, unit='ms', utc=True)
    fields = df[['open','high','low','close','volume']]
    df['good'] = np.isfinite(fields).all(axis=1) & (fields > 0).all(axis=1) & \
        (df.high >= df[['open','close','low']].max(axis=1)) & \
        (df.low <= df[['open','close','high']].min(axis=1))
    date_map = pd.read_csv(OLD/'private-date-map.csv')
    hashes, detail, notes = {}, [], []
    for row in date_map.itertuples(index=False):
        t = pd.Timestamp(row.as_of_utc)
        result, z = calc(df, t)
        future = df.copy(); future.loc[future.index >= t, ['open','high','low','close']] *= 2
        assert calc(future, t)[0] == result
        if result is None:
            detail.append({'id':row.id,'as_of':str(t),'quality':'UNKNOWN_INCOMPLETE'})
            notes.append(f'## {row.id}\n\n一年背景数据不足，留空。\n')
            continue
        a = z.reset_index(drop=True)
        assert len(a)==365 and float(a.high.max())==result['high'] and float(a.low.min())==result['low']
        assert float(a.close.iloc[-1])==result['last']
        scale = float(a.close.iloc[0])
        fig, ax = plt.subplots(figsize=(10, 4))
        x = np.arange(365)
        ax.plot(x, a.close.to_numpy()/scale*100, lw=1.2, color='#1b597d')
        ax.fill_between(x, a.low.to_numpy()/scale*100, a.high.to_numpy()/scale*100,
                        color='#1b597d', alpha=.17)
        ax.set_title(f'{row.id} | 365 completed daily bars before observation')
        ax.set_ylabel('Relative price, first close = 100');ax.set_xlabel('Earlier  ←  Time  →  Observation')
        ax.set_xticks([]);ax.grid(alpha=.2);fig.tight_layout()
        path = pack/f'{row.id}-background.png';fig.savefig(path,dpi=130);plt.close(fig)
        hashes[row.id] = digest(path)
        prior = (OLD/'reviewer-pack'/f'{row.id}.png').resolve()
        context = ('当时可用材料中：一方观察到现货主动买盘相对较稳、永续卖压偏强和期权保护需求上升；'
                   '另一方认为现货需求偏弱、反弹可能是短期交易；第三方也对反弹背后的现货资金持保留意见。'
                   '这些是不同机构和指标的描述，不是对真实情绪的直接测量；网页具体发布时间和历史版本未完全核实。'
                   if t >= pd.Timestamp('2026-11-03',tz='UTC') else '截至该点未取得符合时间要求的同期情绪参考，UNKNOWN。')
        notes.append(f'## {row.id}\n\n[一年背景]({row.id}-background.png)；[原 56 日/8 日图]({prior})。\n\n{context}\n')
        detail.append({'id':row.id,'as_of':t.isoformat(),'quality':'OK',**result})
    (pack/'README.md').write_text('# 既有匿名盘面的大背景补充\n\n'
        '原图与本补充是同一批五个相近时点，不能视为独立五个市场周期。\n'
        '先看每个编号的一年背景，再看原图；线为日收，高低范围为浅色。'
        '一年图按一年窗口首日日收归一化，原图按 56 日窗口首日日收归一化，两个图的数字不可直接比较。'
        '随后参考文字线索并记录阶段、证据、竞争解释和看不清之处。'
        '阶段含义见事先说明；资料源不同、可能认出历史，不保证盲态。\n\n'+'\n'.join(notes))
    (BASE/'private-detail.json').write_text(json.dumps(detail,indent=2))
    (BASE/'manifest.json').write_text(json.dumps({'raw_sha256':digest(BASE/'bitfinex-1d-raw.json'),
        'prior_mapping_sha256':digest(OLD/'private-date-map.csv'), 'protocol_sha256':digest(PROTOCOL),
        'script_sha256':digest(Path(__file__)),'image_sha256':hashes,
        'quality':'strict historical windows; 5 future perturbations passed'},indent=2))
    print(json.dumps({'valid':len(hashes),'results':detail},indent=2))


if __name__ == '__main__':
    main()
