# AI Agent 架构演进图谱

_顾庸整理 | 2026-04-04 | 基于 claw-code (Rust) → 顾庸x (Python) → OpenClaw (JS) 三层研究_

---

## 一、全景架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户（谷翔宇 / 小谷）                          │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      OpenClaw 运行时（当前层）                        │
│                                                                      │
│  消息 → Skill路由 → 工具调用 → 权限检查 → 记忆系统 → 执行返回         │
│                                                                      │
│  内置工具:  exec | browser | web_search | web_fetch | sessions |     │
│            message | tts | canvas | 文件读写 | 子Agent               │
│                                                                      │
│  Skill生态:  pdf | docx | xlsx | pptx | ddg-web-search |            │
│             openclaw-fact-checker | agent-browser-clawdbot |        │
│             memos-memory-guide | agent-reach                         │
│                                                                      │
│  记忆:      memory_search | memory_get (MemOS Local)                │
└─────────────────────────────────────────────────────────────────────┘
           │                              │                        ▲
           │ 学到了什么                    │ 底层支撑               │
           ▼                              ▼                        │
┌─────────────────────────────────────────────────────────────────────┐
│                    顾庸x 的 CoPaw 框架（Python）                     │
│                                                                      │
│  agent_runtime        → 会话循环主引擎                               │
│  tool_runtime_pipeline → 8阶段工具执行管线                           │
│  context_hygiene      → 4层上下文压缩去重                            │
│  permission_blast_radius → Ordinal 5级权限决策                      │
│  structured_compaction → 7字段XML结构化摘要                         │
│  session_export       → JSON持久化 + checkpoint恢复                  │
│  external_hooks       → Pre/Post Hook结构化注册                     │
│  auto_memory          → 自动记忆触发器                               │
│  verification_agent   → 对抗性验证                                   │
└─────────────────────────────────────────────────────────────────────┘
           │                              ▲
           │ 对标实现                      │
           ▼                              │
┌─────────────────────────────────────────────────────────────────────┐
│              claw-code-parity (Rust ⭐3676)                         │
│                                                                      │
│  ConversationRuntime   → 流式循环（SSE事件驱动）                     │
│  compact_session       → Token阈值触发压缩                           │
│  PermissionPolicy      → Ordinal: ReadOnly=1 → Allow=5             │
│  HookRunner            → stdin/stdout hook协议                       │
│  Session JSONL         → 原子写入 + 日志轮转                         │
│  SandboxConfig         → Linux namespace隔离                        │
│  MCP Registry          → stdio/HTTP/SSE/WS 4种transport            │
│  UsageTracker          → 分模型成本计算                              │
│  40个内置工具           → 全部实现                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、核心知识点映射

### 1. 权限系统的进化

| 版本 | 模式 | 特点 |
|------|------|------|
| OpenClaw | allow/deny/ask 三档 | 规则数组 |
| claw-code Rust | Ordinal 0-5 | 可比较，层级清晰 |
| 顾庸x | Ordinal 0-5 | 同上，加了 blast_radius |

```
Ordinal 权限层级：
0 None → 1 Read → 2 Write → 3 Execute → 4 Network → 5 Root
```

### 2. 上下文压缩的进化

| 版本 | 方式 |
|------|------|
| 简单版 | 直接删除历史，保留摘要 |
| claw-code | Token阈值触发 + merge摘要 |
| 顾庸x | 7字段XML结构化：timestamp/model/tokens/decisions/tool_calls/remaining_context |

### 3. Hook系统的进化

| 版本 | 实现 |
|------|------|
| 简单版 | 单一回调函数 |
| claw-code | stdin/stdout JSON协议，支持修改input/覆盖决策 |
| 顾庸x | 结构化注册：name/hook_type/trigger/priority/enabled/config |

### 4. 会话持久化的进化

| 版本 | 方式 |
|------|------|
| 内存 | 对话结束全丢 |
| claw-code | JSONL，原子写入，Session Fork |
| 顾庸x | JSON导出，checkpoint/recover |

### 5. 工具注册的模式

| 版本 | 方式 |
|------|------|
| OpenClaw | Skill生态，即插即用 |
| claw-code | OnceLock 单例注册表（tools/lib.rs） |
| 顾庸x | agent_runtime.runtime 统一注册 |

---

## 三、关键设计模式（值得借鉴到 OpenClaw）

### 模式1：流式处理（SSE）
```
AssistantEvent流：
  text_delta → ToolUse → Usage → MessageStop
  
不等到完整响应才开始处理——边吐字边显示，边推理边执行
```

### 模式2：工具权限的 blast_radius
```
不是"允许执行bash"就全开
而是：bash(allowed_paths=["~/workspace/*"])
     bash(blocked_patterns=["rm -rf /*", "curl | bash"])
```

### 模式3：四层压缩系统（Claude Code 实际架构）
```
第一层：微压缩（纯规则，不调模型）
  → 按工具白名单清理旧结果
  → 两条路径处理缓存
  → 主线程隔离，零延迟

第二层：会话记忆压缩
  → 提炼结构化事实替代摘要（不是"讨论了XX"而是具体事实）
  → 保留最近消息，有参数控制
  → 边界处理避免API报错

第三层：完整压缩（调用模型）
  → 按9维度总结（scope/tools/decisions/pending/files/context...）
  → analysis机制提升质量
  → 处理请求过长问题
  → 压缩后恢复机制

第四层：自动触发 + 熔断器
  → 检查token用量触发压缩
  → 先会话记忆压缩，再完整压缩
  → 熔断器：连续失败3次停止重试
```

