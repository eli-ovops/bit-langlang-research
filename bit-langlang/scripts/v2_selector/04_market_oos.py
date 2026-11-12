"""04 真样本外（市场口径）：用 2024-07-01~2026-10 行情检验"选择器"信号本身。

任务书要求的切分是 train<=2024-06-30 / test>=2024-07-01，但原始交割单止于
2024-06-20，test 段他的仓位为 0。因此这里把选择器信号冻结（参数全部来自
train<=2023-12-31 的他自己的交易），在 2024-07 之后的市场数据上做一次性检验：
每个币每天（00:00 UTC）当作一个"做多候选"，看被选中的候选之后 24h/72h 收益
是否高于未被选中的候选 —— 这检验的是"信号本身"的样本外预测力，不是他的实盘。

防重叠：24h 用全部日；72h 每 3 天取一个，避免前向窗口重叠。
输出：data/selector/market_oos.csv、market_uncond.csv
运行：python3 scripts/v2_selector/04_market_oos.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OOS_START = pd.Timestamp("2024-07-01")
OOS_END = pd.Timestamp("2026-10-15")   # 留出 72h 前向空间


def main():
    C.ensure_outdir()
    feats = pd.read_csv(os.path.join(C.OUT_DIR, "features.csv.gz"))
    feats["entry_time"] = pd.to_datetime(feats["entry_time"])
    feats["split"] = np.where(feats["entry_time"] <= C.TRAIN_END, "train", "test")
    train = feats[feats.split == "train"].copy()
    train = C.add_model_feats(train)
    with open(os.path.join(C.OUT_DIR, "model_results.json")) as f:
        model = json.load(f)
    coef = np.array(model["ridge_R"]["coef_vector"])
    mu = np.array(model["ridge_R"]["feature_mean"])
    sd = np.array(model["ridge_R"]["feature_sd"])

    # ---- 冻结切点（全部来自他的 train 交易） ----
    box_q = np.nanpercentile(train["box20"].dropna(), [20, 40, 60, 80])
    rs_q = np.nanpercentile(train["rs7"].dropna(), [20, 40, 60, 80])
    Xtr = (train[C.MODEL_FEATS].to_numpy(float) - mu) / sd
    score_tr = np.dot(np.hstack([np.ones((len(Xtr), 1)), Xtr]), coef)
    score_cut = np.nanpercentile(score_tr, 90)

    # ---- 市场候选池：10 币 × 每个交易日 00:00 UTC ----
    uni = _market_universe()
    print(f"市场候选池（2024-07 之后）：{len(uni)} 行")

    uni["r_box20"] = C.assign_bins(uni["box20"].to_numpy(), box_q) == 4
    uni["r_rs7"] = C.assign_bins(uni["rs7"].fillna(0).to_numpy(), rs_q) == 4
    uni["r_model"] = uni["score"].to_numpy() >= score_cut
    uni["r_season"] = uni["season_on"].to_numpy() == 1
    rule_cols = {
        "box20_Q5(高波动)": "r_box20",
        "rs7_Q5(相对强度)": "r_rs7",
        "model_score_top10%": "r_model",
        "season_ON": "r_season",
    }
    rows = []
    for name, col in rule_cols.items():
        for h in (24, 72):
            d = uni if h == 24 else uni[uni["entry_date"].dt.dayofyear % 3 == 0]
            d = d.dropna(subset=[f"fwd{h}h"])
            m = d[col].to_numpy(bool)
            hi, lo = d[m], d[~m]
            if len(hi) < 50 or len(lo) < 50:
                rows.append({"rule": name, "horizon": h, "n_sel": int(len(hi)),
                             "note": "样本不足"})
                continue
            ct = C.cluster_diff(hi, lo, f"fwd{h}h")
            ctr = C.cluster_diff(hi.dropna(subset=[f"rel{h}h"]),
                                 lo.dropna(subset=[f"rel{h}h"]), f"rel{h}h")
            rb = _pctile(float(hi[f"fwd{h}h"].mean()), d, len(hi), f"fwd{h}h")
            rows.append({
                "rule": name, "horizon": h, "n_sel": int(len(hi)), "n_pool": int(len(d)),
                "sel_mean": float(hi[f"fwd{h}h"].mean()),
                "unsel_mean": float(lo[f"fwd{h}h"].mean()),
                "diff": ct["diff"], "cluster_t": ct["t"], "cluster_p": ct["p"],
                "overlap_days": ct["n_overlap_days"],
                "sel_mean_rel": float(hi[f"rel{h}h"].mean()),
                "unsel_mean_rel": float(lo[f"rel{h}h"].mean()),
                "diff_rel": ctr["diff"], "cluster_t_rel": ctr["t"], "cluster_p_rel": ctr["p"],
                "random_pctile": rb["pctile"], "random_p": rb["p"],
            })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(C.OUT_DIR, "market_oos.csv"), index=False)

    # ---- 无条件市场背景（为什么这类信号在 A 股/币市容易"假阳性"） ----
    unc = []
    for y, g in uni.groupby(uni["entry_date"].dt.year):
        unc.append({"year": int(y), "n": len(g),
                    "mean_fwd24h": float(g["fwd24h"].mean()),
                    "mean_fwd72h": float(g["fwd72h"].mean()),
                    "mean_rel24h": float(g["rel24h"].mean()),
                    "mean_rel72h": float(g["rel72h"].mean()),
                    "pct_rel24h_pos": float((g["rel24h"] > 0).mean())})
    unc_df = pd.DataFrame(unc)
    unc_df.to_csv(os.path.join(C.OUT_DIR, "market_uncond.csv"), index=False)

    print(out.round(4).to_string(index=False))
    print()
    print(unc_df.round(4).to_string(index=False))


def _pctile(actual_mean, pool, k, tgt, n_boot=2000, seed=2026):
    rng = np.random.default_rng(seed)
    x = pool[tgt].dropna().to_numpy(float)
    n = len(x)
    k = int(min(k, n))
    means = np.array([x[rng.choice(n, k, replace=False)].mean() for _ in range(n_boot)])
    return {"pctile": float((means < actual_mean).mean() * 100),
            "p": float((1 + (means >= actual_mean).sum()) / (n_boot + 1))}


def _market_universe() -> pd.DataFrame:
    daily = C.build_daily_all()
    m5 = C.build_5m_all()
    dates = pd.date_range(OOS_START.normalize(), OOS_END.normalize(), freq="D")
    rows = []
    for s in C.MARKETS:
        for day in dates:
            entry_ms = int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)
            rows.append({"mkt": s, "entry_ms": entry_ms, "entry_date": day})
    uni = pd.DataFrame(rows)
    parts = []
    for s in C.MARKETS:
        sub = uni[uni.mkt == s].sort_values("entry_ms")
        d = daily[s].sort_values("ct")
        sub = pd.merge_asof(sub, d[["ct", "close"] + C.DAILY_FEATS].sort_values("ct"),
                            left_on="entry_ms", right_on="ct", direction="backward")
        sub = sub.rename(columns={"ct": "d1_ct"})
        m = m5[s].sort_values("ct")
        sub = pd.merge_asof(sub, m.sort_values("ct"), left_on="entry_ms", right_on="ct",
                            direction="backward")
        sub = sub.rename(columns={"ct": "m5_ct"})
        parts.append(sub)
    uni = pd.concat(parts, ignore_index=True).dropna(subset=["close", "m5_close"])
    uni = uni.rename(columns={"m5_close": "p0"})
    uni["sign"] = 1.0

    # 模型特征 + 前向收益
    uni = C.add_model_feats(uni)
    with open(os.path.join(C.OUT_DIR, "model_results.json")) as f:
        model = json.load(f)
    coef = np.array(model["ridge_R"]["coef_vector"])
    mu = np.array(model["ridge_R"]["feature_mean"])
    sd = np.array(model["ridge_R"]["feature_sd"])
    X = (uni[C.MODEL_FEATS].to_numpy(float) - mu) / sd
    uni["score"] = np.dot(np.hstack([np.ones((len(X), 1)), X]), coef)

    with np.errstate(all="ignore"):
        btc = m5["BTCUSDT"].sort_values("ct")[["ct", "m5_close"]]
        btc = btc.rename(columns={"m5_close": "btc_close"}).reset_index(drop=True)
        px = pd.concat([m5[s].sort_values("ct")[["ct", "m5_close"]].assign(mkt=s)
                        for s in C.MARKETS], ignore_index=True)
        px = px.sort_values("ct").reset_index(drop=True)
        btc0 = pd.merge_asof(uni[["entry_ms"]].sort_values("entry_ms"), btc,
                             left_on="entry_ms", right_on="ct", direction="backward")
        uni["btc0"] = btc0["btc_close"].to_numpy()
        for h in (24, 72):
            left = uni[["mkt", "entry_ms"]].copy()
            left["tgt"] = left["entry_ms"] + h * 3600 * 1000
            left["_i"] = np.arange(len(left))
            left = left.sort_values("tgt").reset_index(drop=True)
            q = pd.merge_asof(left, px, left_on="tgt", right_on="ct", by="mkt",
                              direction="backward")
            q = q.sort_values("_i")
            uni[f"p_{h}h"] = q["m5_close"].to_numpy()
            uni[f"fwd{h}h"] = uni[f"p_{h}h"] / uni["p0"] - 1.0
            lb = uni[["entry_ms"]].copy()
            lb["tgt"] = lb["entry_ms"] + h * 3600 * 1000
            lb["_i"] = np.arange(len(lb))
            qb = pd.merge_asof(lb.sort_values("tgt").reset_index(drop=True), btc,
                               left_on="tgt", right_on="ct", direction="backward")
            qb = qb.sort_values("_i")
            uni[f"btc_{h}h"] = qb["btc_close"].to_numpy()
            uni[f"rel{h}h"] = (uni[f"p_{h}h"] / uni["p0"]
                               - uni[f"btc_{h}h"] / uni["btc0"])
            uni.loc[uni.mkt == "BTCUSDT", f"rel{h}h"] = np.nan
    return uni.sort_values(["entry_date", "mkt"]).reset_index(drop=True)


if __name__ == "__main__":
    main()
