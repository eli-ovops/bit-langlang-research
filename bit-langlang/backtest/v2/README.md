# backtest/v2 —— bit浪浪 风格策略 v2（预判式承接 + 假突破反转）

> 一句话：**只做多、只在 BTC 日线"季节"允许时、等价格回到支撑区域、5m 出现止跌反转才进；
> 5m 结构止损（1–2%）、T1=3R 减半、剩余 5m 摆动低点跟踪、最长 14 天；成本按 0.05%/边 +
> 0.03~0.08% 滑点 + 资金费。**

结论（详见 `docs/v2-回测报告.md`）：**v2 仍然亏损，未通过 G1/G2**。本目录保留可复现的
完整实验，包括"为什么不行"的诊断。

---

## 1. 快速复现

```bash
cd /Volumes/EXTERNAL/bit浪浪
export PYTHONPATH=$PWD

# 样本内（可反复跑；结构选择/改 bug 只能在这一段）
python3 -m backtest.v2.run --split is

# 归因表（读 trades CSV）与诊断（只用 IS 入场集，不接触 OOS）
python3 -m backtest.v2.analyze
python3 -m backtest.v2.diagnostics

# 防未来函数自检（S1–S9 全部应 PASS）
python3 -m backtest.v2.sanity --split is

# 样本外：只跑一次（脚本要求显式确认；报告里的 OOS 就是这一次的输出）
python3 -m backtest.v2.run --split oos --allow-oos
```

结果写入 `data/backtest_v2/`：

| 文件 | 内容 |
|---|---|
| `trades_{is,oos}.csv` | 每笔信号（含 stop_pct / gross_R / cost_R / net_R / setup / season / BTC 上下文） |
| `portfolio_trades_{split}_{tier}.csv` | 通过并发约束的实际成交（含 notional / pnl / equity） |
| `equity_mtm_{split}_{tier}.csv` | 组合日终 MTM 权益 |
| `summary.json` | 全部指标 + G1/G2/G3/G4 判定（含 v1 基线） |
| `summary_symbols_{split}_{tier}.csv` | 逐币指标 |
| `monthly_{split}_{tier}.csv` | 月度 net_R / pnl |
| `v1_vs_v2.csv` | v1 vs v2 对照 |
| `analysis_{split}_*.csv` | 归因（币/年/月/setup/季节/BTC 状态/成本分解） |
| `diagnostics.json` | 入场路径统计 + 出场几何 what-if（IS only，非交付配置） |
| `sanity_{split}.txt` | 未来函数 / 数据一致性自检 |
| `tables/*.md` | 报告用的 markdown 表格（自动生成） |
| `figs/*.png` | 权益+回撤曲线、R 分布、持仓分布 |

---

## 2. 规则（冻结，不可用 OOS 调）

| 层 | 实现 | 依据 |
|---|---|---|
| 方向 | **只做多** | 任务书；一手问答 N7/p21 |
| 季节 | BTC 日线：`close > EMA50 且 EMA50 5 日上行 且 close > EMA200`，**shift(1)** | 规格 §2.1 Spring/Summer 代理 |
| 标的趋势 | 标的自身日线 `close > EMA50`（shift(1)）——IS 二选一结构项，ON 优于 OFF | 防"大盘向上、个股下跌"的接刀 |
| 支撑 | 前 10 日低 / 前 20 日低 / 前 24h 低；价格**仍在支撑上方 0.4%~1.85%**（预判式承接） | 规格 §2.3；交割单洞察 §4"止损 1–2%" |
| 扳机 | 5m：A 假突破收回（近 4 根刺破支撑≥0.2% 后收回）或 B 承接止跌（阳线+收盘高于前收+收在当根上半区） | 一手问答 p6/p7/p10 |
| 不追突破 | 信号根不创前 20 根 5m 新高；前 6 根累计涨幅 <2% | 一手问答"尽量不做突破" |
| 止损 | 5m 摆动低点（前 5 根最低）/ 支撑 L 取更深者，下方 `max(0.15%, 0.3×ATR14)`；距离 ∈ [0.3%, **2%**] | 规格 §2.5；任务书 |
| 空间 | 到最近日线阻力（前 20/60/120 日最高）≥ **5%** | 交割单洞察"5~65% 振幅贡献全部利润" |
| 止盈 | **T1 = 3R 减半**；剩余止损推保本，再用 5m 摆动低点跟踪；**最长 14 天，无 8h 时间止损** | 任务书；交割单洞察 §4 |
| 成交 | 信号 5m 收盘后**下一根开盘**市价；同根 bar 先判止损再判 T1（保守） | 规格 §3.2 |
| 成本 | taker 0.05%/边 + 滑点 0.03%(BTC/ETH) / 0.08%(山寨) + 资金费逐次累计（单次 \|rate\|>0.3% 截断） | 任务书；规格 §7.6 |
| 组合 | 最多 3 笔并发，满仓跳过；逐笔风险 = 权益的 1.5% / 3.3%；杠杆上限 BTC/ETH 10×、山寨 5× | 任务书；一手问答 N4/N7 |
| 初始资金 | 2000 USDT | 规格 §7.5 |

### 关于"止损 5m 摆动低点下方"的两种读法

| 读法 | 含义 | 止损距离（中位） | 单笔成本 | IS 期望（2850/3843 笔） |
|---|---|---|---|---|
| **above_support（交付）** | 价格**尚未到**支撑、仍在支撑上方 0.4–1.85% 时预判承接 | 1.30% | 0.21R | **-0.28R** |
| at_support（字面） | 价格**已经跌到**支撑处/轻微跌穿后收回 | 0.90% | 0.30R | -0.37R |

选择 `above_support` 的理由（IS 一次性、非网格）：只有它能让任务书的三条约束同时成立——
止损距离能进入 1–2%（"硬上限 2%"才有意义）、3R 目标≈4.5% 才与"到阻力≥5%"自洽、
24–72h 持有期才有意义。两种读法的 IS 结果都记录在 `diagnostics.json`。

---

## 3. 代码结构

```
backtest/v2/
├── config.py       冻结参数（含依据注释）
├── dataio.py       行情/资金费只读加载（naive UTC）
├── features.py     日线结构（全部 shift(1)）、季节、5m ATR/摆动低点
├── engine.py       信号扫描 + 逐笔撮合（唯一策略实现）
├── portfolio.py    并发上限、两档风险、杠杆上限、MTM 权益
├── metrics.py      逐笔/权益/去尾/成本占比/连亏、G1–G4 判定
├── run.py          IS/OOS 入口（OOS 需 --allow-oos）
├── analyze.py      归因表（读 trades CSV）
├── diagnostics.py  IS-only 解释性诊断（不用于调参）
├── sanity.py       S1–S9 防未来函数/一致性自检
└── utils.py        markdown 表格（不依赖 tabulate）
```

---

## 4. 诚实边界

- 这是**回测**，不是实盘；没有考虑盘口深度、标记价格插针、交易所故障、限频。
- 2022 全年与 2024-07 后 OOS 由 BTC 季节过滤自然空仓/低频，**样本量小**，统计意义有限。
- 4808 笔真实交割单显示他 36.5% 做空、中位持仓 7 分钟；本 v2 只做多、持有期更长，
  是"规则蒸馏版"而非逐笔复刻。
- 参数全部一次冻结，**没有做参数扫描**；IS 只做了 1 个二值结构选择（标的日线趋势 ON/OFF）。