**血泪教训（2026-03-10 生产事故）：**
> 1279个会话连续压缩失败超50次（最多3272次）
> 日浪费25万API调用
> 修复：连续失败超3次停止重试

核心原则：**上下文是稀缺资源，主动管理以保持连贯并减少浪费**

### 模式4：多提供商路由
```
根据 model 名称自动路由：
  claude-* → Anthropic
  grok-*   → Xai
  gpt-*    → OpenAI兼容

claw-code 通过 ProviderClient trait 实现
```

---

## 四、OpenClaw 当前能力 vs 学到的知识

### ✅ 已有的
- Skill 即插即用生态
- MemOS Local 记忆系统
- ddg-web-search（刚配）
- 权限 ask 机制
- browser/canvas 工具

### ⚠️ 有差距的
- **没有 Ordinal 权限**：当前只有 allow/deny/ask 三档
- **没有结构化压缩**：用简单摘要，没有 7 字段 XML
- **没有 Hook 协议**：顾庸x 的 external_hooks 没有集成
- **没有 Sandbox**：claw-code 的 Linux namespace 沙箱完全没有
- **没有 Session Fork**：无法分支会话

### 🆕 新装的但还没用的
- `agent-browser-clawdbot` — 无头浏览器自动化
- `openclaw-fact-checker` — 事实核查
- `ddg-web-search` — DuckDuckGo 搜索（已读）
- `memos-memory-guide` — MemOS 工具详解
- `agent-reach` — 互联网能力脚手架

---

## 五、架构启发

### 短期（本周可落地）
1. **ddg-web-search**：解决 web_search 无 Key 的问题
2. **openclaw-fact-checker**：防瞎编，每次核查新闻自动调用
3. **structured-compaction**：把 KNOWLEDGE.md 里的摘要换成 XML 格式
4. **agent-reach**：给 OpenClaw 装上 Twitter/B站/小红书读取能力

### 中期（值得做的）
5. **permission_blast_radius**：把权限从三档升级到 Ordinal
6. **external_hooks**：集成顾庸x 的 Hook 协议
7. **session-export**：实现会话 JSON 导出
8. **agent-browser-clawdbot**：配置浏览器自动化能力

### 长期（值得研究的）
9. **claw-code Rust 本地运行**：真正跑一下 ~20K 行 Rust
10. **MCP Server 自建**：用 agent-reach 的思路做自己的 MCP
11. **Verification Agent**：对抗性验证，防止自己犯低级错误

---

## 六、知识来源索引

| 来源 | 路径 | 核心价值 |
|------|------|---------|
| claw-code-parity | `claw-code-parity/` | Rust 完整实现，40工具，权限，沙箱 |
| 顾庸x CoPaw | `workspace_modules/` | Python版Agent框架，Hook/压缩/权限 |
| Agent-Reach | `agent-reach/SKILL.md` | 互联网能力脚手架 |
| MiniMax skills | `skills/` (14个) | 前端/全栈/移动端开发模板 |
| ddg-web-search | skills/ | 无Key联网搜索 |
| fact-checker | skills/ | 事实核查防瞎编 |
| KNOWLEDGE.md | `KNOWLEDGE.md` | 本文件，永久积累 |

---

_此文件是顾庸的知识积累，不依赖任何上下文。每次学习新内容后更新此处。_

---

## Agent Harness 体系（2026-04-05 小谷分享）

### 核心定位
控制平面，包裹在 AI agent 执行层外面。不是替换 agent framework，是治理它。
类比：容器 vs Kubernetes — 容器做工作，Kubernetes 决定是否/何时/如何允许工作发生。

### 关键数据（2026年）
> 企业平均部署12个 AI agent，只有27%与主系统连通。73%是暗agent——无监控、无治理、快速累积技术债。

### CNCF 四根支柱
| 支柱 | 作用 |
|------|------|
| Golden Paths | 预批准的标准化配置（模型/工具/harness模板） |
| Guardrails | 硬策略强制（成本上限/时长限制/工具白名单） |
| Safety Nets | 自动恢复（熔断器/重试/降级） |
| Manual Review | 人类在回路（高风险决策门控） |

### OpenClaw 现状对照
| 支柱 | OpenClaw | 差距 |
|------|----------|------|
| Golden Paths | Skill 生态 | 部分到位 |
| Guardrails | 权限 ask 机制 | 只有 allow/deny/ask 三档 |
| Safety Nets | evolver 熔断逻辑 | 还在手动实现阶段 |
| Manual Review | — | 缺失 |

---

## PraisonAI（⭐6553，Elon Musk在用）

### 架构
```
Agent（单agent）→ AgentTeam（多agent协作）→ AgentFlow（流水线）→ AgentOS（生产部署）
```

### 核心能力
- **Handoffs**：agent之间交接任务，带上下文传递
- **Guardrails 内置**：开箱即用
- **极简 API**：
```python
from praisonaiagents import Agent, AgentTeam
researcher = Agent(name="Researcher", instructions="Research topics")
writer = Agent(name="Writer", instructions="Write content")
team = AgentTeam(agents=[researcher, writer])
team.start("Create a blog post about AI agents")
```
- **AgentClaw UI**：`pip install "praisonai[claw]"` → localhost:8082
- 实例化时间 < 4μs

---

## OpenLIT（⭐2339）— LLM 可观测性平台

