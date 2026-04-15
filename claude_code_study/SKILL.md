# Claude Code TypeScript 源码研究

_来源: E:\ai\资源\10src-claudecode\src (1866 TS文件, 34模块)_

## 核心架构发现

### 1. Agent 系统（tools/AgentTool/）

**四种内置 Agent**：

| Agent | 模型 | 权限 | 特点 |
|-------|------|------|------|
| General Purpose | 默认 | 全工具 (`tools: ['*']`) | 简洁 prompt，完成即汇报 |
| Explore | haiku | READ-ONLY | omitClaudeMd=true，省5-15 Gtok/week |
| Plan | inherit | READ-ONLY | 同 Explore 工具集，omitClaudeMd=true |
| Verification | feature flag | READ-ONLY(项目) | 153行反合理化 prompt，强制命令验证 |

**Agent 生命周期（runAgent.ts 974行）**：
1. 初始化 MCP 服务器（agent frontmatter 可定义专属 MCP）
2. 解析工具权限（allowedTools 替换 session 规则，保留 SDK --allowedTools）
3. 构建 system prompt（Explore/Plan 省略 CLAUDE.md + gitStatus）
4. 执行 SubagentStart hooks → 注入 additionalContexts
5. 注册 agent frontmatter hooks（Stop → SubagentStop）
6. 预加载 skills（resolveSkillName 多策略匹配）
7. 创建 subagent context（sync 共享 / async 隔离）
8. 进入 query loop（AsyncGenerator<Message>）
9. 结束时 cleanup（killShellTasks, mcpCleanup, unregisterPerfettoAgent）

**权限模式层级**：bypassPermissions > acceptEdits > auto > agent定义
- async agents 默认 shouldAvoidPermissionPrompts=true
- bubble 模式可以弹窗到父终端

### 2. 记忆系统（memdir/）

**四类型分类**：
- `user` — 用户角色/偏好/知识（永远 private）
- `feedback` — 工作指导，含纠正+确认（默认 private，项目约定 team）
- `project` — 项目上下文，非代码可推导（偏向 team）
- `reference` — 外部系统指针（Linear/Grafana 等）

**MEMORY.md 是索引，不是内容**：
- 200行 / 25KB 上限
- 每行 ≤150 字符，格式：`- [Title](file.md) — one-line hook`
- 两步写入：① 独立文件 ② MEMORY.md 加指针
- 截断时自动追加 WARNING

**frontmatter 格式**：
```yaml
---
name: user_role
description: User is a data scientist focused on observability
type: user  # user | feedback | project | reference
---
记忆内容...
```

**Assistant 模式（KAIROS feature flag）**：
- append-only 日志：`logs/YYYY/MM/YYYY-MM-DD.md`
- 夜间 /dream skill 蒸馏日志 → MEMORY.md + topic files
- 与普通模式的区别：不维护 MEMORY.md 索引，只追加日志

### 3. Token 预算（query/tokenBudget.ts）

- **COMPLETION_THRESHOLD = 0.9**：90% 预算触发判断
- **DIMINISHING_THRESHOLD = 500**：连续3次 delta < 500 → 收益递减 → 停止
- 两种决策：continue（附 nudge 消息）或 stop（含 completionEvent 统计）

### 4. Verification Agent 反合理化策略

核心认知：LLM 会自己找借口跳过验证。解决方法：**明确列出借口，要求做相反的事**。

| 借口 | 正确做法 |
|------|---------|
| "代码看起来正确" | 阅读不是验证，运行它 |
| "实现者的测试已通过" | 实现者是 LLM，独立验证 |
| "应该没问题" | "应该"不是验证，运行它 |
| "让我看代码" | 不，启动服务并调用端点 |
| "我没有浏览器" | 检查 MCP 工具是否可用 |
| "这会花太长时间" | 不是你的决定 |

**验证输出格式（强制）**：
```
### Check: [验证什么]
**Command run:** [执行的命令]
**Output observed:** [实际输出]
**Result: PASS/FAIL**
```
无 Command run 的 PASS = 跳过，被拒绝。

### 5. 关键设计模式

**Agent 工具解析（resolveAgentTools）**：每个 agent 可定义 disallowedTools，过滤掉禁止的工具

**Skill 预加载**：agent frontmatter `skills: [...]` → resolveSkillName（精确→插件前缀→后缀三策略）→ 异步并发加载 skill 内容

**MCP 隔离**：agent 定义的 MCP 服务器是 additive 的，结束时只清理新建的，共享的不清理

**Fork 模式**：useExactTools=true → 继承父级 thinkingConfig 和工具集，产生字节级一致的 API 请求前缀用于 prompt cache

## 与 qclaw 的差距

| 特性 | Claude Code | qclaw | 状态 |
|------|------------|-------|------|
| Agent 四角色 | Explore/Plan/Verify/General | agents/agent_types.py 四角色 | ✅ 已有 |
| READ-ONLY agent | disallowedTools + omitClaudeMd | 部分实现 | 🟡 需补 |
| 记忆四类型 | user/feedback/project/reference | MEMORY.md 直接写内容 | 🟡 需重构 |
| MEMORY.md 索引制 | 两步写入 + 200行限制 | 单文件全量 | 🔴 需学习 |
| Token 预算 | 90% 阈值 + 收益递减检测 | 无 | 🔴 需实现 |
| Verification 反合理化 | 153行 prompt | 无 | 🔴 需学习 |
| Agent MCP 隔离 | additive + selective cleanup | 无 | 🟡 |
| Skill 预加载 | frontmatter + 三策略解析 | 无 | 🟡 |
