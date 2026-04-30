---
name: managed-agents-study
description: >
  Anthropic Managed Agents 架构研究落地包。
  包含 Session/Harness/Sandbox 分离的实现、MCP+Skills 渐进式披露、Subagent 通信协议、exec 凭证隔离。
  适用：理解"手脑分离"架构、设计多智能体系统、加固安全隔离。
version: 1.0.0
tags: [agent-architecture, mcp, skills, sandbox, subagent, session]
---

# Managed Agents 架构研究

## 背景

Anthropic 在 2025 年初发布 Managed Agents，提出"手脑分离"三层架构：
Session（外置记忆）、Harness（决策大脑）、Sandbox（执行双手）。

核心洞察：**虚拟化 Agent 组件，让接口比实现活得久。**

## 三层架构

### Session — 外置记忆体

append-only 事件日志，Harness 通过 `getEvents()` 按需读取。
- 不丢数据（Storage 持久性）
- Harness 决定怎么给模型看数据（Context 策略分离）
- 长程任务、断点续传、审计日志

### Harness — 可替换的编排大脑

无状态，通过 `wake(sessionId)` 从 Session 恢复执行。
- 本质是对模型能力不足的补偿性假设
- 模型升级后，补偿逻辑可能变成技术债
- 托管 Harness 价值：维护成本转移给最清楚模型能力边界的人

### Sandbox — 降维成工具接口

`execute(name, input) → string` 标准接口。
- 凭证在 Vault，不在 Sandbox
- 推理可在 Sandbox 就绪前开始（TTFT 下降 60-90%）

## MCP + Skills 体系

### MCP（Model Context Protocol）

定位：标准化连接层 = USB。
- 解决"够得着"外部资源的问题
- 不解决"知道怎么做"的问题

### Skills（渐进式披露）

定位：领域知识封装 = 操作手册。

三层加载：
1. **Metadata**（~100 token）：name + description，启动时扫描
2. **SKILL.md 主体**（~1-5k token）：按需加载完整指令
3. **附加资源**（脚本/文档）：执行时按需访问

效果：上下文从 16k → 500 token（按需触发）。

## 三层上下文体系（Claude Code 核心设计）

1. **持久层（Session）**：append-only JSONL，永不丢数据，支持 positional slicing
2. **管理层（Compact）**：4种压缩策略（Auto/Micro/Reactive/Snip），Feature Gate 控制
3. **视图层（Context Window）**：LLM 实际看到的变换视图，token 预算控制

关键：Session ≠ Context Window。Session 是完整的执行事实流，Context Window 是它的一个变换视图。

## Harness 6大模块（大厂实践总结）

| 模块 | 核心动作 | 来源 |
|------|---------|------|
| 上下文工程 | Write/Select/Compress/Isolate | Claude Code |
| 记忆和状态管理 | 检查点 + Session 生命周期 | Claude Code |
| 工具和任务编排 | 精选工具集 + 先想后做 | Vercel/Manus |
| 验证护栏 | 确定性约束 + 校验 + 恢复 | Claude Code/Google |
| 评估和观测 | 追踪 + 验收 + 归因 | 通用 |
| 人类接管 | HITL gate（decide/escalate） | CMA API |

## 落地文件

| 文件 | 作用 |
|------|------|
| `session_vault.py` | Session 外置持久化 + getEvents() + wake() |
| `skill_metadata.py` | 技能元数据层 + 渐进式披露（3层） |
| `subagent_protocol.py` | Subagent 通信协议 + 结果压缩 |
| `exec_isolation.py` | Sandbox 凭证隔离（Vault→inject→strip） |
| `context_layers.py` | 三层上下文体系（持久→压缩→视图） |
| `harness_modules.py` | Harness 6大模块完整实现 |
| `workflow_patterns.py` | Anthropic 5种Workflow + Agent模式 |
| `run_all.bat` | 一键验证脚本 |

## 落地原则

1. **假设会过时**：补偿逻辑隔离在可替换模块中
2. **安全依赖架构而非规则**：凭证和不可信代码物理隔离
3. **上下文管理独立**：记忆存储 vs 记忆使用分离

## 演进线（Harness Engineering）

2022-2024: Prompt Engineering（表达问题）
2025: Context Engineering（信息量问题）
2026: Harness Engineering（执行问题）

Prompt ⊂ Context ⊂ Harness

## 大厂实践对照

| 公司 | 架构 | 关键教训 |
|------|------|----------|
| Anthropic | Planner+Generator+Evaluator | 上下文焦虑是真实存在的；Harness 假设会过时 |
| Google | Generator+Reviser+Verifier | Aletheia 95.1%（原纪录65.7%） |
| Manus | 5次重写 | 凡是希望模型一定做到的事，要靠代码硬约束 |
| OpenAI Codex | 工程师设计环境 | PR需大量人工干预→问题在Harness不在Agent |

## 参考

- Anthropic "Building Effective Agents": anthropic.com/engineering/building-effective-agents
- "Scaling Managed Agents": Anthropic 工程博客
- CSDN: "多数人搭不好Agent？拆解1900个源文件，7个关键真相"
- CSDN: "Anthropic Harness工程入门基础教程"
- CSDN: "Anthropic官方发布Harness:Managed Agents架构设计哲学"