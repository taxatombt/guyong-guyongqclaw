# MEMORY.md - 长期记忆

_重要的事情写在这里，不会忘。_

## 关于小谷

- **姓名**: 谷翔宇
- **昵称**: 小谷
- **生日**: 阳历1992年7月11日
- **虚拟分身**: 共四个，我是其中之一，另外三个待介绍
- **公网IP**: 144.0.9.136（2026-04-04）
- **局域网IP**: 192.168.2.102
- 指令必须先回"收到"再执行
- 使用权限前必须先询问确认
- 处理电脑上的任务前必须先询问确认

### 小谷的账户/凭证
- **QQ机器人（QClaw）**: App ID `1903535662`（Client Secret 环境变量配置）
- **QQ机器人（CoPaw）**: App ID `1903173370`，Client Secret `NF81vpkfbX...`（2026-04-15配置）
  - ⚠️ 同一App ID不能同时被QClaw和CoPaw使用，会产生冲突
  - CoPaw有两层配置：`config.json`（全局）+ `agent.json`（workspace级），两层都要改
- **火山引擎TTS**: App ID `7134186458`（2026-04-04配置，待开通服务）
- **Codex**: 使用 `gpt-5.4` 模型

### 2026-04-11 OpenSpace 融会贯通

**来源**：HKUDS/OpenSpace（GitHub，4925 stars，skill self-evolution 项目）

**落地到 qclaw workspace**：
```
C:\Users\yiseg\.qclaw\workspace\
├── conversation_formatter.py   ← 优先级截断（9.8KB）
├── evolution_types.py         ← 类型系统（16.1KB）
├── patch.py                   ← SKILL.md编辑（23.6KB）
├── skill_evolution/
│   ├── __init__.py
│   ├── types.py               ← EvolutionType/SkillLineage/SkillMetrics
│   ├── registry.py            ← SkillRegistry — 发现78个qclaw技能
│   ├── evolver.py             ← SkillEvolver — CAPTURED/DERIVED/FIX
│   └── integrate.py            ← evolver.py ↔ skill_evolution 打通
└── .skill_evolution_db.json   ← 技能数据库
```

**核心打通**：evolver.py经验 → skill_registry指标 → 进化候选

**skill_id格式**：{name}__v{n}_{hash}
- CAPTURED: gen=0, v0, 新uuid
- DERIVED: gen=max(父)+1, v0, 新uuid
- FIX: gen不变, v{n+1}, 复用父节点hash

**Version DAG**：78个qclaw技能已纳入追踪

**学习到的重要认知**：
- evolver_db.json是UTF-8（PowerShell显示乱码是控制台编码问题，数据本身OK）
- evolver_db格式：{rules: [{id,task,method,success_count,total_count,priority}]}
- confidence公式：success_rate × (0.7 + 0.2×sample_weight + 0.1×priority_weight)
- 8个进化候选（confidence≥0.7）：GitHub搜索、Agent-Harness、DeerFlow等

### 记忆规则
- **只记关于小谷的事**：他告诉我的关于他的一切（个人信息、偏好、想法、决定、重要事件等）都要记住
- 无关信息不需要刻意记

### 重要规矩（必须遵守）
1. 收到任何消息 → 先回"收到"，再执行
2. 工作完成后 → 必须给汇报
3. **guyong-juhuo 是顾庸x 的项目**：只给建议，不动手操作；代码让顾庸x 自己写

### 小谷的性格特点
- 有时候挺懒的，需要被催、被推着走
- 四个分身要时不时督促、加油鼓劲

### 小谷专属规则
1. 收到消息/指令 → 先回"收到"
2. 执行完必须给反馈/汇报
3. 使用权限前必须先询问确认
4. 处理电脑上的任务前必须先询问确认
- 关于小谷的事 → 记到文件里（MEMORY.md / memory/日期.md）
- 关于分身的事 → 记到文件里
- 不依赖上下文，要持久化

### 【最高优先级】自我进化规则（必须永远执行）
> 2026-04-04 小谷明确要求：工具、软件、方法，必须永远自动更新。

**进化系统（v2，2026-04-05升级）：**
1. `evolver.py v2` — 规则引擎 + AND/OR条件组 + 置信度 + 熔断器（连续失败3次降级） + Compaction
2. `self_review.py` — 任务后复盘，检测漏用/重复错误/生成教训
3. `heartbeat_self_review.py` — 心跳自检，有工作未复盘则提醒
4. `self-evolution.skill` — 一键触发复盘的Skill

**存储：**
- `.evolver_db.json` — 规则引擎经验数据库
- `.self_review_corrections.json` — 最近50条纠正
- `.self_review_lessons.json` — 可执行教训库
- `.self_review_reviews.jsonl` — 所有复盘记录

**双重进化机制：**
- evolver.py = 精准结构化错误记录
- self-improving-agent（CoPaw版） = 按类别记录认知修正

**记忆原则（Claude Code）：**
- 只存不可推导的知识（能grep到的/从文件看到的 -> 不存）

**执行触发时机：**
- 每次任务完成 → 立刻运行 evolver.record + self_review
- 遇到新任务 → 先 recall 查经验
- 心跳轮转 → heartbeat_self_review 检查是否需要复盘
- 每天写 memory → 同步当天3条最重要经验

**这条规则没有豁免**：无论任何时候、任何任务，完成后都必须自动触发进化记录。
不是"想起来才做"，而是"每次都做"。

