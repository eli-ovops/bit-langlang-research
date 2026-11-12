# migration_summary.md

## Short Summary

本次 v2 微调基于上一版迁移包，继续保留“通用型 AI 事业转型 + 客户项目交付 + 网站 / 系统 / AI 提效落地总控”主线。

上一版迁移包只读，未修改。新的 v2 上下文文件生成在独立输出目录中。

## 迁移来源

采用的来源目录：

`/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_20260614_092206`

已基于上一版迁移包中的文件微调：

- `CLAUDE.md`
- `PROJECT_STATE.md`
- `TASK_CONTEXT.md`
- `BITLANGLANG_PHILOSOPHY.md`
- `ENGINEERING_RULES.md`
- `RESEARCH_ROADMAP.md`
- `CODEX_PERSONALITY.md`

## 本次做了什么

1. 对 `rewritten_context_files/` 做轻量脱敏，移除具体收入、资金和过度家庭细节。
2. 在 `BITLANGLANG_PHILOSOPHY.md` 顶部增加 `STATUS: ARCHIVED / HISTORICAL ONLY`。
3. 将 30 天目标压缩为两个主目标：一个可展示 Demo、一次淇 / 客户相关可复盘交付。
4. 将云部署、安全学习、客户沟通、SOP 等内容降级为辅助目标，不得挤占主线。
5. 在 `CLAUDE.md` 增加“每天高质量时间有限，默认小步低负担”的任务拆解原则。
6. 在 `TASK_CONTEXT.md` 增加客户沟通要少主题、闲聊建信任、避免一次性推全套能力。
7. 在 `next_steps.md` 增加路径占位符和目标目录存在性提醒。

## Bit浪浪如何被归档

Bit浪浪 / BitLangLang 没有被删除，而是被降级为：

- 历史项目；
- 非当前主线；
- 默认不推进；
- 只在用户明确恢复时才允许只读、离线、非交易研究；
- live / small-live / timer / monitor / scheduler / 账户 / 实盘操作继续禁止。

## 当前主线

当前主线是：

1. 心理疏导、职业与未来规划；
2. 网站开发、腾讯云、服务器部署、域名 / DNS / SSL / HTTPS、基础安全；
3. 与淇的小活协作和真实 case 积累；
4. 本地中小企业客户沟通与获客；
5. 企业官网、库存管理系统、轻量 CRM、小程序、AI 提效工具落地；
6. AI 求职备用路线。

## 后续如何使用

建议先人工检查 `rewritten_context_files/` 内 7 个文件。确认无误后，再备份原上下文文件，并复制替换到目标项目目录。

不要直接覆盖现有项目文件，除非已经人工确认。

## 风险等级

低到中。

原因：

- 本次只生成独立输出目录；
- 未修改原文件；
- 未读取密钥；
- 未访问账户；
- 未启动服务；
- 但内容涉及项目总控迁移，替换前需要人工确认。
