"""02 — 反事实出场：同一入场点，换机械出场规则。

规则（全部无参数搜索，按任务书给定固定清单）：
  * 固定持有 5m/30m/1h/4h/24h/72h：入场后第 N 根 5m 的收盘价出场
  * 跟踪止损：从入场后走过的最高（最低）点回撤 1% / 2%，最长 72h，bar 内按触发价/跳空 open 成交
  * 参照组：他实际入场 + 持有到"平仓 bar 收盘"（即把他的出场价换成同期 bar 的收盘价）
所有结果都扣掉该笔自己的实际手续费（fee/notional），单位 = % 价格变动（1R = 1%）。
产物：data/entry_exit/cf_exits.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def main() -> None:
    d = pd.read_csv(C.OUT / "trades_panel.csv")
    d = d[d["path_ok"]].reset_index(drop=True)
    print(f"panel(path_ok) = {len(d)}")

    out = {f"r_cf_{k}": np.full(len(d), np.nan) for k in C.HOLDS}
    for pct in (1.0, 2.0):
        out[f"r_trail_{int(pct)}"] = np.full(len(d), np.nan)
        out[f"trail_{int(pct)}_hit"] = np.zeros(len(d), dtype=bool)
        out[f"trail_{int(pct)}_bars"] = np.full(len(d), np.nan)
    out["r_bclose"] = np.full(len(d), np.nan)   # 他的入场 + 持有到平仓 bar 收盘
    out["n_future_bars"] = np.zeros(len(d), dtype=int)

    for coin in C.COINS:
        m = C.load_market(coin, "5m")
        ts = m["ts"].values
        o, h, l, cl = (m[k].values for k in ("open", "high", "low", "close"))
        n = len(ts)
        idx = d.index[d["coin"] == coin].values
        if len(idx) == 0:
            continue
        q = d.loc[idx]
        i0 = q["i0"].values.astype(int)
        ix = q["ix"].values.astype(int)
        P0 = q["P0"].values
        s = q["s"].values
        cost = q["cost_pct"].values

        for k, hb in C.HOLDS.items():
            tgt = i0 + hb
            ok = tgt < n
            arr = np.full(len(idx), np.nan)
            arr[ok] = 100.0 * s[ok] * (cl[tgt[ok]] - P0[ok]) / P0[ok]
            out[f"r_cf_{k}"][idx] = arr - cost

        bc = np.full(len(idx), np.nan)
        okx = ix < n
        bc[okx] = 100.0 * s[okx] * (cl[ix[okx]] - P0[okx]) / P0[okx]
        out["r_bclose"][idx] = bc - cost

        for pct in (1.0, 2.0):
            r = np.full(len(idx), np.nan)
            hit = np.zeros(len(idx), dtype=bool)
            bars = np.full(len(idx), np.nan)
            for j, a0 in enumerate(i0):
                rr, bb, hh, _ = C.trailing_stop(o, h, l, cl, int(a0), P0[j], s[j], pct / 100.0, 864)
                r[j] = rr
                bars[j] = bb
                hit[j] = hh
            out[f"r_trail_{int(pct)}"][idx] = r - cost
            out[f"trail_{int(pct)}_hit"][idx] = hit
            out[f"trail_{int(pct)}_bars"][idx] = bars

        out["n_future_bars"][idx] = n - 1 - i0

    res = pd.DataFrame(out)
    res.insert(0, "trade_row", d.index.values)
    res["coin"] = d["coin"].values
    res["entry_day"] = d["entry_day"].values
    res["r_actual"] = d["r_net"].values
    res["hold_bars"] = d["hold_bars"].values
    res["hold_min"] = d["hold_min"].values
    res.to_csv(C.OUT / "cf_exits.csv", index=False)
    print(res.describe().T[["count", "mean", "50%"]].to_string())


if __name__ == "__main__":
    main()
