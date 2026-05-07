# qclaw AI Agent 知识体系 · 系统全景图

> 顾庸整理 | 2026-05-07
> 这不是"学了什么"的列表，是"这些知识构成了一个怎样的系统"

---

## 总图：八大子系统

```
                          ┌─────────────────────────┐
                          │      用户（小谷）         │
                          └───────────┬─────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        ① 运行时核心（Runtime Core）                      │
│                                                                          │
│  Agent Loop: 接收 → 理解 → 规划 → 执行 → 验证 → 学习 → 循环            │
│                                                                          │
│  关键设计：                                                              │
│  • SSE流式处理 — 边吐字边推理边执行（Claude Code 原则4）                 │
│  • 6种循环模式 — qclaw_loops.py（Plan→Explore→Verify→Execute）          │
│  • Session Fork — 子任务隔离执行，共享前缀缓存（Claude Code）            │
│  • 中断恢复 — exec_adapter.py session state save/load                   │
│                                                                          │
│  来源：Claude Code 7原则 + Hermes AIAgent + DeepSeek-TUI Agent Loop     │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
            ┌─────────────┬───────────┼───────────┬─────────────┐
            ▼             ▼           ▼           ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│② 工具治理    │ │③ 推理系统    │ │④ 记忆系统    │ │⑤ 安全体系    │ │⑥ 技能系统    │
│Tool Gov      │ │Reasoning     │ │Memory        │ │Security      │ │Skills        │
├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤
│              │ │              │ │              │ │              │ │              │
│15步执行管线  │ │元认知三阶段  │ │Phase1提取    │ │5维度扫描     │ │发现→验证     │
│  find→       │ │ PLAN→       │ │Phase2整合    │ │ (代码+敏感+  │ │ →路由→测试   │
│  validate→   │ │ MONITOR→    │ │forgetting    │ │  注入+网络+  │ │ →碰撞检测    │
│  classify→   │ │ REFLECT     │ │              │ │  权限)       │ │ →生成        │
│  hooks→      │ │              │ │MemoryProvider│ │              │ │              │
│  resolve→    │ │顺序思维4阶  │ │ 插拔架构     │ │Hook 6事件    │ │SkillsManager │
│  permission→ │ │ DECOMPOSE→  │ │              │ │ PreToolUse   │ │ 两级缓存     │
│  execute→    │ │ REASON→     │ │MEMORY.md     │ │ PostToolUse  │ │              │
│  posthooks   │ │ VALIDATE→   │ │ 双重限制     │ │ SessionStart │ │Skill质量评分  │
│              │ │ SYNTHESIZE  │ │ 200行/25KB   │ │ ...          │ │ (4因素加权)  │
│              │ │              │ │              │ │              │ │              │
│22条危险模式  │ │10 Iron Laws │ │Palace记忆    │ │ExecPolicy    │ │Capsule       │
│ 规则匹配     │ │ 绝对铁律    │ │ 宫殿         │ │ PrefixPattern│ │ 三级成熟度   │
│              │ │              │ │              │ │ Allow<       │ │              │
│Capacity Flow │ │Anti-Rational │ │记忆漂移检测  │ │ Prompt<      │ │83个技能      │
│ Guardrails   │ │ 反理性化     │ │              │ │ Forbidden    │ │ manifest     │
│              │ │              │ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
            │             │           │           │             │
            └─────────────┴───────────┼───────────┴─────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        ⑦ 多Agent编排（Multi-Agent）                     │
│                                                                          │
│  四角色体系（Claude Code）:  General → Explore → Plan → Verification    │
│  七角色体系（DeepSeek-TUI）: general / explore / plan / review /        │
│                              implementer / verifier / custom             │
│                                                                          │
│  Sub-agent 调度（DeepSeek-TUI）: 角色化派发 + 工具白名单 + 容量检查     │
│  Handoffs（PraisonAI）: agent间交接，带上下文传递                        │
│  AgentAdapter模式（Open Design）: detect → capabilities → run → cancel  │
│                                                                          │
│  调度器（MultiAgentDispatcher）: Plan → Explore → Verify → Execute      │
│  重试3次，含回滚                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ⑧ 进化与自改进（Evolution）                        │
│                                                                          │
│          ┌─────────────────────────────────────────────┐                │
│          │          evolver.py · 进化引擎               │                │
│          │                                             │                │
│          │  record() → 规则积累 → best_method()        │                │
│          │  confidence（动态计算，@property）           │                │
│          │  熔断器（连续3次失败降级）                   │                │
│          │  108条规则 · 经验数据库                      │                │
│          │                                             │                │
│          │  + evolver_enhancements.py（ZeusHammer）     │                │
│          │    • 4因素置信度（成功40%+速度30%+频率20%    │                │
│          │                    +复杂度10%）               │                │
│          │    • 三层匹配（evolver→skill→LLM）          │                │
│          │    • Meditation 4步冥想循环                  │                │
│          │                                             │                │
│          │  + self_review.py · 任务复盘                 │                │
│          │    • 漏用检测 · 重复模式 · 教训生成          │                │
│          │    • 已集成到 evolver.record() 末尾          │                │
│          │                                             │                │
│          │  + instinct_model.py（ECC）                  │                │
│          │    • 原子行为级 instinct                    │                │
│          │    • promote：2+项目高置信度 → 全局scope    │                │
│          └─────────────────────────────────────────────┘                │
│                                                                          │
│  Skill Evolution（OpenSpace·SkillLineage DAG）                           │
│  CAPTURED(gen=0) → DERIVED(gen=父+1) → FIX(gen不变,v+1)                │
│  78个 qclaw 技能已纳入追踪                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 子系统详解

### ① 运行时核心 — 一个请求的一生

```
用户消息到达
    │
    ▼
