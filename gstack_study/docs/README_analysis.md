# gstack-main 详细分析笔记

## 项目元数据

- **作者**: Garry Tan（YC President & CEO）
- **Stars**: 135k+（持续增长）
- **定位**: AI 软件工厂，一个人 + gstack = 一支工程团队
- **核心哲学**: "Boil the Lake" — AI 让完整性成本趋近于零

## 与之前学的项目关系

```
Superpowers (clawhub)     → gstack 的 skill 格式 + 评测思路（子集）
Hermes Agent             → gstack 的多 Agent 协调 + 记忆管理（部分重叠）
Claude Code               → gstack 的底层引擎（使用 Claude Code 执行 skill）
guyong-juhuo             → 认知架构，gstack 的底层思考引擎
gstack                   → 完整的产品工厂 = 以上所有 + Garry 的工程判断
```

## 最值得学习的 3 个设计

### 1. Persistent Daemon（比 skill 格式更重要的架构）
- Playwright 3-5 秒冷启动 → ~100ms 持久化
- Cookie/tab/login 跨命令保持
- 对 QA 测试、多步骤流程革命性提升

### 2. Skill 路由（CLAUDE.md / AGENTS.md）
- 用户意图 → Skill 自动分发
- 不靠猜测，靠规则匹配
- OpenClaw 的 AGENTS.md 可以直接借鉴这个模式

### 3. 多专家 Review（review/specialists/）
- 6 个专家角色，分工审查
- 每个专家有独立 checklist
- JSONL 输出格式，易于聚合分析

## 落地优先级

| 优先级 | 内容 | 难度 | 价值 |
|--------|------|------|------|
| P0 | 原子写 + 健康检查（替代 PID） | 低 | 高 |
| P0 | AGENTS.md Skill 路由规则 | 低 | 高 |
| P1 | office-hours 6追问法 | 低 | 高 |
| P1 | investigate 4阶段调试 | 低 | 高 |
| P2 | review 多专家格式 | 中 | 中 |
| P2 | Retro 3维度框架 | 低 | 中 |
| P3 | Browser Daemon（需 Playwright） | 高 | 高 |

## 未深入的内容（后续可继续）

- `autoplan/SKILL.md` (75KB) — 自主规划核心逻辑
- `scripts/resolvers/` — 7个 skill 解析器实现
- `design-review/` — 设计评审 skill
- `cso/` — 安全审计（OWASP+STRIDE）
- `browse/src/server.ts` (102KB) — Daemon 完整实现
