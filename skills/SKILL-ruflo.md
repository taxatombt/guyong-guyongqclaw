---
name: SKILL-ruflo
description: |
  ruflo = Claude Code + Codex dual-mode AI coding swarm (ruvnet/ruflo, 47,936 stars).
  Key: 3-tier model routing, swarm orchestration, HNSW memory, 17 hooks + 12 workers.
  Use when: building multi-agent swarms, need faster memory search, designing agent skills.
---

# ruflo 源码分析落地

**来源**: ruvnet/ruflo (GitHub, 47,936 stars)
**文件**: AGENTS.md(21KB) + README.md(24KB) + CLAUDE.md(42KB) + 25 agent skills + v3/ 文档
**落地**: `E:\ai\学习\ruflo\` + `skills/SKILL-ruflo.md` (本文件)

## 核心架构：Dual-Mode Collaboration

ruflo = Claude Code (🔵) + OpenAI Codex (🟢) 双模编排，并行执行共享内存协调。

```
claude-flow = LEDGER（状态跟踪/记忆存储/协调）
Codex = EXECUTOR（写代码/运行命令/创建文件）
```

**vs qclaw**: qclaw 的 agent dispatcher 类似于 claude-flow，但缺少 Codex 执行层。

## 核心规则1：1 MESSAGE = ALL RELATED OPERATIONS

这是 ruflo 最重要的并发规则：

```bash
# ✅ 正确：在一个消息中批量操作
TodoWrite([...])      # 所有待办一次性写入
Task(...)             # 所有 agent 同时生成
Bash(...)             # 所有命令并发执行
Read([...])           # 所有文件一次性读取

# ❌ 错误：每步单独发消息
TodoWrite([task1])
Task(agent1)
等待...  # 等待是浪费
```

**qclaw 可借鉴**: agents/exec_adapter.py 中的 cleanup chain 可以批量执行

## 核心规则2：3-Tier Model Routing (ADR-026)

```
Tier 1: Agent Booster (WASM)  <1ms,  $0   → 跳过 LLM，纯启发式
Tier 2: Haiku               ~500ms,  $0.0002 → 简单任务
Tier 3: Sonnet/Opus          2-5s,   $0.003-0.015 → 复杂推理
```

**关键洞察**: 90%+ 的任务不需要 LLM，WASM 层用启发式规则处理。

**qclaw 可借鉴**: modelroute 目前只有一层 LLM，可以增加启发式路由层。

## 核心规则3：MCP + Task 同消息调用

```bash
# 在同一消息中，先调 MCP，再调 Task 工具
mcp__ruv-swarm__swarm_init({...})  # MCP 先
Task("Architect", "Design...", "system-architect")  # 立即 Task
```

**qclaw 可借鉴**: 工具调用可以批量（MCP 优先，Task 其次）

## Swarm 协议

### 6 种拓扑
- hierarchical（默认）：分层树形，6-8 agents
- mesh：全连接，去中心化
- ring：环形，循环依赖
- star：星形，中心协调
- adaptive：自适应切换
- hierarchical-mesh：混合

### 共识算法
- raft（默认）：领导者选举，日志复制
- byzantine：拜占庭容错
- gossip：最终一致

### Anti-Drift 机制
防止多个 agent 在迭代中偏离原始目标。

**qclaw 可借鉴**: agents/multi_agent_dispatcher.py 可增加 anti-drift 检查。

## Agent Skills 格式

ruflo 用 YAML frontmatter 定义 agent skill：

```yaml
---
name: consensus-coordinator
description: "分布式共识 agent，使用亚线性求解器..."
tools: mcp__sublinear-time-solver__solve, mcp__flow-nexus__swarm_init
color: red
type: development
capabilities:
  - Byzantine Fault Tolerance
  - 投票机制
  - 负载均衡
priority: high
hooks:
  pre: |  # CI/CD 钩子
    echo "Starting consensus-coordinator..."
  post: |
    echo "Completed consensus-coordinator"
