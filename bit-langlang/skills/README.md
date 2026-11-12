# skills/ —— 本项目可用的外部方法论文库（索引）

> 这些不是自动加载的 Harness skills，而是**资料库索引**：写代码/做研究前按需读对应 `SKILL.md`。
> 上游仓库都在 `vendor/`，此处只做**按用途索引**，不复制内容。

---

## A. 回测与验证（本项目最核心）

| 用途 | 文件 |
|---|---|
| 反过拟合 / "把策略打到死"的方法论、参数稳健性、摩擦成本 | [`vendor/claude-trading-skills-equity/skills/backtest-expert/SKILL.md`](../vendor/claude-trading-skills-equity/skills/backtest-expert/SKILL.md) |
| Walk-forward、purged CV、overfit 检测 | [`vendor/claude-trading-skills/skills/walk-forward-validation/SKILL.md`](../vendor/claude-trading-skills/skills/walk-forward-validation/SKILL.md) |
| VectorBT 完整回测脚本模板 / 优化 / 对比 | [`vendor/vectorbt-backtesting-skills/.claude/skills/backtest/SKILL.md`](../vendor/vectorbt-backtesting-skills/.claude/skills/backtest/SKILL.md) |
| VectorBT 专家（矢量化、指标、成本） | [`vendor/claude-trading-skills/skills/vectorbt/SKILL.md`](../vendor/claude-trading-skills/skills/vectorbt/SKILL.md) |
| Backtrader 回测（事件驱动、逐笔撮合） | [`vendor/claude-trading-skills/skills/backtrader/SKILL.md`](../vendor/claude-trading-skills/skills/backtrader/SKILL.md) |
| 滑点建模 | [`vendor/claude-trading-skills/skills/slippage-modeling/SKILL.md`](../vendor/claude-trading-skills/skills/slippage-modeling/SKILL.md) |
| OHLCV 数据清洗 / 多周期聚合 | [`vendor/claude-trading-skills/skills/ohlcv-processing/SKILL.md`](../vendor/claude-trading-skills/skills/ohlcv-processing/SKILL.md) |
| 信号分类（把主观规则变成可执行标签） | [`vendor/claude-trading-skills/skills/signal-classification/SKILL.md`](../vendor/claude-trading-skills/skills/signal-classification/SKILL.md) |

## B. 市场状态 / 周期（对应"春夏秋冬"）

| 用途 | 文件 |
|---|---|
| 加密市场 regime 识别 | [`vendor/claude-trading-skills-equity/skills/crypto-regime-analyzer/SKILL.md`](../vendor/claude-trading-skills-equity/skills/crypto-regime-analyzer/SKILL.md) |
| 通用 regime 检测（波动聚类、趋势、统计方法） | [`vendor/claude-trading-skills/skills/regime-detection/SKILL.md`](../vendor/claude-trading-skills/skills/regime-detection/SKILL.md) |
| 市场顶部检测 | [`vendor/claude-trading-skills-equity/skills/market-top-detector/SKILL.md`](../vendor/claude-trading-skills-equity/skills/market-top-detector/SKILL.md) |
| 突破交易规划（对应"启动位"） | [`vendor/claude-trading-skills-equity/skills/breakout-trade-planner/SKILL.md`](../vendor/claude-trading-skills-equity/skills/breakout-trade-planner/SKILL.md) |

## C. 风控 / 仓位（对应"分三份、低倍、严格止损"）

