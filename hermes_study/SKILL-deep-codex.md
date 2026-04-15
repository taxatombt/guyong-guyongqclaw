# SKILL-deep-architecture.md
# Hermes AIAgent × Codex Phase1/2 深度对比研究

**时间**: 2026-04-13  
**落地**: `hermes_study/SKILL-deep.md` + `codex_rs_study/SKILL-deep.md`

---

## 一、两大系统架构对比

| 维度 | Hermes (Python) | Codex (Rust) |
|------|----------------|--------------|
| 记忆存储 | SQLite + JSONL | SQLite (sqlx) |
| 执行模型 | ThreadPool + 同步 | async/await + tokio |
| 压缩触发 | 主动预检 (Preflight) | 被动累积 |
| 记忆粒度 | Turn 级 flush | Thread 级 consolidation |
| 工具并发 | 3线程限制 | 按需并行 |

---

## 二、Codex Phase1/Phase2 机制深度解析

### 核心概念

**Phase1 = Per-Rollout Memory Extraction**（每个对话/会话独立运行）
- 触发时机：每个会话结束时
- 输出：`stage1_outputs` 表（一行 = 一个会话的记忆摘要）
- 状态机：PENDING → RUNNING → SUCCEEDED/FAILED
- 全局并发上限：`stage1_running_cap`

**Phase2 = Global Consolidation**（全局唯一运行）
- 触发时机：Phase1 watermark 推进时
- 输入：多个 Phase1 输出的集合
- 输出：`memory_summary.md`（全局记忆）
- 锁机制：全局互斥（stale lease 允许接管）

### Selection Diff 算法（最精华）

```sql
-- 当前选择（本次 Phase2 要处理的）
SELECT thread_id, raw_memory, rollout_summary, usage_count, last_usage
FROM stage1_outputs
WHERE memory_mode = 'enabled'
  AND (raw_memory != '' OR rollout_summary != '')
  AND (last_usage >= cutoff OR (last_usage IS NULL AND source_updated_at >= cutoff))
ORDER BY usage_count DESC, last_usage DESC, source_updated_at DESC
LIMIT n

-- 上次选择（用于计算 diff）
SELECT thread_id FROM stage1_outputs WHERE selected_for_phase2 = 1

-- diff = previous - current = removed threads
```

**结果 = Selection Diff**:
```python
Phase2InputSelection:
    selected: List[Stage1Output]      # 本次要处理的（added + retained）
    previous_selected: List[...]     # 上次处理的
    retained_thread_ids: Vec<Id>    # 交集（既在上次又在本selected）
    removed: Vec<ThreadRef>          # diff：上次有，本次没有
```

### 遗忘机制（Forgetting）

```rust
// 保留策略（按优先级）：
// 1. 当前正在运行的 Phase1 不删除
// 2. selected_for_phase2 = 1 的行不删除
// 3. usage_count > 0 的行（即使超过 cutoff）
// 4. 超过 max_unused_days 的未使用行 → 删除

prune_stage1_outputs_for_retention(max_unused_days=30, limit=100)
```

### 污染追踪（Pollution）

当线程的 `memory_mode` 变化时，标记为 "polluted"，从 Phase2 选择中排除。

---

## 三、Hermes AIAgent 主循环 13 项深度设计

### 1. API调用时间 vs 持久化时间分离

```python
# 原始消息（持久化用）
messages = conversation_history.copy()

# API 调用副本（可注入/归一化）
api_messages = []
for msg in messages:
    api_msg = msg.copy()
    # 注入：记忆 + 插件上下文
    if idx == current_turn_user_idx:
        api_msg["content"] += injected_memory
    # 归一化：strip + sort_keys
    api_msg = normalize(api_msg)
    api_messages.append(api_msg)
```

### 2. flush_memories Sentinel 机制

```python
_sentinel = f"__flush_{id(self)}_{time.monotonic()}"
flush_msg = {"role": "user", "content": flush_content, "_flush_sentinel": _sentinel}
messages.append(flush_msg)

try:
    # 单独调用，只有 memory 工具
    response = call_llm(messages=api_messages, tools=[memory_tool])
finally:
    # 精确切除 flush 及之后的内容
    while messages and messages[-1].get("_flush_sentinel") != _sentinel:
        messages.pop()
    messages.pop()  # 移除 sentinel
```

### 3. IterationBudget + GraceCall

```python
# 每轮开始时重置
self.iteration_budget = IterationBudget(self.max_iterations)

# 主循环条件
while (api_call_count < self.max_iterations 
       and self.iteration_budget.remaining > 0) \
       or self._budget_grace_call:
    if self._budget_grace_call:
        self._budget_grace_call = False  # 消费宽限，不计数
        break  # 宽限后直接退出
    if not self.iteration_budget.consume():
        break  # 真正停止
```

### 4. 记忆注入用户消息（不修改系统提示词）

```python
# 注入到用户消息，而非系统消息
if idx == current_turn_user_idx:
    api_msg["content"] = original_user_message + "\n\n" + memory_context
```

### 5. 外部记忆预取一次，缓存全轮

