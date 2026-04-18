# SKILL.md — Nezha Agent Desktop（多Agent并行编排）

## 项目概览

| 字段 | 值 |
|------|-----|
| 名称 | Nezha — An Agent-First Vibecoding Desktop |
| 作者 | hanshuaikang |
| 地址 | github.com/hanshuaikang/nezha |
| 技术栈 | Tauri（Rust后端） + React + TypeScript |
| 安装包 | **仅7MB**，Electron的零头 |
| 核心功能 | Claude Code + Codex 并行跑，多项目切换，实时终端，Git集成 |
| stars | 正在增长中（非开源大项目，但是设计很精妙）|

## 核心架构

```
┌─────────────────────────────────────────────────────────┐
│  React/TypeScript 前端（src/）                          │
│  ├── App.tsx              ← 状态管理：projects/tasks/sessions│
│  ├── useTerminalManager    ← PTY输出流控：10MB限制/帧预算  │
│  ├── useProjectPanels     ← 多面板状态管理                │
│  └── components/           ← 9个UI组件                   │
│      ├── AnalyticsDashboard ← Usage统计                  │
│      ├── AppSettingsDialog  ← Agent配置（37KB）           │
│      └── ...                                        │
│                                                          │
│  Rust 后端（src-tauri/src/）                             │
│  ├── lib.rs              ← TaskManager（全局共享状态）    │
│  ├── pty.rs               ← PTY创建/进程管理/权限模式     │
│  ├── session.rs           ← 会话检测/状态轮询/JSONL读取   │
│  ├── git.rs               ← Git操作（23KB）              │
│  ├── usage.rs             ← Claude/Codex用量API           │
│  ├── notification.rs      ← 通知管理                     │
│  ├── app_settings.rs      ← Agent路径检测/版本检测        │
│  └── analytics.rs         ← Session指标                  │
└─────────────────────────────────────────────────────────┘
```

## 核心设计亮点

### 1. PTY虚拟终端 — Claude Code/Codex 直接跑在里面

**`pty.rs`（24KB）** — 最关键的文件。

```rust
// 权限模式三档
fn build_claude_cmd(agent_bin: &str, permission_mode: &str) -> CommandBuilder {
    match permission_mode {
        "ask"         => "--permission-mode default"
        "auto_edit"   => "--permission-mode acceptEdits"
        "full_access" => "--dangerously-skip-permissions"
    }
}

// PTY emit 背压控制
const PTY_EMIT_CHANNEL_CAPACITY: usize = 32;  // 有界channel，满时内核缓冲区反压
const DRAIN_FRAME_BUDGET = 128 * 1024;         // 每帧最多128KB，避免UI卡顿
```

**三件事同时做**：
1. PTY reader 线程：读取进程输出 → 发 `agent-output` 事件给前端
2. Session watcher：检测 `.codex/sessions/rollout-*.jsonl` → 读取对话历史
3. Exit monitor：轮询子进程退出 → 更新任务状态

### 2. Session 自动发现 — 不依赖任何API

**`session.rs`（53KB）** — 最复杂的文件。

Codex session 检测：
```rust
fn collect_session_files(dir: &Path, out: &mut Vec<PathBuf>) {
    // 只找 rollout-*.jsonl，不碰其他文件
    let is_rollout_jsonl = file_name.starts_with("rollout-") && ends_with(".jsonl");
}
```

Claude session 检测：轮询 `~/.claude/projects/*/sessions/*.jsonl`，解析 JSONL 找 `session_id`。

关键设计：用 `notify` crate 监听文件变化（文件系统事件驱动），避免轮询浪费。

### 3. 状态共享 — TaskManager 全局单例

```rust
pub struct TaskManager {
    pub pty_masters: Mutex<HashMap<String, Box<dyn MasterPty + Send>>>,
    pub pty_writers:  Mutex<HashMap<String, Box<dyn Write + Send>>>,
    pub child_handles: Mutex<HashMap<String, Arc<Mutex<Box<dyn Child + Send + Sync>>>>>,
    pub cancelled_tasks: Mutex<HashSet<String>>,
    pub codex_sessions: Mutex<HashMap<String, CodexSessionInfo>>,
    pub claude_sessions: Mutex<HashMap<String, ClaudeSessionInfo>>,
    pub claimed_session_paths: Mutex<HashSet<String>>,  // 防重复claim
    pub codex_rpc: Arc<Mutex<Option<CodexRpcClient>>>,    // 复用app-server进程
}
```

### 4. 流控 — requestAnimationFrame 协作调度

**前端 `useTerminalManager.ts`**：
```typescript
// 协作式调度：isInputPending() 检查用户是否在输入
if (navigator.scheduling?.isInputPending?.()) {
    rafId = requestAnimationFrame(drainPendingOutputs);  // 让出主线程
    return;
}
```

### 5. 图片附件处理

Claude Code 本身不支持粘贴图片，但 Nezha 做了桥接：
```rust
// pty.rs - save_task_images()
let attachments_dir = Path::new(project_path)
    .join(".nezha").join("attachments").join(task_id);
fs::create_dir_all(&attachments_dir)?;
// 解析 "data:image/png;base64,<data>" 格式，保存为 .png/.jpg/.gif/.webp
// 路径追加到 prompt 末尾：[Attached images]\n/path/to/img0.png
```

## qclaw 可移植设计点

| 设计 | Codex/Claude Code | qclaw落地 |
|------|------------------|----------|
| **PTY虚拟终端** | Claude Code官方只支持CLI | `kc-gui` skill可模拟类似效果 |
| **权限模式** | 三档控制（ask/auto_edit/full） | `agents/tool_pipeline.py`已有 |
| **Session发现** | 文件系统监听+JSONL解析 | `agents/session_checkpoint.py`已有 |
| **有界Channel背压** | PTY满时write()阻塞 | 可借鉴`ralph_anti_loop.py`的熔断机制 |
| **7MB安装包** | Tauri比Electron小10x | qclaw本身就是轻量工具 |
| **Usage统计** | Claude API + Codex API分别查询 | `qclaw_insights.py`已有统计 |
| **图片粘贴桥接** | Claude Code本身不支持→桥接 | 顾庸t的agent-browser已有 |

## 关键数据

- **AppSettingsDialog.tsx**：37KB，配置Agent路径/版本/Prompt前缀
- **git.rs**：23KB，完整Git操作集（commit/diff/status/log/branch）
- **notification.rs**：14KB，通知系统
- **session.rs**：53KB，最复杂，会话检测核心
- **pty.rs**：24KB，进程管理核心
- **analytics.rs**：9KB，Usage分析

## 核心技术依赖

```toml
# Rust端
portable_pty       # 跨平台伪终端
notify             # 文件系统事件监听
uuid               # Session ID生成
serde_json         # JSON序列化
tokio              # 异步任务

# TypeScript端
@tauri-apps/api/core   # Tauri invoke/emit
@tauri-apps/plugin-dialog  # 文件选择对话框
```
