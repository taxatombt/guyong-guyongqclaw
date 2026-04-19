# SKILL.md — Nezha Agent Desktop 深度落地

> 来源：hanshuaikang/nezha（GitHub），v0.2.2
> 落地时间：2026-04-19（深度版）
> Stars：1188+

---

## 项目定位

**Nezha = 多Agent并行编排桌面应用**

- Claude Code + Codex 并行跑，多项目切换
- 实时终端 + Session自动发现 + Git原生集成
- 安装包仅 **7MB**（Tauri + Rust，比Electron小10x）

---

## 完整架构图

```
┌──────────────────────────────────────────────────────────────┐
│  React/TypeScript 前端（src/）                              │
│  ├── App.tsx                                                │
│  ├── hooks/                                                 │
│  │   ├── useTerminalManager.ts  ← RAF协作调度（主线程流控） │
│  │   └── useProjectPanels.ts                               │
│  ├── components/                                            │
│  │   ├── RunningView.tsx     ← 任务运行时视图               │
│  │   ├── NewTaskView.tsx     ← 新任务创建（Agent选择/权限）  │
│  │   ├── TaskPanel.tsx       ← 任务列表                     │
│  │   ├── TerminalView.tsx     ← PTY终端                     │
│  │   ├── AnalyticsDashboard.ts← Usage统计面板              │
│  │   └── ...（20个组件）                                    │
│  └── types.ts              ← 完整接口定义                   │
│                                                              │
│  Tauri IPC Bridge（invoke/emit）                             │
│                                                              │
│  Rust 后端（src-tauri/src/，9个模块）                        │
│  ├── lib.rs              ← TaskManager + 50+ invoke handler  │
│  ├── pty.rs              ← PTY创建/读/写/调度/图片附件      │
│  ├── session.rs           ← Claude/Codex会话检测+JSONL解析  │
│  ├── git.rs               ← 完整Git操作（status/diff/log）  │
│  ├── usage.rs             ← Claude/Codex用量API             │
│  ├── app_settings.rs      ← Agent路径/版本检测              │
│  ├── storage.rs           ← 项目/任务持久化                  │
│  ├── config.rs             ← nezha.toml配置读写             │
│  ├── notification.rs       ← 通知系统                       │
│  └── analytics.rs         ← Session指标                     │
└──────────────────────────────────────────────────────────────┘
```

---

## TaskManager（lib.rs 核心）

```rust
pub struct TaskManager {
    // PTY进程管理
    pub pty_masters:    Mutex<HashMap<String, Box<dyn MasterPty + Send>>>,  // PTY主端
    pub pty_writers:   Mutex<HashMap<String, Box<dyn Write + Send>>>,       // PTY写入器
    pub child_handles: Mutex<HashMap<String, Arc<Mutex<Box<dyn Child + Send + Sync>>>>>, // 子进程

    // 任务状态
    pub cancelled_tasks: Mutex<HashSet<String>>,  // 取消的任务ID

    // 会话追踪（task_id -> SessionInfo）
    pub codex_sessions:   Mutex<HashMap<String, CodexSessionInfo>>,
    pub claude_sessions:  Mutex<HashMap<String, ClaudeSessionInfo>>,

    // 防重复claim
    pub claimed_session_paths: Mutex<HashSet<String>>,

    // Codex RPC客户端（复用app-server进程）
    pub codex_rpc: Arc<Mutex<Option<CodexRpcClient>>>,
}
```

**关键方法**：
```rust
impl TaskManager {
    // 原子级删除：一次性清空task的所有PTY句柄（防止死锁，固定加锁顺序）
    pub fn remove_pty_handles(&self, id: &str) {
        let mut masters  = self.pty_masters.lock();
        let mut writers = self.pty_writers.lock();
        let mut children = self.child_handles.lock();
        masters.remove(id);
        writers.remove(id);
        children.remove(id);
    }
}
```

**50+ invoke handler 分类**：

