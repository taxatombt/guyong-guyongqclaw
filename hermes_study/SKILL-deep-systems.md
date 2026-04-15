# SKILL-deep-systems.md
# Hermes × Codex 深度系统研究 — 完整成果

**时间**: 2026-04-13  
**来源文件**: 6个核心系统文件  
**落地**: `hermes_study/` + `memory_pipeline.py`

---

## 一、context_compressor.py — 上下文压缩完整算法

**文件**: `E:\Hermes\agent\context_compressor.py` (33KB, 778行)

### 核心设计参数

```python
threshold_percent=0.50    # 50% 上下文时触发压缩
protect_first_n=3        # 前3条消息永远保留
protect_last_n=20        # 后20条消息永远保留
summary_target_ratio=0.20  # 压缩到上下文20%的大小
tail_token_budget=20000   # 尾部保护 ~20K tokens
min_summary_tokens=1000   # 摘要最小 tokens
```

### 压缩算法（4步）

```
Step 1: 工具结果剪枝（无LLM调用，廉价预热）
Step 2: 保护头部（前3条）+ 尾部（~20K tokens）
Step 3: 中间段 LLM 摘要
Step 4: 清理孤立 tool_call/result 对
```

### 关键1：工具结果剪枝

```python
# 从后向前遍历，保护最近 protect_tail_tokens 的内容
for i in range(len(result) - 1, -1, -1):
    accumulated += msg_tokens
    if accumulated > protect_tail_tokens:
        boundary = i
        break
```

### 关键2：Structured Summary Template

```python
## Goal
[What the user is trying to accomplish]

## Constraints & Preferences
[User preferences, coding style, constraints]

## Progress
### Done
[Completed work — specific file paths, commands]
### In Progress
[Work currently underway]

## Decisions & Key Learnings
[Important decisions, patterns, gotchas]

## Next Steps
[Immediate next actions]
```

### 关键3：Boundary Alignment（防止切断工具对）

```python
def _align_boundary_forward(messages, idx):
    # 如果 idx 是 tool result，向后推到非 tool 消息
    while messages[idx].role == 'tool':
        idx += 1
    return idx

def _align_boundary_backward(messages, idx):
    # 如果 idx-1 是连续 tool result，向后推找到父 assistant
    while messages[idx-1].role == 'tool':
        idx -= 1
    if messages[idx-1].role == 'assistant' and messages[idx-1].tool_calls:
        idx = idx - 1  # 包含整个 tool_call/result 组
    return idx
```

### 关键4：迭代摘要（vs 每次从零开始）

```python
if self._previous_summary:
    # 增量更新：保留已有信息 + 添加新进展
    prompt = f"""Update the summary using this exact structure.
    PRESERVE all existing information that is still relevant.
    ADD new progress from the new turns."""
```

---

## 二、prompt_caching.py — Anthropic Prompt Caching

**文件**: `E:\Hermes\agent\prompt_caching.py` (73行，纯函数，无状态)

### system_and_3 策略

```
Breakpoint 1: System prompt（所有轮次稳定）
Breakpoint 2: 最后第3条非系统消息
Breakpoint 3: 最后第2条非系统消息
Breakpoint 4: 最后第1条非系统消息
```

### 适用条件

```python
if "claude" in model and self._is_openrouter_url():
    api_messages = apply_anthropic_cache_control(api_messages)
# 节省 ~75% 输入 token 成本
```

### 实现逻辑

```python
def apply_anthropic_cache_control(messages, cache_ttl="5m"):
    messages = copy.deepcopy(messages)
    marker = {"type": "ephemeral", "ttl": cache_ttl}
    
    # 1. System prompt
    if messages[0].role == "system":
        messages[0]["content"] = [{"type": "text", "text": ..., "cache_control": marker}]
    
    # 2-4. Last 3 non-system messages
    non_sys = [i for i in range(len(messages)) if messages[i].role != "system"]
    for idx in non_sys[-3:]:
        messages[idx]["cache_control"] = marker
    
    return messages
```

---

## 三、insights.py — 用量报告生成

**文件**: `E:\Hermes\agent\insights.py` (33KB, 791行)

### 报告结构

