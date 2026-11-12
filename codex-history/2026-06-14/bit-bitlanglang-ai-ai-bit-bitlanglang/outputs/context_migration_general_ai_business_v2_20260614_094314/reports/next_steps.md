# next_steps.md

## 人工检查

先打开并检查：

```bash
open "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314"
```

重点检查：

1. `rewritten_context_files/` 内 7 个文件是否符合当前主线。
2. Bit浪浪是否只是归档，而不是删除。
3. 是否正确表达淇合作、博众家具张总 / 大叔、网站 / 系统 / AI 提效。
4. 是否有不适合长期使用的个人信息。
5. 是否需要再删减或改口吻。

## 替换前备份

如果要把新文件复制到某个目标项目，先备份目标项目原文件。

重要提醒：

- `/path/to/target/project` 是占位符，执行前必须替换为真实项目路径。
- 替换前必须确认目标目录存在。
- 不要直接复制运行示例命令。

示例命令：

```bash
cd "/path/to/target/project"
mkdir -p "context_backup_$(date +%Y%m%d_%H%M%S)"
cp CLAUDE.md PROJECT_STATE.md TASK_CONTEXT.md BITLANGLANG_PHILOSOPHY.md ENGINEERING_RULES.md RESEARCH_ROADMAP.md CODEX_PERSONALITY.md "context_backup_$(date +%Y%m%d_%H%M%S)/"
```

注意：上面命令中的两次 `date` 会生成不同目录名。更稳妥的方式：

```bash
cd "/path/to/target/project"
BACKUP_DIR="context_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp CLAUDE.md PROJECT_STATE.md TASK_CONTEXT.md BITLANGLANG_PHILOSOPHY.md ENGINEERING_RULES.md RESEARCH_ROADMAP.md CODEX_PERSONALITY.md "$BACKUP_DIR/"
```

## 复制替换

人工确认后，再复制替换：

```bash
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/CLAUDE.md" "/path/to/target/project/CLAUDE.md"
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/PROJECT_STATE.md" "/path/to/target/project/PROJECT_STATE.md"
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/TASK_CONTEXT.md" "/path/to/target/project/TASK_CONTEXT.md"
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/BITLANGLANG_PHILOSOPHY.md" "/path/to/target/project/BITLANGLANG_PHILOSOPHY.md"
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/ENGINEERING_RULES.md" "/path/to/target/project/ENGINEERING_RULES.md"
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/RESEARCH_ROADMAP.md" "/path/to/target/project/RESEARCH_ROADMAP.md"
cp "/Users/USER/Documents/Codex/2026-06-14/bit-bitlanglang-ai-ai-bit-bitlanglang/outputs/context_migration_general_ai_business_v2_20260614_094314/rewritten_context_files/CODEX_PERSONALITY.md" "/path/to/target/project/CODEX_PERSONALITY.md"
```

## 让 Codex / Claude 读取新上下文

替换后，在新会话开头使用：

```text
请先读取 CLAUDE.md、PROJECT_STATE.md、TASK_CONTEXT.md、BITLANGLANG_PHILOSOPHY.md、ENGINEERING_RULES.md、RESEARCH_ROADMAP.md、CODEX_PERSONALITY.md，并按其中规则执行。
```

## 建议下一步

1. 先不要替换真实项目文件。
2. 人工读一遍 `rewritten_context_files/`。
3. 如需精简，可先压缩个人隐私和财务描述。
4. 再选择一个目标项目目录做备份替换。
5. 替换后开新会话验证：默认是否变成 AI 事业转型 / 客户项目交付总控。