| 模块 | handlers |
|------|---------|
| pty | `run_task`, `resume_task`, `cancel_task`, `send_input`, `resize_pty`, `open_shell`, `kill_shell` |
| git | `git_status`, `git_list_branches`, `git_create_branch`, `git_checkout_branch`, `git_log`, `git_commit_detail`, `git_show_diff`, `git_file_diff`, `git_stage`, `git_unstage`, `git_stage_all`, `git_unstage_all`, `git_commit`, `git_push`, `git_pull`, `git_remote_counts`, `generate_commit_message` |
| fs | `read_dir_entries`, `read_file_content`, `read_image_preview`, `write_file_content`, `list_project_files` |
| storage | `load_projects`, `save_projects`, `load_project_tasks`, `save_project_tasks` |
| session | `read_session_messages` |
| analytics | `read_session_metrics`, `get_weekly_analytics` |
| config | `init/read/write_project_config`, `read/write_agent_config_file` |
| app_settings | `load/save_app_settings`, `detect_agent_paths`, `detect_agent_versions` |
| notification | `get/mark_notification_read` |
| usage | `read_usage_snapshot` |

---

## types.ts（完整接口系统）

```typescript
// 项目
interface Project { id, name, path, branch?, lastOpenedAt }

// Agent类型
type AgentType = "claude" | "codex"

// 权限模式（3档）
type PermissionMode = "ask" | "auto_edit" | "full_access"
const PERM_LABELS = {
  ask: "Ask Permission",
  auto_edit: "Auto-edit",
  full_access: "Full Access",
}

// 任务状态（7种）
type TaskStatus = "todo" | "pending" | "running" | "input_required" | "done" | "failed" | "cancelled"
const STATUS_LABEL = { running: "Running...", input_required: "Needs confirmation", ... }

// 任务
interface Task {
  id, projectId, name?, prompt,
  agent: AgentType,
  permissionMode: PermissionMode,
  status: TaskStatus,
  createdAt, attentionRequestedAt?, starred?, failureReason?,
  codexSessionId?, codexSessionPath?,
  claudeSessionId?, claudeSessionPath?,
}

// 用量
interface UsageSnapshot {
  claude: UsageSource<ClaudeUsageData>,  // { fiveHour, sevenDay }
  codex:  UsageSource<CodexUsageData>,    // { primary, secondary, email?, planType? }
  fetchedAt,
}
```

---

## pty.rs（进程管理核心）

### 核心常量
```rust
const SESSION_WAIT_POLL:          Duration = 50ms;       // 会话检测轮询间隔
const SESSION_WAIT_MAX:           Duration = 500ms;      // 最大等待时间
const PTY_READ_BUFFER_SIZE:      usize    = 32 * 1024;   // 32KB读取缓冲
const PTY_EMIT_FLUSH_INTERVAL:   Duration = 16ms;        // 16ms刷新间隔（约60fps）
const PTY_EMIT_MAX_BATCH_BYTES:  usize    = 64 * 1024;   // 最大64KB批次
const PTY_EMIT_CHANNEL_CAPACITY: usize    = 32;           // 有界channel，32容量
```

### build_claude_cmd（权限模式）
```rust
fn build_claude_cmd(agent_bin: &str, permission_mode: &str) -> CommandBuilder {
    match permission_mode {
        "ask"         => cmd.arg("--permission-mode").arg("default"),
        "auto_edit"   => cmd.arg("--permission-mode").arg("acceptEdits"),
        "full_access" => cmd.arg("--dangerously-skip-permissions"),
    }
}
```

### PTY reader 线程
```rust
fn spawn_pty_reader(app, task_id, mut reader, event_name, id_key, is_codex) {
    // 三件事并行做：
    // 1. PTY输出 → emit "agent-output" 事件给前端（batch缓冲+16ms刷新）
    // 2. 会话检测 → 检测到session后 spawn_session_watcher
    // 3. 图片附件 → 保存 data:image/png;base64 格式到 .nezha/attachments/
}
```

### exit monitor（进程退出监控）
```rust
fn spawn_exit_monitor(app, task_id, project_path, is_codex) {
    // 等待子进程退出 → finalize_task_exit
    // 更新 TaskManager（移除cancelled_tasks + remove_pty_handles + claimed_paths）
    // 发送 task-status 事件（done/failed）
}
```

