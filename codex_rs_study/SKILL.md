# codex_rs_study — OpenAI Codex CLI 源码逆向

> 来源：OpenAI/codex（GitHub），codex-rs 核心模块
> 规模：1768KB / 50个核心文件
> 定位：对比参考，不运行

---

## 核心架构概览

`
用户输入 → CodexThread → Session → AgentControl
                                   
                          ToolOrchestrator → ToolRouter → ToolRegistry
                                   
                          HookRuntime → PreToolUse / PostToolUse
                                   
                          MemoryPipeline → Phase1(提取) → Phase2(整合)
                                   
                          RolloutRecorder → StateDB
`

**两个关键对比：**
- Claude Code（gstack）= 每次推理全量加载记忆
- Codex = 启动时两阶段异步记忆pipeline

---

## 一、记忆系统（最核心创新）

### 触发时机

根会话启动 + 非ephemeral + 记忆开启 + 非子agent + StateDB可用
→ 后台异步执行 Phase1 → Phase2

### 两阶段pipeline

**Phase1：Rollout提取（并行，按rollout）**

StateDB → claim eligible rollouts（启动claim规则）
       → 过滤到memory相关response items
       → 并行发送到模型（concurrency cap）
       → 提取：raw_memory / rollout_summary / rollout_slug
       → 存储到StateDB（stage-1 outputs）

- 每个job lease在DB中，防止并发重复
- 失败带retry backoff，不hot-loop
- 三个结果：succeeded / succeeded_no_output / failed

**Phase2：全局整合（串行）**

StateDB stage-1 outputs → 选择top-N
                        → 同步本地memory artifacts
                        → 生成consolidation子agent
                        → 写 memory_summary.md / MEMORY.md / skills/

- 只运行一个global consolidation job（串行保护）
- 按 usage_count 排序 + last_usage 过滤
- selection diff（added/retained/removed）驱动遗忘机制

### Memory Folder结构

`
memory_root/
├── memory_summary.md       ← 系统prompt永远加载，导航+高信息密度
├── MEMORY.md              ← 手册条目，grep关键词，聚合洞见
├── raw_memories.md        ← Phase1输出合并，最新在前
├── skills/                ← 可复用流程，SKILL.md入口
│   └── skill-name/SKILL.md
└── rollout_summaries/     ← 每个rollout的摘要
    └── rollout_slug.md
`

### Memory质量规则（核心原则）

1. 只存不可推导的知识
2. 优先用户偏好 > 程序性知识
3. 优化减少未来用户 steering，而不是减少 agent 搜索
4. 证据只基于实际发生，不发明
5. 不存 secrets（redact）
6. 没有有意义的更新就不写文件（no-op allowed）

**有价值的记忆：**
- 稳定的用户操作偏好、重复的 dislike
- 决策触发点（避免浪费探索）
- 失败护盾：symptom → cause → fix + verification + stop rules
- Repo orientation：入口、配置、命令
- 工具quirks和可靠shortcuts
- 验证性reproduction plans

**无价值：**
- 泛泛建议（be careful）
- 存secrets/credentials
- 复制大段原始输出
- 把探索性讨论变成永久记忆

### 遗忘机制（forgetting mechanism）

Phase2读取diff：
  - added: 新增的rollout
  - retained: 继续保留的
  - removed: 被遗忘的

对removed的thread_id：
  → 在MEMORY.md中只删除该thread支撑的内容
  → 保留shared/still-supported内容
  → 不删除整个block

### Phase2 Consolidation Prompt 核心指令

Goal: 帮助未来agent：
- 深刻理解用户（不需要重复指令）
- 更少tool calls解决相似任务
- 重用proven workflows和verification checklists
- 避免已知landmines和failure modes

优先级：
- 稳定用户偏好 > 程序性知识
- 减少用户steering > 减少agent搜索努力

---

## 二、Agent控制系统

### AgentControl

- 每个root thread/session树只创建一个AgentControl
- 共享给所有子agent，保持registry scope在root thread
- 使用Weak引用避免循环引用

### AgentMetadata

- agent_name: nickname（从配置或默认列表选择）
- agent_status: AgentStatus枚举
- last_task_message: 最后任务描述

### Spawn模式

FullHistory：完整历史
LastNTurns(N)：只最后N个turn

### 保留的RolloutItem

