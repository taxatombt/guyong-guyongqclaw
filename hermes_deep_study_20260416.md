# Hermes 源码深度研究：记忆与进化

_2026-04-16 | 来源：E:\ai\资源\8hermes-agent-main\hermes-agent-main_

---

## 一、记忆系统架构（Memory System）

### 1.1 MemoryManager（memory_manager.py, 14KB）

**核心设计：1+1 Provider架构**

```
MemoryManager
├── BuiltinMemoryProvider（始终存在，不可移除）
└── ExternalMemoryProvider（最多1个，plugin机制）
```

**关键约束**：
- 内置provider始终第一注册，无法移除
- 外部provider最多1个 → 防止tool schema膨胀
- 第二个外部provider被拒绝并打warning日志
- 任何provider失败不影响其他provider

**生命周期钩子（完整8个）**：

| 钩子 | 时机 | 用途 |
|------|------|------|
| `initialize()` | Agent启动 | 建资源/连接/后台线程 |
| `system_prompt_block()` | 系统prompt组装 | 静态信息注入 |
| `prefetch()` | 每轮API调用前 | 记忆召回上下文 |
| `queue_prefetch()` | 每轮完成后 | 队列下次召回 |
| `sync_turn()` | 每轮完成后 | 异步持久化 |
| `on_turn_start()` | 回合开始 | turn计数/范围管理 |
| `on_pre_compress()` | 上下文压缩前 | 提取将被压缩的洞察 |
| `on_delegation()` | 子代理完成后 | 观察子代理工作结果 |

**记忆围栏机制**：
```python
def build_memory_context_block(raw_context: str) -> str:
    return (
        "<memory-context>\n"
        "[System note: The following is recalled memory context, "
        "NOT new user input.]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )
```
围栏防止模型把记忆内容当作用户输入。

---

### 1.2 MemoryProvider ABC（memory_provider.py, 10KB）

**9个核心方法 + 6个可选hook**：

```python
class MemoryProvider(ABC):
    @property
    def name(self) -> str:  # 'builtin' | 'honcho' | 'hindsight' | 'mem0' ...

    def is_available(self) -> bool:
        # 只检查配置/依赖，不做网络调用
        return True

    def initialize(self, session_id, **kwargs) -> None:
        # kwargs包含：hermes_home, platform, agent_context, agent_identity
        pass

    def system_prompt_block(self) -> str:  # 静态系统信息
    def prefetch(self, query, session_id) -> str:  # 快速返回缓存结果
    def queue_prefetch(self, query, session_id) -> None:  # 队列下次召回
    def sync_turn(self, user_content, assistant_content, session_id) -> None:
    def get_tool_schemas(self) -> List[Dict]:  # OpenAI function格式
    def handle_tool_call(self, tool_name, args, **kwargs) -> str:  # JSON string

    # 可选hook
    def on_turn_start(self, turn_number, message, **kwargs)
    def on_session_end(self, messages: List[Dict])
    def on_pre_compress(self, messages) -> str  # 提取压缩洞察
    def on_delegation(self, task, result, child_session_id, **kwargs)
    def on_memory_write(self, action, target, content)  # 内置写入镜像
```

**is_available()设计意图**：不联网，只检查配置和依赖 → 快速启动判断

**on_pre_compress()返回值**：给压缩prompt的额外指令，确保压缩时保留provider提取的洞察

**on_delegation()**：父agent观察子代理工作结果，但不复制子代理的记忆

---

### 1.3 ContextCompressor（context_compressor.py, 34KB, 778行）

**四步压缩算法**：

```
1. Prune Tool Results（无LLM调用，廉价预热）
   → 旧tool结果>200字符替换为 "[Old tool output cleared]"

2. Protect Head（保护前N条消息，默认3条）
   → system prompt + 第一次对话

3. Protect Tail（按token预算，最后~20K tokens）
   → 最近工作状态不丢失

4. Summarize Middle（LLM调用，结构化摘要）
   → 压缩比 = 20%（压缩内容/目标摘要tokens）
```

**结构化摘要模板**：
```
Goal: [工作目标]
Progress: [已完成的工作]
Decisions: [关键决策]
Files: [涉及的文件]
Next Steps: [下一步计划]
```

**迭代压缩机制**：
- 首次压缩：summarize middle turns
- 后续压缩：`self._previous_summary` + 新middle turns → 增量更新摘要
- 避免重复总结同一内容

**Summary Token预算**：
- 下限：2000 tokens（最小摘要粒度）
- 上限：min(5% of context_length, 12000)
- 比率：20%（压缩内容/摘要目标）