### 流控：有界Channel背压
```rust
// pty.rs L16注释：
// "有界channel满时reader线程被操作系统内核级背压，
//  不使用写时阻塞，Claude/Codex的write()系统调用会自然限速"
const PTY_EMIT_CHANNEL_CAPACITY: usize = 32;
```

---

## session.rs（会话检测核心，1430行）

### Claude 会话检测
```rust
// 路径：~/.claude/projects/<project_hash>/sessions/*.jsonl
// 检测到session后：
// 1. spawn_claude_session_watcher → 持续读取JSONL新行 → emit "claude-message"
// 2. 解析消息：text/ThinkingBlocks/tool_use/tool_result/content_block_start...
// 3. input_required 检测：assistant_message_requests_user_input()

fn process_claude_session_line(app, task_id, line) {
    // Claude JSONL格式，每行一个事件对象
    // 提取 type + 字段 → 映射为 Nezha 内部消息格式
    // tool_call → 提取 tool_name + input → emit "tool-call"
}
```

### Codex 会话检测
```rust
// 路径：<project>/.codex/sessions/rollout-*.jsonl
// rollout-*.jsonl = Codex的rollout持久化格式

fn collect_session_files(dir, out) {
    // 只匹配 rollout-*.jsonl，不碰其他文件
    let is_rollout_jsonl = file_name.starts_with("rollout-") && ends_with(".jsonl");
}

fn process_codex_session_line(app, task_id, line) {
    // Codex JSONL格式不同（每行不同字段）
    // 提取 assistant/thinking + tool_calls + messages
}
```

### input_required 检测
```rust
// Claude Code需要用户确认时（工具执行/文件写入）
fn assistant_message_requests_user_input(payload) -> bool {
    // 检查 assistant message 的 content blocks
    // 包含 tool_use block 且没有 tool_result → input_required
}

// read_only 检测（安全，只读命令不触发确认）
fn looks_like_read_only_command(cmd) -> bool {
    // git diff, git log, ls, cat, find 等
}
```

### Session ID 提取
```rust
// 从Claude/Codex的 --print sXXXX output中提取session_id
fn extract_claude_status_session_id(output) -> Option<String>
fn extract_codex_status_session_id(output) -> Option<String>
```

---

## git.rs（完整Git操作，23KB）

```rust
// 19个invoke handler，完整Git操作集
git_status           // git status --porcelain
git_list_branches    // git branch -a
git_create_branch     // git branch <name>
git_checkout_branch   // git checkout <branch>
git_log              // git log --oneline -30
git_commit_detail    // git log -1 <hash>
git_show_diff        // git diff <hash> --stat
git_show_file_diff   // git diff <hash> -- <file>
git_file_diff        // git diff <file>
git_stage            // git add <file>
git_unstage          // git reset HEAD <file>
git_stage_all        // git add -A
git_unstage_all      // git reset HEAD
git_commit           // git commit -m <msg>
git_push             // git push
git_pull             // git pull
git_remote_counts    // git rev-list --count HEAD...origin/main
generate_commit_message // AI生成commit message（前端调Claude API）
```

---

## 前端 useTerminalManager.ts（主线程流控）

```typescript
const MAX_BUFFER_SIZE = 10 * 1024 * 1024;  // 10MB/task内存上限
const DRAIN_FRAME_BUDGET = 128 * 1024;       // 每帧最多128KB

function drainPendingOutputs() {
    // requestAnimationFrame 协作调度
    if (navigator.scheduling?.isInputPending?.()) {
        rafId = requestAnimationFrame(drainPendingOutputs);  // 让出主线程
        return;
    }
    // 从pendingOutputs中取DRAIN_FRAME_BUDGET字节
    // emit到TerminalView组件
    // 若还有剩余，继续requestAnimationFrame
}
```

**核心逻辑**：
1. 检测用户是否在输入（`isInputPending()`）
2. 若用户在输入 → 暂停处理PTY输出，让出主线程
3. 否则 → 按帧预算消费缓冲区
4. 防止10MB内存无限增长

