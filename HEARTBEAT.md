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
4. **系统状态** → gateway 状态 / 磁盘空间 / 最近错误日志
5. **系统洞察** → `qclaw_insights.get_quick_summary()` — evolver 规则/工具使用统计
5. **自我复盘** → 运行 heartbeat_self_review.py，有输出则提醒小谷

## 状态记录

记录在 `memory/heartbeat-state.json`，格式：
```json
{
  "lastReminded": "2026-04-05",
  "lastMemoryMaint": "2026-04-05",
  "lastTodoCheck": "2026-04-05"
}
```

## 规则

- 早上8-22点执行（晚间不打扰）
- 每次心跳只执行一项，轮转进行
- 有重要发现才通知小谷，否则沉默（HEARTBEAT_OK）

## 🔴 红线：磁盘管理（2026-05-17）

**永远不要操作磁盘的管理和磁盘内容的更改。** 包括但不限于：
- 不删除磁盘上的文件（除 workspace 内明确限定的：_deprecated/、_download/、临时 _tmp*）
- 不修改磁盘分区、格式化、清理系统文件
- 不操作 C/D/E/F 盘的系统目录内容
- 不执行磁盘清理工具（cleanmgr、disk cleanup 等）
- 每日零点任务的"清理"仅限 workspace 内的文件索引，不涉及磁盘层面操作