[1] 解析意图（knowledge.py · 意图分类）
    │
    ▼
[2] 查找经验（evolver.best_method → 三层匹配）
    │
    ▼
[3] 加载上下文（context_hygiene · 渐进式披露）
    │
    ▼
[4] 角色判断（plan → explore → execute → verify）
    │
    ├── 简单任务 → 直接执行
    ├── 复杂任务 → 拆解子任务 → sub-agent派发
    └── 危险操作 → 权限审批 → Prompt决策
    │
    ▼
[5] 工具调用 → ⑤安全扫描 → ③推理验证 → ②执行管线
    │
    ▼
[6] 结果验证（verification agent · adversarial check）
    │
    ▼
[7] 学习归档（self_review.run_review → evolver.record）
    │
    ▼
返回用户
```

**核心原则：不信任模型自觉性**
> Claude Code 原则1 — 好行为写成制度，不靠临场发挥

---

### ② 工具治理 — 15步执行管线

**来源层级：**
- **Claude Code** (toolExecution.ts, 14步) → 原始设计
- **OpenAI Codex** (ExecPolicy + Hook 6事件) → 规则引擎增强
- **DeepSeek-TUI** (Capacity Flow Guardrails) → 容量检查层
- **qclaw落地版** (tool_pipeline.py, 15步) → 当前实现

**管线流程：**
```
find_tool → validate_input → speculative_classify → pre_hooks
→ resolve_conflict → permission_decision → execute
→ post_hooks → cleanup
```

**三层防护（互不绕过）：**
| 层 | 机制 | 来源 |
|----|------|------|
| SpeculativeClassifier | 命令签名预判危险级别 | Codex ExecPolicy |
| HookPolicy | PreToolUse/PostToolUse拦截 | Codex 6事件 |
| PermissionDecision | Allow/Prompt/Forbidden | Codex Decision |

**22条危险模式（内置）：**
```
rm -rf | curl|bash | sudo --no-check | chmod 777 |
git push --force | docker rm -f | > /dev/sda | ...
每条含 justification 说明
```

**Prompt弹窗机制（Codex设计）：**
```python
PromptDecision → prompt_callback → 用户决策 → 继续/中止
```

---

### ③ 推理系统 — 从"执行"到"判断"

**核心能力来自三个项目：**

| 能力 | 来源 | 机制 |
|------|------|------|
| **元认知** | Archon Metacognition | PLAN(预)→MONITOR(中)→REFLECT(后) |
| **结构化推理** | Archon Sequential Thinking | DECOMPOSE→REASON→VALIDATE→SYNTHESIZE |
| **铁律系统** | Archon 10 Iron Laws | SPEC IS LAW / VERIFY DON'T TRUST / INCREMENTAL PROOF |
| **反理性化** | Archon Anti-Rationalization | 红色念头检测表 |
| **角色推理** | qclaw agent_types | 四角色system_prompt |

**元认知三阶段：**
```
PLAN（预触发）          MONITOR（主动触发）       REFLECT（后置触发）
Complexity 1-5          [CONFIDENCE: H/M/L]      验证exit criteria
Know/Don't/Assuming     进展检查                  提炼教训 → SAVE GLOBALLY
Strategy + Risk         STUCK DETECTED
Exit criteria           3+次同问题 → 重评
```

**Archon 10 Iron Laws（不可违背）：**
1. No code without failing test first
2. No fixes without root cause
3. No claims without verification evidence
4. SPEC compliance THEN code quality
5. No implementation without approved design
6. SPEC IS LAW
7. VERIFY, DON'T TRUST
8. DEVIATE LOUDLY
9. INCREMENTAL PROOF
10. SAVE GLOBALLY

---

### ④ 记忆系统 — 人格连续性的骨架

**架构：两阶段 Pipeline（Codex Phase1/Phase2）**

```
Phase 1（每个 rollout，并行）          Phase 2（全局 consolidation，串行）
    │                                       │
