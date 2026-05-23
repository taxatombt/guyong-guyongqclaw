# qclaw AI Agent 知识体系 · 六层架构

> 顾庸整理 | 2026-05-11 | 从8子系统重构为6层流程
> 不是模块清单，是任务从进来→出去→学习的完整流向

---

## 总流：感知→认知→记忆→执行→安全→进化

```
用户消息到达
    │
    ▼
① 感知层：channel_adapter → 解析意图 → 分类任务
    │
    ▼
② 认知层：agent_types（四角色）→ 规划推理
    │
    ├── 简单任务 → 直接到④
    └── 复杂任务 → ③检索经验
    │
    ▼
③ 记忆层：evolver.best_method() → 检索相似任务经验
    │
    ▼
④ 执行层：tool_pipeline（15步）→ 工具调用
    │
    ▼
⑤ 安全层：PreToolUse Hook → 危险检测 → PermissionDecision
    │
    ▼
执行完成
    │
    ▼
⑥ 进化层：evolver.record() → self_review.run_review() → viki/raw/更新
    │
    ▼
下次任务（③直接使用本次经验）
```

---

## 各层项目贡献

### ① 感知层（Perceptual）

| 项目 | 贡献 |
|------|------|
| OpenClaw | 22渠道适配（QQ/微信/Telegram/Discord...） |
| qclaw | channel_adapter.py（统一消息格式） |
| 金策智算 | 快照收集器（实时状态追踪对比） |
| QuantDinger | 数据工厂模式（多源异构→标准化抽象） |

**qclaw 落地**：✅ `channel_adapter.py`

---

### ② 认知层（Cognitive）

| 项目 | 贡献 |
|------|------|
| Archon | 元认知三阶段（PLAN→MONITOR→REFLECT）|
| juhuo | 10D 判断系统 |
| ECC | instinct 原子行为级规则 |
| Hermes | Agent Loop（SSE流式处理）|
| Qlib | Meta Controller（自适应调整模型/策略）|
| 金策智算 | 分析代理（自动分析回测结果）|
| QuantDinger | LLM多代理研究团队（基本面/情绪/技术分析）|
| TradingAgents | 交易Agent协调（基本面/情绪/新闻/宏观/交易五路LLM）|
| Buffett Oracle Analyzer | 12模块分析框架 + 巴菲特计分卡(36分制) |

**qclaw 落地**：✅ `agent_types.py`（四角色）+ ⚪ 缺元认知PLAN/MONITOR

---

### ③ 记忆层（Memory）

| 项目 | 贡献 |
|------|------|
| Brain v1.1.8 | 三速记忆（工作/情节/语义）|
| OpenClaw | 四类记忆（working/episodic/semantic/procedural）|
| Codex | Phase1提取 + Phase2整合 + forgetting |
| Viki | LLM Wiki（增量编译、无RAG）|
| Qlib | Information Extractor（异构数据→有效信息）|
| QuantDinger | SQLite本地存储（隐私优先持久化）|
| TradingAgents | LangGraph checkpoint（崩溃恢复）+ Per-ticker SQLite |
| Buffett Oracle Analyzer | cases/analysis-reports/ 案例记忆库 |
| **mem0** | 多信号融合(BM25+语义+实体)、实体链接、Agent事实一等公民 |
| **TDAI** | L0→L1→L2→L3 四层自动提取 + warm-up + Checkpoint Recovery + downward-only timer + Session GC |
| **OpenViking** | 文件系统范式上下文管理 + 三分类(Resource/Memory/Skill) + 八类记忆 + 渐进式加载(L0/L1/L2) + Viking URI + Session→Commit→Memory管线 |

**qclaw 落地**：✅ `qclaw_unified_memory.py`（7合1）+ ✅ `mem0_hybrid_search.py` + ✅ `mem0_entity_extractor.py` + ✅ `evolver.record_agent_fact()` + ✅ `tdai_memory_pipeline.py`（47KB Pipeline调度器）+ ✅ `openviking_context.py`（10KB上下文管理器）

---

### ④ 执行层（Execution）

| 项目 | 贡献 |
|------|------|
| DeepSeek-TUI | 角色化Agent（general/explore/plan/review/implementer/verifier/custom）|
| Codex | ToolRegistry（23工具+危险模式）|
| Open Design | AgentAdapter（8种适配器）|
| Symphony | Orchestrator（polling→dispatch→reconciliation）|
| Qlib | 完整ML管道（Data→特征→训练→回测→部署）|
| 金策智算 | 三省六部制（分权协同、风控闭环）|
| QuantDinger | 端到端工作流（研究→策略→回测→实盘一体化）|
| TradingAgents | LangGraph DAG（多Agent协调）+ Pydantic结构化输出 |
| Buffett Oracle Analyzer | OpenClaw Skill 标准工作流（SKILL.md + 原则/方法分离）|

**qclaw 落地**：✅ `tool_pipeline.py`（15步）+ ✅ `MultiAgentDispatcher`（四角色）

---

### ⑤ 安全层（Security）

| 项目 | 贡献 |
|------|------|
| Codex | Hook 6事件（PreToolUse/PostToolUse/PermissionReq/SessionStart/UserPromptSubmit/Stop）|
| DeepSeek-TUI | Capacity Flow Guardrails（容量检查）|
| Archon | 10 Iron Laws（铁律系统）|
| 金策智算 | 一致性比较器（回测-实盘验证）+ 诊断报告 |
| TradingAgents | 3角色风控团队（风险评估/控制/合规）|
| Buffett Oracle Analyzer | evals.json 评估驱动质量门控 |