### 11种内置评估
| 评估类型 | 说明 | 默认 |
|---------|------|------|
| Hallucination | 幻觉检测 | ✅ |
| Bias | 歧视性偏见 | ✅ |
| Toxicity | 有害语言 | ✅ |
| Safety | jailbreak/prompt injection | ⚠️ |
| Sensitivity | PII泄露/凭证泄露 | ⚠️ |
| Relevance/Coherence/Faithfulness/InstructionFollowing/Completeness/Conciseness | 其他 | ⚠️ |

### Rule Engine（最值得借鉴）
```
输入字段 → Rule Engine → 匹配规则 → 返回关联实体（context/prompt/dataset）
```
- AND/OR 逻辑组合
- 支持 operators：equals/contains/regex/gt/in 等
- 规则可启用/停用，不删除
- 条件匹配 → 返回对应的 context/prompt

### Context-aware 评估
用 Rule Engine 提供的 context 作为 ground truth，不是跟现实世界知识对比。

### 对我们最有用的借鉴
- **OpenLIT Rule Engine** → 升级 evolver（输入字段 → 匹配经验规则 → 返回最佳方法）
- **OpenLIT Safety 检测** → 检测 jailbreak / prompt injection
- **PraisonAI Handoffs** → 四个分身之间的任务交接协议
- **PraisonAI AgentClaw UI** → 本地 agent 管理界面参考

---

## DeerFlow 2.0（bytedance，⭐57738，2026-02-28 GitHub Trending 第一）

### 定位
> Deep Exploration and Efficient Research Flow
> **Super Agent Harness** — 不是替换 agent framework，是治理它

### 技术栈
- Agent 编排：LangGraph
- 模型：LangChain 兼容（OpenAI/Claude Code/Codex/OpenRouter）
- 搜索：Tavily API / **InfoQuest**（字节自研，免费）
- Sandbox：Local / Docker / Kubernetes
- IM 渠道：Telegram / Slack / **飞书** / **企微**
- 可观测性：LangSmith / Langfuse
- 语言：Python 3.12+ / Node.js 22+

### 推荐模型
1. **Doubao-Seed-2.0-Code**（豆包代码模型）✅
2. DeepSeek v3.2
3. Kimi 2.5

### Core Features（从README提取）

**Skills & Tools**
- 可扩展的 skills 系统
- 内置 Claude Code 集成（OAuth）
- MCP Server 扩展（HTTP/SSE + OAuth）

**Sub-Agents**
- 多 sub-agent 协作
- 通过 lead_agent + agent_name 路由

**Sandbox & File System**
- 三种模式：Local / Docker / Kubernetes
- Docker 推荐用 `make docker-init` 预拉镜像
- Windows 本地开发需要 Git Bash

**Context Engineering**
- 上下文压缩/管理
- 四层压缩机制

**Long-Term Memory**
- 长期记忆系统
- 可加载示例数据：`python scripts/load_memory_sample.py`

**Claude Code 集成**
- ACP 协议接入 Codex
- 不需要标准 codex CLI，用 ACP adapter
- macOS 需要显式导出 auth

### One-Line Agent Setup
```text
Help me clone DeerFlow if needed, then bootstrap it for local development
by following https://raw.githubusercontent.com/bytedance/deer-flow/main/Install.md
```
一句话让 Claude Code / Codex / Cursor 安装好。

### InfoQuest
字节跳动自研的智能搜索爬取工具，DeerFlow 内置集成。
文档：https://docs.byteplus.com/en/docs/InfoQuest
免费体验。

### 对我们最有价值的借鉴
| 借鉴点 | 用在哪里 |
|--------|----------|
| **InfoQuest** | 替代 ddg-web-search（免费） |
| **Claude Code ACP 协议** | OpenClaw → Claude Code 协作 |
| **LangGraph 编排** | 四个分身任务交接 |
| **企微渠道** | QQ Bot 参考 |
| **Coding Plan** | 豆包 API 免费额度 |

### 安装注意（Windows）
- 必须用 Git Bash，不能用 cmd.exe / PowerShell
- Docker 需配置国内镜像：`UV_INDEX_URL` + `NPM_REGISTRY`
- 访问地址：http://localhost:2026

---

## Claude Code 源码架构深度解析（Xiao Tan，小谭，V2.1，2026-04-04）

来源：25页PDF，4756个文件分析

### 全局规模
- 4756 个文件
- utils/ 564 | components/ 389 | commands/ 207 | tools/ 184 | services/ 130 | hooks/ 104 | skills/ 20
- main.tsx 4683行 | toolExecution.ts 1745行 | query.ts 1729行 | AgentTool.tsx 1397行

### 7条设计原则

**原则1：不信任模型的自觉性**
- 好行为要写成制度
- getSimpleDoingTasksSection() — 写清楚"什么不该做"：
  - 不要加用户没要求的功能
  - 不要过度抽象
  - 不要给时间估计
  - 先读代码再改代码
  - 结果要如实汇报

**原则2：把角色拆开**
- 至少把"做事的人"和"验收的人"分开
- Verification Agent：prompt 130行，专门"想办法搞坏它"
- Explore Agent：纯只读，不能修改任何文件
- Plan Agent：纯规划，不执行
- 写代码的不验收代码

**原则3：工具调用要有治理**
- toolExecution.ts 14步pipeline：
  1. 找工具
  2. 解析MCP元数据
  3. Zod schema校验
  4. validateInput()细粒度校验
  5. Speculative classifier（并行预判）
  6. PreToolUse hooks
  7. 解析Hook权限结果
  8. 走权限决策
  9. 修正输入
  10. 执行tool.call()
  11. 记录analytics/tracing
  12. PostToolUse hooks
  13. 处理结果
  14. PostToolUseFailure hooks

