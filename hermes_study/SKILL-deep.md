# SKILL-deep-hermes-AIAgent.md
# Hermes AIAgent 深度分析 — run_agent.py (518KB, 10267行)

**状态**: 深度研究完成  
**来源**: `E:\Hermes\run_agent.py`  
**落地目录**: `hermes_study/`  
**时间**: 2026-04-13

---

## 架构总览

```
AIAgent (run_agent.py)
├── 初始化 (line 516): 40+ 参数, 插件式架构
├── run_conversation (line 7500): 主循环, ~1000行
│   ├── 前置检查 (TCP健康/压缩/插件钩子)
│   ├── 主循环 while (迭代预算/中断/重试)
│   │   ├── 消息预处理 (标准化/注入/过滤)
│   │   ├── API调用 (streaming + 4种错误恢复)
│   │   ├── 工具执行 (并发/顺序/并发度决策)
│   │   ├── 上下文压缩 (主动/被动)
│   │   └── 记忆刷新 (flush_memories)
│   └── 后置处理 (轨迹保存/会话持久化)
└── 支持系统
    ├── Memory (flush_memories, 独立于主循环)
    ├── Skill (skill_nudge, 迭代计数触发)
    └── Tool (并发执行, 独立线程池)
```

---

## 核心发现（13项 Hermes 独有设计）

### 1. 记忆注入：用户消息，不是系统提示词

**问题**：记忆内容应该注入到哪里？

**Hermes 答案**：注入到**用户消息**，而不是系统提示词。

**原理**：
- 系统提示词 = 缓存前缀（CP 命中核心）
- 记忆 = 动态内容，每次变化导致 CP 未命中
- 注入用户消息 = 系统提示词不变 = CP 高命中

**代码位置**：`run_conversation` line 7896-7907
```python
if idx == current_turn_user_idx and msg.get("role") == "user":
    _injections = []
    if _ext_prefetch_cache:
        _fenced = build_memory_context_block(_ext_prefetch_cache)
        _injections.append(_fenced)
    if _plugin_user_context:
        _injections.append(_plugin_user_context)
    if _injections:
        _base = api_msg.get("content", "")
        api_msg["content"] = _base + "\n\n" + "\n\n".join(_injections)
```

**关键**：`api_messages` 是副本，不修改原始 `messages`。所以会话持久化保存的是原始消息，API 调用用的是注入后的副本。

**qclaw 落地**：在 `memory_pipeline.py` 的调用侧，记忆注入到用户消息而非系统消息。

---

### 2. flush_memories：Sentinel 标记 + 原子性清理

**问题**：上下文压缩前，如何安全提取记忆？

**Hermes 答案**：
1. 给 flush 消息加唯一 sentinel：`f"__flush_{id(self)}_{time.monotonic()}"`
2. 单独调用，只暴露 memory 工具
3. API 调用结束后，用 sentinel 精确切除 flush 消息
4. finally 块保证清理（即使 API 调用失败）

```python
# 添加 flush 消息
_sentinel = f"__flush_{id(self)}_{time.monotonic()}"
flush_msg = {"role": "user", "content": flush_content, "_flush_sentinel": _sentinel}
messages.append(flush_msg)

try:
    response = call_llm(task="flush_memories", messages=api_messages, ...)
    # 执行 memory tool calls
finally:
    # 精确切除：只删 flush 消息之后的内容
    while messages and messages[-1].get("_flush_sentinel") != _sentinel:
        messages.pop()
    if messages and messages[-1].get("_flush_sentinel") == _sentinel:
        messages.pop()
```

**qclaw 落地**：在 `memory_pipeline.py` 的 Phase2 中，使用 sentinel 机制确保压缩前记忆提取的原子性。

---

### 3. IterationBudget + Grace Call

**问题**：如何控制迭代次数？

**Hermes 答案**：IterationBudget 类 + 宽限调用

```python
class IterationBudget:
    def __init__(self, max_total: int):
        self._used = 0
        self.max_total = max_total

    def consume(self) -> bool:
        """Returns False when budget exhausted"""
        if self._used >= self.max_total:
            return False
        self._used += 1
        return True

    def refund(self) -> None:
        """Refund on API error - retry shouldn't count"""
        if self._used > 0:
            self._used -= 1
```

**Grace Call**：预算耗尽后，给模型一次"宽限"，让它自己决定是否结束。

```python
while api_call_count < self.max_iterations and self.iteration_budget.remaining > 0 or self._budget_grace_call:
    if self._budget_grace_call:
        self._budget_grace_call = False  # 消费宽限
    elif not self.iteration_budget.consume():
        break  # 真正的停止
```

**qclaw 落地**：evolver.py 新增 `IterationBudget` 类，工具执行超时时 refund。

---

### 4. TCP 连接健康检查（每轮前）

**问题**：provider 故障后如何恢复？

```python
# 在 run_conversation 开始时（第7573行）
if self.api_mode != "anthropic_messages":
    try:
        if self._cleanup_dead_connections():
            self._emit_status(
                "Detected stale connections — cleaned up automatically."
            )
    except Exception:
        pass
```

**qclaw 落地**：可选功能。在 `qclaw_loops.py` 的 CI Loop 模式中，每次迭代前检查。

---

### 5. 外部记忆预取（循环前一次，缓存全轮）

**问题**：记忆检索在每次工具调用时都执行？

**Hermes 答案**：只在循环开始前调用一次，结果缓存供全轮使用。

```python
# 在主循环之前（第7814行）
_ext_prefetch_cache = ""
if self._memory_manager:
    _ext_prefetch_cache = self._memory_manager.prefetch_all(_query) or ""
```

