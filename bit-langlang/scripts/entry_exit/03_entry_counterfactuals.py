"""03 — 反事实入场：随机时刻入场，按同样的出场规则出场。

对照设计（同币、±1 天，均匀随机时刻；每笔抽 N_RAND 次）：
  * 规则 duration : 他的实际持有时长（= 持有到 i0+hold_bars 的收盘，等价于"他的入场+bar收盘出场"的随机版）
  * 规则 cf_*     : 固定持有 5m/30m/1h/4h/24h/72h
  * 规则 trail_1/2: 从最高点回撤 1%/2% 的跟踪止损（最长 72h）
另外：
  * global / global_era : 币和时刻都随机的市场β（全区间 / 他的交易区间），只算 duration 规则
  * 对 LOCAL 抽样计算入场时点特征（未来 24h 波动、前高空间、箱体紧致度）
所有收益都扣该笔自己的实际手续费，单位 = % 价格变动（1R = 1%）。
产物：data/entry_exit/random_entry.csv, data/entry_exit/entry_features.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

N_RAND = 20
SEED = 20261029
LOOKBACK_BARS = 288  # ±1 天


def main() -> None:
    d = pd.read_csv(C.OUT / "trades_panel.csv")
    d = d[d["path_ok"]].reset_index(drop=True)
    rng = np.random.default_rng(SEED)

    feats_actual, feats_rand, rand_rows = [], [], []

    for coin in C.COINS:
        m5 = C.load_market(coin, "5m")
        m1 = C.load_market(coin, "1d")
        ts, cl, op = m5["ts"].values, m5["close"].values, m5["open"].values
        h5, l5 = m5["high"].values, m5["low"].values
        ts1, h1, l1, c1 = (m1[k].values for k in ("ts", "high", "low", "close"))
        n = len(ts)

        idx = d.index[d["coin"] == coin].values
        if len(idx) == 0:
            continue
        q = d.loc[idx]
        i0 = q["i0"].values.astype(int)
        hb = q["hold_bars"].values.astype(int)
        s = q["s"].values
        cost = q["cost_pct"].values
        pos_row = q.index.values
        day = q["entry_day"].values

        # ---- 实际入场点的特征 ----
        for j, a0 in enumerate(i0):
            feats_actual.append(dict(
                trade_row=int(pos_row[j]), coin=coin, kind="actual", entry_day=int(day[j]),
                fwd_vol_24h=C.forward_vol(cl, int(a0), 288, past=False),
                past_vol_24h=C.forward_vol(cl, int(a0), 288, past=True),
                entry_bar_range=100.0 * (h5[a0] - l5[a0]) / cl[a0],
            ))

        # ---- LOCAL 随机入场（多出场规则）----
        lo = np.maximum(i0 - LOOKBACK_BARS, 0)
        hi = np.minimum(i0 + LOOKBACK_BARS, n - 2)
        for j in range(len(idx)):
            if hi[j] <= lo[j]:
                continue
            draws = rng.integers(lo[j], hi[j] + 1, N_RAND)
            for k, r_i in enumerate(draws):
                r_i = int(r_i)
                base = 100.0 * s[j] / op[r_i]
                rec = dict(trade_row=int(pos_row[j]), coin=coin, kind="local", draw=int(k),
                           entry_day=int(day[j]), offset_bars=r_i - i0[j])
                ei = r_i + hb[j]
                if ei < n:
                    rand_rows.append({**rec, "rule": "duration",
                                      "r_rand": base * (cl[ei] - op[r_i]) - cost[j]})
                for name, hh in C.HOLDS.items():
                    ei = r_i + hh
                    if ei < n:
                        rand_rows.append({**rec, "rule": f"cf_{name}",
                                          "r_rand": base * (cl[ei] - op[r_i]) - cost[j]})
                for pct in (1.0, 2.0):
                    rr, _, hit, _ = C.trailing_stop(op, h5, l5, cl, r_i, op[r_i], s[j],
                                                   pct / 100.0, 864)
                    if np.isfinite(rr):
                        rand_rows.append({**rec, "rule": f"trail_{int(pct)}",
                                          "r_rand": rr - cost[j]})
                if k < 5:
                    day_ms = (int(ts[r_i]) // 86_400_000) * 86_400_000
                    di = int(np.searchsorted(ts1, day_ms, side="right") - 1)
                    sp = r20 = r5 = tight = np.nan
                    if di >= 20:
                        H20, L20 = h1[di - 20 : di].max(), l1[di - 20 : di].min()
                        cprev = c1[di - 1]
                        sp = 100.0 * ((H20 - op[r_i]) if s[j] > 0 else (op[r_i] - L20)) / op[r_i]
                        r20 = 100.0 * (H20 - L20) / cprev
                        r5 = 100.0 * (h1[di - 5 : di].max() - l1[di - 5 : di].min()) / cprev
                        tight = r5 / r20 if r20 > 0 else np.nan
                    feats_rand.append(dict(
                        trade_row=int(pos_row[j]), coin=coin, kind="random",
                        entry_day=int(day[j]),
                        fwd_vol_24h=C.forward_vol(cl, r_i, 288, past=False),
                        past_vol_24h=C.forward_vol(cl, r_i, 288, past=True),
                        entry_bar_range=100.0 * (h5[r_i] - l5[r_i]) / cl[r_i],
                        space_prior=sp, range20_pct=r20, range5_pct=r5,
                        tightness_5_20=tight,
                    ))

    # ---- GLOBAL：币和时刻都随机（duration 规则）；另给同期(era)版本 ----
    coins = {}
    for coin in C.COINS:
        m5 = C.load_market(coin, "5m")
        coins[coin] = (m5["open"].values.astype(float), m5["close"].values.astype(float),
                       m5["ts"].values)
    coin_names = np.array(C.COINS)
    era_lo, era_hi = int(d["entry_ms"].min()), int(d["exit_ms"].max())
    for j in range(len(d)):
        hb = int(d["hold_bars"].values[j])
        s = d["s"].values[j]
        cost = d["cost_pct"].values[j]
        for kind in ("global", "global_era"):
            for k in range(N_RAND):
                c = coin_names[rng.integers(0, len(coin_names))]
                op_c, cl_c, ts_c = coins[c]
                n_c = len(op_c)
                if kind == "global":
                    lo_i, hi_i = 0, n_c - 2 - hb
                else:
                    lo_i = int(np.searchsorted(ts_c, era_lo, side="left"))
                    hi_i = int(np.searchsorted(ts_c, era_hi, side="right")) - 1 - hb
                if hi_i <= lo_i:
                    continue
                r_i = int(rng.integers(lo_i, hi_i))
                r_rand = 100.0 * s * (cl_c[r_i + hb] - op_c[r_i]) / op_c[r_i] - cost
                rand_rows.append(dict(trade_row=int(d.index[j]), coin=str(c), kind=kind,
                                      draw=int(k), entry_day=int(d["entry_day"].values[j]),
                                      offset_bars=np.nan, rule="duration", r_rand=r_rand))
        if (j + 1) % 500 == 0:
            print(f"  global {j+1}/{len(d)}")

    rand = pd.DataFrame(rand_rows)
    rand.to_csv(C.OUT / "random_entry.csv", index=False)

    # ---- 特征表 ----
    feat_df = pd.concat([pd.DataFrame(feats_actual), pd.DataFrame(feats_rand)], ignore_index=True)
    extra = d[["space_prior", "range20_pct", "range5_pct", "tightness_5_20"]].copy()
    extra["trade_row"] = d.index.values
    extra = extra.rename(columns={c: c + "_p" for c in extra.columns if c != "trade_row"})
    feat_df = feat_df.merge(extra, on="trade_row", how="left")
    for c in ["space_prior", "range20_pct", "range5_pct", "tightness_5_20"]:
        feat_df[c] = feat_df[c].fillna(feat_df[c + "_p"])
        feat_df = feat_df.drop(columns=[c + "_p"])
    feat_df.to_csv(C.OUT / "entry_features.csv", index=False)

    print(f"random rows={len(rand)}")
    print(rand.groupby(["kind", "rule"])["r_rand"].agg(["count", "mean", "median"]).to_string())
    print(f"features rows={len(feat_df)}")


if __name__ == "__main__":
    main()