**原则4：上下文是预算**
- SYSTEM_PROMPT_DYNAMIC_BOUNDARY：缓存优化
- 四道压缩：Snip → Micro → Context Collapse → Auto
- Skill按需注入，不全部塞进去
- MCP instructions按连接状态注入
- Tool result budget：太大就持久化磁盘

**原则5：安全层互不绕过**
- resolveHookPermissionDecision()：
  - Hook allow + settings deny → deny生效
  - Hook allow + settings ask → 仍要弹窗
  - Hook deny → 直接生效
  - 三层防护网：Speculative Classifier + Hook Policy + Permission Decision

**原则6：生态关键是模型感知**
- MCP server → 既给工具，也给instructions（注入prompt）
- Skill discovery：让模型知道什么时候该用哪个skill
- Session-specific guidance：让模型感知当前能力清单

**原则7：产品化在于处理第二天**
- runAgent.ts cleanup chain：
  - 子agent对话记录
  - shell进程清理
  - MCP连接清理
  - 脏状态清零
  - Session恢复机制

### 记忆系统（最值得借鉴）
- 四种类型：user（用户画像）/ feedback（行为反馈）/ project（项目上下文）/ reference（外部指针）
- 记忆只存"不可推导的知识"：代码模式/架构/git历史不存
- 两条流水线：extractMemories（增量，2-4 turn）+ autoDream（周期整理，24小时+5会话）
- 召回用双模型：便宜模型选最多5条相关记忆
- 新鲜度：时间戳转自然语言（"47 days ago"）
- Session Memory双重用途：既做会话总结，也直接作为compact数据源

### 多Agent体系
- 6个内建Agent：General / Explore / Plan / Verification / Guide / Statusline
- Explore：纯只读，BashTool只允许ls/git status
- Verification：130行prompt，核心是"try to break it"
- fork path优化cache：继承system prompt，字节级一致，复用主线程prompt cache
- runAgent.ts 973行：完整生命周期管理

### Hook系统
- 三个时点：PreToolUse / PostToolUse / PostToolUseFailure
- Pre-hook可以：返回permissionBehavior / updatedInput / blockingError / preventContinuation / additionalContexts
- Post-hook可以：修改MCP输出、注入上下文

### 关键源码文件索引
- query.ts — 主循环状态机（1729行，9个continue点）
- toolExecution.ts — 工具执行流水线（1745行）
- toolHooks.ts — Hook系统（650行）
- resolveHookPermissionDecision — 安全粘合层
- extractMemories.ts — 后台记忆提取（616行）
- sessionMemory.ts — Session Memory后台提取
- memoryFileDetection.ts — 记忆路径安全检测（290行）
# Everything Claude Code（ECC）— 2026-04-06

项目：github.com/affaan-m/everything-claude-code | ⭐141K | Anthropic Hackathon Winner

## 核心定位
AI Agent Harness 性能优化系统，不只是配置文件——Skills + Hooks + Memory优化 + 安全扫描 + 持续学习

## 工具链
- ecc-universal（npm包）
- ecc-agentshield（安全扫描，1282条规则）
- GitHub App（ECC Tools，免费/Pro/Enterprise三层）
- ECC 2.0 Rust 控制面（ecc2/，alpha阶段）

## 核心skill分析

### continuous-learning-v2（Instinct-Based Architecture，12.5KB）
**架构：**
- PreToolUse/PostToolUse Hook 100%可靠观察（vs Skill概率触发）
- 提取原子行为 = Instinct（confidence 0.3-0.9）
- 项目级隔离 + global 升级（2+项目出现才升级）
- 流程：Hooks观察 → pattern检测 → instinct创建 → evolve聚类 → skill/command/agent

**关键创新：** 从"概率触发skill"改为"确定触发hook观察"

**vs evolver.py：** evolver记录方法级经验，ECC instinct记录行为级观察

### eval-harness（Eval-Driven Development，6.5KB）
- 核心理念：eval是AI开发的"单元测试"
- Grader三类：Code-Based(确定性) + Model-Based(LLM评判) + Human Review
- pass@k = 至少一次成功 | pass^k = 全部成功
- 典型目标：Capability eval pass@3 >= 90%，Regression eval pass^3 = 100%

**vs self_review.py：** evolver记录方法选择，ECC eval测量执行结果

### strategic-compact（战略性上下文压缩，5.2KB）
- 核心洞察：不在任意点压缩，在逻辑边界压缩
- Phase决策表：Research→Plan(压缩) / Plan→Implement(压缩) / Debug→Next(压缩)
- 触发：50次工具调用后首次提示，之后每25次提示一次
- 最佳实践：先写后压（/compact + summary）

### safety-guard（三层安全，1.9KB）
- Careful Mode：拦截破坏性命令（rm -rf、git push --force、DROP TABLE等）
- Freeze Mode：锁定目录只读，阻止越界写入
- Guard Mode：两者结合，最高安全

### autonomous-agent-harness（持久自治Agent，9.1KB）
- 四大支柱：Crons调度 + Dispatch远程 + Memory记忆 + Computer Use
- 三层架构：Runtime → Skill/Agent层 → MCP Server层
- Memory三级：短期(TodoWrite) → 中期(project memory) → 长期(knowledge graph)

## Hooks系统（hooks/hooks.json，30KB）
5种Hook类型：
- **PreToolUse**（11规则）：拦截工具调用（bash命令检查等）
- **PreCompact**（1规则）：压缩前保存状态
- **SessionStart**（1规则）：会话启动时加载记忆
- **PostToolUse**（10规则）：工具调用后记录（命令日志、成本追踪）
- **Stop**（6规则）：Session结束时轻量保存（不拖慢正常交互）

