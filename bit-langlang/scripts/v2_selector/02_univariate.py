"""02 单变量检验：IC / 五分位（train 切点固定到 test）/ AUC / 按日聚类 t / bootstrap。

只有入场时点可观测特征。训练段 train<=2023-12-31，测试段 2024-01-01~2024-06-20
（任务书的 2024-07 切分在本数据上 test=0，见 01 审计）。

输出（data/selector/）：
- univariate_ic.csv        连续目标 × 特征 × 段 的 Spearman IC
- quintile_summary.csv     五分位均值/中位数（二值目标即胜率）+ Q5-Q1 按日聚类 t + bootstrap CI
- auc_summary.csv          二值目标 AUC（盈利/亏损、R>0.5）
- base_rates.csv           各目标在 train/test 的基准率
- multiplicity.json        检验次数与 Bonferroni 阈值

运行：python3 scripts/v2_selector/02_univariate.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

CONT_TARGETS = [
    ("R", "B：风险单位 R=pnl/(0.1*margin)，截尾|R|<=20"),
    ("A_pnl", "A：原始 USDT pnl"),
    ("A_norm", "A：pnl/margin（按规模归一）"),
    ("fwd24h", "C：我方行情入场后 24h 收益（按他方向）"),
    ("fwd72h", "C：72h"),
    ("rel24h", "C：相对 BTC 24h（已剔除 BTC 自身）"),
    ("rel72h", "C：相对 BTC 72h"),
]
BIN_TARGETS = [
    ("win_any", "盈利 vs 亏损"),
    ("big_win", "R>0.5"),
]


def main():
    C.ensure_outdir()
    df = pd.read_csv(os.path.join(C.OUT_DIR, "features.csv.gz"))
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["entry_date"] = df["entry_time"].dt.normalize()
    tr_mask, te_mask = C.split_masks(df)
    df["split"] = np.where(tr_mask, "train", np.where(te_mask, "test", "drop"))
    df = df[df["split"] != "drop"].copy()
    print(f"train={int((df.split=='train').sum())}, test={int((df.split=='test').sum())}")

    ic_rows, q_rows, auc_rows = [], [], []
    cont_names = [t for t, _ in CONT_TARGETS]
    bin_names = [t for t, _ in BIN_TARGETS]

    for feat in C.ALL_FEATS:
        # ---------- 连续目标：IC + 五分位 ----------
        for tgt in cont_names:
            sub = df.dropna(subset=[feat, tgt])
            for split in ("train", "test"):
                s = sub[sub.split == split]
                if len(s) < 30:
                    continue
                ic = C.spearman(s[feat], s[tgt])
                ic_rows.append({"feature": feat, "target": tgt, "split": split,
                                "n": len(s), "ic": ic,
                                "ic_t": ic * np.sqrt(len(s) - 2) / np.sqrt(max(1e-12, 1 - ic**2))
                                if np.isfinite(ic) else np.nan})
            tr = sub[sub.split == "train"]
            te = sub[sub.split == "test"]
            if len(tr) < 100 or len(te) < 30 or tr[feat].nunique() < 3:
                continue
            qs = C.five_quintiles(tr[feat].to_numpy())
            for split, s in (("train", tr), ("test", te)):
                b = C.assign_bins(s[feat].to_numpy(), qs)
                for bi in range(5):
                    g = s[b == bi]
                    if len(g) < 20:
                        continue
                    q_rows.append(_qrow(feat, tgt, split, str(bi), g))
                hi, lo = s[b == 4], s[b == 0]
                if len(hi) >= 20 and len(lo) >= 20:
                    d = _cluster_diff(hi, lo, tgt)
                    q_rows.append({"feature": feat, "target": tgt, "split": split,
                                   "bin": "Q5-Q1", "n": len(hi) + len(lo),
                                   "mean": float(hi[tgt].mean() - lo[tgt].mean()),
                                   "median": float(hi[tgt].median() - lo[tgt].median()),
                                   "cluster_t": d["t"], "cluster_p": d["p"],
                                   "n_days": d["n_days"],
                                   "boot_lo": d["lo"], "boot_hi": d["hi"]})
        # ---------- 二值目标：AUC + 五分位胜率 ----------
        for tgt in bin_names:
            sub = df.dropna(subset=[feat, tgt])
            for split in ("train", "test"):
                s = sub[sub.split == split]
                if len(s) < 30 or s[tgt].nunique() < 2:
                    continue
                auc_rows.append({"feature": feat, "target": tgt, "split": split,
                                 "n": len(s), "auc": C.auc(s[tgt].to_numpy(), s[feat].to_numpy()),
                                 "base_rate": float(s[tgt].mean())})
            tr = sub[sub.split == "train"]
            te = sub[sub.split == "test"]
            if len(tr) < 100 or len(te) < 30 or tr[feat].nunique() < 3:
                continue
            qs = C.five_quintiles(tr[feat].to_numpy())
            for split, s in (("train", tr), ("test", te)):
                b = C.assign_bins(s[feat].to_numpy(), qs)
                for bi in range(5):
                    g = s[b == bi]
                    if len(g) < 20:
                        continue
                    q_rows.append(_qrow(feat, tgt, split, str(bi), g))
                hi, lo = s[b == 4], s[b == 0]
                if len(hi) >= 20 and len(lo) >= 20:
                    d = _cluster_diff(hi, lo, tgt)
                    q_rows.append({"feature": feat, "target": tgt, "split": split,
                                   "bin": "Q5-Q1", "n": len(hi) + len(lo),
                                   "mean": float(hi[tgt].mean() - lo[tgt].mean()),
                                   "median": float(hi[tgt].median() - lo[tgt].median()),
                                   "cluster_t": d["t"], "cluster_p": d["p"],
                                   "n_days": d["n_days"],
                                   "boot_lo": d["lo"], "boot_hi": d["hi"]})

    ic = pd.DataFrame(ic_rows)
    q = pd.DataFrame(q_rows)
    a = pd.DataFrame(auc_rows)
    ic.to_csv(os.path.join(C.OUT_DIR, "univariate_ic.csv"), index=False)
    q.to_csv(os.path.join(C.OUT_DIR, "quintile_summary.csv"), index=False)
    a.to_csv(os.path.join(C.OUT_DIR, "auc_summary.csv"), index=False)

    base = []
    for tgt in cont_names + bin_names:
        for split in ("train", "test"):
            s = df[df.split == split][tgt].dropna()
            base.append({"target": tgt, "split": split, "n": len(s),
                         "mean": float(s.mean()), "median": float(s.median()),
                         "std": float(s.std()), "pct_pos": float((s > 0).mean())})
    pd.DataFrame(base).to_csv(os.path.join(C.OUT_DIR, "base_rates.csv"), index=False)

    n_ic = int(ic["ic"].notna().sum())
    n_q = len(q)
    n_auc = len(a)
    total = n_ic + n_q + n_auc
    mult = {"n_ic_tests": n_ic, "n_quintile_tests": n_q, "n_auc_tests": n_auc,
            "n_total_tests": total,
            "bonferroni_alpha_0.05": 0.05 / total,
            "note": "每个 特征×目标×段 的 IC/分位/按日聚类 t/AUC 均计入检验次数；"
                    "特征与目标全部预先登记，未用 test 段做任何筛选，故 test 段为一次性验证。"}
    with open(os.path.join(C.OUT_DIR, "multiplicity.json"), "w") as f:
        json.dump(mult, f, ensure_ascii=False, indent=2)
    print(json.dumps(mult, ensure_ascii=False, indent=2))
    _print_summary(ic, q, a)


def _qrow(feat, tgt, split, bi, g):
    ct = C.clustered_t(g, tgt)
    return {"feature": feat, "target": tgt, "split": split, "bin": str(bi),
            "n": len(g), "mean": float(g[tgt].mean()), "median": float(g[tgt].median()),
            "cluster_t": ct["t"], "cluster_p": ct["p"], "n_days": ct["n_days"],
            "boot_lo": np.nan, "boot_hi": np.nan}


def _cluster_diff(hi, lo, tgt, n_boot=1000, seed=7):
    """两组均值差的按日聚类 t + 按日 bootstrap CI。"""
    days = sorted(set(hi["entry_date"]) | set(lo["entry_date"]))
    h = hi.groupby("entry_date")[tgt].agg(["sum", "count"])
    l = lo.groupby("entry_date")[tgt].agg(["sum", "count"])
    rows = []
    for d in days:
        a = h.loc[d] if d in h.index else None
        b = l.loc[d] if d in l.index else None
        rows.append((a["sum"] if a is not None else 0.0,
                     a["count"] if a is not None else 0,
                     b["sum"] if b is not None else 0.0,
                     b["count"] if b is not None else 0))
    arr = np.array(rows)
    hs, hc, ls, lc = arr.T
    ok = (hc > 0) & (lc > 0)
    if ok.sum() < 5:
        return {"t": np.nan, "p": np.nan, "n_days": int(ok.sum()), "lo": np.nan, "hi": np.nan}
    diffs = hs[ok] / hc[ok] - ls[ok] / lc[ok]
    t, p, nd = C.tstat(diffs)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, len(diffs), len(diffs))
        boots[i] = diffs[idx].mean()
    return {"t": t, "p": p, "n_days": nd,
            "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5))}


def _print_summary(ic, q, a):
    print("\n=== IC (train) |ic| 最大 12 个 ===")
    t = ic[ic.split == "train"].dropna(subset=["ic"])
    print(t.reindex(t["ic"].abs().sort_values(ascending=False).index)
          .head(12)[["feature", "target", "n", "ic"]].to_string(index=False))
    print("\n=== Q5-Q1 (test) 按日聚类 t |t| 最大 12 个 ===")
    s = q[(q.split == "test") & (q["bin"] == "Q5-Q1")].dropna(subset=["cluster_t"])
    print(s.reindex(s["cluster_t"].abs().sort_values(ascending=False).index)
          .head(12)[["feature", "target", "n", "mean", "cluster_t", "cluster_p",
                     "boot_lo", "boot_hi"]].to_string(index=False))
    print("\n=== AUC (test) 偏离 0.5 最大 12 个 ===")
    t = a[a.split == "test"].dropna(subset=["auc"])
    t = t.assign(dev=(t["auc"] - 0.5).abs())
    print(t.sort_values("dev", ascending=False).head(12)
          [["feature", "target", "n", "auc", "base_rate"]].to_string(index=False))


if __name__ == "__main__":
    main()
