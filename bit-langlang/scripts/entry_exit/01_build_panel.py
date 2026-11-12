"""01 — 构建逐笔反事实面板。

对 10 个有行情的币、对齐 5m/1d 行情，计算每笔仓位的：
  * MFE/MAE（入场后 5m/30m/1h/4h/24h/72h，以及到实际平仓时刻）
  * 实际实现收益（价格口径 + 资金口径）、成本
  * 平仓后 5m/30m/1h/4h/24h 的"延续漂移"（出场管理 alpha 的直接证据）
  * 入场时点可观测/事后特征：未来 24h 实现波动、过去 20 日到前高空间、箱体紧致度
产物：data/entry_exit/trades_panel.csv, data/entry_exit/alignment.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

OUT = C.OUT
OUT.mkdir(parents=True, exist_ok=True)

POST_EXIT = {"5m": 1, "30m": 6, "1h": 12, "4h": 48, "24h": 288}
PAST_RET = {"1h": 12, "4h": 48, "24h": 288}


def main() -> None:
    pos = C.load_positions()
    ten = pos[pos["coin"].notna()].copy()
    print(f"positions total={len(pos)}  10-coin={len(ten)}")

    rows = []
    align_report = {}
    for coin in C.COINS:
        m5 = C.load_market(coin, "5m")
        m1 = C.load_market(coin, "1d")
        ts = m5["ts"].values
        o, h, l, cl = (m5[k].values for k in ("open", "high", "low", "close"))
        ts1 = m1["ts"].values
        o1, h1, l1, c1 = (m1[k].values for k in ("open", "high", "low", "close"))

        q = ten[ten["coin"] == coin].copy().reset_index(drop=True)
        i0 = C.floor_bar(ts, q["entry_ms"].values)
        ix = C.floor_bar(ts, q["exit_ms"].values)
        ok = (i0 >= 0) & (i0 < len(ts) - 1)
        # 无行情覆盖（早于上市）的仓位单列
        n_no_market = int((~ok).sum())
        q = q[ok].reset_index(drop=True)
        i0, ix = i0[ok], ix[ok]
        ix = np.clip(ix, i0, len(ts) - 1)

        # 价格尺度（PEPE 1000 倍）
        k = C.price_scale_factor(cl[i0], q["entry"].values)
        scale = 10.0 ** k
        P0 = q["entry"].values * scale
        Px = q["exit"].values * scale

        # 对齐质量：入场价是否落在入场 bar 的 [low, high]
        in_bar = (P0 >= l[i0] * 0.999) & (P0 <= h[i0] * 1.0005)
        # 更宽松的"可接受"：|log 偏差| < 1.5 * bar 半幅，用于剔除明显错位
        mid = (h[i0] + l[i0]) / 2
        half = np.maximum((h[i0] - l[i0]) / 2, 1e-9)
        misaligned = np.abs(P0 - mid) > 3.0 * half

        # 价格口径一致性：入场价与所在 bar 收盘价的对数偏差
        px_dev = np.abs(np.log10(P0 / cl[i0]))

        s = q["s"].values
        r_px = s * (Px - P0) / P0 * 100.0
        r_pnl = q["pnl"].values / q["notional"].values * 100.0
        cost = -q["fee"].values / q["notional"].values * 100.0

        # ---- 每个 horizon 的 MFE/MAE ----
        feat = {}
        # 逐笔算 MFE/MAE（p0/s 依赖单笔）
        for name, hb in C.HOLDS.items():
            mfe = np.empty(len(q))
            mae = np.empty(len(q))
            for j in range(len(q)):
                mfe[j], mae[j] = C.mfe_mae_window(h, l, int(i0[j]), hb, P0[j], s[j])
            feat[f"mfe_{name}"] = mfe
            feat[f"mae_{name}"] = mae

        mfe_e = np.empty(len(q))
        mae_e = np.empty(len(q))
        for j in range(len(q)):
            mfe_e[j], mae_e[j] = C.mfe_mae_to_exit(h, l, int(i0[j]), int(ix[j]), P0[j], Px[j], s[j])
        feat["mfe_exit"] = mfe_e
        feat["mae_exit"] = mae_e

        # ---- 平仓后延续漂移 ----
        for name, hb in POST_EXIT.items():
            arr = np.full(len(q), np.nan)
            for j in range(len(q)):
                b = int(ix[j]) + hb
                if b < len(cl):
                    arr[j] = 100.0 * s[j] * (cl[b] - Px[j]) / Px[j]
            feat[f"post_exit_{name}"] = arr

        # ---- 未来/过去实现波动（未来量仅用于事后描述） ----
        feat["fwd_vol_24h"] = np.array([C.forward_vol(cl, int(a), 288, past=False) for a in i0])
        feat["past_vol_24h"] = np.array([C.forward_vol(cl, int(a), 288, past=True) for a in i0])
        feat["vol_ratio"] = feat["fwd_vol_24h"] / np.where(
            feat["past_vol_24h"] > 0, feat["past_vol_24h"], np.nan
        )

        # ---- 入场时点的过去收益 & 当日 bar 特征 ----
        for name, hb in PAST_RET.items():
            arr = np.full(len(q), np.nan)
            for j in range(len(q)):
                a = int(i0[j]) - hb
                if a >= 0:
                    arr[j] = 100.0 * (P0[j] - cl[a]) / cl[a]
            feat[f"past_ret_{name}"] = arr
        feat["entry_bar_range"] = 100.0 * (h[i0] - l[i0]) / cl[i0]

        # ---- 日线：到前高空间 / 箱体紧致度（只用入场日之前的日线） ----
        day_ms = (q["entry_ms"].values // 86_400_000) * 86_400_000
        di = np.searchsorted(ts1, day_ms, side="right") - 1
        space = np.full(len(q), np.nan)
        rng20 = np.full(len(q), np.nan)
        rng5 = np.full(len(q), np.nan)
        atr14 = np.full(len(q), np.nan)
        for j in range(len(q)):
            d = int(di[j])
            n = C.PAST_DAYS_SPACE
            if d < max(n, 15):
                continue
            H20 = h1[d - n : d].max()
            L20 = l1[d - n : d].min()
            cprev = c1[d - 1]
            if s[j] > 0:
                space[j] = 100.0 * (H20 - P0[j]) / P0[j]  # 到 20 日高点的向上空间
            else:
                space[j] = 100.0 * (P0[j] - L20) / P0[j]  # 到 20 日低点的向下空间
            rng20[j] = 100.0 * (H20 - L20) / cprev
            rng5[j] = 100.0 * (h1[d - 5 : d].max() - l1[d - 5 : d].min()) / cprev
            tr = np.maximum(
                h1[d - 14 : d] - l1[d - 14 : d],
                np.maximum(
                    np.abs(h1[d - 14 : d] - c1[d - 15 : d - 1]),
                    np.abs(l1[d - 14 : d] - c1[d - 15 : d - 1]),
                ),
            )
            atr14[j] = 100.0 * tr.mean() / cprev
        feat["space_prior"] = space
        feat["range20_pct"] = rng20
        feat["range5_pct"] = rng5
        feat["tightness_5_20"] = feat["range5_pct"] / np.where(rng20 > 0, rng20, np.nan)
        feat["atr14_1d_pct"] = atr14

        out = q.copy()
        out["i0"] = i0
        out["ix"] = ix
        out["hold_bars"] = ix - i0
        out["price_scale"] = scale
        out["P0"] = P0
        out["Px"] = Px
        out["r_px"] = r_px
        out["r_pnl"] = r_pnl
        out["cost_pct"] = cost
        out["r_net"] = r_px - cost
        out["px_dev"] = px_dev
        out["entry_in_bar"] = in_bar
        out["misaligned"] = misaligned
        for kk, vv in feat.items():
            out[kk] = vv
        rows.append(out)

        align_report[coin] = dict(
            n_positions=int(len(ten[ten["coin"] == coin])),
            n_aligned=int(len(q)),
            n_no_market=n_no_market,
            price_scale=scale,
            entry_in_bar_hit=float(in_bar.mean()) if len(q) else None,
            misaligned_3half=float(misaligned.mean()) if len(q) else None,
            data_start=str(pd.to_datetime(ts[0], unit="ms")),
            data_end=str(pd.to_datetime(ts[-1], unit="ms")),
        )

    panel = pd.concat(rows, ignore_index=True)
    panel["entry_day"] = (panel["entry_ms"] // 86_400_000).astype("int64")
    panel["entry_date"] = pd.to_datetime(panel["entry_day"] * 86_400_000, unit="ms")
    panel["year"] = panel["entry_date"].dt.year

    # 标记：可做路径分析的子样本（排除负持仓/明显错位）
    # path_ok：价格/时间口径可用的子样本
    #   入场价落在入场 bar 内（正常），或 与 bar 收盘价偏差 <5%（分钟取整/成交价差异）
    #   再排除负持仓
    panel["path_ok"] = (panel["entry_in_bar"] | (panel["px_dev"] <= 0.05)) & (panel["hold_min"] >= 0)
    print(f"path_ok={panel['path_ok'].mean():.4f}  excluded={int((~panel['path_ok']).sum())}")
    print(f"panel={len(panel)}  entry_in_bar={panel['entry_in_bar'].mean():.3f} "
          f"misaligned={panel['misaligned'].mean():.3f}")

    panel.to_csv(OUT / "trades_panel.csv", index=False)

    # 覆盖率
    coverage = dict(
        positions_total=int(len(pos)),
        positions_10coin=int(len(ten)),
        coverage_10coin=float(len(ten) / len(pos)),
        aligned=int(len(panel)),
        coverage_aligned=float(len(panel) / len(pos)),
        entry_in_bar_hit=float(panel["entry_in_bar"].mean()),
        zero_hold=int((panel["hold_min"] == 0).sum()),
        neg_hold=int((panel["hold_min"] < 0).sum()),
        price_scale=align_report,
    )
    with open(OUT / "alignment.json", "w") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in coverage.items() if k != "price_scale"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
