"""共同工具：数据加载、可观测特征、目标变量、统计检验。

设计约束（任务书硬性要求）：
- 只用入场时点可观测信息：日线特征一律用"最后一条已收盘日线"（等价 shift(1)）；
  5m 特征只用 close_time <= entry_utc 的 K 线。
- 训练/测试切分：任务书要求 train<=2024-06-30 / test>=2024-07-01，但原始交割单
  只到 2024-06-20 12:52（北京时间），该切分下 test 样本数 = 0。因此主分析改用
  可行的最后一段留出：train <= 2023-12-31，test = 2024-01-01 ~ 2024-06-20。
  （另做按年 walk-forward 稳健性：2023、2024 两折。）
- 无 scipy/sklearn/statsmodels：AUC、Spearman、聚类 t、bootstrap、ridge logistic
  全部用 numpy 自实现，t 的 p 值用正态近似（样本量足够，且主显著性判据为
  按日聚类/bootstrap，已披露）。
"""
from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MARKET = os.path.join(ROOT, "data", "market")
POS_CSV = os.path.join(ROOT, "data", "processed", "v2", "trades_positions.csv")
OUT_DIR = os.path.join(ROOT, "data", "selector")

# 10 个有 5m+1d 行情的币（占他全部仓位的比例见覆盖率报告）
SYMBOL_MAP = {
    "BTC-USDT-SWAP": "BTCUSDT",
    "ETH-USDT-SWAP": "ETHUSDT",
    "SOL-USDT-SWAP": "SOLUSDT",
    "DOGE-USDT-SWAP": "DOGEUSDT",
    "PEOPLE-USDT-SWAP": "PEOPLEUSDT",
    "TRB-USDT-SWAP": "TRBUSDT",
    "WLD-USDT-SWAP": "WLDUSDT",
    "APT-USDT-SWAP": "APTUSDT",
    "ORDI-USDT-SWAP": "ORDIUSDT",
    "PEPE-USDT-SWAP": "1000PEPEUSDT",
}
MARKETS = sorted(SYMBOL_MAP.values())

TRAIN_END = pd.Timestamp("2023-12-31 23:59:59")   # 主分析训练段截止（含）
TEST_START = pd.Timestamp("2024-01-01")            # 主分析测试段开始
REQ_TRAIN_END = pd.Timestamp("2024-06-30 23:59:59")  # 任务书要求（不可行，见上）
REQ_TEST_START = pd.Timestamp("2024-07-01")

M5_MS = 5 * 60 * 1000
D1_MS = 24 * 60 * 60 * 1000