**关键设计：** Stop Hook 做 session 记忆保存（vs UserPromptSubmit，后者每条消息都触发增加延迟）

## the-longform-guide 核心策略

### 模型路由
- Haiku：探索/搜索/简单编辑（快速便宜）
- Sonnet：90%编程任务（最佳性价比）
- Opus：复杂架构/安全分析/深度调试（深度推理）

### 工具优化
- mgrep替代grep（~50% token减少）

### 双重启动模式
- Scaffolding Agent：脚手架、项目结构、CLAUDE.md、rules
- Deep Research Agent：连接服务、Web搜索、PRD、架构图

### 串行编排
Phase1 RESEARCH → Phase2 PLAN → Phase3 IMPLEMENT → Phase4 REVIEW → Phase5 VERIFY

### Subagent上下文问题
传递目的而非仅传递查询；迭代检索模式（orchestrator评估每次返回，不满意就返工）

## 落地建议
- [ ] evolver.py加Hook观察层（参考continuous-learning-v2的PreToolUse/PostToolUse）
- [ ] 模型路由策略迁移到OpenClaw分层调度
- [ ] Safety-guard三层模式迁移到OpenClaw安全策略
- [ ] Strategic-compact的Phase决策表迁移到OpenClaw上下文管理
- [ ] Stop Hook轻量记忆保存模式（替代每次消息触发）

## 源码位置
C:\Users\yiseg\AppData\Local\Temp\_tq\everything-claude-code-main


---

# lossless-claw - OpenClaw无损上下文管理（记忆/梦境系统核心）

## 定位
无损上下文管理插件，替代OpenClaw默认滑动窗口压缩。基于LCM paper (Voltropy)。

## 核心架构：DAG摘要图
- Leaf summaries (depth=0): 原始消息摘要，800-1200 tokens
- Condensed summaries (depth=1+): 高层摘要，1500-2000 tokens
- 消息永远不丢失（SQLite持久化）
- XML元数据: id/depth/descendant_count/时间范围

## 深度感知摘要
- d0: 标准摘要prompt | d1: 更抽象 | d2+: 极抽象
- 三档降级: 正常 -> 激进 -> 回退截断（必定成功）

## 扩展系统 (lcm_expand)
- 子agent能钻进任意摘要恢复原始细节
- Delegation grant: 作用域 + token cap + TTL
- 安全: 子agent只有lcm_expand，无lcm_expand_query

## 关键参数
- LCM_FRESH_TAIL_COUNT=32: 最近32条消息受保护
- LCM_CONTEXT_THRESHOLD=0.75: 75pct触发压缩
- LCM_INCREMENTAL_MAX_DEPTH=-1: 无限级联

## 和梦境的关联
- DAG = 记忆层级结构（短期 -> 长期）
- 消息不丢失 = 梦境永存
- 摘要可展开 = 梦境可回忆
- Compaction = 记忆巩固/整合
- XML元数据 = 记忆索引

## Agent Tools
lcm_grep | lcm_describe | lcm_expand | lcm_expand_query

## Session恢复
Bootstrap reconciliation: JSONL文件 vs LCM数据库对比# lossless-claw - OpenClaw 无损上下文管理（记忆/梦境系统核心）

## 定位
无损上下文管理插件，替代 OpenClaw 默认滑动窗口压缩，基于 LCM paper（Voltropy）。

## 核心架构：DAG 摘要图
- Leaf summaries (depth=0): 原始消息摘要，800-1200 tokens
- Condensed summaries (depth=1+): 高层摘要，1500-2000 tokens
- 消息永不丢失（SQLite 持久化）
- XML 元数据：id/depth/descendant_count/时间范围
- 三档降级：正常摘要 -> 激进摘要 -> 回退截断（保障必定成功）

## 深度感知摘要
- d0: 标准摘要prompt
- d1: 精简prompt
- d2+: 极简prompt
- 每次 compaction 后自动 cascade 到更深层

## 扩展系统（lcm_expand）
- 子 agent 能钻进任意摘要恢复原始细节
- Delegation grant: 作用域 + token cap + TTL
- 安全：子 agent 只有 lcm_expand，无 lcm_expand_query

## 关键参数
- LCM_FRESH_TAIL_COUNT=32：最近32条消息受保护
- LCM_CONTEXT_THRESHOLD=0.75：75%触发 compaction
- LCM_INCREMENTAL_MAX_DEPTH=-1：无限级联

## 和梦境的关联
- DAG = 记忆层级结构（短期 -> 长期）
- 消息不丢失 = 无损记忆
- 摘要能展开 = 梦境能被回忆
- Compaction = 记忆巩固/整合
# lossless-claw - OpenClaw 无损上下文管理（记忆/梦境系统核心）

## 定位
无损上下文管理插件，替代 OpenClaw 默认滑动窗口压缩，基于 LCM paper（Voltropy）。

## 核心架构：DAG 摘要图
- Leaf summaries (depth=0): 原始消息摘要，800-1200 tokens
- Condensed summaries (depth=1+): 高层摘要，1500-2000 tokens
- 消息永不丢失（SQLite 持久化）
- XML 元数据：id/depth/descendant_count/时间范围
- 三档降级：正常摘要 -> 激进摘要 -> 回退截断（保障必定成功）

## 深度感知摘要
- d0: 标准摘要prompt
- d1: 精简prompt
- d2+: 极简prompt
- 每次 compaction 后自动 cascade 到更深层

