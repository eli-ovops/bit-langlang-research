# scripts/entry_exit — 进出场机制的反事实分析（task-7）

结论与证据表见 `docs/进出场机制.md`；产物在 `data/entry_exit/`。
只做**反事实评估**：不调参、不重跑策略、未来数据不进入任何入场规则。

| 脚本 | 作用 | 产物 |
|---|---|---|
| `common.py` | 数据层：时区/对齐（floor）/价格尺度（PEPE 1000×）/MFE-MAE/跟踪止损/按日聚类 bootstrap | — |
| `01_build_panel.py` | 对齐 10 币 5m/1d，算每笔的 MFE/MAE（5m/30m/1h/4h/24h/72h + 到平仓）、平仓后漂移、波动/空间特征 | `trades_panel.csv`, `alignment.json` |
| `02_exit_counterfactuals.py` | 同一入场点的机械出场：固定持有 5m–72h、跟踪止损 1%/2%、持有到平仓 bar 收盘 | `cf_exits.csv` |
| `03_entry_counterfactuals.py` | 同币 ±1 天随机时刻入场（×20 次）× 各出场规则；全样本/同期异币 β；入场时点特征 | `random_entry.csv`, `entry_features.csv` |
| `04_stats.py` | 捕获率、反事实出场/入场、波动-空间选择、alpha 分解、稳健性、多重比较（共 39 个检验） | `tables/T0–T19*.csv`, `tables.md`, `summary.json` |

```bash
cd /Volumes/EXTERNAL/bit浪浪
python3 scripts/entry_exit/01_build_panel.py
python3 scripts/entry_exit/02_exit_counterfactuals.py
python3 scripts/entry_exit/03_entry_counterfactuals.py   # ~30s
python3 scripts/entry_exit/04_stats.py
```

口径：收益单位 = % 价格变动（1R=1%），净 = 扣该笔真实手续费（fee/notional）；
区间 = 按入场日（UTC）聚类 bootstrap 95%CI（2000 次、按笔数加权）+ Liang-Zeger 聚类稳健 t；
去尾 = 剔除该指标最大 5 笔。随机数种子固定（SEED=20261029），结果可复现。
