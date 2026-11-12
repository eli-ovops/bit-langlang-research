"""05 防未来函数自检：用原始行情独立重算若干特征，逐笔对比特征表。

检查项：
S1 日线：对 300 个随机仓位，只用"收盘时刻 <= entry_utc"的最后一条日线重算 box20 / dist_hi120；
S2 5m：只用"收盘时刻 <= entry_utc"的 bar 重算 m5_ret4h / m5_volratio / m5_dist_hi20；
S3 特征表里 d1_lag_min>=0 且 m5_lag_min>=0（特征 bar 不晚于入场）；
S4 用重算样本统计最大绝对误差。

输出：data/selector/sanity.json（PASS/FAIL + 误差）
运行：python3 scripts/v2_selector/05_sanity.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C


def main():
    C.ensure_outdir()
    feat = pd.read_csv(os.path.join(C.OUT_DIR, "features.csv.gz"))
    feat["entry_time"] = pd.to_datetime(feat["entry_time"])
    rng = np.random.default_rng(20261029)
    sample = feat.sample(min(300, len(feat)), random_state=int(rng.integers(1 << 31)))

    # 预热缓存
    d1_cache, m5_cache = {}, {}
    errs = {"box20": [], "dist_hi120": [], "m5_ret4h": [], "m5_volratio": [],
            "m5_dist_hi20": []}
    fails = []
    for _, r in sample.iterrows():
        s = r["mkt"]
        if s not in d1_cache:
            d1_cache[s] = C.load_d1(s)
            m5_cache[s] = C.load_m5(s)
        d = d1_cache[s]
        idx = np.searchsorted(d["ct"].to_numpy(), int(r["entry_ms"]), side="right") - 1
        if idx < 0:
            fails.append((r["symbol"], str(r["entry_time"]), "no daily bar"))
            continue
        dd = d.iloc[max(0, idx - 119): idx + 1]
        box20 = dd["high"].iloc[-20:].max() / dd["low"].iloc[-20:].min() - 1
        hi120 = dd["high"].max()
        dist120 = dd["close"].iloc[-1] / hi120 - 1 if len(dd) >= 60 else np.nan

        m = m5_cache[s]
        i5 = np.searchsorted(m["ct"].to_numpy(), int(r["entry_ms"]), side="right") - 1
        mm = m.iloc[max(0, i5 - 59): i5 + 1]
        ret4h = mm["close"].iloc[-1] / mm["close"].iloc[-49] - 1
        volratio = mm["volume"].iloc[-12:].mean() / mm["volume"].iloc[-48:].mean()
        disthi20 = mm["close"].iloc[-1] / mm["high"].iloc[-20:].max() - 1

        errs["box20"].append(abs(box20 - r["box20"]))
        errs["dist_hi120"].append(abs(dist120 - r["dist_hi120"]))
        errs["m5_ret4h"].append(abs(ret4h - r["m5_ret4h"]))
        errs["m5_volratio"].append(abs(volratio - r["m5_volratio"]))
        errs["m5_dist_hi20"].append(abs(disthi20 - r["m5_dist_hi20"]))

    res = {"n_checked": int(len(sample)), "fail_no_bar": len(fails),
           "S3_lag_nonnegative": bool((feat["d1_lag_min"] >= 0).all() and
                                      (feat["m5_lag_min"] >= 0).all()),
           "d1_lag_min_range": [float(feat["d1_lag_min"].min()), float(feat["d1_lag_min"].max())],
           "m5_lag_min_range": [float(feat["m5_lag_min"].min()), float(feat["m5_lag_min"].max())]}
    for k, v in errs.items():
        a = np.array([x for x in v if np.isfinite(x)])
        res[k + "_max_abs_err"] = float(a.max()) if len(a) else np.nan
        res[k + "_p99_abs_err"] = float(np.percentile(a, 99)) if len(a) else np.nan
    tol = {"box20": 1e-8, "dist_hi120": 1e-8, "m5_ret4h": 1e-9,
           "m5_volratio": 1e-9, "m5_dist_hi20": 1e-9}
    res["S1_S2_recompute"] = "PASS" if all(res[k + "_max_abs_err"] <= tol[k] for k in tol) else "FAIL"
    res["overall"] = "PASS" if (res["S1_S2_recompute"] == "PASS" and
                                res["S3_lag_nonnegative"] and res["fail_no_bar"] == 0) else "FAIL"
    with open(os.path.join(C.OUT_DIR, "sanity.json"), "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
