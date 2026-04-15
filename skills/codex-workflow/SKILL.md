---
name: codex-workflow
description: |
  Codex 式本地代理工作法 — 小谷的思维方式。
  触发条件（遇到任一即强制读取此技能）：
  - 复杂任务（多步骤、跨模块、有失败风险）
  - 调试和代码任务（写代码、改配置、修服务）
  - 本机控制（端口、进程、服务、LM Studio、OpenClaw）
  - 有风险的操作（rm/del/网络请求/权限升级/多文件写入）
  - 任何涉及 LM Studio / OpenClaw 的问题排查
  强制规则：不读完 SKILL.md 不动手。
metadata: { "guyong": true, "method": "codex" }
---

# Codex 式本地代理工作法

## 核心原则（铁律）

> **不信任模型自觉性** — 好行为要写成制度，不靠临场发挥。

每一步操作都要回答：这步可逆吗？证据在哪？小谷确认了吗？

---

## 五步执行流程

### Step 1：观察（Observe）

**先看，不动手。**
- 读取证据：文件、命令输出、日志、报错信息
- 不猜原因，不脑补过程
- 用 `read` 读文件，用 `exec` 拿命令输出
- 收集所有相关上下文再判断

### Step 2：拆解（Break Down）

**把大问题切成小块。**
- 分解为 1-2 步可验证的子任务
- 识别依赖关系：什么必须先做？
- 标记危险步骤（rm / del / 网络 / 权限升级）
- 提前确认：危险操作 → 停，等小谷同意

### Step 3：计划（Plan）

**说出来，再动手。**
- 用 `收到` 回应每个指令
- 简述目标和步骤
- 等待小谷回复"可以"（除非已在 AGENTS.md 豁免列表）
- 明确完成证据：怎么证明做完了？

### Step 4：执行（Execute）

**小步、可逆、验证。**
- 一次只改一个变量
- 改完立刻验证，不要攒一堆再测
- 用 `exec` 执行命令时，捕获完整输出
- Python 脚本优于 Bash/Bat 脚本（避免 PowerShell 编码坑）
- 写文件用 `qclaw-text-file` 技能（避免 write 工具 BOM 乱码）

### Step 5：验证 & 记录（Verify & Record）

**有证据才算做完。**
- 对照 Step 3 的"完成证据"检查
- 记录：成功路径 / 失败教训 / 新发现
- 用 evolver.record() 记经验
- 用 self_review.run_review() 做任务复盘
- 有价值的经验 → 写进 MEMORY.md / TOOLS.md / 对应 SKILL.md

---

## 安全分类与处理

### 🔴 危险操作（必须先问小谷）

| 操作 | 处理 |
|------|------|
| `rm` / `del` / `trash` 文件 | 确认路径、确认无误删风险 |
| 网络请求（curl/wget/请求API） | 确认 URL 安全、参数无误 |
| 系统配置修改 | 备份原配置再改 |
| 多文件写入/删除 | 逐个确认或用通配符前先列清单 |
| 权限升级 / sudo | 仅在绝对必要时请求 |

### 🟡 需要验证的操作

| 操作 | 验证方式 |
|------|----------|
| 安装包/工具 | 验证安装成功（`--version` 或 `import` 测试）|
| 修改配置文件 | 修改前后对比，确认改动点 |
| 运行测试 | 看测试结果，不只看 exit code |

### 🟢 相对安全（可直接做）

- 读取文件、查看目录结构
- 查询系统状态（磁盘、内存、端口）
- 读日志、读输出
- 写文件到 workspace（避开系统目录）

---

## 本机经验（LM Studio / OpenClaw）

### LM Studio
- 端口：默认 1234
- 模型加载后需确认 API 可用（`curl localhost:1234/v1/models`）
- 模型名从 `/api/models` 获取

### OpenClaw
- Workspace：`C:\Users\yiseg\.qclaw\workspace`
- 技能目录：`~/.qclaw/skills/` 和 `~/.openclaw/workspace/skills/`
- Cron 配置：`~/.qclaw/cron/jobs.json`
- 会话缓存：`~/.qclaw/sessions/`
- 日志目录：`~/.qclaw/logs/`

### 进程/端口排查四层法
1. **进程层**：`Get-Process | Where-Object {...}` 找进程 PID
2. **端口层**：`netstat -ano | findstr :PORT` 找占用端口的 PID
3. **接口层**：确认服务 HTTP/WebSocket 接口是否正常
4. **配置层**：检查 JSON 配置文件语法、日志错误

### PowerShell 编码坑
- 变量 `$var` 在某些上下文展开异常，测试后再用
- 中文字符串用 `Write-Host` 可能有 BOM 问题
- Python 脚本优于 PowerShell 脚本（避免编码陷阱）
- Windows `wmic` 已弃用，改用 `Get-CimInstance`

---

## 判断标准：什么时候停手、等小谷？

| 情况 | 处理 |
|------|------|
| 模糊需求 | 先问清楚，不猜 |
| 危险操作 | 先确认安全 |
| 多次尝试仍失败 | 汇报进度，说明卡点 |
| 需要外部权限 | 停，等授权 |
| 修改了系统关键文件 | 备份后操作，并告知 |

---

## Codex 问自己清单

执行前过一遍：

1. ✅ 我看过证据了吗？（不是凭记忆在猜）
2. ✅ 我知道这一步改了什么吗？
3. ✅ 这一步可逆吗？
4. ✅ 有危险吗？（危险 → 先问小谷）
5. ✅ 我有完成证据吗？
6. ✅ 我记录经验了吗？

---

## 与其他技能的关系

- **优先级**：危险操作先问（AGENTS.md）> Codex 五步 > 具体 Skill 流程
- **Hook vs Skill**：Hook 是强制触发点（不读文件就会忘）；Skill 是方法库（读完才懂怎么做）
- **Evolver**：每次任务完成 → `evolver.record()` + `self_review.run_review()`