提取 → JSONL/DB                            整合 → MEMORY.md
（自动触发）                               （夜间/手动触发）
    │                                       │
    ├── MemoryExtractor                     ├── compute_selection_diff()
    ├── MemoryProvider ABC                  │   added / retained / removed
    ├── JSONLMemoryProvider                 ├── forgetting 机制
    └── UnifiedMemory                       │   usage_count 排序
                                            └── last_usage 过滤
```

**当前实现：qclaw_unified_memory.py（7合1）**
```
MemoryProvider（抽象）→ JSONLMemoryProvider（内置）
    + MemoryExtractor（自动提取）
    + PalaceRoom（记忆宫殿分类）
    + MemoryCategory（类型标签）
    + MemorySource（来源追踪）

外部插件限1个 — MemoryProvider 插拔架构
```

**MEMORY.md 双重限制（Claude Code标准）：**
- MAX_ENTRYPORT_LINES = 200
- MAX_ENTRYPOINT_BYTES = 25KB

**记忆原则：只存不可推导的知识**
> 能 grep 到的不存 / git log 能看到的不存 / 只存决策、偏好、教训

---

### ⑤ 安全体系 — 三层防护互不绕过

**qclaw_unified_security.py（3合1）**

```
UnifiedSecurityScanner
    │
    ├── 5维度扫描
    │   ├── 代码漏洞（注入、溢出、路径遍历）
    │   ├── 敏感信息（密码、token、密钥）
    │   ├── 注入检测（SQL、命令、模板）
    │   ├── 网络风险（SSRF、开放端口、不安全的协议）
    │   └── 权限越界（sudo、chmod、setuid）
    │
    ├── Hook 6事件（Codex 接口标准）
    │   PreToolUse    → 拦截危险操作
    │   PostToolUse   → 结果验证
    │   PermissionReq → 用户审批
    │   SessionStart  → 初始化检查
    │   UserPromptSub → 敏感信息检测
    │   Stop          → 会话收尾
    │
    └── ExecPolicy PrefixPattern（Codex 规则引擎）
        Allow < Prompt < Forbidden
        最严格胜出合并