| 用途 | 文件 |
|---|---|
| 仓位 sizing 方法大全（固定分数、波动调整、Kelly） | [`vendor/claude-trading-skills/skills/position-sizing/SKILL.md`](../vendor/claude-trading-skills/skills/position-sizing/SKILL.md) |
| 风险预算 / 单笔风险 / 相关性 | [`vendor/claude-trading-skills/skills/risk-management/SKILL.md`](../vendor/claude-trading-skills/skills/risk-management/SKILL.md) |
| Kelly 公式与实操陷阱 | [`vendor/claude-trading-skills/skills/kelly-criterion/SKILL.md`](../vendor/claude-trading-skills/skills/kelly-criterion/SKILL.md) |
| 回撤熔断器（连亏保护） | [`vendor/claude-trading-skills-equity/skills/drawdown-circuit-breaker/SKILL.md`](../vendor/claude-trading-skills-equity/skills/drawdown-circuit-breaker/SKILL.md) |
| 仓位计算器 | [`vendor/claude-trading-skills-equity/skills/position-sizer/SKILL.md`](../vendor/claude-trading-skills-equity/skills/position-sizer/SKILL.md) |
| 期货/合约仓位 | [`vendor/claude-trading-skills-equity/skills/futures-position-sizer/SKILL.md`](../vendor/claude-trading-skills-equity/skills/futures-position-sizer/SKILL.md) |
| 盘前纪律闸门（"不符合逻辑就不开"） | [`vendor/claude-trading-skills-equity/skills/pre-trade-discipline-gate/SKILL.md`](../vendor/claude-trading-skills-equity/skills/pre-trade-discipline-gate/SKILL.md) |

## D. 出场 / 复盘

| 用途 | 文件 |
|---|---|
| 出场策略（止盈、移动止损、保本） | [`vendor/claude-trading-skills/skills/exit-strategies/SKILL.md`](../vendor/claude-trading-skills/skills/exit-strategies/SKILL.md) |
| 单笔复盘模板（signal postmortem） | [`vendor/claude-trading-skills-equity/skills/signal-postmortem/SKILL.md`](../vendor/claude-trading-skills-equity/skills/signal-postmortem/SKILL.md) |
| 交易绩效教练 | [`vendor/claude-trading-skills-equity/skills/trade-performance-coach/SKILL.md`](../vendor/claude-trading-skills-equity/skills/trade-performance-coach/SKILL.md) |
| 交易日志 / 记忆 | [`vendor/claude-trading-skills/skills/trade-journal/SKILL.md`](../vendor/claude-trading-skills/skills/trade-journal/SKILL.md) · [`vendor/claude-trading-skills-equity/skills/trader-memory-core/SKILL.md`](../vendor/claude-trading-skills-equity/skills/trader-memory-core/SKILL.md) |

## E. 策略框架 / 数据接口（备查）

| 用途 | 文件 |
|---|---|
| 策略工程化框架（信号→仓位→风控→执行） | [`vendor/claude-trading-skills/skills/strategy-framework/SKILL.md`](../vendor/claude-trading-skills/skills/strategy-framework/SKILL.md) |
| 特征工程（从 OHLCV 造因子） | [`vendor/claude-trading-skills/skills/feature-engineering/SKILL.md`](../vendor/claude-trading-skills/skills/feature-engineering/SKILL.md) |
| pandas-ta / ta-lib 指标 | [`vendor/claude-trading-skills/skills/pandas-ta/SKILL.md`](../vendor/claude-trading-skills/skills/pandas-ta/SKILL.md) |
| 币价数据（CoinGecko） | [`vendor/claude-trading-skills/skills/coingecko-api/SKILL.md`](../vendor/claude-trading-skills/skills/coingecko-api/SKILL.md) |
| DEX 数据（DexScreener） | [`vendor/claude-trading-skills/skills/dexscreener-api/SKILL.md`](../vendor/claude-trading-skills/skills/dexscreener-api/SKILL.md) |

---

## 使用建议

1. **写回测前**先读 `backtest-expert` + `walk-forward-validation`，把"防自欺"变成代码里的默认检查。
2. **设计仓位**先读 `position-sizing` + `drawdown-circuit-breaker`，把"输无数次仍然活着"量化成风险预算。
3. **实现季节过滤**先读 `crypto-regime-analyzer` + `regime-detection`，再决定用均线代理还是结构代理。
4. **每跑完一轮**用 `signal-postmortem` 的模板把亏损单分类：体系内亏损 / 逻辑错误 / 纪律错误。