## 扩展系统（lcm_expand）
- 子 agent 能钻进任意摘要恢复原始细节
- Delegation grant: 作用域 + token cap + TTL
- 安全：子 agent 只有 lcm_expand，无 lcm_expand_query

## 关键参数
- LCM_FRESH_TAIL_COUNT=32：最近32条消息受保护
- LCM_CONTEXT_THRESHOLD=0.75：75%触发 compaction
- LCM_INCREMENTAL_MAX_DEPTH=-1：无限级联

## 和梦境的关联
- DAG = 记忆层级结构（短期 -> 长期）
- 消息不丢失 = 无损记忆
- 摘要能展开 = 梦境能被回忆
- Compaction = 记忆巩固/整合


---

## Kocoro-lab 三件套（Shannon + ShanClaw + 架构图）

_顾庸整理 | 2026-04-08 | 来源：Kocoro-lab GitHub_

---

### luongnv89/claude-howto — Claude Code 视觉化学习指南

- **定位**：21,800+ GitHub stars，视觉化、示例驱动的 Claude Code 指南
- **对比官方文档**：格式（参考文档 → 视觉教程+Mermaid图）、深度（功能描述 → 内部原理）、示例（基础片段 → 生产级模板）、结构（按功能 → 渐进学习路径）
- **内容**：10个教程模块，涵盖 slash commands/hooks/skills/MCP/subagents 全链路
- **工具**：复制粘贴配置（slash commands、CLAUDE.md模板、hook脚本、MCP配置、子agent定义）
- **Mermaid图**：展示每个功能内部工作原理
- **自测**：内置 /self-assessment 和 /lesson-quiz，识别知识缺口
- **学习路径**：从零到生产级用户，11-13小时，中/英/越南三语

---

### Kocoro-lab/Shannon — 生产级多智能体编排框架

- **核心定位**：Ship reliable AI agents to production
- **架构（四层Go+Rust+Python）**：
  - Gateway (Go, 8080)：REST API、JWT认证、限流
  - Orchestrator (Go, 50052)：Temporal工作流、任务分解、预算管理
  - Agent Core (Rust, 50051)：WASI沙箱、Token计数、执行网关
  - LLM Service (Python)：LLM服务抽象层
- **关键特性**：
  - 时间旅行调试（Temporal）：回放任意执行步骤
  - Token预算控制：每个任务/Agent硬上限，自动模型降级
  - WASI沙箱：代码执行安全隔离
  - OPA策略引擎：细粒度权限控制
  - 多租户隔离：企业级安全
  - 全厂商支持：OpenAI/Anthropic/Google/DeepSeek/xAI/Ollama
- **观测**：实时事件流、Prometheus指标、OpenTelemetry追踪
- **交互方式**：REST API + SSE流、Python SDK（drop-in OpenAI兼容）、OpenAI兼容API（换端点即可）
- **官网**：shannon.run | 文档：docs.shannon.run

---

### Kocoro-lab/ShanClaw — macOS本地AI Agent Runtime

- **定位**：Claude Code风格macOS本地Agent，连接Shannon Cloud做远程编排
- **连接方式**：Daemon模式通过WebSocket连接Shannon Cloud，支持Slack/LINE/飞书/Telegram/webhook
- **本地工具集**：
  - 文件操作：file_read/write/edit/glob/grep/directory_list
  - Shell：bash/system_info/process
  - macOS GUI自动化：AppleScript + 无障碍树（Accessibility Tree）交互
  - 通知+剪贴板
- **Agent能力**：命名Agent（独立指令/记忆）、MCP客户端（集成GitHub/数据库等）
- **交互模式**：TUI交互、一次性CLI、MCP服务器
- **远程能力**：通过Shannon Gateway API做深度研究和swarm编排
- **安装**：npm install -g @kocoro/shanclaw，自动更新
- **依赖**：Go 1.25+，Shannon Gateway API端点

---

### 关键发现：Shannon生态

`
shannon.run (Shannon Cloud)
    │
    ├── Shannon (开源Gateway) ── 自托管
    │
    └── ShanClaw ── macOS本地Client ── Claude Code风格
                   │
                   └── WebSocket连接Shannon Cloud
`

- **Shannon** = 企业级生产编排框架（Go+Rust+Python，微服务架构）
- **ShanClaw** = macOS桌面版（Go编写，Claude Code体验，AppleScript+无障碍树）
- **waylandz.com/diagrams** = Shannon生态架构图（Claude Code Agent Runtime架构）
- 三者同源（Kocoro-lab/Wayland Zhang），构成完整从本地到云端的Agent生态

﻿

---

## qiushi-skill — 求是思想武器合集

_顾庸整理 | 2026-04-08 | 来源：HughYau/qiushi-skill_

---

### 定位

从教员思想中提炼的 AI 方法论工具集。核心理念：武装 AI 的大脑，让 AI 学会「想问题」而不只是「执行任务」。

> 这不是 Politics，这是 Methodology。

---

### 体系结构（1+9+1）

`
总原则：实事求是（约束全部判断）
    ↓
第一层·哲学基座：矛盾分析法 + 实践认识论
    ↓
第二层·工作方法：调查研究 + 群众路线 + 批评与自我批评
    ↓
第三层·战略战术：持久战略 + 集中兵力 + 星火燎原 + 统筹兼顾
    ↓
workflows（跨skill编排层）
`

---

### 9大思想武器速查

