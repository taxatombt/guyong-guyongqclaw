# SKILL-superpowers.md — Superpowers 技能框架学习笔记

> 来源：https://github.com/obra/superpowers（219,981⭐）
> 整理：顾庸 | 2026-06-07

## 核心方法论

Superpowers 是一套完整的 AI Agent 软件开发方法论，不只是一个技能库。

### 工作流（7步）

```
brainstorming → design spec → writing plans → subagent-driven-development → TDD → code review → finish branch
```

1. **brainstorming**：不急着写代码，先问清楚要做什么，分块确认设计
2. **using-git-worktrees**：设计确认后，创建隔离工作区+新分支
3. **writing-plans**：拆任务（2-5分钟/个），每个任务有精确文件路径+完整代码+验证步骤
4. **subagent-driven-development**：每个任务分派独立子Agent，两阶段审查
5. **test-driven-development**：RED-GREEN-REFACTOR 循环强制
6. **requesting-code-review**：按计划审查，严重问题阻断进度
7. **finishing-a-development-branch**：验证测试→合并/PR/保留/丢弃

### 关键设计

| 概念 | 说明 |
|------|------|
| Subagent-Driven Development | 每个任务=独立子Agent，两阶段审查（spec合规→代码质量）|
| TDD 强制 | 先写测试→看它失败→写最小代码→看它通过→提交 |
| 验证文化 | verification-before-completion，验证后才能声明完成 |
| 可组合技能 | 12个独立技能，按需触发，不强制全用 |
| YAGNI + DRY | 不写用不到的代码，不重复 |

### 技能列表（12个）

**Testing**: test-driven-development
**Debugging**: systematic-debugging, verification-before-completion
**Collaboration**: brainstorming, writing-plans, executing-plans, dispatching-parallel-agents, requesting-code-review, receiving-code-review, using-git-worktrees, finishing-a-development-branch, subagent-driven-development
**Meta**: writing-skills, using-superpowers

## 对 qclaw 的落地建议

### 🔥🔥🔥 立即可用

1. **Subagent 模式**：用 `sessions_spawn` 实现，每个复杂任务拆成子任务分派
2. **验证文化**：强化"汇报前必须验证"（已在 SOUL.md）
3. **TDD for Skills**：写 SKILL.md 前先定义测试用例

### 🔥🔥 考虑后续

4. **Systematic Debugging**：4阶段根因分析落地到 qclaw
5. **Writing Plans**：复杂任务拆分模板（2-5分钟/任务粒度）

### 与 qclaw 已有系统的关系

| Superpowers | qclaw 对标 |
|-------------|-----------|
| subagent-driven-development | sessions_spawn + subagents |
| TDD | SOUL.md 已有原则，未落地 |
| verification-before-completion | 2026-05-09 假汇报教训 |
| writing-plans | AGENTS.md 决策树（简化版）|
| systematic-debugging | 未落地 |
| using-git-worktrees | 未落地（单机环境）|