**qclaw 落地**：✅ `tool_pipeline.py`（15步，22危险模式）+ ⚪ 缺PostToolUse验证

---

### ⑥ 进化层（Evolution）

| 项目 | 贡献 |
|------|------|
| juhuo | 闭环进化（judgment→action→verify→learn）|
| Brain v1.1.8 | 置信度回检 |
| OpenSpace | Skill Evolution（CAPTURED/DERIVED/FIX + DAG）|
| ZeusHammer | Meditation 4步冥想循环 |
| Qlib | Meta Controller（自适应策略调整）|
| 金策智算 | 基因策略适配器（信号阈值/风控参数自动调）+ 策略谱系 |
| QuantDinger | Docker部署架构（可复现环境）|
| TradingAgents | 辩论历史回检 + 对抗性自我评估 |
| **TDAI** | 全自动记忆管道（idle timeout + 阈值触发 + 会话GC + crash恢复）|
| Buffett Oracle Analyzer | v1.1 版本更新日志（Skill简化迭代）|

**qclaw 落地**：✅ `evolver.py` + ✅ `self_review.py`（已联动）

---

## 项目贡献矩阵（6层×已学项目）

| 项目 | ①感知 | ②认知 | ③记忆 | ④执行 | ⑤安全 | ⑥进化 |
|-------|--------|--------|--------|--------|--------|--------|
| OpenClaw | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Codex | — | — | ✅ | ✅✅✅ | ✅✅✅ | — |
| Hermes | ✅✅ | ✅ | ✅✅ | ✅✅ | — | ✅✅✅ |
| Archon | — | ✅✅✅ | — | — | ✅✅✅ | — |
| DeepSeek-TUI | — | — | — | ✅✅✅ | ✅✅ | — |
| Brain v1.1.8 | — | — | ✅✅✅ | — | — | ✅✅ |
| juhuo | — | ✅✅✅ | — | — | — | ✅✅✅ |
| OpenSpace | — | — | — | — | — | ✅✅✅ |
| Symphony | — | — | — | ✅✅✅ | — | — |
| ECC | — | ✅ | — | — | — | ✅✅ |
| ZeusHammer | — | — | — | — | — | ✅✅✅ |
| SenseNova-Skills | — | ✅ | — | ✅✅ | — | ✅ |
| khazix-skills | — | ✅✅ | — | ✅ | — | ✅✅ |
| Anthropic Managed Agents | — | ✅✅ | ✅✅✅ | ✅✅✅ | ✅✅✅ | ✅ |
| GBrain | — | ✅✅ | ✅✅✅ | ✅ | — | ✅✅ |
| **Qlib** | — | ✅✅ | ✅✅ | ✅✅✅ | — | ✅✅ |
| **金策智算** | ✅✅ | ✅✅ | — | ✅✅✅ | ✅✅ | ✅✅✅ |
| **QuantDinger** | ✅✅ | ✅✅✅ | ✅ | ✅✅✅ | — | ✅✅ |
| **TradingAgents** | — | ✅✅✅ | ✅ | ✅✅ | ✅ | ✅ |
| **Buffett Oracle Analyzer** | — | ✅✅✅ | ✅ | ✅ | ✅✅ | ✅ |
| **mem0** | — | — | 🔥🔥🔥 | — | — | 🔥 |
| **TDAI** | — | 🔥🔥 | 🔥🔥🔥🔥🔥 | — | — | 🔥🔥 |
| **OpenViking** | — | 🔥🔥🔥 | 🔥🔥🔥🔥 | — | — | 🔥🔥🔥 |

---

## qclaw 六层落地状态

| 层 | 状态 | 说明 |
|---|------|------|
| ① 感知层 | ✅ 完成 | `channel_adapter.py`（22渠道）|
| ② 认知层 | 🟡 部分 | 四角色✅，元认知PLAN/MONITOR❌ |
| ③ 记忆层 | ✅ 完成 | `qclaw_unified_memory.py` + `mem0_hybrid_search.py` + `mem0_entity_extractor.py` + `evolver.record_agent_fact()` + `tdai_memory_pipeline.py` + `openviking_context.py` |
| ④ 执行层 | ✅ 完成 | `tool_pipeline.py`（15步）+ `MultiAgentDispatcher` |
| ⑤ 安全层 | 🟡 部分 | PreToolUse✅，PostToolUse❌，10铁律❌ |
| ⑥ 进化层 | ✅ 完成 | `evolver.py` + `self_review.py`联动✅ |

---

## 下一步（按优先级）

1. **补②认知层**：元认知PLAN/MONITOR阶段（Archon）
2. **补⑤安全层**：PostToolUse验证 + 10 Iron Laws注入
3. **补④执行层**：Symphony Orchestrator（多Agent协调）
4. **补⑥进化层**：阶段门控（SenseNova Stage Gate）+ 断点续跑
5. **补⑥技能系统**：分层技能架构（Tier 0 基础层 + Tier 1 业务层）
6. **补③记忆层**：neat-freak 三层知识同步 + 反膨胀规则 + MEMORY.md 清理
7. **补②认知层**：横纵分析法（hv-analysis）作为学新项目的标准框架

---

_六层架构：任务流向明确，从"模块清单"到"流程顺序"，不冗余。每次学新项目，更新本文件的矩阵和状态表。_