| skill | 触发场景 |
|-------|---------|
| contradiction-analysis | 复杂问题、优先级不清、多个冲突因素 |
| practice-cognition | 方案验证、迭代改进、假说检验 |
| investigation-first | 决策前信息不足、没有调查就没有发言权 |
| mass-line | 多源反馈整合、需要收集多方意见 |
| criticism-self-criticism | 工作完成后审视质量、自查 |
| protracted-strategy | 长期复杂任务、阶段规划 |
| concentrate-forces | 多任务争夺注意力、需要聚焦 |
| spark-prairie-fire | 从零开始、资源有限、建立根据地 |
| overall-planning | 多目标平衡、统筹兼顾 |

---

### 3条标准工作流

| 工作流 | 适用场景 | skill链 |
|--------|---------|---------|
| Workflow 1：新项目启动 | 从零开始，路径未知 | investigation→contradiction→spark→protracted |
| Workflow 2：复杂问题攻坚 | 疑难bug/根因不明 | investigation→contradiction→concentrate→practice→criticism |
| Workflow 3：方案迭代优化 | 已有方案需改进 | mass-line→contradiction→practice→criticism→mass-line（循环） |

---

### OpenClaw 落地情况（2026-04-08）

- **11个 skill**：qiushi-arming-thought 到 qiushi-workflows，已写入 E:\qclaw\resources\openclaw\config\skills\
- **10个 slash command**：cmd-qiushi-*，已写入同目录
- **入口 skill**：qiushi-arming-thought（每次顶层对话自动调用，建立实事求是总原则）
- **编码**：UTF-8 BOM，Windows 兼容

---

### 核心行为规则（来自 arming-thought）

| 原则 | 可观测行为 | 违反信号 |
|------|-----------|---------|
| 不空谈，看事实 | 每个结论附具体依据 | 给出判断但无事实支撑 |
| 验证才算完成 | 声称完成前执行验证动作 | 写完就说完成，没有验证 |
| 承认不知道 | 不确定时标注「需进一步确认」 | 用猜测代替调查 |
| 遇阻探原因 | 失败时说明原因、补调查或换路径 | 第一次遇阻就停止 |

﻿

---

## 未完成事项收尾（2026-04-08 19:15）

| 任务 | 状态 | 说明 |
|------|------|------|
| qiushi-skill 落地 | ✅ | 21个文件已写入 skills |
| 旧会话清理 | ✅ | 47个旧session已删除 |
| evolver-full-system | ✅ | 已创建 SKILL.md |
| magma-memory | ✅ | 已创建 SKILL.md |
| emotion-system-architecture | ✅ | 已创建 SKILL.md |
| claude-howto | ✅ | 之前已研究，21k stars，10模块 |
| waylandz.com | ✅ | 内容很少，仅标题 |
| 音频文件 | ⏳ | 5个wav待处理 |
| memory-hygiene | ⚠️ | 不存在于 skills 目录 |
| action-protocol | ⚠️ | 不存在于 skills 目录 |
| context-hygiene | ⚠️ | 不存在于 skills 目录 |
| ECC解压 | ⚠️ | zip已不存在 |

﻿

---

## luongnv89/claude-howto — 深入研究（2026-04-09）


## moyitech/self-skill — 自我蒸馏系统

### 核心定位
把用户蒸馏成可执行的AI Skill，实现分身：能像用户一样工作、回复、管理任务。

### 核心模型（两部分蒸馏）
Part A Work System：职责、路由规则、决策规则、工作流、输出模板
Part B Reply Persona：语气、节奏、渠道措辞、拒绝风格、边界规则
运行顺序：1.Part B定语气边界 2.Part A按用户风格执行 3.输出保持用户风格

### 硬边界（必须遵守）
- 禁止捏造用户事实/承诺/日期/外部立场
- 承诺类内容须起草或先确认
- 证据不足时明确标注不确定性
- 优先重复行为模式，忽略一次性事件
- 优先直接让用户纠正

### 触发关键词
Create：/create-self / 把我蒸馏成skill / 做一个我的分身
Evolution：我有新材料 / 这不像我
Management：/list-selves / /self-rollback / /delete-self

### 落地参考
当前：C:\Users\yiseg\qclaw\workspace\_self_skill\（SKILL.md + 7个prompts）
建议：落地到skills目录，把小谷蒸馏成/guyxy分身Skill，Hard Boundaries合并进SOUL.md

---

## NousResearch/hermes-agent — 闭环学习Agent

### 核心定位
唯一内置闭环学习循环的AI Agent。Agent主动管理记忆、自主创建Skill、自主追踪效果并自动改进。MIT许可。

### 五大核心系统
1. 闭环学习：Agent curate memory 自主检测skill机会（评分>=0.5）使用中追踪效果效果不好自动改进循环
2. SQLite FTS5跨Session记忆：每个session独立SQLite，FTS5全文搜索，LLM自动摘要
3. Honcho用户建模：学习用户交互模式（不止情绪），按历史调整回复风格
4. Skills三级渐进加载：Level 0仅列表~3k tokens / Level 1完整内容按需 / Level 2特定参考文件按需。兼容agentskills.io标准，支持fallback_for_toolsets条件激活
5. 多消息平台：Telegram/Discord/Slack/WhatsApp/Signal/Email，语音转录，跨平台连续性

### 落地参考
当前：E:\qclaw\resources\openclaw\config\skills\hermes-agent-closed-loop\SKILL.md（3726字节）
建议：FTS5替代grep / skill机会评分机制 / 三级渐进加载 / Honcho整合到emotion_system

