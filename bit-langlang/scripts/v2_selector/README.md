# 选择器研究脚本（task-4）

对应文档：`docs/选择器研究.md`；产物：`data/selector/`。

| 脚本 | 作用 | 主要输出 |
|---|---|---|
| `common.py` | 数据加载、23 个入场可观测特征、目标 A/B/C、numpy 统计工具（AUC/Spearman/按日聚类 t/按日 bootstrap/岭回归/logistic） | — |
| `01_build_features.py` | 构建特征表；覆盖率/时间对齐/缺失审计；"他的交易 vs 同币同期随机时点"选择偏差对比 | `features.csv.gz`、`audit.json`、`selection_bias.csv`、`unconditional_sample.csv.gz` |
| `02_univariate.py` | 23 特征 × 9 目标的单变量检验：Spearman IC、五分位（train 切点固定到 test）、Q5-Q1 按日聚类 t、按日 bootstrap、AUC；登记多重比较次数 | `univariate_ic.csv`、`quintile_summary.csv`、`auc_summary.csv`、`base_rates.csv`、`multiplicity.json` |
| `03_multivariate_rule.py` | 5 特征 logistic / 岭回归（train 拟合、test 一次性）；十分位累计 R；7 条预登记规则；随机选择器基准；按年 walk-forward；目标 C 的币种身份混淆检验 | `model_results.json`、`decile_table.csv`、`rule_results.csv`、`walkforward.csv`、`coin_confound.csv`、`baseline_summary.json` |
| `04_market_oos.py` | 真样本外（2024-07~2026-10 市场口径，非他的仓位）：冻结信号在 10 币日频候选池上的前向 24h/72h 检验 | `market_oos.csv`、`market_uncond.csv` |
| `05_sanity.py` | 防未来函数自检：300 笔随机仓位用原始行情独立重算特征；检查特征 bar 均不晚于入场 | `sanity.json` |

运行顺序：01 → 02 → 03 → 04 → 05。全部确定性（固定随机种子）。

口径要点：
- 日线特征用"最后一条已收盘日线"（等价 shift(1)），5m 只用 `close_time <= entry_utc` 的 bar。
- 主切分：train ≤2023-12-31 / test 2024-01-01~2024-06-20（任务书的 2024-07 切分不可行，因为交割单止于 2024-06-20）。
- 10 币覆盖 2,499/4,651 仓位（53.7%）；选择偏差见文档 §1。
