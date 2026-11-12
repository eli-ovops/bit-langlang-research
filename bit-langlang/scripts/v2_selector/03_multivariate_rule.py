"""03 多变量模型 + 预登记简单规则 + 随机选择器基准 + walk-forward + 目标 C 混淆检验。

所有选择/拟合只用 train（<=2023-12-31）；test（2024-01-01~2024-06-20）只做一次性验证。
无 scipy：logistic 用 L2 正则全批量梯度下降，线性用闭式岭回归。

输出（data/selector/）：
- model_results.json     5 特征模型的系数/AUC/IC/十分位
- decile_table.csv       按模型分数十分位的 R 汇总（train/test）
- rule_results.csv       预登记规则 train/test 绩效 + 按日聚类 + 去尾 + 随机基准分位
- random_baseline.csv    随机选择器零分布
- walkforward.csv        按年 walk-forward（2023、2024 两折）
- coin_confound.csv      目标 C 是"选币 edge"还是"币种身份"
- baseline_summary.json  基准率、覆盖、规模偏差

运行：python3 scripts/v2_selector/03_multivariate_rule.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

MODEL_FEATS = C.MODEL_FEATS


def main():
    C.ensure_outdir()
    df = pd.read_csv(os.path.join(C.OUT_DIR, "features.csv.gz"))
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["entry_date"] = df["entry_time"].dt.normalize()
    tr_m, te_m = C.split_masks(df)
    df["split"] = np.where(tr_m, "train", np.where(te_m, "test", "drop"))
    df = df[df["split"] != "drop"].copy()
    df = C.add_model_feats(df)

    tr, te = df[df.split == "train"], df[df.split == "test"]

    # ---------------- 基准率 / 规模偏差 ----------------
    base = {
        "n_train": int(len(tr)), "n_test": int(len(te)),
        "train": C.sel_stats(tr, np.ones(len(tr), bool)),
        "test": C.sel_stats(te, np.ones(len(te), bool)),
        "pnl_margin_corr_train": float(np.corrcoef(tr["pnl"], tr["margin"])[0, 1]),
        "median_margin_by_year": {str(y): float(g["margin"].median())
                                  for y, g in df.groupby(df.entry_time.dt.year)},
        "mean_R_by_year": {str(y): float(g["R"].mean())
                           for y, g in df.groupby(df.entry_time.dt.year)},
        "per_coin": {},
    }
    for sym, g in df.groupby("mkt"):
        base["per_coin"][sym] = {
            "n": int(len(g)), "n_test": int((g.split == "test").sum()),
            "mean_R": float(g["R"].mean()), "median_R": float(g["R"].median()),
            "win_rate": float(g["win_any"].mean()),
            "sum_pnl": float(g["pnl"].sum())}

    # ---------------- 多变量模型（train 拟合，test 一次性验证） ----------------
    Xtr = tr[MODEL_FEATS].to_numpy(float)
    Xte = te[MODEL_FEATS].to_numpy(float)
    Xtr_s, Xte_s, mu, sd = C.standardize(Xtr, Xte)
    ytr_win = tr["win_any"].to_numpy(float)
    w_win = C.fit_logistic_ridge(Xtr_s, ytr_win, lam=1.0)
    p_tr = C.logistic_predict(Xtr_s, w_win)
    p_te = C.logistic_predict(Xte_s, w_win)

    # 线性模型目标：R（已截尾 ±20）；岭回归 lam 固定=1
    w_lin = C.fit_ridge_linear(Xtr_s, tr["R"].to_numpy(float), lam=1.0)
    s_tr = np.hstack([np.ones((len(Xtr_s), 1)), Xtr_s]) @ w_lin
    s_te = np.hstack([np.ones((len(Xte_s), 1)), Xte_s]) @ w_lin

    model = {
        "features": MODEL_FEATS,
        "note": "5 特征预先固定（来自他的体系：季节/龙头强度/空间/箱体/5m 动量），"
                "未做任何特征搜索；标准化参数只用 train。",
        "logistic_win": {
            "coef_standardized": dict(zip(["intercept"] + MODEL_FEATS, w_win.round(4).tolist())),
            "auc_train": C.auc(ytr_win, p_tr), "auc_test": C.auc(te["win_any"].to_numpy(float), p_te),
            "base_rate_train": float(tr["win_any"].mean()), "base_rate_test": float(te["win_any"].mean()),
        },
        "ridge_R": {
            "coef_standardized": dict(zip(["intercept"] + MODEL_FEATS, w_lin.round(4).tolist())),
            "coef_vector": [float(x) for x in w_lin],
            "feature_mean": [float(x) for x in mu],
            "feature_sd": [float(x) for x in sd],
            "ic_train": C.spearman(s_tr, tr["R"].to_numpy(float)),
            "ic_test": C.spearman(s_te, te["R"].to_numpy(float)),
        },
    }

    # 十分位表（切点用 train 分数）
    cuts = C.decile_cuts(s_tr)
    dec = pd.concat([
        C.decile_table(tr.assign(_s=s_tr), s_tr, cuts, tag="train"),
        C.decile_table(te.assign(_s=s_te), s_te, cuts, tag="test"),
    ], ignore_index=True)
    dec.to_csv(os.path.join(C.OUT_DIR, "decile_table.csv"), index=False)

    # top decile vs rest（按日聚类）
    def top_decile_eval(split_df, score, tag):
        b = C.assign_bins(score, cuts)
        top = split_df[b == 9]
        rest = split_df[b <= 8]
        d = C.cluster_diff(top, rest, "R")
        st = C.sel_stats(split_df, b == 9, "R")
        # 去掉选中样本里最大的 5 笔 R
        top_sorted = top.sort_values("R", ascending=False)
        drop5 = top_sorted.iloc[5:]
        rb = _pctile(float(top["R"].mean()), split_df, len(top), "R")
        return {"tag": tag, "n_top": int(len(top)), "share_of_pool": float(len(top) / len(split_df)),
                "top_mean_R": float(top["R"].mean()), "top_median_R": float(top["R"].median()),
                "top_win": float(top["win_any"].mean()), "top_PF": st.get("PF"),
                "rest_mean_R": float(rest["R"].mean()),
                "diff_vs_rest": d["diff"], "cluster_t": d["t"], "cluster_p": d["p"],
                "n_overlap_days": d["n_overlap_days"], "boot_lo": d["lo"], "boot_hi": d["hi"],
                "top_mean_R_drop_biggest5": float(drop5["R"].mean()) if len(drop5) else np.nan,
                "random_pctile_of_mean": rb["pctile"], "random_p": rb["p"],
                "random_null_p95": rb["null_p95_mean"]}

    model["top_decile"] = {
        "linear_score": {"train": top_decile_eval(tr, s_tr, "train"),
                         "test": top_decile_eval(te, s_te, "test")},
        "logistic_score": {"train": top_decile_eval(tr, p_tr, "train"),
                           "test": top_decile_eval(te, p_te, "test")},
    }
    # 模型分对 A/C 目标的 IC
    model["ic_other_targets_test"] = {
        t: C.spearman(s_te, te[t].to_numpy(float)) for t in
        ["A_pnl", "A_norm", "fwd24h", "fwd72h", "rel24h", "rel72h"]}

    # ---------------- 预登记规则 ----------------
    qt = {f: C.five_quintiles(tr[f].dropna().to_numpy())
          for f in ["box20", "rs7", "dist_hi120", "btc_vol20_pctile"]}
    rules = {
        "R1_season_ON": lambda s: s["season_on"] == 1,
        "R2_long_only": lambda s: s["side"] == "多",
        "R3_season_ON_and_long": lambda s: (s["season_on"] == 1) & (s["side"] == "多"),
        "R4_box20_Q5": lambda s: C.assign_bins(s["box20"].to_numpy(), qt["box20"]) == 4,
        "R5_rs7_Q5": lambda s: C.assign_bins(s["rs7"].to_numpy(), qt["rs7"]) == 4,
        "R6_dist_hi120_Q1_space": lambda s: C.assign_bins(s["dist_hi120"].to_numpy(), qt["dist_hi120"]) == 0,
        "R7_btcvol_Q1": lambda s: C.assign_bins(s["btc_vol20_pctile"].to_numpy(), qt["btc_vol20_pctile"]) == 0,
    }
    rule_rows = []
    for name, fn in rules.items():
        for tag, s in (("train", tr), ("test", te)):
            mask = pd.Series(fn(s), index=s.index).fillna(False).astype(bool)
            if mask.sum() < 10 or (~mask).sum() < 10:
                rule_rows.append({"rule": name, "split": tag, "n": int(mask.sum()),
                                  "note": "样本不足（该规则在本段被季节点几乎完全占满/清空）"})
                continue
            st = C.sel_stats(s, mask.to_numpy())
            d = C.cluster_diff(s[mask], s[~mask], "R")
            top_sorted = s[mask].sort_values("R", ascending=False)
            drop5 = top_sorted.iloc[5:]
            rb = _pctile(float(s.loc[mask, "R"].mean()), s, int(mask.sum()), "R")
            rule_rows.append({
                "rule": name, "split": tag, "n": st["n"],
                "mean_R": st["mean_R"], "median_R": st["median_R"], "sum_R": st["sum_R"],
                "win_rate": st["win_rate"], "PF": st["PF"],
                "R_cluster_t_vs0": st["R_day_cluster_t"], "R_cluster_p_vs0": st["R_cluster_p"],
                "diff_vs_rest": d["diff"], "cluster_t_diff": d["t"], "cluster_p_diff": d["p"],
                "n_overlap_days": d["n_overlap_days"], "boot_lo": d["lo"], "boot_hi": d["hi"],
                "mean_R_drop_biggest5": float(drop5["R"].mean()) if len(drop5) else np.nan,
                "random_pctile_of_mean": rb["pctile"], "random_p": rb["p"],
            })
    rules_df = pd.DataFrame(rule_rows)
    rules_df.to_csv(os.path.join(C.OUT_DIR, "rule_results.csv"), index=False)

    # ---------------- walk-forward（按年） ----------------
    wf_rows = []
    for year in (2023, 2024):
        fit = df[df.entry_time < f"{year}-01-01"]
        ev = df[(df.entry_time >= f"{year}-01-01") & (df.entry_time < f"{year + 1}-01-01")]
        if len(fit) < 200 or len(ev) < 100:
            wf_rows.append({"fold": year, "note": "样本不足"})
            continue
        Xf = fit[MODEL_FEATS].to_numpy(float)
        Xe = ev[MODEL_FEATS].to_numpy(float)
        Xf_s, Xe_s, _, _ = C.standardize(Xf, Xe)
        wf_lin = C.fit_ridge_linear(Xf_s, fit["R"].to_numpy(float), lam=1.0)
        se = np.hstack([np.ones((len(Xe_s), 1)), Xe_s]) @ wf_lin
        cuts_f = C.decile_cuts(np.hstack([np.ones((len(Xf_s), 1)), Xf_s]) @ wf_lin)
        b = C.assign_bins(se, cuts_f)
        top = ev[b == 9]
        rest = ev[b <= 8]
        d = C.cluster_diff(top, rest, "R")
        row = {"fold": str(year), "n_fit": len(fit), "n_eval": len(ev),
               "ic_test": C.spearman(se, ev["R"].to_numpy(float)),
               "top_n": int(len(top)), "top_mean_R": float(top["R"].mean()) if len(top) else np.nan,
               "rest_mean_R": float(rest["R"].mean()) if len(rest) else np.nan,
               "diff": d["diff"], "cluster_t": d["t"], "cluster_p": d["p"]}
        # 预登记规则在同年份的 R 均值
        for name, fn in rules.items():
            mask = pd.Series(fn(ev), index=ev.index).fillna(False).astype(bool)
            row[f"{name}_n"] = int(mask.sum())
            row[f"{name}_meanR"] = float(ev.loc[mask, "R"].mean()) if mask.sum() else np.nan
        wf_rows.append(row)
    pd.DataFrame(wf_rows).to_csv(os.path.join(C.OUT_DIR, "walkforward.csv"), index=False)

    # ---------------- 目标 C：是"选币 edge"还是"币种身份"？ ----------------
    coin_rows = []
    d_c = df.dropna(subset=["rel72h", "box20", "atr_pct", "rs30"]).copy()
    d_c["rel72h_dm"] = d_c["rel72h"] - d_c.groupby("mkt")["rel72h"].transform("mean")
    for f in ["box20", "atr_pct", "rs30"]:
        d_c[f + "_dm"] = d_c[f] - d_c.groupby("mkt")[f].transform("mean")
    for tag, s in (("train", d_c[d_c.split == "train"]), ("test", d_c[d_c.split == "test"])):
        for f in ["box20", "atr_pct", "rs30"]:
            coin_rows.append({"split": tag, "feature": f, "target": "rel72h",
                              "n": len(s),
                              "ic_raw": C.spearman(s[f], s["rel72h"]),
                              "ic_within_coin": C.spearman(s[f + "_dm"], s["rel72h_dm"])})
    for mkt, g in d_c.groupby("mkt"):
        coin_rows.append({"split": "all", "feature": "coin_mean", "target": "rel72h",
                          "n": len(g), "ic_raw": np.nan,
                          "ic_within_coin": np.nan,
                          "coin": mkt, "coin_mean_rel72h": float(g["rel72h"].mean()),
                          "coin_mean_rel24h": float(g["rel24h"].mean())})
    coin_df = pd.DataFrame(coin_rows)
    coin_df.to_csv(os.path.join(C.OUT_DIR, "coin_confound.csv"), index=False)

    base["model"] = model
    with open(os.path.join(C.OUT_DIR, "model_results.json"), "w") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    with open(os.path.join(C.OUT_DIR, "baseline_summary.json"), "w") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)

    _print(model, dec, rules_df, coin_df, wf_rows)


def _random_baseline(pool: pd.DataFrame, k: int, tgt: str = "R",
                     n_boot: int = 2000, seed: int = 2026) -> dict:
    """实际选择集 vs 同分布随机抽 k 笔的零分布：返回分位与单尾 p。"""
    rng = np.random.default_rng(seed)
    x = pool[tgt].to_numpy(float)
    n = len(x)
    k = int(min(k, n))
    means = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.choice(n, k, replace=False)
        means[i] = x[idx].mean()
    return {"k": k, "null_mean_of_means": float(means.mean()),
            "null_sd_of_means": float(means.std(ddof=1)),
            "null_p95_mean": float(np.percentile(means, 95)),
            "null_p5_mean": float(np.percentile(means, 5))}


def _pctile(actual_mean: float, pool: pd.DataFrame, k: int, tgt="R", n_boot=2000, seed=2026) -> dict:
    rng = np.random.default_rng(seed)
    x = pool[tgt].to_numpy(float)
    n = len(x)
    k = int(min(k, n))
    means = np.array([x[rng.choice(n, k, replace=False)].mean() for _ in range(n_boot)])
    pct = float((means < actual_mean).mean() * 100)
    p = float((1 + (means >= actual_mean).sum()) / (n_boot + 1))
    return {"pctile": pct, "p": p, "null_p95_mean": float(np.percentile(means, 95)),
            "null_mean": float(means.mean()), "null_sd": float(means.std(ddof=1))}


def _print(model, dec, rules, coin, wf):
    print("=== 模型 ===")
    print(json.dumps(model["logistic_win"], ensure_ascii=False, indent=2))
    print(json.dumps(model["ridge_R"], ensure_ascii=False, indent=2))
    print("=== 线性分数 top decile ===")
    print(json.dumps(model["top_decile"]["linear_score"], ensure_ascii=False, indent=2))
    print("=== 规则 ===")
    print(rules[["rule", "split", "n", "mean_R", "median_R", "win_rate", "PF",
                 "cluster_t_diff", "cluster_p_diff", "mean_R_drop_biggest5",
                 "random_pctile_of_mean"]].to_string(index=False))
    print("=== walk-forward ===")
    print(pd.DataFrame(wf)[["fold", "n_eval", "ic_test", "top_mean_R", "rest_mean_R",
                            "cluster_t", "cluster_p"]].to_string(index=False))
    print("=== C 目标混淆 ===")
    print(coin.to_string(index=False))


if __name__ == "__main__":
    main()
