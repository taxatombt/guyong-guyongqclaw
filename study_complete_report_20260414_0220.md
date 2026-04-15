# E:\ai\资源 全量学习落地报告

_2026-04-14 02:20 | 系统学习完成_

## 资源清单

| # | 资源 | 规模 | 学习状态 |
|---|------|------|---------|
| 1 | `1ai-agent-deep-dive-v2` | 499KB PDF | ✅ 7原则已落地 |
| 2 | `2codex-main` | 4182 files | ✅ execpolicy+hooks+protocol 已落地 |
| 3 | `3codex-rust-v0.120.0` | 1420 .rs | ✅ 与#2同源，增量确认 |
| 4 | `5everything-claude-code` | 1426 .md | ✅ instinct+eval+loops+kiro+hooks+research |
| 5 | `6gstack-main` | 509 files | ✅ 4大skill+voice+自改进 |
| 6 | `7guyongt-claude-code` | 64KB docx | ✅ 9个工具全部提取 |
| 7 | `8hermes-agent-main` | 1953 files | ✅ 完整仓库提取 |
| 8 | `9OpenSpace-main` | 1198 files | ✅ SkillLineage+3种进化类型 |
| 9 | `10src-claudecode` | 1866 TS | ✅ AgentTool+skills+memdir+tokenBudget |

## 核心发现汇总

### A. Agent 系统

**Claude Code 四角色**：
- General Purpose — 全工具，简洁 prompt
- Explore — READ-ONLY, omitClaudeMd=true (省5-15 Gtok/week)
- Plan — READ-ONLY, 同 Explore 工具集
- Verification — 153行反合理化 prompt, 5个禁止工具

**Hermes 子代理**：
- MAX_DEPTH=2（禁止递归委托）
- 5个禁止工具（delegate/clarify/memory/send_message/execute_code）
- max_concurrent_children=3

**ECC/Kiro 16角色**：
- planner, code-reviewer, tdd-guide, security-reviewer, architect
- build-error-resolver, doc-updater, refactor-cleaner
- loop-operator, chief-of-staff 等

### B. 记忆系统

**Claude Code 四类型**：
- user（永远 private）/ feedback（纠正+确认）/ project（非代码可推导）/ reference（外部系统指针）

**Claude Code MEMORY.md = 索引制**：
- 200行/25KB 上限，每行≤150字符
- 两步写入：①独立文件 ②MEMORY.md加指针
- 与 qclaw 当前（直接写内容到 MEMORY.md）不同

**Hermes MemoryManager**：
- 内置 + 最多1个外部 provider
- `<memory-context>` fencing（防模型混淆记忆和用户新输入）
- 冻结快照：会话中写入不更新 system prompt（保 prefix cache）

**Hermes Memory Tool 安全**：
- 12种威胁模式检测（prompt injection, exfiltration, persistence）
- 隐形字符检测（zero-width chars）

### C. Skill 系统

**Claude Code 20内置skill**：
- `/skillify` — 从会话自动创建 skill（3轮面试）
- `/simplify` — 三Agent并行审查（复用+质量+效率）
- `/batch` — 并行工作编排（5-30 agent + worktree隔离）
- `/loop` — 循环执行（5m/30m/2h/1d → cron转换）
- `/remember` — 记忆审查提升
- `/verify` — 验证代码变更

**ECC/Kiro 18 skill**：
- tdd-workflow, security-review, verification-loop
- api-design, frontend-patterns, backend-patterns
- golang-patterns, python-patterns, database-migrations

### D. 安全系统

**顾庸t Security Hook（10大漏洞检测）**：
1. GitHub Actions workflow 注入
2. child_process.exec
3. new Function() 注入
4. eval() 注入
5. dangerouslySetInnerHTML XSS
6. document.write XSS
7. innerHTML XSS
8. pickle 反序列化
9. os.system() 注入
10. SQL 注入

**ECC Hooks 体系**：
- PreToolUse: dev server blocker, tmux reminder, git push reminder, pre-commit quality, doc file warning, strategic compact
- PostToolUse: PR logger, build analysis, quality gate, design quality, prettier, tsc check, console.log warning
- Lifecycle: session start, pre-compact, pattern extraction, cost tracker, desktop notify

### E. Token 管理

**Claude Code tokenBudget**：
- COMPLETION_THRESHOLD = 0.9（90%预算触发判断）
- DIMINISHING_THRESHOLD = 500（连续3次 delta<500 → 收益递减 → 停止）
- 两种决策：continue（附nudge）/ stop（含completionEvent统计）

