# 04 AlphaFox 平台操作手册与约束

> CLI 根目录：`/Volumes/EXTERNAL/亚力克斯 /AlphaFox研究-20261027/CLI接入-20261029/`（目录名结尾有空格！）
> 可执行：`node_modules/.bin/alphafox`
> 认证：已通过 `alphafox auth login` 存在 OS keychain；**永远不要传 `--token`**。

## 1. 当前订阅与计费状态（2026-10-30 00:53 UTC 实测）

| 项 | 值 |
|---|---|
| 订阅 | **free**（Pro 已于 2026-10-30T00:51:35Z 到期；`currentPeriodEnd` 已过） |
| paperSlots | **0** |
| 运行中的 5 个 paper 策略 | coverage=`included`，reason=`novice_paper_waiver_missing`，**$0.00/h** |
| 钱包 | 0 USDC（未充值） |
| 新开/重启策略 | **可能失败**：无 paper slot → PAYG $0.01/h → 钱包 0 → `insufficient wallet balance for this trader hourly charge` |

**⚠️ 关键：不要随便 stop 代理 A。** 一旦停下，当前 free 订阅可能无法重新 start（需要 slot/余额）。如需停，先向用户确认。

## 2. 命令分层

| 层级 | 例子 | 说明 |
|---|---|---|
| read | `api GET ... --format json --no-input` | 只读，安全 |
| write | `POST ...` 部分 | 一般写 |
| high-risk-write | start/stop/update/create/delete | 需 `--yes`；用户已总体授权，但**先备份、再执行、记录** |

发现命令：`alphafox catalog`（全量操作）、`alphafox schema <operationId>`（请求体 schema）。
官方 skills 文档：`node_modules/@alphafox/cli/skills/`（尤其 `engine-backtest/SKILL.md`、`strategy/SKILL.md`）。

## 3. 常用只读查询

```bash
AF="/Volumes/EXTERNAL/亚力克斯 /AlphaFox研究-20261027/CLI接入-20261029/node_modules/.bin/alphafox"
"$AF" api GET /api/v1/trading/traders --format json --no-input
"$AF" api GET /api/v1/trading/traders/<ID>/runtime --format json --no-input
"$AF" api GET /api/v1/trading/traders/<ID>/positions --format json --no-input
"$AF" api GET /api/v1/trading/traders/<ID>/account-status --format json --no-input
"$AF" api GET /api/v1/trading/traders/<ID>/orders --format json --no-input
"$AF" api GET /api/v1/trading/traders/<ID>/performance --format json --no-input
"$AF" api GET /api/v1/trading/strategy-billing --format json --no-input
"$AF" api GET /api/v1/subscriptions/me --format json --no-input
"$AF" api GET /api/v1/exchange-connectors --format json --no-input
```

## 4. 写操作（high-risk，全部要 `--yes` + 先备份）

### stop（必须带 body！）
```bash
"$AF" api POST /api/v1/trading/traders/<ID>/stop \
  --body '{"closePositions": false}' --yes --format json --no-input
```
- `closePositions=true` 会平掉该策略仓位；false 保留。
- 上次不带 body 报 `body_schema` 错误。

### start
```bash
"$AF" api POST /api/v1/trading/traders/<ID>/start \
  --body '{"expectedCoverageType":"included","enableSLTPMonitoring":true}' \
  --yes --format json --no-input
```
- 槽位满/钱包 0 会 412 `insufficient wallet balance for this trader hourly charge`。

### update trader（改名称/配置/连接器）
```bash
# body = {"name":..., "exchangeConnectorId":..., "configSchemaVersion":4, "config":{common,strategy}}
"$AF" api PATCH /api/v1/trading/traders/<ID> --body @/tmp/body.json --yes --format json --no-input
```
- `configSchemaVersion` 必须与该 trader 当前版本一致（本次为 4）。
- 改配置前先 `GET /traders/<ID>` 拿旧 config，写入备份文件。

### 配置校验（策略定义）
```bash
"$AF" api POST /api/v1/trading/strategy-definitions/<definitionId>/validate-config \
  --body '{"config":{...}}' --format json --no-input
```

### 创建 trader（高风险；当前订阅下大概率失败）
```bash
"$AF" api POST /api/v1/trading/traders --body @/tmp/create.json --yes --format json --no-input
```
需要 `strategyDefinitionId`、`exchangeConnectorId`、config 等；当前无空 slot，**不要尝试**。

## 5. 回测（本地 Engine，免费、零写入）

```bash
"$AF" engine-backtest run \
  --experiment <EXPERIMENT_ID> \
  --definition moving_average_breakout \
  --config @/tmp/config.json \
  --exchange binance \
  --range 2022-05-01..2026-10-25 \
  --initial-equity 2000 \
  --replay-timeframe 1h \
  --data-quality basic \
  --no-persist \
  --format json --no-input
```
- `--no-persist` 零写入；结果在 `data.metrics`。
- 已有 experiment：
  - cta_v1：`01a17d0a-0470-74ff-b4f7-9aa3da4ce63c`
  - moving_average_breakout：`01a17cd5-d2d0-72e3-b53f-8c279301fed4`
  - dca：`01a17cf4-2fd5-7649-8532-6f2a03b46a56`
  - grid：`01a17cef-ec3e-7400-8c9a-af15d6161adc`
- 已知限制：grid 的 planBacktest 可能不支持（会直接报错，不要绕过）。

## 6. 已知坑（踩过的）

1. 目录名 `亚力克斯 ` 结尾空格 → 所有命令加引号。
2. `api` 命令要 `--format json --no-input`；写操作加 `--yes`。
3. stop 必须带 `{"closePositions": bool}`。
4. start 需要空闲 included slot；当前订阅已过期 → 无 slot。
5. update 的 body 必须带 `configSchemaVersion`（4）。
6. 同一 connector 同时只能挂一个活跃 trader；换绑用 `exchangeConnectorId` 字段。
7. `engine-backtest` 缺 `common.execution.leverage` 会被自动填 10x；配置里要显式写。
8. 不要传 `--token`；不要输出账户 ID。
9. 不要创建第 6 个 running paper（会触发付费失败）。
10. 不要把 `strategyDefinitionId` 试图改成别的定义——update 不支持换定义；需要新建 trader。

## 7. 备份与恢复

| 对象 | 备份路径 |
|---|---|
| 被替换的 `ETH 均线突破` 原配置 | `研究-20261029/被替换交易备份-ETH均线突破.json` |
| 代理 A 当前配置 | 本文档 §1 + `研究-20261029/平台回测-代理策略.md` |
| 代理 B（cta_v1）配置 | `/tmp/cta_proxy_config.json`（临时；建议复制进研究目录保存） |
| 冻结 TPH 参数 | `verify/frozen_config.json` 与 `交接包/frozen_config.copy.json` |

**恢复原则**：先读当前 state/config → 写备份 → 再改；每次改动记录到 `研究-20261029/` 下的日志。