**原理**：工具调用10次 = 10次延迟 + 10次成本。只检索一次，注入用户消息，全轮复用。

**qclaw 落地**：在 `memory_pipeline.py` 的调用侧，记忆预取一次注入，不在每次工具调用时重复检索。

---

### 6. 对话压缩的 Sentinel 保护

**问题**：压缩逻辑本身会丢失消息？

**Hermes 答案**：压缩前必须 flush_memories，sentinel 保护压缩范围。

```python
# _compress_context 中（第6551行附近）
# 压缩前先 flush
if messages and messages[-1].get("_flush_sentinel"):
    return  # 已经在 flush 中，不重复压缩
```

---

### 7. 4种错误恢复机制

| 错误类型 | 恢复策略 | 触发条件 |
|---------|---------|---------|
| 429 Rate Limit | 等待 + 重试 | HTTP 429 |
| Auth Error | credential pool 切换 | HTTP 401/403 |
| Length Continuation | 重试 + 截断 | HTTP 400 + length |
| Model Fallback | 降级模型 | RuntimeError |

---

### 8. 并发工具执行：3个护栏

```python
# _execute_tool_calls_concurrent
max_workers = min(num_tools, _MAX_TOOL_WORKERS)  # 不超过3
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(_run_tool, ...) for i, tc in enumerate(parsed_calls)]
    concurrent.futures.wait(futures)  # 等待全部完成
```

**护栏**：
1. `_MAX_TOOL_WORKERS = 3` — 限制并发度
2. `enforce_turn_budget(turn_tool_msgs)` — 每轮预算
3. `_should_parallelize_tool_batch()` — 判断是否真的需要并行

---

### 9. 技能触发器：迭代计数

```python
# skill nudge (line 7876)
if self._skill_nudge_interval > 0 and "skill_manage" in self.valid_tool_names:
    self._iters_since_skill += 1

# 主循环结束后检查（不在循环内！）
if self._iters_since_skill >= self._skill_nudge_interval:
    # 触发 skill_manage 建议
    self._spawn_background_review(...)
```

**原理**：不是单次成功触发，而是**累积迭代次数**触发。

---

### 10. Anthropic Prompt Caching 自动检测

```python
# 自动检测 Claude + OpenRouter 组合
if "claude" in model and self._is_openrouter_url():
    api_messages = apply_anthropic_cache_control(
        api_messages,
        cache_ttl=self._cache_ttl,
        native_anthropic=(self.api_mode == 'anthropic_messages')
    )
```

**qclaw落地**：如果 qclaw 模型路由支持 Anthropic，在 API 调用前自动检测并应用缓存控制。

---

### 11. API消息标准化：strip + sort_keys

```python
# 归一化消息格式，确保前缀匹配
for am in api_messages:
    if isinstance(am.get("content"), str):
        am["content"] = am["content"].strip()  # 去除多余空格

# 归一化工具参数 JSON
args_obj = json.loads(tc["function"]["arguments"])
tc["function"]["arguments"] = json.dumps(args_obj, separators=(",", ":"), sort_keys=True)
```

**原理**：确保 token 前缀比特级一致，使 KV 缓存命中率最大化。

---

### 12. 中断隔离：线程级别

```python
# 主循环开始前记录执行线程 ID
self._execution_thread_id = threading.current_thread().ident

# interrupt() 只中断这个线程
def interrupt(self, message: str = None):
    self._interrupt_requested = True
    self._interrupt_message = message
    # 信号只发给 _execution_thread_id
```

---

### 13. 插件钩子系统（pre_llm_call）

```python
# 在主循环每次 API 调用前
_pre_results = _invoke_hook(
    "pre_llm_call",
    session_id=self.session_id,
    user_message=original_user_message,
    conversation_history=list(messages),
    ...
)
# 结果注入用户消息，不修改系统提示词
```

---

## 与 qclaw 的集成点

| Hermes 设计 | qclaw 落地文件 | 优先级 |
|------------|--------------|--------|
| 记忆注入用户消息 | `memory_pipeline.py` | P0 |
| Sentinel flush | `memory_pipeline.py` Phase2 | P0 |
| IterationBudget + grace | `evolver.py` | P1 |
| 外部记忆预取一次 | `memory_pipeline.py` | P1 |
| 4种错误恢复 | `qclaw_eval.py` | P2 |
| 并发3线程 | `qclaw_loops.py` Infinite Loop | P1 |
| 迭代计数技能触发 | `instinct_model.py` | P2 |

---

## 与其他 Hermes 文件的关系

```
run_agent.py (主循环)
    │
    ├── display.py ────── KawaiiSpinner/皮肤引擎/文件快照
    ├── memory_manager.py ── 外部记忆管理器
    ├── memory_provider.py ─ 记忆提供者（内置/Honcho/Mem0）
    ├── context_compressor.py ── 上下文压缩（_compress_context）
    ├── prompt_caching.py ── Anthropic CP 自动检测
    ├── insights.py ───────── 轨迹/洞察提取
    ├── skill_commands.py ─── skill_manage 工具实现
    ├── credential_pool.py ── 多凭证管理（auth恢复）
    └── rate_limit_tracker.py ── 429 追踪
```

---

## 最核心的设计哲学

> **"API调用时间 vs 持久化时间分离"**

Hermes 大量使用这个模式：
- `api_messages` = API 调用副本（可注入/归一化）
- `messages` = 持久化副本（保持原始）

这使得：
1. 记忆注入不影响会话历史大小
2. 压缩不影响 API 调用格式
3. 插件钩子不影响会话持久化