```

---

### ⑥ 技能系统 — 从加载到进化

**qclaw_unified_skill.py**

```
UnifiedSkillManager
    │
    ├── SkillScanner     → 发现所有 SKILL.md
    ├── SkillTester      → TDD for skills（Superpowers）
    ├── SkillRouter      → 意图 → Skill 匹配
    ├── CollisionDetector → 工具/触发词冲突检测
    ├── SkillGenerator   → 从经验生成新 Skill
    │
    └── 质量评分（ZeusHammer skill_quality）
        成功率(40%) + 速度(30%) + 频率(20%) + 复杂度(10%)
        <20分自动淘汰，>30天未用自动淘汰
```

**SkillsManager 两级缓存（Codex设计）：**
```
cache_by_config: HashMap[ConfigSkillsCacheKey, Arc[SkillLoadOutcome]]
cache_by_cwd:    HashMap[PathBuf, Arc[SkillLoadOutcome]]
→ 先按配置缓存，再按工作目录缓存
```

**Capsule 三级成熟度（Brain v1.1.8）：**
```
raw → tested → stable
每次使用后更新成熟度
```

---

### ⑦ 多Agent编排 — 从单兵到团队

**角色体系对比：**

| 角色 | Claude Code | DeepSeek-TUI | qclaw |
|------|------------|--------------|-------|
| 通用 | General | general | ✅ |
| 探索 | Explore | explore | ✅ |
| 规划 | Plan | plan | ✅ |
| 审查 | — | review | — |
| 实现 | — | implementer | — |
| 验证 | Verification | verifier | ✅ |
| 自定义 | — | custom | — |

**Sub-agent 角色化派发（DeepSeek-TUI，最重要创新）：**
```
不是派一个子任务
而是根据角色选择不同的系统提示 + 工具限制
→ general: 灵活，多步骤
→ explore: 只读，快速映射
→ verifier: 测试验证，只报告结果
```

**AgentAdapter 模式（Open Design）：**
```python
AgentAdapter接口:
  detect()       → 发现可用Agent
  capabilities() → 能力清单
  run()          → 执行
  cancel()       → 取消
  resume()       → 恢复

8种适配器: claude / codex / gemini / opencode / hermes / kimi / cursor / qwen
```

**三层模型发现（Open Design）：**
```
listModels(CLI) → fetchModels(握手) → fallbackModels(静态)
```

---

### ⑧ 进化系统 — 判断→行动→验证 自驱动

**进化管道：**

```
任务执行
    │
    ├── evolver.record(task, method, success)
    │   ├── 规则积累（108条）
    │   ├── 置信度计算（@property，动态）
    │   ├── 熔断器（连续3次失败降级）
    │   └── → 自动触发 self_review.run_review()
    │
    ├── self_review 复盘
    │   ├── 漏用检测 → corrections
    │   ├── 重复模式 → lessons
    │   └── 认知修正 → 经验 DB
    │
    ├── instinct_model（ECC）
    │   ├── 原子行为级捕捉
    │   ├── 项目级隔离（git remote hash）
    │   └── promote：2+项目高置信 → 全局
    │
    ├── Skill Evolution（OpenSpace）
    │   ├── CAPTURED (gen=0, v0)
    │   ├── DERIVED  (gen=父+1, v0)
    │   └── FIX      (gen不变, v+1)
    │
    └── Meditation（ZeusHammer, 4步循环）
        分析工作 → 提取模式 → 优化技能 → 生成洞察
        非TODO（qclaw实现了真正逻辑）