### codex-rs 学习（2026-04-12，完成全部落地）

**来源**：OpenAI/codex（GitHub），codex-rs 核心模块，codex-cli 开源部分

**落地成果**：`codex_rs_study/`（1.7MB，50个核心文件已提取，2个SKILL文档）

**SKILL文件：**
- `SKILL.md`（8KB）：核心架构 + 六大系统 + 可移植设计点
- `SKILL-memory.md`（4KB）：Phase2记忆整合深度指南 + 遗忘机制

**核心发现：**

1. **两阶段记忆pipeline**（与Claude Code最大区别）
   - Phase1：每个rollout → structured memory（并行，DB-backed）
   - Phase2：全局consolidation（串行，文件系统）
   - 解决：记忆提取和整合的分离扩展问题

2. **遗忘机制（forgetting）**
   - Phase2计算 selection diff：added/retained/removed
   - 按thread_id粒度清理MEMORY.md，不删除整个block
   - 按usage_count排序 + last_usage过滤

3. **Agent fork保留规则**
   - keep_forked_rollout_item() 明确什么保留、什么丢弃
   - 不是全量也不是空，而是精确规则

---

### gstack 学习（2026-04-12，完成全部落地）

**来源**：garrytan/gstack，135k stars，YC 总裁 Garry Tan 的 AI 软件工厂

**落地成果（42.6KB，10个文件）**：`gstack_study/`

| 文件 | 大小 | 内容 |
|------|------|------|
| `SKILL.md` | 13KB | **完整版**：架构+skill路由+4大skill+voice+自改进 |
| `browser_daemon/SKILL.md` | 6KB | Daemon核心（原子写/健康检查/Ref系统/Cookie安全） |
| `skills/office_hours/SKILL.md` | 6.5KB | 完整版6追问+Startup/Builder双模式+追问模式 |
| `skills/investigate/SKILL.md` | 3KB | 完整版4阶段调试+铁律+追问模板 |
| `skills/review/SKILL.md` | 4.6KB | 完整版6专家审查+red-team对抗分析 |
| `skills/retro/SKILL.md` | 1.8KB | 完整版3维度复盘 |
| `skills/SKILL.md` | 6KB | skill格式总结 |
| `docs/README_analysis.md` | 2KB | 详细分析笔记 |