- system/developer/user：始终保留
- assistant FinalAnswer：保留
- 丢弃：Reasoning, ShellCalls, FunctionCalls, ToolCalls

→ fork时保留什么有明确规则，不是全量保留

---

## 三、Hook系统

### 支持的事件

PreToolUse / PostToolUse / SessionStart / Stop / UserPromptSubmit

### PreToolUse output schema

- allow: bool（是否允许执行）
- modified_input: 可修改tool输入
- reason: 原因说明

### 关键设计

Hook可以allow/deny/修改输出
Schema文件在 hooks/schema/generated/

---

## 四、Tool系统

### ToolOrchestrator

registry + router + sandboxing + parallel execution

### 危险命令检测（shell-command）

PowerShell parser + dangerous list
在执行前检测，不依赖沙箱兜底

---

## 五、Compact系统（上下文压缩）

### 触发条件

上下文token超出阈值 → 触发CompactTask
生成压缩摘要 → 替换历史消息 → 保持compact标记

### Compact类型

PreTurn（turn之前压缩）
MidTurn（turn中间压缩）
Manual（手动触发）
Remote（远程compact）

---

## 六、Guardian审批系统

### 权限Policy

Deny / Ask / Allow 三档

### 审批流程

用户请求危险操作
→ Guardian.review()
→ 展示给用户
→ 用户 approve/deny
→ 记录decision

---

## 七、关键设计对比

Claude Code（gstack）vs OpenAI Codex：

| 设计 | Claude Code | Codex |
|------|-----------|-------|
| 记忆 | 全量加载 | 两阶段pipeline |
| 记忆格式 | SKILL.md | Phase1=raw, Phase2=consolidation |
| 工具发现 | Skill路由 | ToolRegistry + MCP |
| 审批 | 交互式确认 | Guardian policy |
| 压缩 | Compact | Compact + remote |
| Agent | 分身并行 | Sub-agent树 |
| Shell安全 | Landlock/bwrap | dangerous_command检测 |

---

## 八、可移植设计点

### 1. 两阶段记忆pipeline

Phase1: rollout → structured_memory（并行，DB-backed）
Phase2: 全局consolidation（串行，文件系统）

→ 解决：记忆提取和整合的分离扩展

### 2. 遗忘机制（forgetting）

selection diff → added/retained/removed
→ 增量更新，不全量重写
→ MEMORY.md 按 thread_id 粒度清理

### 3. Agent fork保留规则

keep_forked_rollout_item()
→ 明确什么该保留、什么该丢弃
→ 不是全量也不是空

### 4. Hook Schema生成

hooks/schema/generated/*.schema.json
→ 版本化，可验证
→ PreToolUse / PostToolUse / SessionStart / Stop

### 5. Shell命令安全检测

PowerShell parser + dangerous list
→ 在执行前检测，不依赖沙箱兜底

---

## 落地文件索引

codex_rs_study/                              1.7MB / 50文件

Core files (from extraction):
- codex-rs_core_src_codex.rs              ← 核心(302KB)
- codex-rs_core_src_memories_phase1.rs    ← Phase1(20KB)
- codex-rs_core_src_memories_phase2.rs    ← Phase2(17KB)
- codex-rs_core_templates_memories_consolidation.md ← Consolidation prompt(47KB)
- codex-rs_core_src_agent_control.rs       ← Agent控制(43KB)
- codex-rs_core_src_hook_runtime.rs        ← Hook系统(11KB)
- codex-rs_core_src_tools_orchestrator.rs  ← 工具编排(15KB)
- codex-rs_core_src_compact.rs            ← 压缩系统(20KB)
- codex-rs_core_src_exec_policy.rs         ← 执行策略(30KB)
- codex-rs_protocol_src_permissions.rs     ← 权限系统(77KB)
- codex-rs_protocol_src_protocol.rs         ← 协议定义(173KB)
- codex-rs_shell-command_src_parse_command.rs ← Shell解析(82KB)
- codex-rs_state_src_runtime_memories.rs   ← StateDB memories(164KB)
- codex-rs_state_src_runtime_threads.rs    ← StateDB threads(50KB)

SDK files:
- sdk/python/src/codex_app_server/generated/v2_all.py ← Python SDK(188KB)

Config:
- codex-rs_core_config.schema.json          ← Config Schema(84KB)
- codex-rs_core_src_config_mod.rs          ← Config模块(90KB)
