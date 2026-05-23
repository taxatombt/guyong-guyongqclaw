---
name: tdai-memory-pipeline
description: |
  TencentDB-Agent-Memory L0→L1→L2→L3 分层记忆管道 Python 版。
  调度器 (MemoryPipelineManager) + Checkpoint 持久化 + 三层记忆提取。
  整合 mem0 的混合检索 + evolver.py 的 Agent 事实记录。

metadata:
  openclaw:
    emoji: "🧠"
---

# TDAI Memory Pipeline — L0→L1→L2→L3 分层记忆调度器

Python port of TencentDB-Agent-Memory (GitHub 2k stars). 将原始对话 L0 → 原子事实 L1 → 场景 L2 → 人设 L3。

## 核心组件

### MemoryPipelineManager (`tdai_memory_pipeline.py`)

主调度器，管理 L0→L1→L2→L3 的自动触发。

**关键特性：**
- **Warm-up mode**: 新会话 L1 触发阈值 1→2→4→...→N
- **L1 idle timeout**: 用户停止打字后自动触发 L1
- **L2 downward-only timer**: 仅可提前，不可推迟（防止饥饿）
- **Session GC**: 淘汰冷会话
- **Checkpoint 恢复**: crash 后可恢复所有状态

**快速开始：**
```python
from tdai_memory_pipeline import create_default_pipeline, CapturedMessage
import datetime

mgr = create_default_pipeline(data_dir=".tdai_memory", every_n=5)
mgr.set_l1_runner(my_l1_fn)
mgr.set_l2_runner(my_l2_fn)
mgr.set_l3_runner(my_l3_fn)
mgr.start()

# 每次对话轮次
ts = datetime.datetime.now().isoformat()
msg = CapturedMessage(role="user", content="消息内容", timestamp=ts)
mgr.notify_conversation("session-key", [msg])

# 关闭
mgr.destroy()
```

### CheckpointManager

原子写入 JSON checkpoint (`pipeline_checkpoint.json`)，tmp+rename 防崩溃损坏。

### SerialQueue / ManagedTimer

- **SerialQueue**: 串行任务队列（L1/L2/L3 各一个）
- **ManagedTimer**: 可重置/向下提前的定时器（L1 idle timer + L2 schedule timer）

## L1 / L2 / L3 Runner 接口

Pipeline 本身不执行具体的记忆提取，而是通过 runner 回调实现。

### L1 Runner: `fn(session_key, messages) -> None`
- messages: `List[CapturedMessage]`
- 职责：从原始消息提取结构化事实
- 默认实现: `create_l1_runner(workspace_dir)` → 调用 evolver.py 的 `record_agent_fact()`

### L2 Runner: `fn(session_key, cursor) -> None`
- cursor: `str` (ISO timestamp) 上次提取位置
- 职责：将 L1 事实聚合成场景块

### L3 Runner: `fn() -> None`
- 无参数
- 职责：从所有场景生成全局人设 (persona)
- 默认实现: `create_l3_runner(workspace_dir)` → 生成 `persona_tdai.md` stub

## 与现有 qclaw 系统集成

### 已集成
- `mem0_hybrid_search.py` — 多信号融合检索（L1/L2 检索增强）
- `mem0_entity_extractor.py` — 实体链接（L1 结构化提取）
- `evolver.py record_agent_fact()` — L1 事实记录
- `SYSTEM.md` — 六层架构 ③记忆层 + ⑥进化层

### 待集成
- L1: 接入 OpenClaw LLM 做结构化提取（替代 stub）
- L2: 场景聚合（目前是 stub）
- L3: LLM 生成 persona（目前是统计 stub）
- Mermaid 符号记忆: 上下文卸载（Context Offloading）

## 与 Codex / Hermes / ECC 对比

| 系统 | 记忆分层 | 自动化 | Warm-up | 上下文卸载 |
|------|----------|--------|----------|-------------|
| **TDAI** | L0→L1→L2→L3 四层 | ✅ 全自动 | ✅ | ⏳ (Mermaid stub) |
| Codex | Phase1→Phase2 两层 | ✅ | ❌ | ✅ render_workspace_tree |
| Hermes | 内置 JSONL + 外部插件 | ⏳ 部分 | ❌ | ❌ |
| ECC | instinct + evolver | ⏳ 部分 | ❌ | ❌ |

## 配置参数

```python
PipelineConfig(
    every_n_conversations=5,          # L1 稳态触发阈值
    enable_warmup=True,               # 是否启用 warm-up
    l1_idle_timeout_seconds=600,       # L1 空闲超时 (10 min)
    l2_delay_after_l1_seconds=90,      # L1 完成后延迟多久触发 L2
    l2_min_interval_seconds=900,       # L2 最小间隔 (15 min)
    l2_max_interval_seconds=3600,      # L2 最大间隔 (1 hour)
    l2_session_active_window_hours=24, # 会话活跃窗口
    persona_trigger_every_n_memories=50, # L3 触发频率
)
```

## Checkpoint 格式

文件位置: `.metadata/pipeline_checkpoint.json`

```json
{
  "last_captured_timestamp": 0.0,
  "total_processed": 0,
  "memories_since_last_persona": 0,
  "pipeline_states": {
    "session-key": {
      "conversation_count": 0,
      "last_active_time": 1715760000.0,
      "warmup_threshold": 0,
      "l2_pending_l1_count": 0,
      "l2_last_extraction_time": ""
    }
  }
}
```

## 运行测试

```bash
E:\PYTON\python.exe tdai_memory_pipeline.py
```

应输出：
```
=== TDAI Memory Pipeline Demo ===
L1[demo-session]: extracted from 1 messages...
Warm-up advanced → next=2
Warm-up graduated → steady-state
Final queue sizes: {'l1_size': 0, ...}
=== Demo complete ===
```

## 从 TypeScript 源码的关键设计提取

1. **Split-state Checkpoint**: runner_states 和 pipeline_states 分离，防止互相覆盖
2. **Atomic capture**: captureAtomically() 在读-改-写锁内执行，消除竞态窗口
3. **Downward-only L2 timer**: `tryAdvanceTo()` — 只能提前，不能推迟
4. **Warm-up mode**: 新会话 threshold 指数增长，快速建立初始记忆
5. **Session GC**: 按 last_active_time 淘汰冷会话
6. **与 L3 的 Persona 集成**: 全局 dedup + 可重入的 L3 queue

## 文件清单

| 文件 | 大小 | 状态 |
|------|------|------|
| `tdai_memory_pipeline.py` | ~47KB | ✅ 完成，测试通过 |
| `skills/SKILL-tdai-memory.md` | ~8KB | ✅ 本文件 |
| `ai_agent_study/SYSTEM.md` | 更新 | 🔄 进行中 |

## 来源

Tencent/TencentDB-Agent-Memory (GitHub, 2k stars)
- TypeScript 源码 3000+ 行
- 架构设计文档 2000+ 行
- 已提取学习资产：`memory-pipeline-design.md`, `memory-architecture.md`, `context-offloading.md`