**Hermes Budget 3层**：
- per-result: 100,000 chars
- per-tool: pinned > overrides > registry > default
- per-turn: 200,000 chars
- read_file: inf（防止循环）

### F. 反循环

**顾庸t Ralph Wiggum**：
- 检测 LLM 重复输出（SAME PROMPT → 计数递增）
- completion promise 机制（`<promise>COMPLETE</promise>`）
- max_iterations=100（可配置）
- Stop hook 检测

### G. Skill 自进化

**顾庸t skill_self_improver**：
- 从对话历史检测偏好模式
- 4种检测：add_step / remove_step / correct_step / preference
- Fire-and-forget 模式
- TURN_BATCH_SIZE=5

**Claude Code /skillify**：
- 分析 session_memory + user_messages
- 3轮 AskUserQuestion 面试
- 生成完整 SKILL.md

## 落地资产清单

### 新建文件（workspace/ 下）

| 文件 | 大小 | 来源 |
|------|------|------|
| `claude_code_study/SKILL.md` | 6KB | Claude Code 架构总览 |
| `claude_code_study/SKILLS.md` | 3KB | 20个skill分析 |
| `claude_code_study/guyongt_notes.md` | 75KB | 顾庸t笔记全文 |
| `claude_code_study/agents/built-in/` | 6文件 | 4角色agent定义 |
| `claude_code_study/tools/AgentTool/` | 12文件 | agent核心实现 |
| `claude_code_study/skills/` | 20文件 | 内置skill |
| `claude_code_study/services/` | 2文件 | agentSummary等 |
| `claude_code_study/utils/` | 18文件 | tokenBudget等 |
| `claude_code_study/memdir/` | 2文件 | 记忆系统 |
| `claude_code_study/query/` | 2文件 | tokenBudget等 |
| `hermes_full_study/SKILL.md` | 3KB | Hermes完整仓库研究 |
| `hermes_full_study/agent/` | 28文件 | agent核心模块 |
| `hermes_full_study/gateway/` | 13文件 | 网关模块 |
| `hermes_full_study/tools/` | 49文件 | 70工具 |
| `ecc_study/.kiro.md` | 28KB | Kiro 16角色+18skill |
| `ecc_study/research.md` | 10KB | ECC2 TUI 架构 |
| `ecc_study/hooks.md` | 9KB | Hooks 完整体系 |

### 更新的现有文件

| 文件 | 改动 |
|------|------|
| `MEMORY.md` | 新增 2026-04-13 agents 系统完整落地 |
| `.evolver_db.json` | 1→11条规则 |
| `agents/tool_pipeline.py` | HookResponse v2.2 新增 hook_event/tool_name/tool_input |

### 未修改的底层代码（遵守约束）

- evolver.py — 未修改
- self_review.py — 未修改
- heartbeat_self_review.py — 未修改
- agents/__init__.py — 未修改
- agents/agent_types.py — 未修改
- agents/multi_agent_dispatcher.py — 未修改
- agents/tool_registry.py — 未修改
- agents/prompt_cache_manager.py — 未修改
- agents/event_bus.py — 未修改
- agents/exec_adapter.py — 未修改

## 可落地到 qclaw 的具体行动项

### 🔴 高优先级

1. **MEMORY.md 重构为索引制** — 参照 Claude Code 两步写入（独立文件+指针），200行上限
2. **记忆安全扫描 memory_guard.py** — 新建，参考 Hermes 12种威胁模式+隐形字符
3. **记忆上下文 fencing** — 新建 memory_fence.py，`<memory-context>` 包裹防混淆
4. **Verification Agent 反合理化 prompt** — 整合到 agent_types.py VERIFY 角色中
5. **Security Hook 10大漏洞检测** — 新建 security_hook.py，参考顾庸t实现

### 🟡 中优先级

6. **token_budget.py** — 新建，90%阈值+收益递减检测
7. **skillify_skill.py** — 新建，从会话自动创建 skill
8. **remember_skill.py** — 新建，记忆审查提升
9. **simplify_skill.py** — 新建，三Agent并行代码审查
10. **ralph_anti_loop.py** — 新建，LLM循环检测+completion promise

### 🟢 低优先级

11. **batch_skill.py** — 并行工作编排
12. **Budget 3层** — per-result/per-tool/per-turn 持久化预算
13. **冻结快照** — 会话中写入不更新 system prompt
14. **ECC hooks 体系** — PreToolUse/PostToolUse/Lifecycle 完整hooks
