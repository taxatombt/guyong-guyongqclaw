# Nezha 学习落地 — 2026-04-18

## 找到了什么

**hanshuaikang/nezha** — "An Agent-First Vibecoding Desktop"  
核心：一个 Tauri 桌面应用，把 Claude Code 和 Codex **直接跑在虚拟终端（PTY）里**，同时管理多项目、多会话、多任务。

## 源码分析结果

### 目录结构
```
nezha/
├── src/                    # React + TypeScript 前端
│   ├── App.tsx             # 主状态管理（20164B）
│   ├── types.ts            # Project/Task/AgentType/PermissionMode
│   ├── hooks/
│   │   ├── useTerminalManager.ts   # PTY输出流控（9180B）⭐
│   │   ├── useProjectPanels.ts     # 多面板管理（6004B）
│   │   ├── useUsageSnapshot.ts     # Usage统计
│   │   └── useCancellableInvoke.ts
│   └── components/         # 9个组件
│       ├── AnalyticsDashboard.tsx  # Usage仪表盘
│       ├── AppSettingsDialog.tsx   # Agent配置（37KB！⭐）
│       ├── FileExplorer.tsx       # 文件树
│       └── FileViewer.tsx          # Markdown+代码编辑器
│
└── src-tauri/src/          # Rust 后端
    ├── lib.rs              # TaskManager 全局单例（4523B）
    ├── pty.rs               # PTY创建/进程管理/权限（24367B）⭐⭐⭐
    ├── session.rs           # 会话检测/JSONL解析（53094B）⭐⭐⭐
    ├── git.rs               # Git操作（23457B）
    ├── usage.rs             # Claude+Codex Usage API（19469B）
    ├── notification.rs      # 通知系统（13911B）
    ├── app_settings.rs      # Agent路径/版本检测（12579B）
    ├── analytics.rs         # Session指标（9297B）
    ├── fs.rs                # 文件操作（8145B）
    ├── config.rs            # 项目配置（6319B）
    ├── storage.rs           # 项目/任务持久化（5228B）
    └── main.rs              # 入口（180B）
```

## 核心设计（最值得学的地方）

### 1. PTY 虚拟终端 — 最高价值设计

Claude Code 和 Codex **不是被"调用"的工具，而是直接跑在PTY里**：
```rust
// pty.rs — 启动 Claude Code 或 Codex
let agent_bin = get_agent_bin(&agent);  // 根据 agent="claude"|"codex" 选bin
let is_codex = agent == "codex";

// 权限模式三档
fn build_claude_cmd(agent_bin: &str, permission_mode: &str) -> CommandBuilder {
    match permission_mode {
        "ask"         => c.arg("--permission-mode").arg("default")
        "auto_edit"   => c.arg("--permission-mode").arg("acceptEdits")
        "full_access" => c.arg("--dangerously-skip-permissions")
    }
}
```

关键：Claude Code 跑在PTY里 → 输出完全保留原始行为 → 只是外面包了一层编排层。

### 2. Session 自动发现 — 零 API 依赖

**`session.rs`（53KB）** 最精妙的部分：

```rust
// Codex session 检测：监听 rollout-*.jsonl 文件
fn collect_session_files(dir: &Path, out: &mut Vec<PathBuf>) {
    // 只找 rollout-*.jsonl，不碰其他
    let is_rollout_jsonl = file_name.starts_with("rollout-") 
                        && file_name.ends_with(".jsonl");
}

// 用 notify crate 做文件系统事件驱动（不是轮询！）
let mut watcher_opt = notify::RecommendedWatcher::new(tx, notify::Config::default())
    .ok()
    .and_then(|mut w| {
        w.watch(&session_path, RecursiveMode::NonRecursive).ok()?;
        Some(w)
    });
```

**Claude session 检测**：轮询 `~/.claude/projects/*/sessions/*.jsonl`，解析JSONL找session_id。

### 3. 有界 Channel 背压 — 内核级流控

```rust
// pty.rs
const PTY_EMIT_CHANNEL_CAPACITY: usize = 32;  // 有界channel
// 满了 → reader线程的 send() 阻塞 → 内核缓冲区满
// → write() 系统调用阻塞 → Claude Code的输出自动被限流
```

### 4. 前端 RAF 协作调度 — UI不卡顿

```typescript
// useTerminalManager.ts
function drainPendingOutputs() {
    // 关键：isInputPending() 检查用户是否在输入
    if (navigator.scheduling?.isInputPending?.()) {
        rafId = requestAnimationFrame(drainPendingOutputs);
        return;  // 让出主线程
    }
    // 处理输出...
    if (pendingOutputs.size > 0 && !rafId) {
        rafId = requestAnimationFrame(drainPendingOutputs);
    }
}
```

### 5. 图片粘贴桥接

Claude Code 本身不支持图片粘贴 → Nezha做了桥接：
```rust
// 解析 "data:image/png;base64,<data>" 格式
// 保存到 .nezha/attachments/{task_id}/
// prompt末尾追加：[Attached images]\n/path/to/img0.png
```

### 6. TaskManager 全局单例

```rust
pub struct TaskManager {
    pub pty_masters: Mutex<HashMap<String, Box<dyn MasterPty + Send>>>,
    pub pty_writers:  Mutex<HashMap<String, Box<dyn Write + Send>>>,
    pub child_handles: Mutex<HashMap<String, Arc<Mutex<Box<dyn Child + Send + Sync>>>>>,
    pub cancelled_tasks: Mutex<HashSet<String>>,
    pub codex_sessions: Mutex<HashMap<String, CodexSessionInfo>>,
    pub claude_sessions: Mutex<HashMap<String, ClaudeSessionInfo>>,
    pub claimed_session_paths: Mutex<HashSet<String>>,
    pub codex_rpc: Arc<Mutex<Option<CodexRpcClient>>>,  // 复用app-server进程
}
```

### 7. 37KB 的 AppSettingsDialog

包含了完整的 Agent 配置 UI：路径选择、版本检测、Prompt前缀、权限模式等。

## 对 qclaw 的启发

| Nezha 设计 | qclaw 现状 | 启发 |
|-----------|----------|------|
| Claude Code 在PTY里跑，外面包编排 | qclaw的sessions_spawn是独立进程 | **更彻底的隔离：agent跑在真实终端里，而不是被qclaw调用** |
| Session文件监听+JSONL解析 | agents/session_checkpoint已有类似 | **可以借鉴notify crate做事件驱动** |
| 7MB安装包（Tauri） | OpenClaw本身已轻量 | 验证了"集成优于重写"的思路 |
| 权限三档 | agents/tool_pipeline.py已有 | 可以更精细化 |
| 协作式流控（isInputPending） | 无类似设计 | 可以借鉴到terminal输出管理 |

## 最核心的认知

**Nezha 的设计哲学：Agent-First。**

Claude Code/Codex 不是"被控制的工具"，而是"拥有完整自主权的协作者"。Nezha只负责：
1. 启动/终止
2. 输入/输出路由
3. 会话持久化
4. 多任务管理

这和 qclaw 的"分身"概念高度一致——每个分身有自己的记忆、自己的判断、自己的行动，只是在同一个环境里协作。

## Files

- `nezha_study/SKILL.md`（4934B）— 完整总结
- 本文档

## Git Commit

需要把小谷的所有study目录都git add + push。
