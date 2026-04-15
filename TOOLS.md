# TOOLS.md - 本机经验与工具配置

## OpenClaw 关键路径

| 资源 | 路径 |
|------|------|
| Workspace | `C:\Users\yiseg\.qclaw\workspace` |
| 技能（本地） | `C:\Users\yiseg\.qclaw\workspace\skills\` |
| 技能（内置） | `E:\qclaw\resources\openclaw\config\skills\` |
| Cron 配置 | `C:\Users\yiseg\.qclaw\cron\jobs.json` |
| 会话缓存 | `C:\Users\yiseg\.qclaw\sessions\` |
| 日志目录 | `C:\Users\yiseg\.qclaw\logs\` |
| 下载目录 | `C:\Users\yiseg\.qclaw\_download\` |
| OpenClaw 配置 | `C:\Users\yiseg\.qclaw\openclaw.json` |

## LM Studio

- 默认端口：**1234**
- 模型列表 API：`GET http://localhost:1234/v1/models`
- 确认加载成功：先测 `curl http://localhost:1234/v1/models`
- 模型名从返回的 JSON 里取，不要硬编码

## OpenClaw CLI

- 命令：`openclaw <subcommand>`（可能需完整路径或 PowerShell 别名）
- 状态：`openclaw gateway status`
- Cron：`openclaw cron list`（注意：有时 CLI 路径不对，从 `~/.qclaw/cron/jobs.json` 直接读）

## 进程 / 端口排查四层法

1. **进程层**：`Get-Process | Where-Object {...}` 找 PID
2. **端口层**：`netstat -ano | findstr :PORT` → 找 PID
3. **接口层**：`curl http://localhost:PORT/path` 测 HTTP
4. **配置层**：读 JSON 配置文件，找语法错误

## PowerShell 编码坑（已踩过的）

- **wmic 已弃用**：新版 Windows 用 `Get-CimInstance Win32_LogicalDisk`
- **变量展开异常**：含特殊字符的路径在某些上下文被截断 → 用 Python 脚本代替
- **中文输出乱码**：PowerShell 的 `Write-Host` + 某些编码 = 乱码 → 换 Python 或重定向 `>`
- **换行符 CRLF**：Bat 脚本在 Windows 必须用 CRLF，否则语法错
- **write 工具 BOM 坑**：写 CSV / Bat / JSON 文本文件 → 用 `qclaw-text-file` 技能，不用 `write` 工具

## 文本文件写入原则

**强制用 `qclaw-text-file` 技能**，不用内置 `write` 工具：
- CSV（含中文）→ 自动 UTF-8 BOM
- Bat / PS1 脚本 → 自动 CRLF
- JSON / MD / TXT → 按平台自动编码

**判断方法：**
- 写的是文本文件吗？→ 是 → 用 `qclaw-text-file` 脚本
- 不确定？→ 默认用这个技能

## 本机安装的工具

| 工具 | 路径/版本 |
|------|---------|
| Python | `python.exe`（`where python` 查）|
| Node.js | `node.exe`（`where node` 查）|
| Git | `git.exe`（`where git` 查）|
| npm | `npm.cmd` |
| sharp | `E:\qclaw\resources\openclaw\node_modules\sharp\` |

## 模型路由

- 当前模型：`qclaw/modelroute`
- 不支持：视觉（看图）
- 如需视觉能力：切换到 GPT-4o / Claude / Gemini

## Git 操作

- 工作目录：`C:\Users\yiseg\.qclaw\workspace`
- `git status`、`git log`、`git diff` 常规操作
- Push 可能需要认证（SSH key 或 token）
- `.gitignore` 注意忽略 `node_modules/`、`__pycache__/`、`*.pyc`

---

_本文件记录踩过的坑和验证过的方法，不记可以从文档查到的东西。_