**序列化给Summarizer的格式**：
```
[USER]: {content}          # 用户消息
[ASSISTANT]: {content}    # 助手回复
[TOOL CALL {id}]: {name}({args})  # 工具调用
[TOOL RESULT {id}]: {content}     # 工具结果
```

每个消息超过6000字符 → 保留头4000+尾1500，中间截断

**配置参数**：
- `threshold_percent`: 0.50（50% context时触发压缩）
- `protect_first_n`: 3（保护前3条）
- `protect_last_n`: 20（保护最后20条）
- `summary_target_ratio`: 0.20（摘要/压缩内容比）
- `summary_model_override`: 用便宜模型做摘要

---

## 二、进化与洞察系统

### 2.1 InsightsEngine（insights.py, 34KB）

**功能：会话历史分析 → 用量报告**

```python
class InsightsEngine:
    def __init__(self, db):  # SessionDB实例
        self.db = db
        self._conn = db._conn

    def generate(self, days=30, source=None) -> Dict[str, Any]:
        # 从SQLite查询会话数据
        # 计算：token消耗/成本估算/工具使用/活动趋势/模型分布
```

**报告结构**：
```python
{
  "period": {"start": datetime, "end": datetime, "days": N},
  "sessions": {"total": N, "by_platform": {...}},
  "tokens": {"input": N, "output": N, "cache_read": N, "cache_write": N},
  "cost_usd": {"total": float, "by_model": {...}},
  "tool_usage": {"top_tools": [...], "by_platform": {...}},
  "activity": {"daily_counts": [...]},
  "models": {"usage_by_model": {...}},
  "session_duration": {"avg_seconds": float}
}
```

**成本估算**：用 `CanonicalUsage` + `estimate_usage_cost()`
- 支持 cache_read_tokens / cache_write_tokens（Anthropic MCP）
- 未知模型 → status="unknown"，amount_usd=0

**条形图输出**：用 `█` 字符画ASCII图表

### 2.2 TrajectoryCompressor（trajectory_compressor.py, 63KB）

**用途：压缩agent轨迹用于训练**

```
压缩策略：
1. 保护first turns（system/human/first GPT/first tool）
2. 保护last N turns（最终行动和结论）
3. 仅压缩middle turns（从第2个tool response开始）
4. 只压缩到目标token budget所需量
5. 压缩区域替换为单个human summary消息
6. 保留剩余tool calls（模型在summary后继续工作）
```

**目标用户**：想用Hermes轨迹数据微调模型的场景

### 2.3 Insights → Self-Model 桥接

**qclaw的self_model_insights_bridge.py已落地**：
- insights.py提供token/cost/tool数据
- bridged.py将usage数据转化为自我模型输入
- 用量模式 → 判断偏好推断

---

## 三、子代理与委托系统

### 3.1 DelegateTool（delegate_tool.py, 45KB）

**子代理架构**：
```
Parent Agent
├── 子代理1（独立会话，限制工具集）
├── 子代理2（独立会话，限制工具集）
└── 子代理3（最多3个并发）
    └── 孙子代理（MAX_DEPTH=2，禁止）
```

**被封锁的工具（DELEGATE_BLOCKED_TOOLS）**：
```python
frozenset([
    "delegate_task",   # 禁止递归委托
    "clarify",          # 禁止用户交互
    "memory",           # 禁止写共享MEMORY.md
    "send_message",     # 禁止跨平台副作用
    "execute_code",     # 子代理应推理而非写脚本
])
```

**配置优先级**：`config.yaml > env(DELEGATION_MAX_CONCURRENT_CHILDREN) > default(3)`

**父子通信**：父context只看到delegation call + summary result，**不看到**子代理中间过程

---

## 四、qclaw落地对照

| Hermes设计 | qclaw落地 | 状态 |
|-----------|-----------|------|
| MemoryManager 1+1 provider | memory_fence.py + memory_pipeline.py | ✅ 部分 |
| MemoryProvider ABC | agent/memory_provider.py接口已定义 | ⚠️ 待完善 |
| `<memory-context>`围栏 | memory_fence.py围栏机制 | ✅ |
| on_pre_compress hook | qclaw_compactor.py四步压缩 | ✅ |
| ContextCompressor结构化摘要 | context_compressor.py落地 | ✅ |
| InsightsEngine | qclaw_insights（内建）| ✅ |
| TrajectoryCompressor | 未落地 | ❌ |
| DELEGATE_BLOCKED_TOOLS | agent/agent_types.py VERDICT禁止工具 | ✅ |
| MAX_DEPTH=2委托 | multi_agent_dispatcher.py | ✅ |
| 9个MemoryProvider hook | memory_pipeline.py | ⚠️ 部分 |

---

## 五、核心认知（记忆与进化）

