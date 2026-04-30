# 学习归档 - agents系统 + 进化系统

> 从 MEMORY.md 迁出，2026-04-24 精简时归档

## agents/ 运行时完整实现（2026-04-13，完成）

7个模块，55个API导出：

| 文件 | 字节 | 功能 |
|------|------|------|
| `agent_types.py` | 11,814 | 6种Agent角色 |
| `tool_pipeline.py` | 42,559 | 15步管道 + 22危险模式 + HookDispatcher |
| `exec_adapter.py` | 10,635 | 执行适配器 + SessionLifecycleManager |
| `multi_agent_dispatcher.py` | 15,179 | 调度器（轮询+4种路由策略）|
| `tool_registry.py` | 19,756 | 23工具注册，危险模式检测 |
| `prompt_cache_manager.py` | 13,955 | Anthropic Prompt Cache + TokenBudget |
| `event_bus.py` | 8,195 | 10事件类 + JSONL导出 |
| `token_budget.py` | 10,970 | 三维预算 + 5级降级(Hermes Guide) |

**版本**：2.1.0

## skill_evolution 系统

```
skill_evolution/
├── types.py          # SkillData/Rule/EvolverConfig
├── registry.py       # SkillRegistry（78技能）
├── evolver.py        # 核心进化引擎（~48KB）
├── integrate.py      # evolver_db → skill_registry
└── __init__.py
```

FIX进化时skill_id复用父节点hash，仅改版本号。confidence公式：success_rate × (0.7 + 0.2×min(tc/10,1) + 0.1×(priority+1)/10)

## Claude Code 7原则落地（2026-04-13）

1. 不信任模型自觉性 → 各角色system_prompt
2. 角色拆分 → Verify/Explore/Plan Agent
3. 工具治理 → 15步pipeline
4. 上下文预算 → qclaw_compactor + PromptCache
5. 安全互不绕过 → tool_pipeline._resolve
6. 模型感知 → agents/__init__导出
7. 第二天处理 → exec_adapter.py cleanup chain

## 进化系统v2（evolver + self_review + heartbeat）

三个程序：evolver.py（规则引擎+熔断器）、self_review.py（复盘+教训）、heartbeat_self_review.py（心跳自检）

触发：每次任务完成→evolver.record+self_review | 新任务→best_method | 心跳→check_and_remind | 每日→3条最重要经验

## Memory System v4.0（2026-04-20）

来源：Claude-Mem + MemPalace

落地：memory/目录下5文件
- memory_hooks.py（5生命周期Hook）
- palace.py（Wing/Room/Drawer存储）
- memory_worker.py（HTTP API+异步队列）
- knowledge_graph.py（实体+关系+图遍历）
- memory_integration.py（统一接口）

## codex execpolicy落地（2026-04-13）

tool_pipeline.py v2.0：justification字段 + PromptDecision + FailedAbort级联