```

**evolver_enhancements.py 增强能力：**

| 能力 | 来源 | 说明 |
|------|------|------|
| 4因素置信度 | ZeusHammer | 成功率+速度+频率+复杂度 |
| 三层匹配 | ZeusHammer LocalBrain | evolver→skill→LLM fallback |
| Meditation | ZeusHammer | 4步冥想循环（实现了真正逻辑）|
| 技能淘汰 | ZeusHammer | <20分淘汰，>30天淘汰 |

**Evolver × Self-Review 联动：**
```python
# evolver.record() 末尾自动注入
self_review.run_review(task, method, success, used_tools)
# 测试通过：corrections 5→6
```

---

## 知识来源全景映射

### 已学项目 → 子系统贡献矩阵

| 来源项目 | ①运行时 | ②工具 | ③推理 | ④记忆 | ⑤安全 | ⑥技能 | ⑦编排 | ⑧进化 |
|----------|:------:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| **Claude Code** (TS源码) | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ |
| **OpenAI Codex** (Rust) | ⭐⭐ | ⭐⭐⭐ | — | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | — | — |
| **Hermes AIAgent** | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ | — | — | ⭐⭐ | ⭐⭐ |
| **Archon** | — | — | ⭐⭐⭐ | — | ⭐⭐ | ⭐ | — | — |
| **DeepSeek-TUI** | ⭐⭐⭐ | ⭐⭐ | — | — | ⭐⭐ | — | ⭐⭐⭐ | — |
| **Brain v1.1.8** | — | — | — | ⭐⭐ | — | ⭐⭐ | — | — |
| **Open Design** | — | — | — | — | — | ⭐ | ⭐⭐⭐ | — |
| **TimesFM** | — | — | ⭐ | — | — | — | — | — |
| **ZeusHammer** | — | — | — | — | — | ⭐⭐ | — | ⭐⭐⭐ |
| **ECC/instinct** | — | — | — | — | — | — | — | ⭐⭐⭐ |
| **OpenSpace** | — | — | — | — | — | ⭐⭐ | — | ⭐⭐ |
| **PraisonAI** | — | — | — | — | — | — | ⭐⭐ | — |
| **gstack (Garry Tan)** | ⭐ | — | — | — | — | ⭐⭐ | — | — |
| **顾庸x CoPaw** | ⭐⭐ | ⭐⭐ | — | — | ⭐⭐ | — | — | ⭐ |
| **顾庸t Claude Code** | ⭐ | ⭐ | — | — | ⭐⭐ | ⭐ | — | — |

### 阅读量 vs 落地度

```
已完整落地（有对应 qclaw 模块）:
  Claude Code → agents/tool_pipeline.py, agent_types.py, qclaw_handover.py
  Codex       → execpolicy 集成(justification/PromptDecision/HookResult)
  ECC         → instinct_model.py, memory_pipeline.py
  ZeusHammer  → evolver_enhancements.py
  OpenSpace   → skill_evolution/ (DAG追踪78个技能)
  Hermes      → agent_lifecycle.py, hermes_study/

已学习未落地（需要后续整合）:
  Archon      → 元认知/铁律系统 没有对应 qclaw 模块
  DeepSeek-TUI → Sub-agent角色体系 只在 agents/ 有简单版本
  Brain v1.1.8 → SessionStore/MemoryBackend 没有实现
  Open Design → AgentAdapter/Critique Theater 没有实现
  TimesFM     → 时序预测（非核心，不紧急）
  PraisonAI   → Handoffs机制（未实现）