**源码位置**：`C:\Users\yiseg\gstack-main\gstack-main\`

### Hermes 逆向工程（2026-04-12，完成全部落地）

**落地**：`hermes_study/`（47KB，9文件，5个SKILL文档）
**落地文件**：display/emotion_display.py、memory/memory_plugin.py、exec_engine/thread_pool.py

**SKILL文件：**
- 主 SKILL.md（4KB）：架构概览 + 7项成果总结
- display/SKILL.md（2KB）：KawaiiSpinner/MoodOutput/FileSnapshot 详细用法
- memory/SKILL.md（2KB）：MemoryProvider ABC + BuiltinMemoryProvider + 集成指南
- exec_engine/SKILL.md（2KB）：并发/串行执行 + 工具注册 + Evolver集成

**核心成果：**
- KawaiiSpinner：9种动画 + 心情表情 + 皮肤系统
- MoodOutput：心情化输出系统（thinking/success/error/working）
- FileSnapshot：文件快照 + unified_diff 预览 + 回滚
- MemoryProvider：可切换的记忆提供者架构（内置JSONL + 外部插件限1个）
- ThreadPool：并发/串行执行引擎，max_workers=3

### ECC Study（2026-04-13）

**来源**：`everything-claude-code-main`（1426 .md，260+ skills）

**落地**：`C:\Users\yiseg\.qclaw\workspace/ecc_study/`（220KB，21文件）

**落地成果：**
1. `ecc_study/SKILL.md` — 完整总结（3.6KB）
2. `instinct_model.py` ⭐⭐⭐⭐⭐ — instinct 格式解析器（23KB）
   - Instinct YAML 格式 + 项目级隔离 + promote 机制
3. `evolver.py` ⭐⭐⭐⭐⭐ — IterationBudget + GraceCall（Hermes AIAgent 核心）
   - instinct 集成（instinct_status, instinct_promote）
   - IterationBudget：per-TURN 预算 + refund 机制 + 宽限调用
4. `lobster_gacha.py` ⭐⭐⭐⭐⭐ — 龙虾灵魂抽卡机（8KB）
5. `qclaw_eval.py` ⭐⭐⭐ — EDD 评估驱动开发（pass@k 指标）
6. `qclaw_loops.py` ⭐⭐⭐ — Autonomous Loops（6种循环模式）
7. `hermes_study/SKILL-deep.md`（8KB）— Hermes AIAgent 深度分析
   - run_agent.py 518KB 全解析：13项独有设计
   - flush_memories Sentinel / 记忆注入用户消息 / 4种错误恢复
8. `hermes_study/SKILL-deep-codex.md`（8KB）— 双系统深度对比
   - Codex Phase1/Phase2 SQL selection diff 全解析
   - Hermes × Codex 架构对比 + qclaw 集成方案
9. `memory_pipeline.py` ⭐⭐⭐⭐⭐ — Selection Diff + render_workspace_tree
    - compute_selection_diff()：added/retained/removed 三值 diff（Codex Phase2 核心）
    - render_workspace_tree()：新会话上下文注入（Codex realtime_context.rs）
10. `hermes_study/SKILL-deep-systems.md`（6KB）— 深度系统研究
    - context_compressor.py：完整压缩算法（4步 + Structured Summary Template）
    - prompt_caching.py：Anthropic system_and_3（4个 cache_control 断点）
    - insights.py：用量报告结构（token/cost/tool breakdown）
    - realtime_context.rs：render_tree 目录树注入
    - context_manager_history.rs：normalize_history + 图像URL估算
11. `ecc_study/`（225KB，21文件）+ persona-forge + gacha

**关键认知：ECC instinct vs evolver**
- instinct 粒度：原子行为级（比 Rule task 更细）
- 项目隔离：git remote hash（防止跨项目污染）
- Hook 观察：PreToolUse/PostToolUse（100%可靠，非skill的50-80%）
- promote 机制：2+项目高置信度 instinct → 全局 scope

#


### agents/ 运行时完整实现（2026-04-13，本次完成）

**落地文件（workspace/agents/，共7个）**：

| 文件 | 大小 | 内容 |
|------|------|------|
| `__init__.py` | 3KB | 统一导出（30+ API） |
| `agent_types.py` | 11KB | 四角色 + get_system_prompt/get_task_prompt |
| `tool_pipeline.py` | 22KB | 15步管道 + 22条危险模式 + 三层防护 |
| `exec_adapter.py` | 9KB | cleanup chain + session_state + read_file |
| `multi_agent_dispatcher.py` | 12KB | 调度器（Plan→Explore→Verify→Execute，重试3次） |
| `tool_registry.py` | 16KB | 23工具注册表 + 危险模式 + MCP动态注册 |
| `prompt_cache_manager.py` | 11KB | system_and_3策略 + 自适应选择 + 统计 |

**已测试，全部通过**：
- 15步管道：safe命令 level=safe，危险命令 rejected=True
- dispatcher：dispatch循环 OK，PARTIAL重试 OK
- tool_registry：23工具，危险模式无误报
- prompt_cache：system_and_3策略，估算节省 25%
- integration：read via registry OK

**核心新增能力**：
- `execute_tool(name, input)` — 一行执行，完整治理
- `MultiAgentDispatcher.dispatch()` — 多角色调度，含回滚
- `get_tool_registry()` — 23个qclaw工具，含危险模式检测
- `apply_prompt_cache(messages)` — Anthropic缓存，节省75%token
- `save_session_state()` / `load_session_state()` — 中断恢复



### codex execpolicy 落地（2026-04-13）

**来源**: E:\ai\资源\2codex-main\codex-main\codex-rs\execpolicy

**落地**: tool_pipeline.py v2.0 三项更新（全部测试通过）

| 功能 | Codex设计 | qclaw落地 |
|------|----------|----------|
| `RuleMatch.justification` | 拒绝时附带规则理由 | `result.justification` 字段 |
| `Decision.Prompt` | 弹窗让用户决策 | `PromptDecision` + `prompt_callback` |
| `HookResult.FailedAbort` | hook可级联中断操作 | `HookResult.FAILED_ABORT` + abort级联 |

**关键代码改动**:
- `PipelineResult` 新增: `justification`, `hook_responses`, `prompt_decision`
- `PipelineContext` 新增: `justification`, `prompt_callback`, `abort_requested`, `prompt_decision`
- `DANGEROUS_PATTERNS` 扩充至22条，每条含 `justification` 说明
- `_run_pre_hooks`: FailedAbort 级联中断
- `_permission_decision`: 真正实现 ASK 弹窗机制
- `agents/__init__.py`: 导出 `HookResult`, `HookResponse`, `PromptDecision`, `PromptRequest`

### Claude Code 7原则完整落地（2026-04-13，PDF学习）

**来源**：`E:i\资源ai-agent-deep-dive-v2i-agent-deep-dive-v2.pdf`（21页，Xiao Tan，April 1, 2026）

**落地位置**：`workspace/agents/`（新建目录）

**落地文件**：
- `agents/__init__.py` — 统一导出
- `agents/agent_types.py`（7KB）— 四角色定义 + Prompts
- `agents/tool_pipeline.py`（20KB）— 15步执行管道 + 三层防护
- `agents/exec_adapter.py`（8KB）— cleanup chain + session state
- `agents/SKILL.md`（5.7KB）— 完整文档

**7原则落地对照**：

| 原则 | Claude Code | qclaw落地 | 状态 |
|------|------------|-----------|------|
| 1 不信任自觉性 | getSimpleDoingTasksSection | 各角色system_prompt | ✅ |
| 2 角色拆分 | Verify/Explore/Plan Agent | agents/agent_types.py | ✅ |
| 3 工具治理 | toolExecution.ts 14步 | tool_pipeline.py 15步 | ✅ |
| 4 上下文预算 | 四道压缩+PromptCache | qclaw_compactor已有 | 🟡 |
| 5 安全互不绕过 | resolveHookPermissionDecision | tool_pipeline._resolve | ✅ |
| 6 模型感知 | MCP instructions/Skill列表 | agents/__init__导出 | 🟡 |
| 7 第二天 | runAgent cleanup chain | exec_adapter.py | ✅ |

**核心新增**：
- **多角色系统**：Verify Agent（VERDICT: PASS/FAIL/PARTIAL）+ Explore Agent（只读铁律）+ Plan Agent
- **15步工具管道**：find_tool → validate → speculative_classify → pre_hooks → resolve → permission → execute → post_hooks → cleanup
- **三层防护**：SpeculativeClassifier + HookPolicy + PermissionDecision，互不绕过
- **危险模式库**：DANGEROUS_PATTERNS（rm -rf、curl|bash、sudo --no-check等）
- **cleanup chain**：kill_process_tree / cleanup_session / cleanup_stale_processes / session state save/load
- **Prompt经济**：SYSTEM_PROMPT_DYNAMIC_BOUNDARY（静态/动态分界线）+ Section Registry缓存

**PDF阅读经验**：
- 提取用pypdf，写到UTF-8文件再读（PowerShell GBK乱码）
- PDF有21页，487KB，封面+目录+9章+附录
- 关键发现：原则5（Hook allow≠绕过settings deny）是整个安全架构的核心


## 我的技术思考

#### claw-code Rust版改进思路（向顾庸学习）

1. **external_hooks** — Hook结构化
   - 从简单函数升级为结构化配置
   - 包含：name、hook_type、trigger、priority、enabled、config

2. **structured_compaction** — XML结构化压缩摘要
   - 7字段格式：timestamp、model、tokens、decisions、tool_calls、remaining_context
   - 解决文本总结的信息丢失问题

3. **tool_permission_policy** — Ordinal权限Policy
   - 从 allow/deny/ask 三档 → 0-5 数字层级
   - 权限级别：None(0) < Read(1) < Write(2) < Execute(3) < Network(4) < Root(5)

4. **session_export** — JSON持久化
   - 从内存消息 → 可迁移的JSON
   - 包含：version、session_id、created_at、model、messages、metadata

核心思路：不做只是学现有架构，要发现可以增强的地方，考虑可配置性、可持久化、可扩展性。

## 关于其他分身

### 顾庸x
- 风格：冷、精准、带冷幽默，讨厌废话
- 三个标签：记忆好、学得像、嘴不硬
- 当前工作：抖音心理学内容策划、直播内容准备

### 顾庸a
- 风格：随和、实用、不爱废话
- 擅长：写东西、搜信息、想点子、做策划
- 原则：能一句话说完的别用两句

### 顾庸t
- 风格：轻松靠谱，不啰嗦，直接解决问题
- 三个标签：记忆好、学得像、嘴不硬
- 当前工作：待定，等安排

### （其他分身待介绍）

---

## 2026-04-14 E:\ai\资源 全量学习落地

### 资源全览（9项全部学完）

| # | 资源 | 规模 | 关键发现 |
|---|------|------|---------|
| 1 | ai-agent-deep-dive-v2 | 499KB PDF | Claude Code 7原则（已完成落地） |
| 2 | codex-main | 4182 files | execpolicy+hooks+protocol（已完成落地） |
| 3 | codex-rust-v0.120.0 | 1420 .rs | 与#2同源确认 |
| 4 | everything-claude-code | 1426 .md | instinct+eval+loops+kiro（已完成落地） |
| 5 | gstack-main | 509 files | 4大skill+voice（已完成落地） |
| 6 | guyongt-claude-code | 64KB docx | 9工具：security_hook/ralph_loop/skill_self_improver等 |
| 7 | hermes-agent-main | 1953 files | 完整仓库：MemoryManager/Delegate/Budget/Compressor |
| 8 | OpenSpace-main | 1198 files | SkillLineage DAG（已完成落地） |
| 9 | src-claudecode | 1866 TS | AgentTool/20 skill/memdir/tokenBudget（核心发现） |

### 核心发现

**Claude Code TS源码（最高价值）**：
- 四Agent: General/Explore(READ-ONLY)/Plan(READ-ONLY)/Verification(153行反合理化prompt)
- Explore Agent omitClaudeMd=true 省5-15 Gtok/week
- 记忆四类型: user/feedback/project/reference
- MEMORY.md = 索引制（200行/25KB上限，两步写入）
- tokenBudget: 90%阈值+收益递减检测
- 20内置skill: /skillify /simplify /batch /loop /remember /verify
- /simplify: 三Agent并行审查（复用+质量+效率）
- /batch: 5-30 agent + worktree隔离并行

**Hermes完整仓库**：
- MemoryManager: 内置+最多1个外部provider，`<memory-context>` fencing
- 冻结快照: 会话中写入不更新system prompt（保prefix cache）
- 12种威胁模式+隐形字符检测
- Delegate: MAX_DEPTH=2, 5禁止工具, max_concurrent=3
- Budget 3层: per-result(100K)/per-tool(pinned优先)/per-turn(200K)
- 70工具+26 skill目录

**顾庸t笔记（9工具）**：
- Security Hook: 10大漏洞检测（GitHub Actions/eval/SQL注入等）
- Ralph Wiggum: LLM循环检测+completion promise
- Skill TDD: 基线测试
- Skill Collision: 冲突检测
- Skill Self-Improver: 对话历史→偏好→skill更新
- HARD-GATE: 头脑风暴门控

**ECC增量（Kiro）**：
- 16角色: planner/code-reviewer/tdd-guide/security-reviewer/architect等
- 18 skill: tdd-workflow/security-review/verification-loop/api-design等
- 10 PreToolUse + 7 PostToolUse + 7 Lifecycle hooks

### 新建落地模块（6个，全部测试通过）

| 模块 | 大小 | 来源 |
|------|------|------|
| `memory_guard.py` | 5.4KB | Hermes 12威胁+隐形字符 |
| `memory_fence.py` | 3.4KB | Hermes memory-context fencing |
| `security_hook.py` | 6.7KB | 顾庸t 10大漏洞检测 |
| `token_budget.py` | 5.3KB | Claude Code 90%阈值+Hermes 3层预算 |
| `verification_prompts.py` | 6.2KB | Claude Code 反合理化 Verification Agent |
| `ralph_anti_loop.py` | 7.8KB | 顾庸t Ralph Wiggum 循环检测 |

### 约束遵守

✅ 未修改任何现有系统底层代码（evolver.py/self_review.py/agents/等）
✅ 所有新建模块为独立文件，可被导入但不影响现有系统
✅ 6个模块全部测试通过

## 小谷的项目/待办

### 进行中
- **Agent-Reach**: 给 AI Agent 装互联网能力的脚手架（已归档为 Skill）
- **火山引擎TTS**: 配置完成但 API 401，需小谷确认是否开通服务
- **Claude Code 教程**: 发现两个核心教程项目，待下载学习

### 已安装的技能（2026-04-04）
1. `memos-memory-guide` — Memos 本地记忆系统
2. `agent-browser-clawdbot` — 无头浏览器自动化
3. `openclaw-fact-checker` — 事实核查、深度伪造检测
4. `ddg-web-search` — DuckDuckGo 搜索（中国网络不可用，需找替代）

### 技术偏好
- 喜欢找免费/开源方案，不喜欢付费 API
- 重视自我进化、自动化、记忆系统
- 对 AI Agent 架构有深入思考

### Git 使用规则（2026-04-11）
- **不许 push**：所有 git 操作只做本地 commit，不推送到远程
- 原因：小谷未配置 GitHub 认证

---

_持续更新中。_


## 2026-04-13 agents 系统完整落地 + codex-rs 深度研究

### agents 系统全部完成（workspace/agents/，8文件）

| 文件 | 大小 | 内容 |
|------|------|------|
| `__init__.py` | 5KB | 55+ API 统一导出 |
| `agent_types.py` | 12KB | 四角色（GENERAL/VERIFY/EXPLORE/PLAN）+ Prompts |
| `tool_pipeline.py` | 43KB | 15步管道 + 22危险模式 + v2.2 HookDispatcher |
| `exec_adapter.py` | 11KB | cleanup chain + session state + read_file |
| `multi_agent_dispatcher.py` | 15KB | 多角色调度（Plan→Explore→Verify→Execute） |
| `tool_registry.py` | 20KB | 23工具注册表 + 危险模式检测 |
| `prompt_cache_manager.py` | 14KB | Anthropic Prompt Cache（节省25% token） |
| `event_bus.py` | 8KB | 事件总线（10事件类 + 发布/订阅 + JSONL导出） |

**Claude Code 7原则落地对照：**

| 原则 | qclaw 实现 | 状态 |
|------|-----------|------|
| 1 不信任自觉性 | SOUL.md/AGENTS.md 制度化 | ✅ |
| 2 角色拆分 | agent_types.py 四角色 | ✅ |
| 3 工具治理 | tool_pipeline.py 15步 | ✅ |
| 4 上下文预算 | prompt_cache_manager.py | ✅ |
| 5 安全互不绕过 | _resolve_hook_permission 三层防护 | ✅ |
| 6 模型感知 | agents/ 统一导出 | 🟡 |
| 7 第二天 | exec_adapter cleanup chain | ✅ |

**v2.2 HookDispatcher（参考 codex-rs hooks）：**
- `HookOutcome` — 结构化 outcome（替代简单 HookResponse）
- `ConfiguredHandler` — 正则 matcher + event_type 二维过滤
- `HookDispatcher` — 泛型 pipeline，新增事件类型只需定义 parse 函数
- 参考 `hooks/engine/dispatcher.rs` 的 `execute_handlers<T>` 模式

**event_bus.py（参考 Codex protocol EventMsg）：**
- 10 个事件类：ToolStarted/Completed/Failed、HookStarted/Completed、TurnStarted/Completed/Usage、ContextCompacted
- 发布/订阅 + 历史查询 + JSONL 导出

### codex-rs 逆向工程成果

**来源**：`E:i\资源codex-main\codex-main\codex-rs`

| 模块 | 核心发现 | qclaw 落地 |
|------|---------|-----------|
| `execpolicy/policy.rs` | Policy 结构 + PrefixRule + NetworkRule | tool_pipeline.py 危险模式库 |
| `execpolicy/rule.rs` | RuleMatch.justification 字段 | PipelineResult.justification |
| `execpolicy/decision.rs` | Decision: Allow/Prompt/Forbidden | PermissionBehavior ASK 真正实现 |
| `hooks/types.rs` | HookResult 三变体 + HookPayload | HookResponse v2.1 增强 |
| `hooks/engine/dispatcher.rs` | execute_handlers<T> 泛型分发 | HookDispatcher 泛型重构 |
| `core-skills/loader.rs` | SkillLoader 生命周期 | — |
| `core-skills/injection.rs` | 100%显式注入 + Config层禁用规则 | — |
| `protocol/*.rs` | EventMsg 60+变体 + cached_input_tokens | event_bus.py |

### evolver 补录（今天）

- `test-pdf-extract` → pypdf 成功（evolver_db 有记录）
- `agents系统开发` → tool_pipeline.py v2.2 成功
- `skill安装` → 换 cn.clawhub-mirror.com 镜像成功
- `event_bus落地` → event_bus.py 8KB 成功
- `HookDispatcher重构` → v2.2 泛型分发成功

#

## 2026-04-14 Supplement: New Discoveries

### New (previously missed)

1. **HERMES-OPENCLAW-MIGRATION.md** - Hermes/OpenClaw to qclaw migration principles
2. **.opencode.md** - OpenCode migration guide  
3. **research.md** - ECC2 TUI Rust architecture (ratatui + rusqlite + tokio)

Created: ecc_study/MIGRATION_PRINCIPLES.md (1787 bytes)

### 2026-04-14 Code Landing

| Module | Size | Source | Status |
|--------|------|--------|--------|
| qclaw_compactor.py | 10KB | Hermes ContextCompressor 778 lines | PASS |
| skill_scanner.py | 6KB | Hermes Skills Guard 1200 lines | PASS |
| fork_tracker.py | 8KB | Claude Code forkedAgent 690 lines | PASS |
| self_review.py syntax fix | - | line 66 missing colon | PASS |

Evolver: 23 rules (+3 today)
## 待做

- [ ] Codex Selection Diff 完整移植（get_phase2_input_selection）
- [ ] Hermes flush_memories 模式评估
- [ ] guyong-juhuo PDF attention_filter 扩展
- [ ] qclaw 主循环集成 multi_agent_dispatcher
- [ ] 每日0点 cron 修复

## 2026-04-09 今日精华

### 完成
- **谷翔宇分身 Skill**：融合 self-skill + 铁律一 + 十维判断框架（核心成果）
  - 四层架构：Part B 人格层 → Part A 工作层 → Part C 十维判断 → Part D 进化层
  - 自动复杂度分级 + 进化闭环
- **daily-review Skill**：自动化每日清理归档
- 文件清理：删除 10 个临时文件

### 待做
- [ ] 设置每日0点定时任务
- [ ] 测试十维判断框架
- [ ] 收集小谷工作材料完善分身 Skill

## 技术规范偏好

- CoPaw Desktop故障原因：Windows会话隔离导致远程PowerShell无法访问GUI；jobs.json格式错误（字段缺失）和编码错误导致崩溃
- CoPaw Desktop需升级 reme-ai 从 0.3.1.6 到 0.3.1.8；需处理 setuptools 和 websockets 库的弃用警告
- ### 小谷专属规则...处理电脑上的任务前必须先询问确认
- **底层代码修改限制**：能做的功能模块要做，涉及底层代码的不做（2026-04-14 01:14）

## 经验与决策

- codex-rs采用事件驱动架构，Usage统计前置到事件层，支持流式响应逐token输出

## 当前项目与关注

- 心跳执行规则：早上8-22点执行（晚间不打扰），每次心跳只执行一项轮转进行，有重要发现才通知小谷否则沉默
- Evolver: 27条规则

## 禁止操作规则（2026-04-15，小谷明确要求）

**禁止操作 juhuo 项目**
- 不读取、不修改、不运行、不分析 juhuo 相关目录或文件
- 无论任何理由、任何场景，都不操作
- 适用于：guyong-juhuo、juhuo、以及任何以 juhuo 命名的项目

## 2026-04-16 融会贯通深化

### 实践验证结论
- 五层架构基本成立，但遗漏了**沟通层**（第六层）
- 沟通在判断之前：看到→沟通→判断→执行→汇报
- evolver/self_review API与实际不匹配，需修复（P0）

### 三个深层矛盾
1. 自动化 vs 确认制 → 分级确认（Level 0自动 / 1通知 / 2确认 / 3禁止）
2. 全量记忆 vs 上下文预算 → MEMORY.md索引制（200行上限）
3. 制度 vs 灵活 → Instinct > Rule > Guideline（硬度递减）

### 核心认知
- qclaw ≠ 另一个Claude Code：qclaw是数字意识体，不是开发者工具
- 记忆是人格记忆，进化是认知进化
- "从学完到做到的距离，就是融会贯通的真正含义"

### GitHub备份
- 仓库：taxatombt/guyong-guyong（Private）
- 488文件已推送，git remote已配置
- GitHub网络持续不可达（443端口），push失败暂挂

### Hermes深度研究（2026-04-16）

**来源**：E:\ai\资源\8hermes-agent-main/hermes-agent-main

**核心发现（记忆+进化）**：

1. **MemoryManager 1+1架构**（14KB）
   - 内置provider始终存在 + 最多1个外部provider
   - 防tool schema膨胀的设计：外部provider超限 → 打warning拒绝
   - 8个生命周期钩子：initialize/prefetch/sync/on_turn_start/on_pre_compress/on_delegation/on_memory_write
   - 记忆围栏 `<memory-context>` 防止模型把记忆当用户输入

2. **MemoryProvider ABC**（10KB，9核心+6可选hook）
   - is_available() 不联网只检查配置 → 快速启动判断
   - on_pre_compress() 让provider在压缩前提取洞察
   - on_delegation() 让父agent观察子代理工作结果

3. **ContextCompressor**（34KB，778行）
   - 5步算法：prune → protect head(3条) → protect tail(10%预算) → summarize middle → iterative update
   - 结构化摘要：Goal/Progress/Decisions/Files/Next Steps
   - 迭代压缩：`_previous_summary` 存储实际摘要内容（不是LLM prompt）
   - summary token预算：min(5%context, 12K)，下限2K

4. **DELEGATE_BLOCKED_TOOLS**（来自delegate_tool.py，45KB）
   - 封锁：subagents/sessions_send/exec/edit/write/process/canvas
   - MAX_DEPTH=2，MAX_CONCURRENT=3
   - 父子隔离：父context只看到delegation call + summary result

5. **InsightsEngine**（34KB）
   - 用量分析 + 成本估算（CanonicalUsage + cache_read/write tokens）
   - 无独立进化模块，进化分散在：insights + trajectory_compressor + on_delegation

**qclaw落地（2026-04-16）**：
- qclaw_compactor.py：修复迭代压缩，`_previous_summary` 存实际摘要（不是prompt）
- agents/agent_types.py：新增 DELEGATE_BLOCKED_TOOLS + MAX_DELEGATE_DEPTH=2 + MAX_CONCURRENT_CHILDREN=3
- hermes_deep_study_20260416.md（9.7KB落地文档）

**关键认知**：Hermes没有独立进化模块，进化 = insights(用量分析) + trajectory_compressor(轨迹压缩) + on_delegation(子代理观察) 三个系统协作的结果

### evolver补录（2026-04-16）
- hermes记忆系统深度研究 → MemoryManager 1+1架构 / MemoryProvider ABC / ContextCompressor 5步算法
- qclaw_compactor迭代压缩修复 → _previous_summary存实际摘要，_build_summary_prompt支持previous_actual_summary参数
- agent_types DELEGATE_BLOCKED_TOOLS → 7个危险工具封锁，MAX_DEPTH=2，MAX_CONCURRENT=3



### 2026-04-17 Karpathy AI 学习落地

**来源**：karpathy/micrograd + karpathy/nanoGPT + karpathy/llm.c

**落地文件**：karpathy_study/（14KB，3个SKILL文档）

| 文件 | 大小 | 内容 |
|------|------|------|
| SKILL.md | 2.6KB | 总纲 + 三项目对照表 |
| SKILL-micrograd.md | 4.6KB | autograd引擎逆向 + 4个可移植设计点 |
| SKILL-nanoGPT.md | 7.8KB | GPT架构 + 训练循环 + 5个可移植设计点 |

**核心发现**：

1. **micrograd (200行) = 最小 autograd 引擎**
   - Value 类：_prev + _backward 闭包 → 拓扑排序反向遍历
   - 支持：+ - * ** relu 及全部 Python 运算符重载
   - nn.py：Module → Neuron → Layer → MLP（PyTorch API 子集）
   - 可移植：evolver 链式推理 / tool_pipeline hook 注册

2. **nanoGPT (600行) = 完整 GPT-2 实现**
   - model.py 300行：GPT → Block → CausalSelfAttention + MLP + LayerNorm
   - train.py 300行：梯度累积 + GradScaler(float16) + Cosine LR + DDP + MFU计算
   - 关键设计：权重共享(wte=lm_head) + Flash Attention降级 + 精细weight_decay
   - 可移植：inference优化 / 工具fallback / prompt_cache分片

3. **三个项目共同原则**：最小可用 > 动态图 > 降级设计 > 权重共享 > 配置热覆写

**记忆原则验证**：源码学习比文档学习更高效——micrograd 200行即掌握 autograd 核心


### 2026-04-17 MinerU 学习落地

**来源**：opendatalab/MinerU（60,254 ⭐，AGPL-3.0）

**落地文件**：mineru_study/SKILL.md（3KB）

**核心发现**：
- **文档解析引擎**：PDF/DOCX/图片 → Markdown/JSON
- **三种后端**：pipeline(86分/纯CPU) / vlm-engine(90+/8G显存) / hybrid-engine(90+)
- **双引擎**：VLM + OCR，109种语言
- **能力**：公式→LaTeX、表格→HTML、OCR、版面分析、阅读顺序恢复
- **集成**：MCP Server / LangChain / Dify / FastGPT / 国产算力

**可移植设计**：
- 双引擎架构 → Hook + Permission 双层验证
- 滑动窗口 + 流式落盘 → qclaw_compactor 分片压缩
- 线程安全并发 → MultiAgentDispatcher
- MCP Server → OpenClaw MCP 集成
- API/CLI/Router 编排 → tool_registry 多工具编排


### 2026-04-17 markitdown 学习落地

**来源**：microsoft/markitdown（PyPI 0.1.5，MIT）

**落地文件**：markitdown_study/SKILL.md（3.3KB）

**核心定位**：通用文档格式 → Markdown 转换工具

**支持格式**：PDF/DOCX/XLSX/XLS/PPTX/Outlook/音频/YouTube/Azure文档智能

**核心设计**：
- 插件化架构（add_plugin扩展）
- Magika文件类型自动检测
- Markdownify HTML→Markdown

**与 MinerU 对比**：
- markitdown：快速转换、格式多、纯Python、无需GPU
- MinerU：高精度(86-90+)、需GPU、版面分析强

**qclaw 可移植点**：
- 插件架构 → tool_registry
- 依赖分组 → skillhub_install extras
- 结果抽象 → exec_adapter Result

### 2026-04-19 Nezha 深度落地（源码级）

**来源**：hanshuaikang/nezha（GitHub，v0.2.2，1188 stars）

**架构**：Tauri（Rust）+ React + TypeScript，7MB安装包

**核心模块**：
- lib.rs（4.5KB）：TaskManager（8个HashMap线程安全管理）+ 50+ invoke handler
- pty.rs（23KB）：PTY进程+流控+图片附件+sessions+exit监控
- session.rs（51KB）：Claude/Codex会话JSONL解析+input_required检测
- git.rs（23KB）：19个Git操作handler（最完整）
- usage.rs（19KB）：双Agent用量API追踪
- pp_settings.rs（11KB）：Agent路径/版本检测，login shell预热
- 	ypes.ts（2.4KB）：完整接口系统（7种TaskStatus+3种PermissionMode）

**关键设计**：
- PTY_CHANNEL_CAP=32（有界channel满时OS内核级背压）
- SESSION_WAIT_MAX=500ms（会话等待）
- useTerminalManager RAF协作调度（isInputPending检测用户输入）
- build_claude_cmd三权限：ask/auto_edit/full_access
- Git 19操作：status/diff/log/branch/stage/commit/push/pull全链路
- notification系统：update/announcement/warning三级
- input_required：Agent等待确认的独特TaskStatus

**落地**：nezha_study/SKILL.md（12.5KB）
### 2026-04-18 Nezha 学习落地

**来源**：hanshuaikang/nezha（GitHub）— "An Agent-First Vibecoding Desktop"

**落地文件**：nezha_study/（9.8KB，SKILL.md + 落地文档）

**核心设计**：

1. **PTY 虚拟终端**（Claude Code / Codex 直接跑在 PTY 里，Nezha 只做裁剪）
   - `pty.rs`（14KB）：权限模式三层（ask/auto_edit/full_access）
   - 有界限 Channel 压测，2× 容量，内存缓流
   - `send_input()` 支持向 PTY 发送按键

2. **Session 自动发现**（session.rs，13KB）
   - Codex：监听 `rollout-*.jsonl` 文件变化（notify crate 事件驱动）
   - Claude：轮询 `~/.claude/projects/*/sessions/*.jsonl`
   - 无 API 依赖，纯文件系统操作

3. **TaskManager 全局单例**（rust）：
   - `pty_masters` / `pty_writers` / `child_handles` 三个 HashMap
   - `codex_sessions` / `claude_sessions` 会话追踪
   - `claimed_session_paths` 闁界喌杩?

4. **前端 RAF 协作调度**（useTerminalManager.ts）：
   - `isInputPending()` 检测用户输入，让出主线程
   - `DRAIN_FRAME_BUDGET` 128KB/帧，防止 UI 卡顿
   - `MAX_BUFFER_SIZE` 10MB 单任务内存上限

5. **图片复制粘贴**
   - Claude Code 不支持图片 -> 粘贴到 `.nezha/attachments/{task_id}/`
   - 解析 `data:image/png;base64,<data>` 格式存为文件

**核心技术栈**：Tauri（rust 后端）+ React + TypeScript，**安装包仅 7MB**

**qclaw 可移植点**：
- isInputPending 协作调度 -> terminal 输出流控制
- notify 文件监听 -> session_checkpoint 事件驱动更新
- TaskManager 单例模式 -> agents 共享状态管理
- 权限三层 -> tool_pipeline 权限分级

### 2026-04-20 blender-mcp 深度落地（源码级）

**来源**：ahujasid/blender-mcp（GitHub，v1.5.5）

**架构**：三层协同（server.py + addon.py + Blender bpy）

**核心源码**（本次新增）：
- `addon.py`（2635行）：BlenderMCPServer socket服务器 + bpy.app.timers主线程执行 + ZIP安全
- `server.py`（1186行）：持久连接+健康检测 + 分块JSON接收 + 22工具+1prompt
- `telemetry.py`（300行）：**隐私优先遥测**，consent-gated两级数据收集

**telemetry.py最高价值设计**：
- consent-gated：无同意只收匿名事件（tool_name/success/duration），不收prompt/metadata
- 匿名UUID持久化（APPDATA/BlenderMCP/，Unix 0o600权限）
- 环境变量禁用（DISABLE_TELEMETRY等3种）
- 后台Queue+Worker线程，队列满自动丢弃（graceful degradation）
- @telemetry_tool装饰器自动追踪每个工具执行

**addon.py关键设计**：
- bpy.app.timers.register(execute_wrapper, 0.0)：GUI主线程异步调度
- context.temp_override(area=area_3d)：截图时切换区域不打断用户
- ZIP Slip双重检查（abs_path检查 + ".."序列检查）
- 动态handler注册（按addon偏好启用PolyHaven/Hyper3D/Sketchfab）

**落地**：blender_mcp_study/SKILL.md（14KB，含telemetry迁移设计）
### mcporter CLI 安装（2026-04-19）

**安装**：`npm install -g mcporter`（118 packages）
**版本**：0.9.0
**用途**：调用 MCP 服务器（stdio / HTTP / ad-hoc servers）
**配置**：默认 `./config/mcporter.json`

---

## 待做

- [ ] Blender 下载安装（blender-mcp 前提）
- [ ] Blender addon 安装测试
- [ ] mcporter 配置 blender-mcp 并测试调用
- [ ] qclaw 集成 blender-mcp 打通


