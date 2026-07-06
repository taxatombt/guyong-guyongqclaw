# HEARTBEAT.md

# 心跳轮转任务清单（每次心跳执行一项）

## 核心原则（2026-04-05 更新）

**记忆系统 = 基础设施**：不是存储，是人格连续性的骨架
- MEMORY.md = 长期记忆（精华）
- memory/ = 工作记忆（可丢弃的中间状态）
- HEARTBEAT.md = 自动归档协议（Progressive Disclosure）

**Progressive Disclosure**：上下文是预算，按需渐进展开

**记忆只存不可推导的知识**（Claude Code 原则）：
- 能从代码/文件 grep 到的 → 不存
- 能从 git log 看到的 → 不存
- 只存：决策、偏好、教训、不可重复的信息
- 原因：存了反而有过时风险

**融会贯通落地（2026-04-05）**：
- evolver.py v2：规则引擎 + 熔断器 + Compaction
- KNOWLEDGE.md：今晚新增 Agent Harness 体系（PraisonAI / OpenLIT / DeerFlow 2.0 / Claude Code 源码解析）
- Superpowers：TDD for skills + CSO 描述优化 + Rationalization Defense

## 轮转任务

1. **记忆维护** → 检查 memory/ 日期文件，更新 MEMORY.md（精华提取）
2. **Evolver 检查** → 问 evolver 今天学到了什么
3. **待办追踪** → 检查 memory/heartbeat-state.json 中的待办
4. **系统洞察** → `qclaw_insights.get_quick_summary()` — evolver 规则/工具使用统计
5. **自我复盘** → 运行 heartbeat_self_review.py，有输出则提醒小谷

⚠️ **系统状态检查已删除**（2026-07-02）：不再检查磁盘空间、gateway 状态、错误日志。用户明确要求不管磁盘。
⚠️ **Blender 安装已删除**（2026-07-06）：用户明确说永远不需要安装 Blender，从所有待办中移除。

## 状态记录

记录在 `memory/heartbeat-state.json`，格式：
```json
{
  "lastReminded": "2026-04-05",
  "lastMemoryMaint": "2026-04-05",
  "lastTodoCheck": "2026-04-05"
}
```

## 变化检测（2026-06-25 新增）

**核心原则：只有发现新变化才执行，否则直接 HEARTBEAT_OK**

每次心跳开始前，必须检查：
1. `memory/heartbeat-state.json` 的 `updatedAt` 字段
2. 距离上次执行是否 **超过 4 小时**（避免频繁执行）
3. 是否有 **新文件/新变化**（memory/ 新增日期文件、git 有新 commit、错误日志有新条目）

**如果以上全部为「否」→ 直接回复 HEARTBEAT_OK，不执行任何任务。**

## 轮转逻辑（修正 2026-06-25）

**问题**：之前每次心跳都执行全套任务，造成循环和噪音。

**修正后**：
- 使用 `lastTask` 字段记录上次执行的任务
- 下次心跳执行「下一个任务」（按顺序轮转）
- 每次只执行 **一项**，不全套执行
- 执行完后更新 `lastTask` 和对应时间戳

轮转顺序：memory_maintenance → evolver_check → todo_check → insights_check → self_review → (回到 memory_maintenance)

⚠️ system_check 已删除（2026-07-02）：不再执行系统状态检查。

## 规则

- 早上8-22点执行（晚间不打扰）
- **每次心跳只执行一项**，轮转进行（见上方「轮转逻辑」）
- **只有发现新变化才执行**，否则直接 HEARTBEAT_OK（见「变化检测」）
- 有重要发现才通知小谷，否则沉默（HEARTBEAT_OK）
- 输出内容简洁，避免冗长的分析过程

## 🔴 红线：磁盘管理（2026-05-17 强化，2026-07-02 用户再次确认）

**永远不要操作磁盘的管理和磁盘内容的更改。** 包括但不限于：
- 不删除磁盘上的文件（除 workspace 内明确限定的：_deprecated/、_download/、临时 _tmp*）
- 不修改磁盘分区、格式化、清理系统文件
- 不操作 C/D/E/F 盘的系统目录内容
- 不执行磁盘清理工具（cleanmgr、disk cleanup 等）
- 每日零点任务的"清理"仅限 workspace 内的文件索引，不涉及磁盘层面操作
- **🔴 2026-07-02 新增：零点任务不再审查磁盘、不许审查磁盘、不许处理磁盘**
- **🔴 2026-07-06 强化：磁盘监控永远不需要。不主动检查磁盘空间。**
- **🔴 2026-07-06 强化：Blender 永远不需要安装，从待办中移除。**