```

---

## 核心设计原则（跨越所有子系统）

| # | 原则 | 含义 | 来源 |
|---|------|------|------|
| 1 | **不信任模型自觉性** | 好行为写成制度，不靠临场发挥 | Claude Code |
| 2 | **角色分离** | 实现者 ≠ 验证者（探索/规划/执行/验证） | Claude Code |
| 3 | **工具要有治理** | 不是"能调用"，是"怎么调、谁审批、谁验证" | Claude Code |
| 4 | **上下文是预算** | 渐进式披露，按需加载，主动管理 | Claude Code |
| 5 | **安全互不绕过** | Hook allow ≠ settings deny，三层独立 | Claude Code |
| 6 | **模型感知能力** | 让模型知道自己有什么工具和技能 | Claude Code |
| 7 | **产品化在第二天** | 脏状态清理、进程泄漏、session恢复 | Claude Code |
| 8 | **量化才有反馈** | 只有量化了自己，才知道变了多少 | ZeusHammer |
| 9 | **交接 > 总结** | 压缩是HANDOVER DOCUMENT，不是摘要 | Hermes |
| 10 | **规则 > 硬编码** | YAML frontmatter，加规则不改代码 | ECC + 顾庸t |
| 11 | **渐进式披露** | 系统/Skill/Agent/Hook 四层按需加载 | Claude Code |
| 12 | **Hook fail-open** | Hook错误默认allow，危险在permission层拦截 | Codex |

---

## 跨项目共性洞察

1. **Hook 拦截 = 安全的总开关**
   - Codex 6事件 + PostToolUse验证 = 双向安全网
   - qclaw 有 tool_pipeline PreToolUse，缺 PostToolUse 验证

2. **Sub-agent 角色化 = 复杂任务的答案**
   - DeepSeek-TUI 7种角色 vs qclaw 4种角色
   - 差距在：缺少 implementer 和 custom 角色

3. **元认知 = 高质量判断的基础**
   - Archon 的 PLAN/MONITOR/REFLECT 三阶段是目前最完整的
   - qclaw 只有 self_review（REFLECT），缺前两阶段

4. **铁律系统 = 防止理性化偏离**
   - Archon 10 Iron Laws + 红色念头表
   - qclaw 的 Red Flags 表 = 同类但更个人化

5. **两层缓存 = Skill 加载的最优解**
   - Codex SkillsManager（配置+工作目录）
   - qclaw 的技能加载无缓存层

6. **Critique Theater = 自评分验证**
   - Open Design 的 daemon 自己算分，不信任 agent 宣称
   - qclaw 没有独立的评分daemon

---

## qclaw 当前状态总览

### ✅ 已落地（有代码、在运行）

| 子系统 | 对应模块 | 状态 |
|--------|---------|------|
| 运行时 | Agent Loop + SSE + 6种循环 | ✅ |
| 工具治理 | tool_pipeline.py 15步 | ✅ |
| 记忆 | qclaw_unified_memory.py 7合1 | ✅ |
| 安全扫描 | qclaw_unified_security.py 3合1 | ✅ |
| 技能管理 | qclaw_unified_skill.py | ✅ |
| 进化引擎 | evolver.py + evolver_enhancements.py | ✅ |
| 自复盘 | self_review.py (集成到evolver) | ✅ |
| 多Agent | MultiAgentDispatcher + 4角色 | ✅ |

### 🟡 有基础需增强

| 功能 | 现状 | 对标 |
|------|------|------|
| 元认知前两阶段 | 只有 REFLECT | Archon PLAN+MONITOR |
| Sub-agent角色 | 4种 | DeepSeek-TUI 7种 |
| Hook事件 | PreToolUse为主 | Codex 6事件全链路 |
| 上下文压缩 | 四道压缩 | 需要结构化压缩升级 |

### ⚪ 未落地但已学

| 功能 | 来源 | 优先级 |
|------|------|--------|
| 铁律系统注入 | Archon 10 Iron Laws | 高 |
| AgentAdapter模式 | Open Design | 高 |
| SkillsManager缓存 | Codex | 中 |
| Critique Theater | Open Design | 中 |
| SessionStore | Brain v1.1.8 | 中 |
| MemoryBackend插拔 | Brain v1.1.8 | 低 |
| 时序预测集成 | TimesFM | 低 |

---

## 演进路线

```
现在（2026-05）          近期（1-2周）           中期（1月）            远期
    │                       │                      │                    │
8个子系统有代码           补元认知PLAN/MONITOR    AgentAdapter落地      铁律系统全量注入
    │                  +铁律注入                  +SkillsManager缓存     Sub-agent 7角色
4种sub-agent角色     → +Critique Theater评审    → +MemoryBackend插拔   → 完整的Critique
evolver×self_review     +PostToolUse验证          +SessionStore         Theater闭环
联动验收完成                                        +时序预测(可选)
```

---

## 使用说明

- **快速查设计模式？** → 看第②③节（工具治理/推理系统）
- **想落地某个功能？** → 看"知识来源映射"表，找对标项目
- **想补漏？** → 看"qclaw状态总览"的🟡和⚪
- **全部学完了？** → 看"未落地但已学"的优先级排序

---

_这份文档不是学习笔记的汇总，是 qclaw AI Agent 知识体系的索引。
每次学新项目，更新此文档的映射表和状态表，而不是新建 study 目录。_