### 1. 记忆的三种形态

Hermes实际上有**三种记忆**：
- **即时记忆**：session内，prefetch/sync_all管理
- **压缩记忆**：context压缩时提取的洞察（on_pre_compress）
- **持久记忆**：BuiltinMemoryProvider的MEMORY.md/USER.md

qclaw目前只有：
- 即时记忆：integrated_memory.py
- 压缩记忆：qclaw_compactor.py
- 持久记忆：MEMORY.md（手动）+ evolver_db.json

**缺失**：三种记忆之间没有打通——压缩时的洞察没有回流到持久记忆

### 2. Provider注册顺序决定tool schema顺序

MemoryManager.add_provider()按顺序注册，tool_to_provider索引：
- 先注册的provider工具名优先
- 工具名冲突 → 打warning，后注册的provider工具被忽略

**qclaw教训**：记忆工具注册顺序要稳定，不能随意改变

### 3. 压缩时机的两种策略

Hermes用了两种：
- **百分比阈值**：`threshold_percent=0.50`（50% context触发）
- **Token预算**：tail_token_budget基于threshold计算

**qclaw对比**：Claude Code用90%阈值+diminishing returns检测，Hermes用50%阈值
- Hermes更保守（提前压缩）
- Claude Code更激进（榨干context）

### 4. 迭代压缩的"记忆累积"问题

Hermes的`_previous_summary`机制解决了：
- 每次压缩都基于"上一份摘要+新内容"做增量更新
- 而不是每次都重新总结所有middle turns

**qclaw问题**：qclaw_compactor.py还没有这个机制，每次压缩是独立的

### 5. 进化不是单一模块

Hermes没有独立的"进化模块"。进化分散在：
- InsightsEngine（用量分析）→ 自我感知
- TrajectoryCompressor（轨迹压缩）→ 训练数据准备
- Delegate（子代理）→ 任务分解
- MemoryProvider.on_delegation() → 观察子代理结果

**qclaw启示**：进化是多系统协作的结果，不是单独的evolver.py

### 6. 子代理的"隔离"设计

DelegateTool的核心：
- 独立会话（无父history）
- 限制工具集（封锁5个危险工具）
- 深度限制（MAX_DEPTH=2）
- 并发限制（最多3个）
- 结果摘要（父只看到summary，不看过程）

这和qclaw的multi_agent_dispatcher设计一致，但qclaw还缺少：
- 并发数量限制（可配置）
- 深度限制硬编码

---

## 六、待落地项

| 优先级 | 项目 | 来源 |
|--------|------|------|
| P1 | TrajectoryCompressor（轨迹压缩用于训练数据）| Hermes |
| P1 | 迭代压缩机制（_previous_summary增量摘要） | Hermes ContextCompressor |
| P2 | memory_pipeline.py打通on_pre_compress→持久记忆 | Hermes MemoryProvider |
| P2 | agent/agent_types.py加DELEGATE_BLOCKED_TOOLS封锁 | Hermes |
| P3 | multi_agent_dispatcher加并发数限制 | Hermes DelegateTool |
| P3 | self_model_insights_bridge激活（insights→自我模型） | Hermes InsightsEngine |

---

## 七、关键代码片段

### Memory围栏注入
```python
def build_memory_context_block(raw_context: str) -> str:
    if not raw_context.strip():
        return ""
    clean = re.sub(r'</?\s*memory-context\s*>', '', raw_context)
    return (
        "<memory-context>\n"
        "[System note: The following is recalled memory context, "
        "NOT new user input.]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )
```

### 迭代压缩（previous_summary）
```python
def _get_summary_prompt(self, middle_turns, previous_summary):
    if previous_summary:
        return (
            "Update this existing summary by adding new information "
            "from the conversation turns below. Preserve the structure.\n\n"
            f"Previous summary:\n{previous_summary}\n\n"
            "New turns:\n{serialized}"
        )
    else:
        return (
            "Create a structured summary of the conversation turns below.\n"
            "Format: Goal / Progress / Decisions / Files / Next Steps\n\n"
            "{serialized}"
        )
```

### Provider注册防重
```python
def add_provider(self, provider: MemoryProvider) -> None:
    is_builtin = provider.name == "builtin"
    if not is_builtin and self._has_external:
        logger.warning("Rejected '%s' — external provider '%s' already registered",
                       provider.name, existing)
        return
    if not is_builtin:
        self._has_external = True
    self._providers.append(provider)
    # Index tool names → provider
    for schema in provider.get_tool_schemas():
        tool_name = schema.get("name", "")
        if tool_name not in self._tool_to_provider:
            self._tool_to_provider[tool_name] = provider
```
