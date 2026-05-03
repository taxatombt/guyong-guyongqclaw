# Claude Code src-claudecode 全量研究完成

## 研究范围
E:\ai\学习\10src-claudecode\（1884个TypeScript文件）

## 研究完成时间
2026-05-01 18:55 GMT+8

---

## 功能开关完整列表（37个）

| Count | Feature | 用途 |
|-------|---------|------|
| 38 | KAIROS | Assistant模式 |
| 31 | TEAMMEM | Teammate功能 |
| 16 | PROACTIVE | 主动触发 |
| 16 | COORDINATOR_MODE | 协调者模式 |
| 15 | HISTORY_SNIP | 历史截断 |
| 12 | TRANSCRIPT_CLASSIFIER | 转录分类 |
| 11 | CONTEXT_COLLAPSE | 上下文折叠 |
| 9 | EXPERIMENTAL_SKILL_SEARCH | 技能搜索 |
| 8 | SHOT_STATS | 统计 |
| 8 | COMMIT_ATTRIBUTION | 提交归因 |
| 8 | BRIDGE_MODE | Bridge模式 |
| 7 | EXTRACT_MEMORIES | 记忆提取 |
| 6 | BASH_CLASSIFIER | Bash安全分类器 |
| 6 | BG_SESSIONS | 后台会话 |
| 6 | AGENT_TRIGGERS | Agent触发器 |
| 5 | WORKFLOW_SCRIPTS | 工作流脚本 |
| 5 | UDS_INBOX | UDS收件箱 |
| 4 | TOKEN_BUDGET | Token预算 |
| 4 | VOICE_MODE | 语音模式 |
| 4 | TEMPLATES | 模板 |
| 3 | CCR_AUTO_CONNECT | CCR自动连接 |
| 3 | MEMORY_SHAPE_TELEMETRY | 记忆遥测 |
| 2 | BREAK_CACHE_COMMAND | 缓存破坏 |
| 2 | REACTIVE_COMPACT | 响应式压缩 |

---

## GrowthBook功能开关系统

### 三层覆盖优先级
1. **CLAUDE_INTERNAL_FC_OVERRIDES** (env var) - ant only
2. **config overrides** (/config Gates tab) - ant only
3. **remote eval** (default)

### 关键机制
- `remoteEvalFeatureValues` - 远程求值缓存
- `pendingExposures` - init前访问的特征
- `loggedExposures` - 去重，防止重复曝光事件
- `onGrowthBookRefresh` - 特征刷新监听器

---

## 快捷键系统 (keybindings/defaultBindings.ts)

### Global上下文
- `ctrl+c` - app:interrupt (双击时间处理)
- `ctrl+d` - app:exit
- `ctrl+l` - app:redraw
- `ctrl+t` - app:toggleTodos
- `ctrl+o` - app:toggleTranscript
- `ctrl+r` - history:search

### Chat上下文
- `escape` - chat:cancel
- `enter` - chat:submit
- `up/down` - history:previous/next
- `ctrl+x ctrl+k` - chat:killAgents

### 平台差异
- **Windows**: `alt+v` (图片粘贴), `meta+m` (模式切换)
- **其他**: `ctrl+v` (图片粘贴), `shift+tab` (模式切换)

---

## 核心服务系统

### 1. AgentSummary (services/AgentSummary/)
- **频率**: 每30秒 (`SUMMARY_INTERVAL_MS = 30_000`)
- **机制**: fork subagent生成1-2句进度摘要
- **缓存**: `cacheSafeParams` 共享prompt cache
- **用途**: Coordinator mode sub-agent UI显示

### 2. PromptSuggestion (services/PromptSuggestion/)
- **开关**: `tengu_chump_inflection` GrowthBook feature
- **抑制条件**:
  - `disabled` - 功能禁用
  - `pending_permission` - 等待权限
  - `elicitation_active` - 活跃请求
  - `plan_mode` - 计划模式
  - `rate_limit` - 速率限制
- **生成条件**: 未abort + ≥2 assistant轮 + 最后响应非API错误

