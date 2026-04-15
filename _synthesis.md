# qclaw 系统设计融会贯通 V2

_2026-04-14 | E:\\ai\\资源 全量研究后深度综合_

## 一、各系统核心架构映射

| 组件 | Claude Code TS | Hermes Python | qclaw |
|------|--------------|---------------|-------|
| Agent循环 | runAgent (AsyncGenerator) | run_agent (530KB) | agents/agent_types.py |
| 记忆系统 | agentMemory.ts (178行) | MemoryManager | memory_fence.py |
| 上下文压缩 | analyzeContext.ts (3430行) | ContextCompressor (778行) | qclaw_compactor.py |
| Prompt Cache | prompt_caching.py | Auxiliary Client | prompt_cache_manager.py |
| 权限决策 | permissionSetup.ts | tools/delegate_tool.py | tool_pipeline.py |
| Fork机制 | forkedAgent.ts (690行) | fork机制 | multi_agent_dispatcher.py |
| Skill系统 | skills/*.ts (20个) | skills/ (309个) | skill_evolution/ |
| Hooks | hooks/*.ts (104个) | tools/*.py (70个) | tool_pipeline.py |
| Token预算 | tokenBudget.ts | budget_config.py | token_budget.py |
| 安全扫描 | - | skills_guard.py | memory_guard.py |

## 二、新发现的核心设计（之前遗漏）

### 1. Claude Code analyzeContext.ts（3430行，Token管理核心）

**最重要发现：TOOL_TOKEN_COUNT_OVERHEAD = 500**

每个工具调用API都带500 token的overhead（工具描述本身的固定前缀）。
当N个工具被分别计数时，每个调用都有这个overhead，导致总overhead = N×500而不是1×500。
Claude Code在分析时减去这个overhead来显示准确的工具内容大小。

**Token计数三策略（级联fallback）：**
1. API直接计数（countMessagesTokensWithAPI）
2. Haiku fallback（countTokensViaHaikuFallback，便宜快速）
3. roughTokenCountEstimation（纯估算，最后兜底）

**AutoCompact机制：**
- GrowthBook feature flag控制开关
- AUTOCOMPACT_BUFFER_TOKENS vs MANUAL_COMPACT_BUFFER_TOKENS
- 只在API返回null时触发

**SKILL_TOKEN_COUNT_OVERHEAD：**
- 每个skill的frontmatter也有overhead
- estimateSkillFrontmatterTokens()

**Progressive Disclosure边界：**
- SYSTEM_PROMPT_DYNAMIC_BOUNDARY：静态/动态分界线
- 只对动态部分增量更新，静态部分保持不变

### 2. Claude Code forkedAgent.ts（690行，Prompt Cache关键）

**Fork = 子代理，但保持Prompt Cache兼容**

CacheSafeParams（必须与父请求完全一致的参数）：
- system_prompt：必须一致才能cache命中
- user_context：影响cache
- system_context：影响cache
- toolUseContext：工具+模型+选项
- forkContextMessages：父上下文消息

**Cloned File State Cache：**
- fork调用cloneFileStateCache()
- 父和子的文件系统状态是隔离克隆
- 但都从同一snapshot继承

**关键洞察：Prompt Cache key = system + tools + model + messages(prefix) + thinking_config**
- 任何参数改变都会导致cache miss
- 所以fork传递的是"已渲染的system prompt字节"，不是重新计算

### 3. Hermes ContextCompressor（778行，压缩算法完整实现）

**v2改进（相比v1）：**
- Structured summary template：Goal + Progress + Decisions + Files + Next Steps
- 迭代摘要更新（preserves info across multiple compactions）
- Token-budget tail protection（固定消息数改为token预算）
- 工具输出裁剪（cheap pre-pass，不用LLM）
- Scaled summary budget（与压缩内容成比例）

**算法五步：**
1. Prune old tool results（无LLM，纯粹文本操作）
2. Protect head messages（system prompt + first exchange）
3. Protect tail by token budget（最近~20K tokens）
4. Summarize middle turns（LLM调用structured prompt）
5. On subsequent：迭代更新previous summary

**关键常量：**
- _MIN_SUMMARY_TOKENS = 2000
- _SUMMARY_RATIO = 0.20（摘要占原文20%）
- _SUMMARY_TOKENS_CEILING = 12000
- _PRUNED_TOOL_PLACEHOLDER = "[Old tool output cleared]"

### 4. Hermes Skills Guard（1200行，Skill安全扫描）

**信任层级（3级）：**
| 级别 | 来源 | 策略 |
|------|------|------|
| builtin | Hermes内置 | 永不扫描，总信任 |
| trusted | openai/skills, anthropics/skills | caution允许 |
| community | 其他 | 任何finding=block（除非--force） |
| agent-created | Agent创建 | caution=ask |

**安装策略（Verdict×TrustLevel矩阵）：**
- safe × any = allow
- caution × builtin/trusted/agent-created = allow
- caution × community = block
- dangerous × any = block（除非--force）

**扫描类别（4类）：**
- exfiltration：数据泄露（curl带密钥、文件泄露）
- injection：注入（eval、pickle反序列化）
- destructive：破坏性命令（rm -rf）
- persistence：持久化（authorized_keys）
- network：网络访问

### 5. Claude Code forkSubagent.ts（211行，隐式Fork机制）

**feature flag：FORK_SUBAGENT**
- 开启时：subagent_type可选
- 省略时：子代理继承父的完整对话+system prompt
- 所有spawn在后台运行（async）

**Mutually exclusive with：**
- Coordinator mode（已有自己的delegation模型）
- Non-interactive session（无交互）

**FORK_AGENT配置（隐式fork默认配置）：**
- tools: ['*']
- useExactTools：继承父的工具池（cache一致）
- permissionMode: 'bubble'：权限弹窗到父终端
- model: 'inherit'：继承父模型（context长度一致）

**Cache注意事项：**
- fork传递的是toolUseContext.renderedSystemPrompt（已渲染字节）
- 如果重新计算getSystemPrompt()可能因为GrowthBook状态不同而diff
- threading rendered bytes = byte-exact cache key

### 6. Claude Code memoryTypes.ts（700行，四类型完整定义）

**TYPES_SECTION_COMBINED（每种类型的元数据）：**
- USER：角色/目标/责任。when_to_save：了解任何用户细节时。how_to_use：工作需要考虑用户视角时。
- FEEDBACK：工作指导。when_to_save：用户提供纠正时。how_to_use：验证工作时。
- PROJECT：项目上下文。when_to_save：非代码可推导时。how_to_use：实现功能时。
- REFERENCE：外部指针。when_to_save：发现Linear/Grafana等引用时。how_to_use：集成时。
- LOCAL：本地agent私有用。不check in VCS。

**parseMemoryType(raw)函数：**
- MEMORY_TYPES = ['user', 'feedback', 'project', 'reference', 'local']
- 枚举而非字符串字面量

### 7. Claude Code messages.ts（5513行，消息类型系统）

**20+ System Message类型：**
| 类型 | 含义 |
|------|------|
| StopHookSummary | Stop钩子执行摘要 |
| ApiMetrics | API使用指标（candidates/cached/turns）|
| BridgeStatus | 桥接状态更新 |
| Tombstone | 占位符（历史记录保留）|
| ToolUseSummary | 工具使用统计 |
| RequestStartEvent | 请求开始事件 |
| MemorySavedMessage | 记忆已保存 |
| AwaySummary | 离开摘要 |

**HookAttachment：**
- 普通attachment vs HookPermissionDecisionAttachment（权限决策专用）
- HookAttachmentWithName = 排除权限决策的类型

### 8. ECC autonomous-loops（6种循环模式）

| 模式 | 复杂度 | 适用场景 |
|------|--------|---------|
| Sequential Pipeline | 低 | 日常开发步骤、脚本 |
| NanoClaw REPL | 低 | 交互式持久会话 |
| Infinite Agentic Loop | 中 | 并行内容生成 |
| Continuous Claude PR Loop | 中 | 多日迭代开发 |
| De-Sloppify | 附加 | 任意循环后的质量清理 |
| Ralphinho / RFC-Driven DAG | 高 | 大规模并行+合并协调 |

**Claude -p 非交互模式：**
- 每个调用隔离上下文窗口
- `set -e` 传播exit codes
- 危险：负面指令（"don't test"）很难精确

**De-Sloppify Pattern：**
- 任何循环后加质量清理pass
- 自动化lint/type check/commit
- Ralphinho的quality pass

## 三、融会贯通：核心连接

### A. Prompt Cache + Fork = Claude Code核心优化

Claude Code的Prompt Cache机制是fork的基础：
- fork保持CacheSafeParams与父一致 → 父的cache可命中
- 子修改toolUseContext但保持system_prompt/model/messages一致 → cache命中
- 结果：子推理成本大幅降低（75%节省来自缓存）

**qclaw应该学习：**
- multi_agent_dispatcher中保持父的cache key
- fork代理时传递已渲染的system prompt字节

### B. Memory Types × Memory Guard × Skills Guard = 三层安全

```
Skill下载 → Skills Guard扫描 → 安装/阻止
     ↓
记忆写入 → Memory Guard扫描 → 允许/警告
     ↓
文件写入 → Security Hook扫描 → 允许/警告
```

三层防御来自不同系统：
- Claude Code：无内置（依赖skill作者）
- Hermes：Skills Guard（1200行，完整信任策略）
- qclaw已有：memory_guard.py + security_hook.py

**qclaw还需要：Skill下载前的Guard扫描**

### C. Context Compressor × Token Budget = 上下文管理闭环

```
Token使用监控（token_budget.py）
    ↓ 接近90%
触发压缩（qclaw_compactor.py）
    ↓
ContextCompressor算法（5步）
    ↓
Structured Summary（Goal/Progress/Decisions/Files/Next）
    ↓
释放上下文空间 → 继续工作
```

**关键洞察：tail protection用的是token预算（20K），不是固定消息数**

### D. Fork × Permission × Hook = Agent隔离三件套

```
forkedAgent
    ├── CacheSafeParams（保持cache兼容）
    ├── cloneFileStateCache（文件系统隔离）
    ├── 权限'bubble'（到父终端显示）
    └── usage tracking（tengu_fork_agent_query事件）
    
权限钩子（permissionSetup）
    ├── allowedTools（白名单）
    ├── deniedTools（黑名单）
    └── PermissionContext（动态权限）

Hook（pre/post/stop）
    ├── PreToolUse：修改输入、block操作
    └── PostToolUse：验证输出、记录metrics
```

### E. Skills × Memory × Tools = 三类可迁移资产

| 资产 | 来源 | qclaw落地 |
|------|------|---------|
| Reusable workflow | Skills | skillify_skill.py |
| Knowledge/facts | Memory | memory_fence.py + MEMORY.md |
| Tool wrappers | MCP/Tools | tool_registry.py |
| Procedural automation | Hooks/Commands | hooks/ |

## 四、qclaw系统设计完整视图

```
qclaw主循环
├── agents/agent_types.py（4角色：GENERAL/VERIFY/EXPLORE/PLAN）
│   ├── VERIFY：反合理化prompt（Verification Agent）
│   ├── EXPLORE：READ-ONLY + omitClaudeMd
│   └── PLAN：verify步骤+具体可操作计划
│
├── agents/tool_pipeline.py（15步管道）
│   ├── 步骤3：_validate_input（DANGEROUS_PATTERNS 22条）
│   ├── 步骤5：_run_pre_hooks（HookDispatcher）
│   └── 步骤6：_resolve_hook_permission（三层防护）
│
├── agents/multi_agent_dispatcher.py
│   ├── fork：CacheSafeParams传递
│   ├── cloneFileStateCache：文件隔离
│   └── MAX_DEPTH=2：防止递归
│
├── memory/
│   ├── memory_fence.py（<memory-context> fencing）
│   ├── memory_guard.py（12威胁+隐形字符）
│   ├── memory_types.py（四类型：user/feedback/project/reference）
│   └── MEMORY.md（索引制，200行上限）
│
├── skills/
│   ├── skillify_skill.py（从会话自动创建）
│   ├── remember_skill.py（记忆审查提升）
│   ├── simplify_skill.py（三Agent并行审查）
│   ├── batch_skill.py（5-30并行工作编排）
│   └── security_hook.py（10大漏洞检测）
│
├── context/
│   ├── token_budget.py（90%阈值+递减检测）
│   ├── prompt_cache_manager.py（system_and_3策略）
│   └── qclaw_compactor.py（Structured Summary五步）
│
└── evolver/（自我进化）
    ├── evolver.py（规则引擎+熔断器）
    ├── self_review.py（任务复盘）
    └── ralph_anti_loop.py（循环检测）
```

## 五、待落地清单（优先级排序）

### 🔴 高优先级
1. **ContextCompressor完整实现**（参考Hermes 778行）
   - Structured Summary Template（Goal/Progress/Decisions/Files/Next）
   - Token-budget tail protection（20K tokens）
   - 工具输出裁剪（cheap pre-pass）
   
2. **Skills Guard扫描**（参考Hermes 1200行）
   - Trust Level系统（builtin/trusted/community）
   - 安装策略矩阵（Verdict×TrustLevel）
   - 4类扫描：exfiltration/injection/destructive/persistence

3. **fork机制完善**（参考Claude Code forkedAgent.ts）
   - CacheSafeParams传递
   - cloneFileStateCache
   - tengu_fork_agent_query事件

### 🟡 中优先级
4. **analyzeContext.ts Token管理**
   - TOOL_TOKEN_COUNT_OVERHEAD = 500
   - countTokensWithFallback三级联
   - estimateSkillFrontmatterTokens

5. **ECC autonomous-loops**
   - Sequential Pipeline（Claude -p）
   - Ralphinho / RFC-Driven DAG
   - De-Sloppify质量清理模式

6. **Claude Code -p非交互模式**
   - 每个调用隔离上下文
   - set -e传播exit codes
   - 负面指令陷阱

### 🟢 低优先级
7. **Hermes Skills Guard扩展**
   - agent-created级别（ask模式）
   - network访问检测
   
8. **Claude Code 20+系统消息类型**
   - Tombstone机制
   - ApiMetrics收集
   - BridgeStatus追踪

## 六、最核心的三个认知

### 认知1：Prompt Cache是Fork的基础

Claude Code的fork不是简单的子进程，
而是通过CacheSafeParams保持父的API cache命中。
任何参数不一致都会导致cache miss。
→ qclaw的multi_agent_dispatcher需要显式管理cache key。

### 认知2：记忆是分层的安全问题

三层防御缺一不可：
- Skills Guard：skill下载时（供应链安全）
- Memory Guard：记忆写入时（prompt注入）
- Security Hook：文件写入时（代码漏洞）

### 认知3：压缩是结构化摘要，不是简单截断

Hermes ContextCompressor的Structured Summary Template：
Goal + Progress + Decisions + Files + Next Steps
迭代摘要保留历史信息，
Token-budget tail protection比固定消息数更精确。
