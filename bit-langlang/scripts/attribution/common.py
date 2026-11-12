"""共享工具：口径定义、资金费估算、聚类 bootstrap。

口径（重要）：
- 规范口径 = data/processed/v2/trades_positions.csv（4,651 个独立仓位，按 symbol+入场分钟聚合）。
  腿口径 trades_legs_dedup.csv（4,798 腿）仅用于对账，不代表独立样本。
- 交割单字段 `pnl` 是**价格方向性盈亏（不含手续费）**：已用 98.6% 的仓位验证
  pnl ≈ notional * sign * (exit/entry - 1)，误差中位数 9e-6（相对 notional）。
  因此：net = pnl + fee（fee 为负）。
- `ret` 字段不可靠（多腿仓位/少数录入错误，ret != pnl/margin）。统一用
  R_gross = pnl / margin, R_net = (pnl + fee) / margin（margin<=0 的 6 行为 NaN）。
- 时间为北京时间（UTC+8）；资金费时间戳为 UTC ms。
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
POS_CSV = ROOT / "data/processed/v2/trades_positions.csv"
LEG_CSV = ROOT / "data/processed/v2/trades_legs_dedup.csv"
MKT = ROOT / "data/market"
OUT = ROOT / "data/attribution"
OUT.mkdir(parents=True, exist_ok=True)

# 有行情/资金费的 10 个币（基础币 -> 文件名前缀）
MKT_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "DOGE": "DOGEUSDT",
    "PEPE": "1000PEPEUSDT",  # 1000PEPE 与 PEPE 资金费率、涨跌比例完全等价
    "ORDI": "ORDIUSDT",
    "TRB": "TRBUSDT",
    "PEOPLE": "PEOPLEUSDT",
    "WLD": "WLDUSDT",
    "APT": "APTUSDT",
}

HOLD_BINS = [-0.001, 5, 30, 240, 1440, np.inf]
HOLD_LABELS = ["<5m", "5-30m", "30m-4h", "4h-24h", ">24h"]

TOP_COINS_10 = ["BTC", "ETH", "PEPE", "APT", "TRB", "WLD", "DOGE", "SOL", "ORDI", "PEOPLE"]


def load_positions() -> pd.DataFrame:
    p = pd.read_csv(POS_CSV, encoding="utf-8-sig")
    p["entry_time"] = pd.to_datetime(p["entry_time"])
    p["exit_time"] = pd.to_datetime(p["exit_time"])
    p["entry_utc"] = p["entry_time"] - pd.Timedelta(hours=8)
    p["exit_utc"] = p["exit_time"] - pd.Timedelta(hours=8)
    p["base"] = p["symbol"].str.replace("-USDT-SWAP", "", regex=False)
    p["mkt"] = p["base"].map(MKT_MAP)
    p["covered_mkt"] = p["mkt"].notna()
    p["side_sign"] = np.where(p["side"] == "多", 1.0, -1.0)
    p["year"] = p["entry_time"].dt.year
    p["month"] = p["entry_time"].dt.to_period("M").astype(str)
    p["day"] = p["entry_time"].dt.date
    p["coin_group"] = np.select(
        [p["base"] == "BTC", p["base"] == "ETH"], ["BTC", "ETH"], default="山寨"
    )
    valid_size = (p["margin"] > 0) & (p["notional"] > 0)
    p["valid_size"] = valid_size
    p["net"] = p["pnl"] + p["fee"]
    p["R_gross"] = np.where(valid_size, p["pnl"] / p["margin"], np.nan)
    p["R_net"] = np.where(valid_size, p["net"] / p["margin"], np.nan)
    p["hold_bucket"] = pd.cut(
        p["hold_min"], bins=HOLD_BINS, labels=HOLD_LABELS, right=False
    )
    p["top10_mkt"] = p["base"].isin(TOP_COINS_10)
    return p


def load_legs() -> pd.DataFrame:
    l = pd.read_csv(LEG_CSV, encoding="utf-8-sig")
    l["entry_time"] = pd.to_datetime(l["entry_time"])
    l["exit_time"] = pd.to_datetime(l["exit_time"])
    return l


# ---------------------------------------------------------------- funding
_fund_cache: dict[str, pd.DataFrame] = {}
_px_cache: dict[str, pd.DataFrame] = {}


def _load_funding(mkt: str) -> pd.DataFrame:
    if mkt not in _fund_cache:
        f = pd.read_csv(gzip.open(MKT / f"{mkt}_funding.csv.gz", "rt"))
        f["utc"] = pd.to_datetime(f["ts"], unit="ms")
        _fund_cache[mkt] = f.sort_values("utc").reset_index(drop=True)
    return _fund_cache[mkt]


def _load_5m(mkt: str) -> pd.DataFrame:
    if mkt not in _px_cache:
        d = pd.read_csv(gzip.open(MKT / f"{mkt}_5m.csv.gz", "rt"), usecols=["ts", "close"])
        d["utc"] = pd.to_datetime(d["ts"], unit="ms")
        _px_cache[mkt] = d.sort_values("utc").reset_index(drop=True)
    return _px_cache[mkt]


def _px_at(px: pd.DataFrame, ts: pd.Timestamp) -> float:
    """时间戳当时（<=ts 的最后一根 5m 收盘）；超出历史返回 nan。"""
    i = np.searchsorted(px["utc"].values, np.datetime64(ts), side="right") - 1
    if i < 0:
        return np.nan
    return float(px["close"].iloc[i])


def attach_funding(p: pd.DataFrame) -> pd.DataFrame:
    """为 10 币仓位估算资金费（USDT，交易者视角，负=支付）。

    规则：在 (entry_utc, exit_utc] 内的每个资金费时点，支付
        -side_sign * rate * notional_est
    notional_est = notional * price(funding_time)/price(entry_time)（价格比例，
    对 PEPE/1000PEPE 的 1000 倍缩放不敏感）。
    资金费率为无量纲，PEPE->1000PEPE 映射不影响结果。
    这是估算：未考虑仓位过程中加减仓，误差量级 < 资金费本身的 10%（持仓中位 8 分钟）。
    """
    out = p.copy()
    out["funding"] = 0.0
    out["funding_n_events"] = 0
    out["funding_status"] = np.where(out["covered_mkt"], "covered", "no_market_data")

    for mkt, grp in out[out["covered_mkt"]].groupby("mkt"):
        fund = _load_funding(mkt)
        fts = fund["utc"].values
        rates = fund["funding_rate"].values
        px = _load_5m(mkt)
        for idx, row in grp.iterrows():
            lo = np.searchsorted(fts, np.datetime64(row["entry_utc"]), side="right")
            hi = np.searchsorted(fts, np.datetime64(row["exit_utc"]), side="right")
            if hi <= lo:
                continue
            pentry = _px_at(px, row["entry_utc"])
            mult = 1.0
            if np.isfinite(pentry) and pentry > 0:
                ratios = np.array([_px_at(px, pd.Timestamp(t)) for t in fts[lo:hi]]) / pentry
                ratios = np.where(np.isfinite(ratios) & (ratios > 0), ratios, 1.0)
            else:
                ratios = np.full(hi - lo, 1.0)
            pay = -row["side_sign"] * np.sum(rates[lo:hi] * row["notional"] * ratios)
            out.at[idx, "funding"] = pay
            out.at[idx, "funding_n_events"] = int(hi - lo)
    out.loc[~out["valid_size"], "funding"] = 0.0  # 无名义本金，无法计算（费用仍计入 fee）
    return out


# ---------------------------------------------------------------- bootstrap
def cluster_bootstrap_sum(
    df: pd.DataFrame, col: str, cluster: str = "day", n_boot: int = 2000, seed: int = 20261029
) -> dict:
    """按 cluster（默认入场日）整群重抽的 sum 的 percentile CI。

    返回 point, ci_lo, ci_hi, n_clusters, se。
    """
    g = df.dropna(subset=[col]).groupby(cluster)[col].agg(["sum", "size"])
    clusters = g.index.values
    sums = g["sum"].values
    sizes = g["size"].values
    n = len(clusters)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, n, n)
        stats[b] = sums[pick].sum()
        means[b] = sums[pick].sum() / max(sizes[pick].sum(), 1)
    point = sums.sum()
    return {
        "point": float(point),
        "ci_lo": float(np.percentile(stats, 2.5)),
        "ci_hi": float(np.percentile(stats, 97.5)),
        "se": float(stats.std(ddof=1)),
        "n_clusters": int(n),
        "mean_point": float(df[col].mean()),
        "mean_ci_lo": float(np.percentile(means, 2.5)),
        "mean_ci_hi": float(np.percentile(means, 97.5)),
        "n": int(df[col].notna().sum()),
    }


def cluster_bootstrap_mean(
    df: pd.DataFrame, col: str, cluster: str = "day", n_boot: int = 2000, seed: int = 20261029
) -> dict:
    r = cluster_bootstrap_sum(df, col, cluster, n_boot, seed)
    return {
        "n": r["n"],
        "mean": r["mean_point"],
        "ci_lo": r["mean_ci_lo"],
        "ci_hi": r["mean_ci_hi"],
        "n_clusters": r["n_clusters"],
    }


def tstat_cluster(df: pd.DataFrame, col: str, cluster: str = "day") -> dict:
    """按日聚类的均值 t 检验（对聚类均值做单样本 t）。

    先按 cluster 求均值，再对聚类均值做 t 检验（保守：忽略簇内样本数差异）。
    """
    d = df.dropna(subset=[col])
    gm = d.groupby(cluster)[col].mean()
    n = len(gm)
    if n < 3:
        return {"t": np.nan, "n_clusters": n, "mean": np.nan, "se": np.nan}
    se = gm.std(ddof=1) / np.sqrt(n)
    mean = gm.mean()
    return {"t": float(mean / se) if se > 0 else np.nan, "n_clusters": n, "mean": float(mean), "se": float(se)}


def diebold_mariano_like_diff(
    df: pd.DataFrame, col: str, mask_a, mask_b, cluster: str = "day"
) -> dict:
    """两组均值差（按日聚类）：对每日的 (mean_a - mean_b) 做 t 检验。"""
    d = df.dropna(subset=[col])
    a = d[mask_a(d)].groupby(cluster)[col].mean()
    b = d[mask_b(d)].groupby(cluster)[col].mean()
    diff = (a - b).dropna()
    n = len(diff)
    if n < 3:
        return {"diff": np.nan, "t": np.nan, "n_clusters": n}
    se = diff.std(ddof=1) / np.sqrt(n)
    return {
        "diff": float(diff.mean()),
        "t": float(diff.mean() / se) if se > 0 else np.nan,
        "n_clusters": int(n),
        "ci_lo": float(diff.mean() - 1.96 * se),
        "ci_hi": float(diff.mean() + 1.96 * se),
    }


def save(df: pd.DataFrame, name: str, fmt: bool = True) -> None:
    path = OUT / name
    if fmt:
        df.to_csv(path, index=False, float_format="%.6f")
    else:
        df.to_csv(path, index=False)
    print(f"[saved] {path.relative_to(ROOT)}  rows={len(df)}")


def money(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float) -> str:
    return f"{x:.1%}"