```python
{
    "overview": {
        "total_sessions", "total_messages", "total_tool_calls",
        "total_tokens", "total_input_tokens", "total_output_tokens",
        "total_cache_read_tokens", "total_cache_write_tokens",
        "estimated_cost", "actual_cost", "total_hours",
        "avg_session_duration", "avg_messages_per_session",
    },
    "models": [...],     # 按模型分组的会话统计
    "platforms": [...],  # 按平台分组的统计
    "tools": [...],     # Top 15 工具使用排行
    "activity": {        # 按天/小时的活动模式
        "by_day": [...],
        "by_hour": [...],
    },
    "sessions": [...],   # Top 10 会话详情
}
```

### 关键公式

```python
# Cost estimation
estimated_cost = sum(estimate_cost(session) for session in sessions)

# Tool usage percentage
pct = (tool["count"] / total_calls * 100) if total_calls else 0

# Cache hit rate
cache_rate = cache_read_tokens / (input_tokens + cache_read_tokens)
```

### qclaw 落地思路

从 evolver_db.json 生成类似的报告：
- tool_usage: 每个工具的成功/失败次数
- sessions: 每次任务的记录
- cost: evolver confidence 变化趋势

---

## 四、realtime_context.py — 新会话上下文注入

**文件**: `codex-rs_core_src_realtime_context.rs` (492行)

### 核心函数

```rust
fn build_recent_work_section(cwd: &Path, recent_threads: &[ThreadMetadata]) -> Option<String>
fn build_current_thread_section(items: &[ResponseItem]) -> Option<String>
fn render_tree(root: &Path) -> Option<Vec<String>>
```

### 注入时机（新会话开始时）

1. 当前线程摘要（最近做的）
2. 近期相关线程（同样 cwd 的）
3. 工作区树结构

### 已落地 → `memory_pipeline.py` 的 `render_workspace_tree()`

```python
def render_workspace_tree(root: pathlib.Path, max_depth=3, max_entries=50) -> str:
    # 排除噪音目录：__pycache__, .git, node_modules, .venv
    # 缩进表示层级：  @ dir/  * file
    return """
@ workspace/
  @ _download/
    * README.md
  @ skills/
    @ codex-workflow/
      * SKILL.md
"""
```

---

## 五、context_manager_history.rs — 历史消息处理

**文件**: `codex-rs_core_src_context_manager_history.rs` (729行)

### 关键函数

```rust
fn normalize_history(&mut self, input_modalities: &[InputModality])
fn process_item(&self, item: &ResponseItem, policy: TruncationPolicy) -> ResponseItem
fn trim_pre_turn_context_updates(...)
fn truncate_function_output_payload(...)
```

### normalize_history 核心逻辑

1. 图像URL → 估算原始字节数，调整 token 计数
2. reasoning 内容单独计数
3. 多模态输入特殊处理

### truncate_function_output_payload

```rust
// 长工具输出截断策略
// HEAD + "...[N chars truncated]..." + TAIL
// 保留关键信息（错误消息、文件路径、命令）
```

---

## 六、与 qclaw 的集成总结

| 发现 | qclaw 落地文件 | 状态 |
|------|--------------|------|
| Structured Summary Template | `memory_pipeline.py` → 整合 prompt | ✅ 概念已有 |
| Tail Token Budget 保护 | `memory_pipeline.py` | ⏳ 待集成 |
| Boundary Alignment | `memory_pipeline.py` | ⏳ 待集成 |
| Anthropic Prompt Caching | `memory_pipeline.py` 调用侧 | ⏳ 待验证模型支持 |
| render_workspace_tree | `memory_pipeline.py` | ✅ 刚实现 |
| insights 报告结构 | `qclaw_eval.py` | ⏳ 可扩展 |

---

## 七、最核心的设计哲学

**1. Tail Protection > Head Protection**
- 旧记忆摘要（middle compression）比删除更有效
- 尾部保护 ~20K tokens，足够最近上下文

**2. 工具结果是最容易被压缩的**
- tool 输出截断不丢失关键信息
- 保留 HEAD + TAIL 格式

**3. 迭代摘要 > 从零摘要**
- 保留已有摘要 + 增量更新
- 避免信息丢失

**4. 新会话上下文 = 结构化注入**
- 不是把所有记忆都塞进去
- 而是：当前任务 + 近期相关 + 工作区树