```python
# 在主循环开始前，只调用一次
_ext_prefetch_cache = self._memory_manager.prefetch_all(original_user_message)

# 注入后，循环内所有迭代复用同一个 prefetch 结果
# 10个工具调用 = 0次额外检索
```

### 6. 主动预压缩（前摄式）

```python
# 在进入主循环之前就检查
if _preflight_tokens >= threshold:
    for _pass in range(3):  # 最多3轮压缩
        messages = compress(messages)
        if len(messages) < orig_len:
            break
```

### 7. Anthropic Prompt Caching 自动检测

```python
if "claude" in model and self._is_openrouter_url():
    api_messages = apply_anthropic_cache_control(
        api_messages,
        cache_ttl=self._cache_ttl,
        native_anthropic=(self.api_mode == 'anthropic_messages')
    )
```

### 8. 4种错误恢复

| 错误 | 策略 | 关键代码 |
|------|------|---------|
| 429 | 等待 + 重试 | rate_limit_tracker |
| Auth | credential_pool | _recover_with_credential_pool |
| Length | 截断 + 重试 | length_continue_retries |
| Fallback | 降级模型 | _try_activate_fallback |

### 9. TCP 连接健康检查（每轮前）

```python
# 防止僵尸连接导致挂起
if self._cleanup_dead_connections():
    self._emit_status("Detected stale connections — cleaned up.")
```

### 10. 工具并发 3 线程 + 预算

```python
max_workers = min(num_tools, _MAX_TOOL_WORKERS)  # 不超过3
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(_run_tool, ...) for tc in parsed_calls]
    concurrent.futures.wait(futures)

# 每轮预算限制
enforce_turn_budget(turn_tool_msgs)
```

### 11. 技能触发：迭代计数累积

```python
# 在循环内计数，在循环外检查
self._iters_since_skill += 1

# 主循环结束后
if self._iters_since_skill >= self._skill_nudge_interval:
    self._spawn_background_review(...)
```

### 12. 中断隔离：线程级别

```python
self._execution_thread_id = threading.current_thread().ident
# interrupt() 只发信号给这个线程
```

### 13. 插件钩子：pre_llm_call

```python
_pre_results = _invoke_hook("pre_llm_call", ...)
_ctx_parts = [r["context"] for r in _pre_results if r.get("context")]
# 注入用户消息，不修改系统提示词
```

---

## 四、与 qclaw 的集成方案

### 立即可落地

| 设计 | qclaw 落地文件 | 状态 |
|------|--------------|------|
| IterationBudget + GraceCall | `evolver.py` | ⏳ 待实现 |
| Selection Diff (added/retained/removed) | `memory_pipeline.py` | ⏳ 待实现 |
| 记忆注入用户消息 | `memory_pipeline.py` | ✅ 已有概念 |
| TCP 健康检查 | `qclaw_loops.py` CI Loop | ⏳ 可选 |
| 外部记忆预取一次 | `memory_pipeline.py` | ⏳ 待实现 |
| 工具并发 3 线程 | `qclaw_loops.py` Infinite | ✅ 已有 |

### IterationBudget 实现方案

```python
class IterationBudget:
    def __init__(self, max_total: int):
        self._used = 0
        self.max_total = max_total
        self._grace_used = False

    def consume(self) -> bool:
        """Returns False when budget exhausted"""
        if self._used >= self.max_total:
            return False
        self._used += 1
        return True

    def refund(self) -> None:
        """Call on error — don't count against budget"""
        if self._used > 0:
            self._used -= 1

    def remaining(self) -> int:
        return max(0, self.max_total - self._used)

    def grace_call(self) -> bool:
        """One final call after budget exhausted"""
        if self._grace_used:
            return False
        self._grace_used = True
        return True
```

### Selection Diff 实现方案

```python
@dataclass
class Phase2SelectionDiff:
    selected: list       # 当前选择的记忆（added + retained）
    previous: list       # 上次选择的
    retained: list       # 交集（上次和本次都有）
    added: list          # 本次新增（selected - previous）
    removed: list         # diff：上次有，本次没有

def compute_selection_diff(current: list, previous: list) -> Phase2SelectionDiff:
    current_ids = {m["thread_id"] for m in current}
    prev_ids = {m["thread_id"] for m in previous}
    
    retained_ids = current_ids & prev_ids
    added_ids = current_ids - prev_ids
    removed_ids = prev_ids - current_ids
    
    return Phase2SelectionDiff(
        selected=current,
        previous=previous,
        retained=[m for m in current if m["thread_id"] in retained_ids],
        added=[m for m in current if m["thread_id"] in added_ids],
        removed=[m for m in previous if m["thread_id"] in removed_ids],
    )
```

---

## 五、最核心的设计哲学

**1. 分离原则**
- API 调用时间 ≠ 持久化时间
- 并发执行 ≠ 无限制并发
- 记忆检索 ≠ 每次都检索

**2. 前摄式 > 被动式**
- 预压缩（进入循环前）
- 预取（循环开始前）
- 健康检查（每轮前）

**3. 原子性 + 可恢复性**
- Sentinel 保护关键操作
- 错误时 refund，不计数
- 宽限调用让模型自己决定结束

**4. 遗忘也是能力**
- Codex: usage_count + max_unused_days 双重过滤
- 不保留所有记忆，只保留有用的
