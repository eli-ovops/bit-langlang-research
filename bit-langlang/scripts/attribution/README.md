# scripts/attribution —— PnL 归因与反事实（第一性原理①）

不调参、不重跑策略，只对 `data/processed/v2/trades_positions.csv`（4,651 个独立仓位，
规范口径）做归因、尾部/规模分解与算术反事实。腿口径 `trades_legs_dedup.csv`（4,798 腿）
只用于对账。

## 运行（需要 pandas / numpy；图表需要 matplotlib）

```bash
cd scripts/attribution
python3 01_pnl_bridge.py
python3 02_dimension_attribution.py
python3 03_tail_structure.py
python3 04_scale_turnover.py
python3 05_counterfactuals.py
python3 06_robustness.py
python3 07_charts.py
python3 08_export_tables.py
python3 09_market_context.py
# 或 sh run_all.sh
```

## 口径（与 `docs/PnL归因.md` 一致）

| 概念 | 定义 | 备注 |
|---|---|---|
| 仓位 | `trades_positions.csv` 一行 = symbol+入场分钟聚合后的独立仓位 | 4,651；腿 4,798（多腿仓位 0.92%，最多 48 腿） |
| 毛价格盈亏 gross | `Σpnl` | 交割单 `pnl` 字段 = `notional × 方向 × (exit/entry−1)`，**不含手续费**；已在 98.6% 单腿仓位上验证（误差中位 9e-6×notional） |
| 手续费 fee | `Σfee` | 为负=支出；双边 taker ≈ 0.1% 名义（-0.0010 占 61% 的仓位） |
| 净盈亏 net | `pnl + fee` | 本文默认口径 |
| 资金费 funding | `−side × rate × notional × price_t/price_entry`，对 `(entry_utc, exit_utc]` 内的每个结算点求和 | 仅 10 币（BTC/ETH/SOL/DOGE/PEPE→1000PEPE/ORDI/TRB/PEOPLE/WLD/APT）可算，覆盖 2,499 仓位 / 70.7% PnL；估算口径与固定名义口径差 9,536U（约 10%） |
| R | `R_gross = pnl/margin`，`R_net = (pnl+fee)/margin` | = 保证金收益率；交割单 `ret` 字段在多腿/个别行不可靠（与 pnl/margin 相关 0.73），不用于主口径 |
| 时间 | 交割单为北京时间（UTC+8）；资金费时间戳为 UTC ms | 已统一 |

## 已知剔除/异常（全部单列披露，不静默删除）

- YFII 39 行（margin 50 万~4,085 万、notional 最高 2.04 亿，单位/金额错误）已在 v2 剔除；若计入毛 PnL 会 +41,951,400U（×8.59）。
- BNT 1 行缺 `exit_time`（+14,300U）已剔除。
- 6 行 AIDOGE `notional=margin=0`：费用 −363.6U 计入 PnL 桥，R/规模分析剔除（无法算 R）。
- 6 行（腿口径 7 行）`hold_min<0`：净 +14,875U，保留并打标；时长桶因该字段归入 NaN，未进时长表。
- 3 行多腿仓位 `legs` 最大 48，其 `ret` 字段与聚合 pnl 不一致——一律用 pnl/margin。

## 产物

`data/attribution/`：
- `pnl_bridge_*.csv` —— PnL 桥（汇总/逐年/逐月/逐币/对账）
- `dim_*.csv` —— 方向、币种分组、Top10、全币种、时长桶、保证金十分位、R 十分位
- `tail_*.csv` —— 去尾、集中度、分布、时长交叉
- `scale_turnover_*.csv`、`scale_vs_edge_yearly.csv` —— 规模与换手
- `counterfactuals.csv`、`counterfactual_*.csv` —— 反事实与复利曲线
- `key_conclusions_ci.csv`、`multiple_comparison.csv`、`robustness_sensitivity.csv` —— 置信区间与稳健性
- `top_trades.csv` —— 净收益前 30 笔明细
- `market_context_*.csv` —— 月度 PnL vs BTC 涨跌（归因对照，非策略）
- `tables_for_doc.md`、`summary.json` —— 文档表格与汇总
- `figures/*.png` —— 图（可选）

## 方法约束

- 置信区间：按**入场日整群** bootstrap（2,000 次，percentile），t 值亦按日聚类；不做 iid 假设。
- 多重比较：本报告约 22 个独立分组检验，Bonferroni 0.05 对应双侧 |t|≈3.05，已用于结论判定。
- 不构造任何未来函数、不做参数搜索、不回测策略；反事实全部是同一笔序的算术重算。
