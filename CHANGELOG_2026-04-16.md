# Changelog — 2026-04-16

> 生成时间：2026-04-16 13:40 CST
> GitHub：taxatombt/guyong-guyong

---

## 本次提交（Commit `17d0617`）

### 新增文件

| 文件 | 大小 | 内容 |
|------|------|------|
| `hermes_deep_study_20260416.md` | 9.7KB | Hermes记忆+进化系统深度研究落地文档 |

### 修改文件

| 文件 | 变更 | 说明 |
|------|------|------|
| `qclaw_compactor.py` | 迭代压缩修复 | `_previous_summary` 存实际摘要内容（不是LLM prompt），`_build_summary_prompt` 支持 `previous_actual_summary` 参数 |
| `agents/agent_types.py` | 新增常量和参数 | `DELEGATE_BLOCKED_TOOLS`（封锁7个危险工具）+ `MAX_DELEGATE_DEPTH=2` + `MAX_CONCURRENT_CHILDREN=3` |
| `MEMORY.md` | 知识更新 | Hermes深度研究（记忆+进化）+ qclaw落地记录 + evolver补录 |
| `.evolver_db.json` | evolver +3条 | 共108条规则 |

---

## 来源：Hermes Agent 深度研究

**源码**：`E:\ai\资源\8hermes-agent-main/hermes-agent-main`
**研究文件**：memory_manager.py / memory_provider.py / context_compressor.py / insights.py / delegate_tool.py / trajectory_compressor.py

### 记忆系统三大发现

1. **MemoryManager 1+1架构**
   - 内置provider始终存在 + 最多1个外部provider
   - 外部provider超限 → 打warning拒绝（防tool schema膨胀）
   - 8个生命周期钩子：initialize / prefetch / sync / on_turn_start / on_pre_compress / on_delegation / on_memory_write
   - 记忆围栏 `<memory-context>` 防止模型把记忆当用户输入

2. **MemoryProvider ABC**
   - 9个核心方法 + 6个可选hook
   - `is_available()` 不联网只检查配置 → 快速启动判断
   - `on_pre_compress()` 让provider在压缩前提取洞察
   - `on_delegation()` 让父agent观察子代理工作结果

3. **ContextCompressor 5步压缩算法**
   - Step1: Prune tool results（无LLM调用）
   - Step2: Protect head（前3条）
   - Step3: Protect tail（10% token预算）
   - Step4: Summarize middle（结构化LLM摘要）
   - Step5: Iterative update（`_previous_summary` 存实际摘要内容）

### 子代理封锁机制

来自 `delegate_tool.py`：
```python
DELEGATE_BLOCKED_TOOLS = frozenset([
    "subagents",          # 禁止递归委托
    "sessions_send",       # 禁止跨会话消息
    "exec",                # 子代理应推理而非写脚本
    "edit", "write",       # 子代理不直接写文件
    "process",             # 禁止进程管理
    "canvas",              # 禁止canvas操作
])
MAX_DELEGATE_DEPTH = 2      # parent→child→孙子拒绝
MAX_CONCURRENT_CHILDREN = 3 # 最多3个并发
```

---

## 待落地清单

| 优先级 | 项目 | 来源 |
|--------|------|------|
| P1 | TrajectoryCompressor（轨迹压缩用于训练数据）| Hermes |
| P1 | memory_pipeline.py打通on_pre_compress→持久记忆 | Hermes |
| P2 | multi_agent_dispatcher加并发数限制 | Hermes DelegateTool |
| P3 | self_model_insights_bridge激活 | Hermes InsightsEngine |

---

_本文件由 qclaw 自动生成，push 后同步到 GitHub_
