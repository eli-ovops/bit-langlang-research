"""进出场机制反事实分析 — 公共数据层。

口径（全文档一致）：
- 交割单时间 = 北京时间；行情 ts = UTC 毫秒。entry_utc = entry_bj - 8h（已由 独立复核 M4 验证）。
- 仓位主表 data/processed/v2/trades_positions.csv（4651 个独立仓位）。
- 行情 data/market/{coin}USDT_{5m,1d}.csv.gz；10 币可用。
- 价格尺度：PEPE-USDT-SWAP 的价格是 1000PEPEUSDT 的 1/1000，按 log10 中位数取整数幂校准（参数无关）。
- 对齐：floor（入场时间落在哪根 5m K 线内就用哪根），不用 searchsorted 取下一根（避免整体后移 1 根）。
- 反事实里的"未来"数据只用于评估，不进入任何入场规则。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MARKET = ROOT / "data" / "market"
PROC = ROOT / "data" / "processed" / "v2"
OUT = ROOT / "data" / "entry_exit"

# 10 个有行情的币
COINS = ["BTC", "ETH", "SOL", "DOGE", "PEOPLE", "TRB", "WLD", "APT", "ORDI", "1000PEPE"]
SYMBOL_MAP = {f"{c}USDT": c for c in COINS}
SYMBOL_MAP["PEPE-USDT-SWAP"] = "1000PEPE"  # 交割单符号 -> 行情符号
for c in COINS:
    SYMBOL_MAP[f"{c}-USDT-SWAP"] = c

BAR_MS = 5 * 60 * 1000
BARS_PER_HOUR = 12

# 固定持有期（bar 数）
HOLDS = {"5m": 1, "30m": 6, "1h": 12, "4h": 48, "24h": 288, "72h": 864}

# 相对入场日、仅用过去数据的日线特征窗口
PAST_DAYS_SPACE = 20
PAST_DAYS_RANGE = 20

R_UNIT_PCT = 1.0  # 1R = 1% 价格变动（固定单位，不做参数搜索）


# --------------------------------------------------------------------------- #
# 行情
# --------------------------------------------------------------------------- #
def load_market(coin: str, tf: str = "5m") -> pd.DataFrame:
    m = pd.read_csv(MARKET / f"{coin}USDT_{tf}.csv.gz")
    # 统一成 numpy 友好类型
    m["ts"] = m["ts"].astype("int64")
    for c in ("open", "high", "low", "close", "volume", "turnover"):
        if c in m:
            m[c] = m[c].astype("float64")
    return m


def load_positions() -> pd.DataFrame:
    p = pd.read_csv(PROC / "trades_positions.csv", encoding="utf-8-sig")
    p["entry_bj"] = pd.to_datetime(p["entry_time"])
    p["exit_bj"] = pd.to_datetime(p["exit_time"])
    p["entry_utc"] = p["entry_bj"] - pd.Timedelta(hours=8)
    p["exit_utc"] = p["exit_bj"] - pd.Timedelta(hours=8)
    p["entry_ms"] = p["entry_utc"].astype("int64") // 10**6
    p["exit_ms"] = p["exit_utc"].astype("int64") // 10**6
    p["coin"] = p["symbol"].map(SYMBOL_MAP)
    p["s"] = np.where(p["side"] == "空", -1.0, 1.0)
    return p


def price_scale_factor(close_at_entry: np.ndarray, entry_price: np.ndarray) -> int:
    """交割单价格与行情价格的 10 的整数幂差（PEPE 类合约 1000 倍）。"""
    lr = np.log10(close_at_entry / entry_price)
    return int(round(float(np.median(lr))))


# --------------------------------------------------------------------------- #
# 对齐
# --------------------------------------------------------------------------- #
def floor_bar(ts: np.ndarray, t_ms: np.ndarray) -> np.ndarray:
    """返回 t_ms 所在 bar 的下标（ts 为 bar 开盘毫秒，升序）。"""
    return np.searchsorted(ts, t_ms, side="right") - 1


# --------------------------------------------------------------------------- #
# 路径统计
# --------------------------------------------------------------------------- #
def mfe_mae_window(high, low, i0: int, h: int, p0: float, s: float):
    """入场后第 1..h 根 5m 的最大有利/不利偏移（%），按方向归一。

    不含入场 bar（其 high/low 部分发生在入场之前），也不含 h 之后。
    """
    n = len(high)
    a = i0 + 1
    b = min(i0 + h, n - 1)
    if a > b:
        return 0.0, 0.0
    hi = high[a : b + 1].max()
    lo = low[a : b + 1].min()
    fav = s * (hi - p0) / p0 if s > 0 else s * (lo - p0) / p0
    adv = s * (lo - p0) / p0 if s > 0 else s * (hi - p0) / p0
    return 100.0 * fav, 100.0 * adv


def mfe_mae_to_exit(high, low, i0: int, ix: int, p0: float, px: float, s: float):
    """到实际平仓时刻的 MFE/MAE（%）。

    用入场后、平仓 bar 之前的整根 bar 的极值，加上实际平仓价这一点；
    入场 bar 与平仓 bar 的极值都不用（边界信息不完整，方向一致的偏保守）。
    """
    n = len(high)
    a = i0 + 1
    b = min(ix - 1, n - 1)
    pts_hi = -np.inf
    pts_lo = np.inf
    if a <= b:
        pts_hi = high[a : b + 1].max()
        pts_lo = low[a : b + 1].min()
    # 平仓价本身也是一个观测点（在同一价格尺度上）
    pts_hi = max(pts_hi, px)
    pts_lo = min(pts_lo, px)
    if not np.isfinite(pts_hi):
        return 0.0, 0.0
    fav = s * (pts_hi - p0) / p0 if s > 0 else s * (pts_lo - p0) / p0
    adv = s * (pts_lo - p0) / p0 if s > 0 else s * (pts_hi - p0) / p0
    return 100.0 * fav, 100.0 * adv


def forward_vol(close: np.ndarray, i0: int, h: int, past: bool = False):
    """入场时点前后 h 根 5m 的实现波动（%，用 5m log 收益的 sqrt(h) 缩放）。

    事后用量（future）只用于描述他的选择，不进入任何入场规则。
    """
    lr = np.diff(np.log(close))
    n = len(lr)
    if past:
        a = max(0, i0 - h)
        b = i0  # lr[i] = close[i+1]/close[i]，所以 [a,b) 对应 past h 根
    else:
        a = i0
        b = min(n, i0 + h)
    seg = lr[a:b]
    if len(seg) < max(3, h // 4):
        return np.nan
    return 100.0 * seg.std(ddof=1) * np.sqrt(h)


def trailing_stop(open_, high, low, close, i0: int, p0: float, s: float, pct: float, maxh: int):
    n = len(high)
    a = i0 + 1
    b = min(i0 + maxh, n - 1)
    if a > b:
        return np.nan, 0, False, np.nan
    if s > 0:
        peak = np.maximum.accumulate(np.concatenate([[p0], high[a : b + 1]]))
        prev = peak[:-1]
        level = prev * (1.0 - pct)
        cond = low[a : b + 1] <= level
        if not cond.any():
            ret = 100.0 * s * (close[b] - p0) / p0
            return ret, b - a + 1, False, np.nan
        t = int(np.argmax(cond))
        op = open_[a + t]
        fill = op if op < level[t] else level[t]  # 跳空则按更差的 open
        return 100.0 * s * (fill - p0) / p0, t + 1, True, level[t]
    trough = np.minimum.accumulate(np.concatenate([[p0], low[a : b + 1]]))
    prev = trough[:-1]
    level = prev * (1.0 + pct)
    cond = high[a : b + 1] >= level
    if not cond.any():
        ret = 100.0 * s * (close[b] - p0) / p0
        return ret, b - a + 1, False, np.nan
    t = int(np.argmax(cond))
    op = open_[a + t]
    fill = op if op > level[t] else level[t]
    return 100.0 * s * (fill - p0) / p0, t + 1, True, level[t]


# --------------------------------------------------------------------------- #
# 统计工具
# --------------------------------------------------------------------------- #
def cluster_bootstrap_mean(values: np.ndarray, days: np.ndarray, n_boot: int = 2000, seed: int = 7):
    """按日聚类的 bootstrap 均值 95%CI + 聚类稳健 t。

    * 重采样单位 = 入场日（UTC）；bootstrap 每次抽天数、再按抽中日的**原始笔数加权**算均值，
      因此目标量与上面报的逐笔均值一致（不是"日均值的均值"）。
    * t 用 Liang-Zeger 型聚类稳健方差：Var(mean) = Σ_d (S_d − n_d·mean)^2 / N^2 × g/(g−1)。
    """
    ok = np.isfinite(values)
    values = np.asarray(values, dtype=float)[ok]
    days = np.asarray(days)[ok]
    if len(values) == 0:
        return dict(n=0, mean=np.nan, ci_lo=np.nan, ci_hi=np.nan, t=np.nan, n_days=0)
    uniq, inv, counts = np.unique(days, return_inverse=True, return_counts=True)
    day_sum = np.bincount(inv, weights=values)
    day_cnt = counts.astype(float)
    N = float(len(values))
    mean = float(values.mean())
    g = len(uniq)
    resid = day_sum - day_cnt * mean
    var = float((resid**2).sum() / N**2)
    if g > 1:
        var *= g / (g - 1)
    se = np.sqrt(var)
    t = mean / se if se > 0 else np.nan
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, g, g)
        boots[i] = day_sum[pick].sum() / day_cnt[pick].sum()
    return dict(
        n=int(len(values)),
        mean=mean,
        median=float(np.median(values)),
        ci_lo=float(np.percentile(boots, 2.5)),
        ci_hi=float(np.percentile(boots, 97.5)),
        t=float(t),
        n_days=int(g),
        boot_std=float(boots.std(ddof=1)),
    )