### 3. SessionMemory (services/SessionMemory/)
- **开关**: `tengu_session_memory`
- **配置**: `tengu_sm_config`
- **阈值**: 
  - `hasMetInitializationThreshold` - 初始化token阈值
  - `hasMetUpdateThreshold` - 更新token阈值
  - `countToolCallsSince` - tool调用计数

### 4. TeamMemorySync (services/teamMemorySync/)
- **API**: `GET/PUT /api/claude_code/team_memory?repo={owner/repo}`
- **Sync语义**:
  - Pull: server wins (覆盖本地)
  - Push: delta upload (仅上传hash不同的key)
  - 删除: 不传播
- **限制**:
  - `MAX_FILE_SIZE_BYTES = 250,000`
  - `MAX_PUT_BODY_BYTES = 200,000`

### 5. Coordinator (coordinator/coordinatorMode.ts)
- **开关**: `COORDINATOR_MODE` feature + `CLAUDE_CODE_COORDINATOR_MODE` env
- **内部工具**: `TEAM_CREATE`, `TEAM_DELETE`, `SEND_MESSAGE`, `SYNTHETIC_OUTPUT`
- **会话恢复**: `matchSessionMode` 翻转env var

---

## Bash权限系统 (tools/BashTool/bashPermissions.ts)

### 关键常量
- `MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50`
- `MAX_SUGGESTED_RULES_FOR_COMPOUND = 5`

### 安全检查流程
1. `parseCommandRaw` - 原始解析
2. `splitCommand` - 分割子命令
3. `parseForSecurityFromAst` - Tree-sitter AST分析
4. `checkSemantics` - 危险命令名检测
5. `checkPathConstraints` - 路径约束
6. `checkSedConstraints` - sed约束
7. `classifyBashCommand` - ANT-ONLY分类器

### 降级策略
Tree-sitter → shell-quote → 简单解析

---

## Task系统 (Task.ts)

### TaskType
- `local_bash` - 本地bash
- `local_agent` - 本地agent
- `remote_agent` - 远程agent
- `in_process_teammate` - 进程内队友
- `local_workflow` - 本地工作流
- `monitor_mcp` - MCP监控
- `dream` - 梦想任务

### TaskStatus
- `pending` / `running` / `completed` / `failed` / `killed`

---

## QueryEngine (QueryEngine.ts + query.ts)

### Feature Gates
- `REACTIVE_COMPACT` - 响应式压缩
- `CONTEXT_COLLAPSE` - 上下文折叠
- `HISTORY_SNIP` - 历史截断
- `EXPERIMENTAL_SKILL_SEARCH` - 技能搜索
- `TEMPLATES` - 作业分类器
- `BG_SESSIONS` - 后台会话摘要

### 核心组件
- `query.ts` - 主查询处理函数
- `QueryEngine.ts` - 查询引擎编排
- `replLauncher.tsx` - REPL启动器

---

## 已覆盖全部核心模块

| 模块 | 状态 |
|------|------|
| Hook系统 (27事件) | ✅ |
| Memory系统 (4-type) | ✅ |
| Coordinator Mode | ✅ |
| Verification Agent | ✅ |
| Permission System | ✅ |
| Agent System (6种) | ✅ |
| Token Budget | ✅ |
| SDK API | ✅ |
| Remote/Sandbox/MCP | ✅ |
| Task System | ✅ |
| Cron调度 | ✅ |
| Bootstrap State | ✅ |
| AppState | ✅ |
| main.tsx启动序列 | ✅ |
| Context系统 | ✅ |
| Skills系统 | ✅ |
| Commands系统 | ✅ |
| GrowthBook | ✅ |
| 快捷键系统 | ✅ |
| AgentSummary | ✅ |
| PromptSuggestion | ✅ |
| SessionMemory | ✅ |
| TeamMemorySync | ✅ |
| Bash权限 | ✅ |
| QueryEngine | ✅ |

---

## qclaw可借鉴点

1. **GrowthBook三层覆盖** → qclaw规则引擎分层
2. **AgentSummary 30秒摘要** → qclaw进度跟踪
3. **TeamMemorySync delta upload** → qclaw记忆同步
4. **MAX_SUBCOMMANDS=50防DoS** → qclaw命令安全
5. **Feature flags** → qclaw功能开关设计