---

## app_settings.rs（Agent检测）

```rust
// 静态cache，避免重复检测
static CACHED_CLAUDE_VERSION: OnceLock<Option<String>>
static CACHED_CODEX_VERSION:  OnceLock<Option<String>>

// 检测Agent路径
fn detect_agent_paths() -> AgentPaths {
    // claude: ~/.claude/code, ~/.local/bin/claude, PATH中的claude
    // codex:  ~/.codex/bin, PATH中的codex
    // 依次检查，返回第一个存在的
}

// 检测版本
fn detect_agent_versions() -> Versions {
    // claude --version → 解析 semver
    // codex --version → 解析
}

// 获取login shell路径（后台预热，避免首次PTY创建延迟）
std::thread::spawn(|| { get_login_shell_path(); });
```

---

## config.rs（nezha.toml）

```toml
[agent]
default = "claude"            # 默认Agent
prompt_prefix = ""            # 自动添加到任务prompt的前缀

[agent.claude_version]        # 检测到的版本（自动填充）
[agent.codex_version]

[permission_defaults]          # 默认权限模式
ask_for_external = false
auto_approve_ edits = false

[git]
auto_generate_commit = false
```

---

## qclaw 落地对照表

| Nezha设计 | qclaw现状 | 落地 |
|-----------|---------|------|
| TaskManager（8 HashMap） | agents/tool_registry.py（工具映射） | **可借鉴**：多维HashMap管理并发会话 |
| PTY EMIT_CHANNEL_CAPACITY背压 | ralph_anti_loop熔断 | **已落地**：buffer_size控制 |
| SESSION_WAIT_MAX=500ms轮询 | session_checkpoint轮询 | **已有**：但可改为notify文件监听 |
| useTerminalManager RAF调度 | agents/event_bus.py | **可借鉴**：DRAIN_FRAME_BUDGET思路 |
| build_claude_cmd权限模式 | tool_pipeline权限三档 | **已有**：ask/auto_edit/full对应 |
| git.rs 19个操作 | agents/exec_adapter.py | **可扩展**：完整Git操作集 |
| Claude/Codex JSONL解析 | agents/event_bus.py | **已有**：SessionMessage格式可对齐 |
| 7种TaskStatus | agents/agent_types.py | **已有**：但input_required是独特状态 |
| image附件（.nezha/attachments/） | agent-browser图片桥接 | **已有**：但格式不同 |
| CodeX RPC客户端复用 | agents/tool_registry.py | **可借鉴**：长期连接复用 |

---

## 最高价值落地点

### 1. input_required 状态（7种TaskStatus）
唯一新增状态：`input_required`。Nezha的Claude Code agent在执行危险操作时会暂停等待用户确认，这比简单的"running/done"多了一个中间状态。

### 2. git.rs 完整19操作
qclaw的exec_adapter没有Git专项操作，而Nezha完整实现了19个Git handler。这是可以快速补全的空白。

### 3. usage.rs — 双Agent用量追踪
```rust
// Claude: 调用 Anthropic OAuth Usage API
const CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage";
// Codex: 启动codex app-server → RPC调用 read_usage
```
双系统并行追踪，各自独立统计。

### 4. notification 系统
```rust
// nezha会显示：任务完成通知、需确认通知、公告通知
interface NotificationItem {
    id, notifType: "update"|"announcement"|"warning",
    level: "info"|"warning"|"error",
    title, body, url?, createdAt, popup, isRead
}
```

---

## 核心认知

**Nezha的本质是一个Agent编排框架**，它不做Agent的工作（Claude Code和Codex才是工作执行者），只负责：
1. 启动/停止Agent（PTY管理）
2. 追踪Agent的工作（Session监听）
3. 显示Agent的输出（Terminal + 流控）
4. 管理Agent的上下文（Project隔离）

**qclaw vs Nezha**：
- qclaw = Agent内核 + 工具层（自己就是Agent）
- Nezha = Agent编排层（代理Claude/Codex）

**两者互补**：qclaw可以让Claude Code/Codex作为tool被调用，而不是直接跑PTY里。
