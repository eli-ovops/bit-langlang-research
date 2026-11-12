"""01 构建特征表 + 数据审计（覆盖率、对齐、缺失、选择偏差对比）。

输出（data/selector/）：
- features.csv.gz         每个可对齐仓位的入场时点特征 + 三个目标变量
- audit.json              覆盖率 / 对齐 / 缺失 / 时间滞后审计
- selection_bias.csv      他的交易 vs 同币同期的"无条件"特征分布对比
- unconditional_sample.csv.gz  无条件采样表（可复算）

运行：python3 scripts/v2_selector/01_build_features.py
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
    pos = C.load_positions()
    print(f"全部仓位: {len(pos)}；有行情的币种仓位: {pos['mkt'].notna().sum()}")

    feat = C.build_feature_table(pos)
    print(f"对齐后行数: {len(feat)}")

    # ---------------- 审计：覆盖率 ----------------
    cov_by_symbol = pos["mkt"].notna().groupby(pos["symbol"]).sum()
    all_by_symbol = pos["symbol"].value_counts()
    cov_df = pd.DataFrame({"n_all": all_by_symbol,
                           "n_covered": cov_by_symbol.reindex(all_by_symbol.index).fillna(0).astype(int)})
    cov_df["covered"] = cov_df["n_covered"] > 0
    cov_df = cov_df.sort_values("n_all", ascending=False)

    aligned = feat.dropna(subset=["m5_close", "close"]).copy()
    # 时间滞后：必须 >=0（无未来信息）
    lag_ok = bool((aligned["d1_lag_min"] >= 0).all() and (aligned["m5_lag_min"] >= 0).all())
    # 目标 C 可用性
    c_ok = aligned[["fwd24h", "fwd72h"]].notna().all(axis=1)

    nan_counts = {f: int(aligned[f].isna().sum()) for f in C.ALL_FEATS}
    nan_counts = dict(sorted(nan_counts.items(), key=lambda kv: -kv[1]))

    audit = {
        "n_positions_all": int(len(pos)),
        "n_positions_covered_10coins": int(pos["mkt"].notna().sum()),
        "coverage_pct": round(100 * pos["mkt"].notna().mean(), 2),
        "n_aligned": int(len(aligned)),
        "n_aligned_pct": round(100 * len(aligned) / len(pos), 2),
        "n_target_c_available": int(c_ok.sum()),
        "target_c_available_pct_of_aligned": round(100 * c_ok.mean(), 2),
        "d1_lag_min": {"min": float(aligned["d1_lag_min"].min()),
                       "median": float(aligned["d1_lag_min"].median()),
                       "max": float(aligned["d1_lag_min"].max())},
        "m5_lag_min": {"min": float(aligned["m5_lag_min"].min()),
                       "median": float(aligned["m5_lag_min"].median()),
                       "max": float(aligned["m5_lag_min"].max())},
        "no_future_info_check_pass": lag_ok,
        "feature_nan_counts": nan_counts,
        "covered_by_symbol": cov_df[cov_df["covered"]][["n_all", "n_covered"]].to_dict("index"),
        "coverage_by_year": {
            str(y): {"n_aligned": int(len(aligned[aligned["entry_time"].dt.year == y])),
                     "n_all": int((pos["entry_time"].dt.year == y).sum())}
            for y in sorted(pos["entry_time"].dt.year.unique())},
        "split_requested": {"train<=2024-06-30": int(len(pos[pos["entry_time"] <= C.REQ_TRAIN_END])),
                            "test>=2024-07-01": int(len(pos[pos["entry_time"] >= C.REQ_TEST_START])),
                            "note": "原始交割单止于 2024-06-20 12:52，要求的 test 段样本为 0；"
                                    "主分析改用 train<=2023-12-31 / test=2024-01-01~2024-06-20。"},
        "split_primary": {"train_end": str(C.TRAIN_END), "test_start": str(C.TEST_START),
                          "n_train": int((aligned["entry_time"] <= C.TRAIN_END).sum()),
                          "n_test": int((aligned["entry_time"] >= C.TEST_START).sum())},
        "target_c_definition": "sign*(P(entry+24h)/P(entry)-1)，P 用我们 5m 行情最后一条已收盘 bar；"
                                "rel*h 为同口径减去 BTC 同期收益（相对强度）。",
        "target_b_definition": "R = pnl/(0.1*margin)，截尾 |R|<=20（原始最大 91.7）。",
    }
    with open(os.path.join(C.OUT_DIR, "audit.json"), "w") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: audit[k] for k in
                      ["coverage_pct", "n_aligned", "no_future_info_check_pass",
                       "n_target_c_available", "d1_lag_min", "m5_lag_min"]},
                     ensure_ascii=False, indent=2))

    # ---------------- 选择偏差：无条件采样对比 ----------------
    uncond = _unconditional_sample(pos)
    bias = _bias_table(aligned, uncond)
    uncond.to_csv(os.path.join(C.OUT_DIR, "unconditional_sample.csv.gz"), index=False)
    bias.to_csv(os.path.join(C.OUT_DIR, "selection_bias.csv"), index=False)
    print(bias.to_string(index=False))

    # ---------------- 保存特征表 ----------------
    keep = (["symbol", "mkt", "side", "sign", "entry_time", "exit_time", "entry_ms",
             "entry", "exit", "notional", "margin", "leverage", "legs", "hold_min",
             "pnl", "ret", "R_raw", "R", "A_pnl", "A_norm", "win_any", "big_win",
             "d1_ct", "m5_ct", "d1_lag_min", "m5_lag_min"]
            + C.ALL_FEATS
            + ["p0", "p_24h", "p_72h", "fwd24h", "fwd72h", "rel24h", "rel72h"])
    feat_out = aligned[keep].copy()
    feat_out.to_csv(os.path.join(C.OUT_DIR, "features.csv.gz"), index=False,
                    compression="gzip")
    print(f"写出 features.csv.gz: {feat_out.shape}")
    return feat_out


def _unconditional_sample(pos: pd.DataFrame, seed: int = 20261029) -> pd.DataFrame:
    """同币、同期、每天随机一个 5m 时刻的"无条件"样本，用于特征分布对比。

    代表"如果他在 10 个币上随机时点入场，特征会是什么样"。
    """
    rng = np.random.default_rng(seed)
    t0 = pos["entry_time"].min().normalize()
    t1 = pos["entry_time"].max().normalize()
    days = pd.date_range(t0, t1, freq="D")
    rows = []
    for s in C.MARKETS:
        d = C.load_m5(s, cols=("ts",))
        first = int(d["ts"].iloc[0])
        last = int(d["ts"].iloc[-1])
        for day in days:
            # 每天随机一个 5m bar 开盘时刻（UTC 日内），转换为北京时间口径的 entry_ms
            day_ms = int(day.tz_localize("Asia/Shanghai").tz_convert("UTC").timestamp() * 1000)
            if day_ms < first or day_ms > last:
                continue
            off = int(rng.integers(0, 288)) * C.M5_MS
            rows.append({"symbol": s, "mkt": s, "entry_time": day + pd.Timedelta(minutes=off),
                         "sign": 1.0, "entry_ms": day_ms + off})
    syn = pd.DataFrame(rows)
    # 复用同一条特征构建路径
    syn_feat = _build_synthetic_features(syn)
    return syn_feat


def _build_synthetic_features(syn: pd.DataFrame) -> pd.DataFrame:
    daily = C.build_daily_all()
    m5 = C.build_5m_all()
    parts = []
    for s in C.MARKETS:
        sub = syn[syn["mkt"] == s].sort_values("entry_ms")
        if sub.empty:
            continue
        d = daily[s].sort_values("ct")
        sub = pd.merge_asof(sub, d[["ct", "close"] + C.DAILY_FEATS].sort_values("ct"),
                            left_on="entry_ms", right_on="ct", direction="backward")
        sub = sub.rename(columns={"ct": "d1_ct"})
        m = m5[s].sort_values("ct")
        sub = pd.merge_asof(sub.sort_values("entry_ms"), m.sort_values("ct"),
                            left_on="entry_ms", right_on="ct", direction="backward")
        sub = sub.rename(columns={"ct": "m5_ct"})
        parts.append(sub)
    out = pd.concat(parts, ignore_index=True)
    out = out.dropna(subset=["close", "m5_close"])
    return out


def _bias_table(his: pd.DataFrame, uncond: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for f in C.ALL_FEATS:
        a = his[f].dropna().to_numpy()
        b = uncond[f].dropna().to_numpy()
        if len(a) < 20 or len(b) < 20:
            continue
        rows.append({
            "feature": f,
            "his_n": len(a), "uncond_n": len(b),
            "his_p25": np.percentile(a, 25), "his_p50": np.percentile(a, 50),
            "his_p75": np.percentile(a, 75),
            "uncond_p25": np.percentile(b, 25), "uncond_p50": np.percentile(b, 50),
            "uncond_p75": np.percentile(b, 75),
            "median_diff": np.percentile(a, 50) - np.percentile(b, 50),
            "welch_t": _welch_t(a, b),
        })
    return pd.DataFrame(rows)


def _welch_t(a, b):
    ma, mb = np.mean(a), np.mean(b)
    va, vb = np.var(a, ddof=1) / len(a), np.var(b, ddof=1) / len(b)
    return float((ma - mb) / np.sqrt(va + vb)) if va + vb > 0 else np.nan


if __name__ == "__main__":
    main()