---
```

**qclaw 可借鉴**: skill_scanner_v2.py 可以增加 color/priority/type 字段。

## Hooks 系统（17 hooks + 12 workers）

### 17 种 Hook
- PreToolUse / PostToolUse
- PreTask / PostTask
- PreMessage / PostMessage
- PreEdit / PostEdit
- PreBash / PostBash
- PreRead / PostRead
- OnError / OnTimeout
- 等等

### 12 Background Workers
- audit：安全审计，优先级 critical，间隔 300s
- optimize：性能优化，优先级 high，间隔 600s
- consolidate：记忆整合，优先级 low，间隔 1800s

### Priority 机制
Hook 按优先级执行：Critical > High > Normal > Low

**qclaw 可借鉴**: tool_pipeline.py 的 hook 链可增加优先级和更多 worker。

## Memory 系统：HNSW（150x-12,500x 加速）

### 核心指标
- M=16：每个节点最大连接数
- efConstruction=200：构建时搜索深度
- efSearch=100：搜索时搜索深度
- metric：cosine/euclidean/dot/manhattan

### Hybrid Backend（ADR-009）
- SQLite：结构化数据（agent metadata）
- AgentDB：向量数据（HNSW 索引）
- LRU Cache：热点数据缓存

### 3-Scope Memory
- project：项目级共享
- local：单个 agent
- user：用户全局

**qclaw 可借鉴**: evolver.py 可用 HNSW 做相似任务匹配。

## Self-Learning 系统

### SONA（Self-Optimizing Neural Architecture）
- 从每次成功中学习模式
- 神经网络的规则化
- 持久化到 ReasoningBank

### ReasoningBank
- 存储成功推理轨迹
- 按任务类型分类
- 新任务先查 ReasoningBank

### LearningBridge
- 连接记忆到神经 pipeline
- 洞察 → 规则转换

**qclaw 可借鉴**: evolver 已经是规则化的学习，可以增加神经轨迹学习。

## Claude Flow CLI（26 commands）

```bash
npx claude-flow@v3alpha swarm init
npx claude-flow@v3alpha agent spawn
npx claude-flow@v3alpha memory store
npx claude-flow@v3alpha hooks post-task
npx claude-flow-codex dual run feature --task "xxx"
```

**qclaw 可借鉴**: qclaw 目前用 Python script 做编排，可以增加 CLI 入口。

## Agent 类型（100+ 种）

| Agent | 功能 | 可借鉴 |
|-------|------|--------|
| consensus-coordinator | BFT 共识 | qclaw 缺 |
| load-balancer | 负载均衡 | qclaw 缺 |
| code-review-swarm | 代码审查 swarm | qclaw 有部分 |
| benchmark-suite | 性能基准 | qclaw 有部分 |
| goal-planner | GOAP 规划 | qclaw 有部分 |
| federation | 零信任安全联盟 | qclaw 缺 |
| self-healing | 自愈系统 | qclaw 缺 |

## Codex 配置（config.toml）

```toml
model = "gpt-5.3-codex"
approval_policy = "on-request"  # untrusted/on-failure/on-request/never
sandbox_mode = "workspace-write"  # read-only/workspace-write/danger-full-access
web_search = "cached"  # disabled/cached/live

[security]
input_validation = true
path_traversal_prevention = true
secret_scanning = true
cve_scanning = true
blocked_patterns = ["\\.env$", "credentials\\.json$"]

[neural]
sona_enabled = true
hnsw_enabled = true
pattern_learning = true

[swarm]
default_topology = "hierarchical"
consensus = "raft"
anti_drift = true
```

**qclaw 可借鉴**: qclaw 目前没有 TOML 配置系统，可以增加。

## qclaw 落地映射

| ruflo 组件 | qclaw 等价 | 差距 |
|-----------|-----------|------|
| 3-Tier Model Routing | modelroute（单层） | 缺 WASM/启发式层 |
| 1 msg = ALL ops | exec_adapter（部分） | 缺批量并发 |
| 17 hooks + 12 workers | tool_pipeline.py（3 hooks） | 差 14 个 hooks |
| HNSW memory | evolver/evolver_db.json（text） | 缺向量搜索 |
| SONA + ReasoningBank | evolver.py（规则） | 缺神经轨迹 |
| Agent skills YAML | skill_scanner_v2（JSON） | 缺 color/type/priority |
| Anti-Drift | dispatcher（部分） | 缺显式检查 |
| Federation security | tool_pipeline.py（部分） | 缺零信任模型 |
| WASM Agent Booster | 无 | 完全缺失 |

## 落地文件

- `E:\ai\学习\ruflo\AGENTS.md` - Agent 编排指南
- `E:\ai\学习\ruflo\CLAUDE.md` - 开发指南（42KB）
- `E:\ai\学习\ruflo\README.md` - 产品概览
- `E:\ai\学习\ruflo\.agents\config.toml` - Codex 配置
- `E:\ai\学习\ruflo\.agents\skills\` - 25+ agent skills
- `E:\ai\学习\ruflo\v3\@claude-flow\hooks\README.md` - Hooks 系统
- `E:\ai\学习\ruflo\v3\@claude-flow\memory\README.md` - Memory 系统
- `E:\ai\学习\ruflo\v3\@claude-flow\cli\README.md` - CLI 命令

## 关键教训

1. **并发即效率**：1 message = ALL related operations，而不是逐条等待
2. **模型分层**：不是所有任务都需要 Sonnet/Opus，90%+ 任务可用启发式或 Haiku
3. **Hook 系统**：17 种 hook + 优先级 + background workers = 完整自动化
4. **HNSW**：向量搜索比文本搜索快 150x-12500x，记忆系统应该迁移到 HNSW
5. **YAML frontmatter**：agent skill 的描述性元数据比 JSON 更易读

---

*来源: ruvnet/ruflo (2026-05-10) | github.com/ruvnet/ruflo*