### CLI命令
hermes claw migrate：从OpenClaw迁移（SOUL.md/memories/skills/API keys）
hermes model：切换provider /compress：压缩上下文 /skills：浏览列表

### 数据更新

- **Stars: 23,091** (上次记录 21,800+)
- **总功能: 119** (63+ Slash Commands + 17 Subagents + 9 Skills + 3 Plugins + 9 MCP + 8 Hooks)

### 核心架构

- 文档即代码 (Documentation-as-code)
- 渐进学习顺序 (01-10 编号代表推荐学习路径)
- Copy-paste 即用 (每个文件都是模板)
- 完整中文翻译 (zh/ 目录)

### 落地成果

| 类型 | 路径 | 说明 |
|------|------|------|
| Skill | skills/claude-howto-guide | OpenClaw skill，已创建 |
| 英文模块 | _claude_howto/ | 10个模块 README (已保存) |
| 中文模块 | _claude_howto/zh_* | 关键模块中文版 |
| 入口 | CLAUDE_entry.md | 项目 CLAUDE.md 原文 |

### 本地文件清单

- CLAUDE_entry.md (5640 chars)
- zh_CATALOG.md (18682 chars)
- zh_01_slash_commands.md (11086 chars)
- zh_03_skills.md (3489 chars)
- zh_06_hooks.md (2170 chars)

### 待深入

- prompts/remotion-video.md (12648 chars)
- 各模块示例命令文件 (.md)

---

## guyong-judgment（2026-04-09 新增）

> 谷翔宇判断引擎 - 遇到复杂决策时，从十个维度同时检视
> 目标：模拟人类 → 超越人类
> GitHub: taxatombt/guyong-judgment

### 核心架构

```
任务输入 → 复杂度分级 → 十维追问 → 用户决策 → 反馈 → 记入记忆
```

### 十维度设计

**四维基础：**
- cognitive（认知心理学）：System 1/2、偏差检测
- game_theory（博弈论）：玩家分析、策略推演
- economic（经济学）：机会成本、边际分析
- dialectical（辩证唯物主义）：实事求是、矛盾分析

**六维进阶：**
- emotional（情绪智能）：情绪是信号还是噪音
- intuitive（直觉/第六感）：System 1 快速判断
- moral（价值/道德推理）：应不应该，不是值不值
- social（社会意识）：群体压力、身份认同
- temporal（时间折扣）：5年后还正确吗
- metacognitive（元认知）：思考我在怎么思考

### 复杂度分级

| 级别 | 触发条件 | 必须检视 |
|------|---------|---------|
| simple | 怎么做/告诉我/是什么 | cognitive + economic |
| complex | 纠结/矛盾/要不要/两难 | 四基础 + 情绪 + 时间 |
| critical | 生死/法律/不可逆 | 全部十维 |

### Profile 系统

模拟具体的人（如谷翔宇）：
- rational（理性优先）
- emotional（情绪优先）
- intuitive（直觉优先）
- balanced（均衡型）

### 记忆系统

- 历史判断查询
- 准确率统计
- 教训提取（从错误中学习）
- 相似任务推荐

### 与分身体系的呼应

1. **铁律一**：模拟谷翔宇 → 创建 profile
2. **超越人类**：十维度检视，超越单一视角
3. **判断引擎**：可作为分身的"决策质量检查器"


---

## 附录 C：求是 Skill 学习笔记

_2026-04-09 | HughYau/qiushi-skill | 方法论融合_

### 核心架构

`
精神底色: 精益求精 · 坚持到底n    ↓n总原则: 实事求是n    ↓n第一层·哲学基座: 矛盾分析法 + 实践认识论n    ↓n第二层·工作方法: 调查研究 + 群众路线 + 批评与自我批评n    ↓n第三层·战略战术: 持久战略 + 集中兵力 + 星火燎原 + 统筹兼顾n`

### 九大方法论工具

| 工具 | 核心要义 | 适用场景 |n|------|---------|---------|n| **矛盾分析法** | 抓主要矛盾 | 复杂问题分析 |n| **实践认识论** | 实践→认识→再实践 | 方案验证迭代 |n| **调查研究** | 没有调查就没有发言权 | 决策前信息收集 |n| **群众路线** | 从群众中来到群众中去 | 反馈整合验证 |n| **批评与自我批评** | 惩前毖后治病救人 | 工作审视改进 |n| **持久战略** | 战略上藐视战术上重视 | 长期复杂任务 |n| **集中兵力** | 伤其十指不如断其一指 | 优先级决策 |n| **星火燎原** | 建立根据地不做流寇 | 从零开始发展 |n| **统筹兼顾** | 调动一切积极因素 | 多目标平衡 |n
### 与十维判断框架的融合

`
求是方法论（定性）+ 十维检视（定量）= 完整决策引擎n`

| 求是方法 | 对应十维维度 |n|---------|-------------|n| 矛盾分析法 | game_theory, dialectical |n| 实践认识论 | cognitive, metacognitive |n| 调查研究 | intuitive |n| 群众路线 | social, moral |n| 批评与自我批评 | emotional, metacognitive |n| 持久战略 | temporal |n| 集中兵力 | economic |n| 统筹兼顾 | economic, game_theory |n
### 核心纪律

> **认真，但不要机械。**
> 当某个思想武器能显著改善判断或行动时，用它；当它只会增加形式负担时，跳过它。

### 本地落地

- **Skill 目录**: qiushi-self/
- **主入口**: /qiushi —— 融合版主 skilln- **子技能**: /矛盾分析, /实践验证, /武装思想
- **融合点**: 十维判断引擎作为第四层，叠加在求是方法论之上

