---
name: gitnexus-setup
description: 自动化安装、配置 GitNexus，注入 MCP 配置、挂载 post-commit 钩子、启动守护进程。当用户要求初始化、配置或重置 GitNexus 环境时调用。
---

# GitNexus 环境初始化 Skill

## 技能描述

在当前 Git 仓库中全自动化安装、配置和管理 GitNexus 后台守护进程。具备幂等性和进程防抖能力，确保代码图谱索引与最新代码保持同步。

**重要提示**：所有输出和交互必须使用中文（简体中文）。

## 触发条件

- "初始化 GitNexus"
- "配置 GitNexus"
- "设置 GitNexus"
- "启动 GitNexus"
- "重置 GitNexus 环境"
- "安装 GitNexus"

## 执行步骤

### 步骤 1：检测环境

```bash
# 检测必需工具
if ! command -v git &> /dev/null || ! command -v npm &> /dev/null; then
    echo "❌ 错误: 需要 Git 和 npm 环境。"
    exit 1
fi

# 检测是否为 Git 仓库
if ! git rev-parse --is-inside-work-tree &> /dev/null; then
    echo "❌ 错误: 当前目录不是 Git 仓库。"
    exit 1
fi
```

### 步骤 2：全局安装 gitnexus（如未安装）

```bash
if ! command -v gitnexus &> /dev/null; then
    echo "📦 正在全局自动安装 gitnexus..."
    npm install -g gitnexus
fi
```

### 步骤 3：进程防抖（释放 KùzuDB 数据库锁）

```bash
pkill -f "gitnexus serve" > /dev/null 2>&1 || true
pkill -f "gitnexus analyze" > /dev/null 2>&1 || true
pkill -f "gitnexus wiki" > /dev/null 2>&1 || true
sleep 1
```

### 步骤 4：后台异步执行图谱分析

```bash
mkdir -p .gitnexus
echo "🔍 正在后台异步分析代码库..."
nohup gitnexus analyze > .gitnexus/analyze.log 2>&1 &
echo $! > ".gitnexus/analyze.pid"
```

### 步骤 5：注入 MCP 配置

```bash
echo "⚙️ 正在为当前项目注入 MCP 配置..."
gitnexus setup
```

### 步骤 6：配置 post-commit 自动更新钩子

```bash
mkdir -p .git/hooks

# 如果钩子已存在，先删除
if [ -f ".git/hooks/post-commit" ]; then
    rm -f ".git/hooks/post-commit"
fi

cat << 'HOOK_EOF' > ".git/hooks/post-commit"
#!/bin/sh
echo "🔄 [GitNexus] 检测到新提交，准备后台更新知识图谱..."

nohup sh -c '
    pkill -f "gitnexus serve" > /dev/null 2>&1 || true
    pkill -f "gitnexus analyze" > /dev/null 2>&1 || true
    sleep 1
    npx gitnexus analyze > .gitnexus/analyze.log 2>&1
' > /dev/null 2>&1 &
HOOK_EOF

chmod +x ".git/hooks/post-commit"
```

## 验证结果

执行成功后，向用户展示：
- 查看索引进度命令：`cat .gitnexus/analyze.log`
- 常用命令提示（中文说明）
- `gitnexus serve` 命令的锁库警告

## 常用命令（中文说明）

| 命令 | 说明 |
|------|------|
| `gitnexus list` | 查看所有已索引的仓库列表 |
| `gitnexus status` | 查看当前仓库的索引状态 |
| `gitnexus serve` | 启动本地 HTTP 服务器，连接 Web UI 查看图谱 |
| ⚠️ serve 会锁定数据库，运行期间无法执行 analyze/wiki |

## 质量标准

1. **幂等性**：多次执行结果一致，不产生错误
2. **进程防抖**：启动新进程前终止旧进程
3. **后台执行**：分析任务异步运行，不阻塞用户
4. **钩子持久化**：post-commit 钩子能 survive 仓库操作
5. **错误处理**：对缺失前置条件给出清晰提示
6. **中文输出**：所有提示和说明使用简体中文

## qclaw 适配说明

此 Skill 已从 auto-devnexus 项目（alexzbg）移植到 qclaw workspace。

### 与 qclaw 的集成点

- **MCP 注册**：`gitnexus setup` 自动注册到 qclaw 的 MCP 配置
- **post-commit 钩子**：自动挂载到当前 Git 仓库
- **索引存储**：`.gitnexus/` 目录在工作区内
- **后台进程**：`analyze.pid` 文件跟踪后台进程 PID