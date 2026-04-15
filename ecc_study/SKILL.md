# ECC Study — Everything Claude Code 融会贯通

> 来源：`everything-claude-code-main` (1426 .md, 260+ skills, MIT license)
> 落地：`C:\Users\yiseg\.qclaw\workspace/ecc_study/`
> 时间：2026-04-13

## 核心成果（5项，按价值排序）

### 1. instinct-based Learning System ⭐⭐⭐⭐⭐
**来源**：`skills/continuous-learning-v2` + `instinct-cli/instinct-cli.py`

比 evolver 强在哪里：

| 维度 | evolver.py（之前） | instinct-cli.py（ECC） |
|------|-------------------|----------------------|
| 模型 | Rule dataclass（task/method） | YAML instincts（trigger/confidence/domain/scope） |
| 粒度 | 任务级 | 原子行为级 |
| 观察 | 手动 record() | PreToolUse/PostToolUse hook（100%可靠） |
| 项目隔离 | 无 | git remote URL hash → 项目隔离 |
| 自动进化 | 手动 suggest | 聚类 → skills/commands/agents |
| promote 机制 | 无 | 2+项目自动 promote 到 global |
| 命令数 | 2（record/recall） | 6（status/import/export/evolve/promote/projects） |

**关键代码**：`instinct-cli.py`（1700行，完整实现）
**落地文件**：`instinct_model.py`（instinct YAML 格式解析器）

### 2. openclaw-persona-forge ⭐⭐⭐⭐⭐
**来源**：`skills/openclaw-persona-forge`（12KB SKILL + 7KB gacha.py）

完整龙虾灵魂锻造系统：
- **gacha.py**：5维度 × 640万种组合（secrets 真随机）
  - 前世身份（40类）× 动机（20类）× 气质（20类）× 说话风格（20类）× 道具（25类）
- **SKILL.md**：完整6步工作流
  - Step 1：10类方向选择/抽卡
  - Step 2：身份张力锻造
  - Step 3：底线规则推导
  - Step 4：名字生成
  - Step 5：头像提示词
  - Step 6：文件生成
- **references/**：identity-tension / boundary-rules / naming-system / avatar-style / output-template

**落地文件**：
- `gacha.py`（直接可用）
- `persona-forge/SKILL.md`（完整引用）

### 3. autonomous-loops ⭐⭐⭐⭐
**来源**：`skills/autonomous-loops`（24KB，6种模式）

| 模式 | 复杂度 | 核心用途 |
|------|--------|---------|
| Sequential Pipeline | 低 | 每日开发步骤串行化 |
| NanoClaw REPL | 低 | 交互式持久会话 |
| Infinite Agentic Loop | 中 | 并行内容生成 |
| Continuous PR Loop | 中 | 多天迭代项目 + CI |
| De-Sloppify Pattern | addon | TDD 后清理 pass |
| RFC-Driven DAG | 高 | 大特性 + 并行单元 + merge 队列 |

### 4. eval-harness ⭐⭐⭐⭐
**来源**：`skills/eval-harness`（6KB）

Eval-Driven Development（EDD）：
- Capability Evals / Regression Evals
- Grader 类型：Code-Based / Model-Based / Human
- pass@k metrics（典型目标：pass@3 > 90%）
- 与 evolver 互补：evolver 记录失败模式 → eval-harness 验证修复

### 5. context-budget + skill-stocktake ⭐⭐⭐
**context-budget**：审计 token 开销（agents/skills/rules/MCP/CLAUDE.md）
**skill-stocktake**：skill 质量审计（Quick Scan + Full Stocktake + subagent 批量评估）

## 对 qclaw 的价值

| qclaw 系统 | ECC 增强点 |
|-----------|-----------|
| evolver.py | instinct 模型 + 项目隔离 + promote |
| evolver.py | Hook 观察（PreToolUse/PostToolUse → 100%可靠）|
| EVOLVER_DB | instinct registry（projects.json） |
| gacha.py | 抽卡引擎（可用于多维度组合生成）|
| openclaw-persona-forge | 完整龙虾灵魂系统 |
| — | eval-harness（EDD，evolver 验证闭环）|
| — | autonomous-loops（自动化循环模式）|

## 落地清单

```
ecc_study/
├── SKILL.md                         ← 本文件
├── autonomous-loops/SKILL.md         ← 24KB，6种循环模式
├── instinct-cli/
│   ├── SKILL.md                     ← continuous-learning-v2（12KB）
│   ├── instinct-cli.py              ← 完整1700行实现
│   ├── detect-project.sh
│   └── test_parse_instinct.py
├── persona-forge/
│   ├── SKILL.md                     ← 12KB，龙虾灵魂系统
│   ├── gacha.py                     ← 7KB，抽卡引擎
│   └── references/                  ← 5个引用文档
├── gacha.py                         ← 独立副本
├── HERMES-OPENCLAW-MIGRATION.md     ← 迁移指南
└── skills/
    ├── coding-standards.md          ← 12KB，编码规范
    ├── context-budget.md             ← 5KB，token 审计
    ├── eval-harness.md              ← 6KB，EDD 框架
    ├── nanoclaw-repl.md             ← REPL 模式
    └── skill-stocktake.md           ← 7KB，skill 审计
```

## 后续行动

- [ ] 将 instinct 格式集成到 evolver.py（YAML instinct + 项目隔离）
- [ ] 将 gacha.py 集成到 qclaw 工作流
- [ ] 安装 openclaw-persona-forge skill 到 qclaw
- [ ] 研究 eval-harness × evolver 的互补关系

---
*来源：Everything Claude Code（MIT License），整理于 2026-04-13*