# ----------------------------------------------------------------------------
# 数据加载
# ----------------------------------------------------------------------------
def load_positions() -> pd.DataFrame:
    p = pd.read_csv(POS_CSV, encoding="utf-8-sig")
    p["entry_time"] = pd.to_datetime(p["entry_time"])
    p["exit_time"] = pd.to_datetime(p["exit_time"])
    p["entry_utc"] = p["entry_time"] - pd.Timedelta(hours=8)
    p["entry_ms"] = (p["entry_utc"].astype("int64") // 10**6)
    p["entry_date"] = p["entry_time"].dt.normalize()
    p["mkt"] = p["symbol"].map(SYMBOL_MAP)
    p["sign"] = np.where(p["side"] == "多", 1.0, -1.0)
    # R = pnl / (0.1*margin)，本人口径风险单位；截尾 |R|<=20
    p["R_raw"] = p["pnl"] / (0.1 * p["margin"])
    p["R"] = p["R_raw"].clip(-20, 20)
    p["A_pnl"] = p["pnl"]                       # 目标 A：原始 USDT pnl（含规模偏差）
    p["A_norm"] = p["pnl"] / p["margin"]        # A 的按规模归一版（≈ret）
    p["win_any"] = (p["pnl"] > 0).astype(int)
    p["big_win"] = (p["R"] > 0.5).astype(int)   # R>0.5 作为"有意义的赢"
    return p


def load_m5(sym: str, cols=("ts", "open", "high", "low", "close", "volume")) -> pd.DataFrame:
    d = pd.read_csv(os.path.join(MARKET, f"{sym}_5m.csv.gz"), usecols=list(cols))
    d["ct"] = d["ts"] + M5_MS  # bar 收盘时刻（UTC ms）
    return d


def load_d1(sym: str) -> pd.DataFrame:
    d = pd.read_csv(os.path.join(MARKET, f"{sym}_1d.csv.gz"))
    d["ct"] = d["ts"] + D1_MS  # 日线 bar 收盘时刻（UTC ms）= 次日 00:00 UTC
    return d


# ----------------------------------------------------------------------------
# 日线特征（全部只用已收盘日线）
# ----------------------------------------------------------------------------
def _daily_features(d: pd.DataFrame, sym: str) -> pd.DataFrame:
    c = d["close"].astype(float)
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    v = d["volume"].astype(float)
    out = pd.DataFrame({"ct": d["ct"], "close": c})
    out["ema50"] = c.ewm(span=50, adjust=False).mean()
    out["ema200"] = c.ewm(span=200, adjust=False).mean()
    out["ema50_slope5"] = out["ema50"] / out["ema50"].shift(5) - 1.0
    r1 = c / c.shift(1) - 1.0
    out["vol20"] = r1.rolling(20).std()
    out["vol20_pctile"] = out["vol20"].rolling(365, min_periods=120).rank(pct=True)
    out["ret5"] = c / c.shift(5) - 1.0
    out["ret7"] = c / c.shift(7) - 1.0
    out["ret30"] = c / c.shift(30) - 1.0
    out["ret60"] = c / c.shift(60) - 1.0
    out["dd20"] = c / c.rolling(20).max() - 1.0
    out["box20"] = h.rolling(20).max() / lo.rolling(20).min() - 1.0
    out["box60"] = h.rolling(60).max() / lo.rolling(60).min() - 1.0
    out["hi60"] = h.rolling(60).max()
    out["hi120"] = h.rolling(120, min_periods=60).max()
    out["dist_hi60"] = c / out["hi60"] - 1.0
    out["dist_hi120"] = c / out["hi120"] - 1.0
    out["min20"] = lo.rolling(20).min()
    out["max20"] = h.rolling(20).max()
    out["pos20"] = (c - out["min20"]) / (out["max20"] - out["min20"])
    # ATR14 (%)，真实波幅用日线 OHLC，全部为已收盘数据
    prev = c.shift(1)
    tr = pd.concat([h - lo, (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    out["atr_pct"] = tr.rolling(14).mean() / c
    out["vol_ratio_5_20"] = v.rolling(5).mean() / v.rolling(20).mean()
    first_ms = int(d["ts"].iloc[0])
    out["data_days"] = (d["ts"] - first_ms) // D1_MS
    out["sym"] = sym
    return out


def build_daily_all() -> dict[str, pd.DataFrame]:
    daily = {s: _daily_features(load_d1(s), s) for s in MARKETS}
    btc = daily["BTCUSDT"].set_index("ct")
    for s in MARKETS:
        x = daily[s]
        b = btc.reindex(x["ct"])
        # 相对 BTC 强度：同一天、同一收盘时刻的日线收益差
        x["rs7"] = x["ret7"].to_numpy() - b["ret7"].to_numpy()
        x["rs30"] = x["ret30"].to_numpy() - b["ret30"].to_numpy()
        if s == "BTCUSDT":  # BTC 相对自己恒为 0，不是有效观测
            x["rs7"] = np.nan
            x["rs30"] = np.nan
        # BTC 季节代理（同一根已收盘日线）
        x["btc_close_gt_ema50"] = (b["close"].to_numpy() > b["ema50"].to_numpy()).astype(float)
        x["btc_ema50_slope5"] = b["ema50_slope5"].to_numpy()
        x["btc_close_gt_ema200"] = (b["close"].to_numpy() > b["ema200"].to_numpy()).astype(float)
        x["btc_vol20_pctile"] = b["vol20_pctile"].to_numpy()
        x["btc_dd20"] = b["dd20"].to_numpy()
        daily[s] = x
    return daily


# ----------------------------------------------------------------------------
# 5m 特征（只用 entry 之前已收盘 bar）
# ----------------------------------------------------------------------------
def _m5_features(d: pd.DataFrame) -> pd.DataFrame:
    c = d["close"].astype(float)
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    v = d["volume"].astype(float)
    out = pd.DataFrame({"ct": d["ct"], "m5_close": c})
    out["m5_ret1h"] = c / c.shift(12) - 1.0
    out["m5_ret4h"] = c / c.shift(48) - 1.0
    out["m5_dist_hi20"] = c / h.rolling(20).max() - 1.0
    out["m5_dist_lo20"] = c / lo.rolling(20).min() - 1.0
    out["m5_dist_hi60"] = c / h.rolling(60).max() - 1.0
    out["m5_dist_lo60"] = c / lo.rolling(60).min() - 1.0
    out["m5_volratio"] = v.rolling(12).mean() / v.rolling(48).mean()
    return out


def build_5m_all() -> dict[str, pd.DataFrame]:
    return {s: _m5_features(load_m5(s)) for s in MARKETS}


# ----------------------------------------------------------------------------
# 特征表
# ----------------------------------------------------------------------------
DAILY_FEATS = [
    "btc_close_gt_ema50", "btc_ema50_slope5", "btc_close_gt_ema200",
    "btc_vol20_pctile", "btc_dd20",
    "rs7", "rs30", "box20", "box60", "dist_hi60", "dist_hi120",
    "atr_pct", "vol_ratio_5_20", "pos20", "data_days", "ret5",
]
M5_FEATS = [
    "m5_ret1h", "m5_ret4h", "m5_dist_hi20", "m5_dist_lo20",
    "m5_dist_hi60", "m5_dist_lo60", "m5_volratio",
]
ALL_FEATS = DAILY_FEATS + M5_FEATS


def build_feature_table(pos: pd.DataFrame) -> pd.DataFrame:
    daily = build_daily_all()
    m5 = build_5m_all()
    cov = pos[pos["mkt"].notna()].copy().sort_values("entry_ms").reset_index(drop=True)

    # 日线 asof：最后一条收盘时刻 <= entry_utc 的日线
    parts = []
    for s in MARKETS:
        sub = cov[cov["mkt"] == s].copy()
        if sub.empty:
            continue
        d = daily[s].sort_values("ct")
        cols = ["ct", "close"] + DAILY_FEATS
        sub = pd.merge_asof(sub.sort_values("entry_ms"), d[cols].sort_values("ct"),
                            left_on="entry_ms", right_on="ct", direction="backward",
                            allow_exact_matches=True)
        sub = sub.rename(columns={"ct": "d1_ct"})
        parts.append(sub)
    feat = pd.concat(parts, ignore_index=True)

    # 5m asof：最后一条收盘时刻 <= entry_utc 的 5m bar
    parts = []
    for s in MARKETS:
        sub = feat[feat["mkt"] == s].copy()
        if sub.empty:
            continue
        m = m5[s].sort_values("ct")
        sub = pd.merge_asof(sub.sort_values("entry_ms"), m.sort_values("ct"),
                            left_on="entry_ms", right_on="ct", direction="backward",
                            allow_exact_matches=True)
        sub = sub.rename(columns={"ct": "m5_ct"})
        parts.append(sub)
    feat = pd.concat(parts, ignore_index=True).sort_values("entry_ms").reset_index(drop=True)

    # 数据新鲜度审计：entry 距特征 bar 收盘的分钟数
    feat["d1_lag_min"] = (feat["entry_ms"] - feat["d1_ct"]) / 60000.0
    feat["m5_lag_min"] = (feat["entry_ms"] - feat["m5_ct"]) / 60000.0

    # ---- 目标 C：用我们行情计算的入场后 24h/72h 收益（按他的方向） ----
    feat = _add_forward_returns(feat, m5)
    return feat


def _add_forward_returns(feat: pd.DataFrame, m5: dict[str, pd.DataFrame]) -> pd.DataFrame:
    fwd_parts = []
    btc = m5["BTCUSDT"].set_index("ct")["m5_close"]
    for s in MARKETS:
        sub = feat[feat["mkt"] == s].copy()
        if sub.empty:
            continue
        m = m5[s].sort_values("ct")[["ct", "m5_close"]].rename(columns={"m5_close": "p0"})
        base = pd.merge_asof(sub.sort_values("entry_ms"), m,
                             left_on="entry_ms", right_on="ct", direction="backward")
        base = base.rename(columns={"ct": "p0_ct"})
        # 入场时点的 BTC 价格（同一收盘时刻）
        bb = btc.reindex(pd.Index(base["p0_ct"])).to_numpy()
        base["btc0"] = bb
        for h, msh in ((24, 24 * 60 * 60 * 1000), (72, 72 * 60 * 60 * 1000)):
            tgt = base["entry_ms"] + msh
            q = pd.merge_asof(pd.DataFrame({"tgt": tgt}), m.rename(columns={"ct": "tct", "p0": "px"}),
                              left_on="tgt", right_on="tct", direction="backward")
            base[f"p_{h}h"] = q["px"].to_numpy()
            bt = pd.merge_asof(pd.DataFrame({"tgt": tgt}), btc.rename_axis("tct").reset_index()
                               .rename(columns={"m5_close": "bpx"}),
                               left_on="tgt", right_on="tct", direction="backward")
            base[f"btc_{h}h"] = bt["bpx"].to_numpy()
            base[f"fwd{h}h"] = base["sign"] * (base[f"p_{h}h"] / base["p0"] - 1.0)
            base[f"rel{h}h"] = base["sign"] * ((base[f"p_{h}h"] / base["p0"])
                                               - (base[f"btc_{h}h"] / base["btc0"]))
        fwd_parts.append(base)
    out = pd.concat(fwd_parts, ignore_index=True).sort_values("entry_ms").reset_index(drop=True)
    # 注意：BTC 自身作为基准时 rel*h 恒为 0（不是有效观测），置为 NaN 避免污染 AUC/IC。
    is_btc = out["mkt"] == "BTCUSDT"
    for h in (24, 72):
        out.loc[is_btc, f"rel{h}h"] = np.nan
    return out


# ----------------------------------------------------------------------------
# 切分
# ----------------------------------------------------------------------------
def split_masks(df: pd.DataFrame, train_end=TRAIN_END, test_start=TEST_START):
    t = df["entry_time"]
    return (t <= train_end), (t >= test_start)


# ----------------------------------------------------------------------------
# 统计工具（numpy 实现）
# ----------------------------------------------------------------------------
def rank(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), dtype=float)
    r[order] = np.arange(1, len(x) + 1, dtype=float)
    # 平均秩处理 ties
    s = x[order]
    i = 0
    n = len(x)
    while i < n:
        j = i + 1
        while j < n and s[j] == s[i]:
            j += 1
        if j - i > 1:
            r[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return r


def spearman(x, y) -> float:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan
    rx, ry = rank(x[ok]), rank(y[ok])
    return float(np.corrcoef(rx, ry)[0, 1])


def auc(y: np.ndarray, s: np.ndarray) -> float:
    """AUC（Mann-Whitney U），tie 取平均秩。y∈{0,1}。"""
    y = np.asarray(y, float)
    s = np.asarray(s, float)
    ok = np.isfinite(s) & np.isfinite(y)
    y, s = y[ok], s[ok]
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    r = rank(s)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def tstat(x: np.ndarray) -> tuple[float, float, int]:
    """普通 iid t 检验（H0 mean=0）。返回 (t, p_normal, n)。"""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return np.nan, np.nan, n
    m = x.mean()
    sd = x.std(ddof=1)
    if sd == 0:
        return np.nan, np.nan, n
    t = m / (sd / math.sqrt(n))
    p = 2 * (1 - _norm_cdf(abs(t)))
    return float(t), float(p), n


def clustered_t(df: pd.DataFrame, val_col: str, day_col: str = "entry_date") -> dict:
    """按入场日聚类的 t 检验：先算每日均值，再对日序列做 t 检验。"""
    g = df.groupby(day_col)[val_col].agg(["mean", "count"])
    g = g[g["count"] > 0]
    t, p, ndays = tstat(g["mean"].to_numpy())
    return {"t": t, "p": p, "n_days": ndays, "n": int(len(df)),
            "mean": float(df[val_col].mean()) if len(df) else np.nan,
            "day_mean": float(g["mean"].mean()) if len(g) else np.nan}


def day_bootstrap_ci(df: pd.DataFrame, val_col: str, n_boot: int = 2000,
                     seed: int = 20261029, day_col: str = "entry_date") -> tuple[float, float]:
    """按日 block bootstrap：重抽入场日，返回均值的 95% CI。"""
    rng = np.random.default_rng(seed)
    g = df.groupby(day_col)[val_col].agg(["sum", "count"])
    sums = g["sum"].to_numpy()
    cnts = g["count"].to_numpy()
    nd = len(g)
    if nd < 5:
        return np.nan, np.nan
    means = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, nd, nd)
        means[b] = sums[idx].sum() / max(cnts[idx].sum(), 1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_normal(t: float) -> float:
    return 2 * (1 - _norm_cdf(abs(t)))


# ----------------------------------------------------------------------------
# 简单模型（numpy）
# ----------------------------------------------------------------------------
def standardize(train: np.ndarray, test: np.ndarray):
    mu = np.nanmean(train, axis=0)
    sd = np.nanstd(train, axis=0)
    sd = np.where((sd == 0) | ~np.isfinite(sd), 1.0, sd)
    return (train - mu) / sd, (test - mu) / sd, mu, sd


def fit_logistic_ridge(X: np.ndarray, y: np.ndarray, lam: float = 1.0,
                       lr: float = 0.1, iters: int = 3000) -> np.ndarray:
    """L2 正则 logistic 回归（全批量梯度下降），返回 [b0, b...]。"""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, k = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(k + 1)
    for _ in range(iters):
        z = Xb @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        g = Xb.T @ (p - y) / n
        g[1:] += lam * w[1:] / n
        w -= lr * g
    return w


def logistic_predict(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    X = np.asarray(X, float)
    z = np.hstack([np.ones((len(X), 1)), X]) @ w
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit_ridge_linear(X: np.ndarray, y: np.ndarray, lam: float = 1.0) -> np.ndarray:
    """闭式岭回归（不含截距惩罚，数据已标准化），返回 [b0, b...]。"""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, k = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    A = Xb.T @ Xb
    reg = np.eye(k + 1) * lam
    reg[0, 0] = 0.0
    return np.linalg.solve(A + reg, Xb.T @ y)


def five_quintiles(train_x: np.ndarray) -> np.ndarray:
    """用训练段的分位点作为切点（测试段复用，避免 test 调参）。"""
    qs = np.nanpercentile(train_x, [20, 40, 60, 80])
    return qs


def assign_bins(x: np.ndarray, qs: np.ndarray) -> np.ndarray:
    b = np.digitize(np.asarray(x, float), qs, right=False)
    b = np.where(np.isfinite(x), b, -1)
    return b


def ensure_outdir():
    os.makedirs(OUT_DIR, exist_ok=True)


# ----------------------------------------------------------------------------
# 组合分析辅助（03 用）
# ----------------------------------------------------------------------------
def sel_stats(df: pd.DataFrame, mask: np.ndarray, tgt: str = "R") -> dict:
    """一个选择子集的绩效统计（R 口径为主）。"""
    s = df[mask]
    if len(s) == 0:
        return {"n": 0}
    pos = s["pnl"] > 0
    pf = s.loc[pos, "pnl"].sum() / max(1e-9, -s.loc[~pos, "pnl"].sum())
    ct = clustered_t(s, tgt)
    ct_win = clustered_t(s, "win_any")
    return {"n": int(len(s)), "mean_R": float(s[tgt].mean()),
            "median_R": float(s[tgt].median()), "sum_R": float(s[tgt].sum()),
            "win_rate": float(s["win_any"].mean()), "PF": float(pf),
            "R_day_cluster_t": ct["t"], "R_cluster_p": ct["p"], "n_days": ct["n_days"],
            "win_day_cluster_t": ct_win["t"], "win_cluster_p": ct_win["p"]}


def cluster_diff(a: pd.DataFrame, b: pd.DataFrame, tgt: str = "R",
                 n_boot: int = 1000, seed: int = 11) -> dict:
    """两组均值差的按日聚类 t（只取两组当天都有交易的日期）+ 按日 bootstrap CI。"""
    h = a.groupby("entry_date")[tgt].agg(["sum", "count"])
    l = b.groupby("entry_date")[tgt].agg(["sum", "count"])
    j = h.join(l, how="inner", lsuffix="_h", rsuffix="_l")
    if len(j) < 5:
        return {"diff": float(a[tgt].mean() - b[tgt].mean()), "t": np.nan, "p": np.nan,
                "n_overlap_days": int(len(j)), "lo": np.nan, "hi": np.nan}
    d = j["sum_h"] / j["count_h"] - j["sum_l"] / j["count_l"]
    t, p, nd = tstat(d.to_numpy())
    rng = np.random.default_rng(seed)
    boots = np.array([d.to_numpy()[rng.integers(0, len(d), len(d))].mean()
                      for _ in range(n_boot)])
    return {"diff": float(a[tgt].mean() - b[tgt].mean()), "t": t, "p": p,
            "n_overlap_days": int(nd),
            "lo": float(np.percentile(boots, 2.5)),
            "hi": float(np.percentile(boots, 97.5))}


def random_subset_baseline(pool: pd.DataFrame, k: int, tgt: str = "R",
                           n_boot: int = 2000, seed: int = 2026) -> dict:
    """从 pool 中随机抽 k 笔（同分布随机选择器），给出均值/ΣR 零分布与实际分位。"""
    rng = np.random.default_rng(seed)
    x = pool[tgt].to_numpy()
    n = len(x)
    k = int(min(k, n))
    means = np.empty(n_boot)
    sums = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.choice(n, k, replace=False)
        means[i] = x[idx].mean()
        sums[i] = x[idx].sum()
    return {"k": k, "pool_n": n,
            "null_mean_of_means": float(means.mean()),
            "null_sd_of_means": float(means.std(ddof=1)),
            "null_p95_mean": float(np.percentile(means, 95)),
            "null_p5_mean": float(np.percentile(means, 5))}


def decile_table(df: pd.DataFrame, score: np.ndarray, qs: np.ndarray,
                 tgt: str = "R", tag: str = "") -> pd.DataFrame:
    """按 train 切点把测试/训练样本分十档，汇总 R 与累计 R。"""
    b = assign_bins(score, qs)
    rows = []
    for d in range(10):
        s = df[b == d]
        if len(s) == 0:
            continue
        pos = s["pnl"] > 0
        rows.append({"tag": tag, "decile": d + 1, "n": len(s),
                     "mean_R": float(s[tgt].mean()), "median_R": float(s[tgt].median()),
                     "sum_R": float(s[tgt].sum()), "win_rate": float(s["win_any"].mean()),
                     "PF": float(s.loc[pos, "pnl"].sum() / max(1e-9, -s.loc[~pos, "pnl"].sum()))})
    out = pd.DataFrame(rows)
    if len(out):
        out["cum_sum_R"] = out["sum_R"].cumsum()
    return out


def decile_cuts(train_score: np.ndarray) -> np.ndarray:
    return np.nanpercentile(train_score, np.arange(10, 100, 10))


MODEL_FEATS = ["season_on", "rs7", "dist_hi120", "box20", "m5_ret4h"]


def add_model_feats(df: pd.DataFrame) -> pd.DataFrame:
    """把 5 个模型特征整理成列（季节合取、BTC 相对强度缺失填 0、缺失填 train 中位数）。"""
    df = df.copy()
    df["season_on"] = ((df["btc_close_gt_ema50"] == 1) &
                       (df["btc_ema50_slope5"] > 0) &
                       (df["btc_close_gt_ema200"] == 1)).astype(float)
    if "rs7" in df:
        df["rs7"] = df["rs7"].fillna(0.0)   # BTC 相对自己无定义 → 0（披露）
    for f in MODEL_FEATS:
        if f == "season_on":
            continue
        med = df.loc[df.get("split", pd.Series("train", index=df.index)) == "train", f].median()
        if not np.isfinite(med):
            med = df[f].median()
        df[f] = df[f].fillna(med)
    return df
