---
name: gitnexus-wiki
description: 使用 GitNexus 调用大语言模型生成项目架构 Wiki。当用户要求生成文档、创建项目 Wiki 或编写架构文档时调用。
---

# GitNexus Wiki 生成器 Skill

## 技能描述

使用 GitNexus 异步调用大语言模型为当前代码库生成架构 Wiki。
生成完成后用户可以直接在浏览器中打开 `.gitnexus/wiki/index.html` 查看结果。

**重要提示**：所有输出和交互必须使用中文（简体中文）。

## 触发条件

- "生成 Wiki"
- "创建文档"
- "写项目文档"
- "生成架构文档"
- "用 GitNexus 写文档"
- "Wiki 生成进度"
- "查看 Wiki 状态"

## 执行步骤

### 步骤 1：检查现有 Wiki 生成状态

```bash
# 检查进程
ps aux | grep -E "gitnexus wiki" | grep -v grep && echo "RUNNING" || echo "NOT_RUNNING"

# 检查 Wiki 文件
ls -lh .gitnexus/wiki/index.html 2>/dev/null && echo "WIKI_EXISTS" || echo "NO_WIKI_FILE"
```

**三种情况处理**：

- **进程正在运行**：告诉用户 Wiki 生成正在进行中
- **Wiki 文件已存在且进程未运行**：询问用户要查看还是重新生成
- **无进程且无 Wiki 文件**：继续执行步骤 2

### 步骤 2：中文 Prompts 替换

```bash
# 使用 node 直接修改 gitnexus 源码中的 prompts.js 为中文版
node -e "
const fs = require('fs');
const path = require('path');
const root = execSync('npm root -g').toString().trim();
const pkgPath = path.join(root, 'gitnexus');
const targetPath = path.join(pkgPath, 'dist', 'core', 'wiki', 'prompts.js');
// 使用 prompts-zh.js 替换原文 prompts.js
"
```

### 步骤 3：读取配置（层级优先级）

| 优先级 | 来源 |
|--------|------|
| 1 | 环境变量：`API_KEY`, `BASE_URL`, `MODEL` |
| 2 | `~/.gitnexus/config.json` |
| 3 | `~/.config/opencode/config.json` |
| 4 | `~/.claude/settings.json` |

```bash
# Node.js 层级读取配置
node -e "
const paths = [
    path.join(os.homedir(), '.gitnexus', 'config.json'),
    path.join(os.homedir(), '.opencode.json'),
    path.join(os.homedir(), '.claude.json')
];
// 依次查找 apiKey、baseUrl、model
"
```

### 步骤 4：进程防抖 + 异步启动 Wiki 生成

```bash
# 强制解除 KùzuDB 数据库占用锁
pkill -f "gitnexus serve" > /dev/null 2>&1 || true
pkill -f "gitnexus analyze" > /dev/null 2>&1 || true
pkill -f "gitnexus wiki" > /dev/null 2>&1 || true
sleep 1

# 后台启动 Wiki 生成
nohup gitnexus wiki --base-url $BASE_URL --model $MODEL > .gitnexus/wiki.log 2>&1 &
echo $! > ".gitnexus/wiki.pid"
```

## 配置缺失处理

如果未找到 API Key，**不要报错结束**。提示用户提供：

> "我没有在您的本地配置中找到大模型 API Key。请直接发送您的 API Key 给我。如果您使用自定义代理或特定模型，也可以一并告诉我（如：Key + 代理地址 + 模型名）。"

收到用户配置后，执行：
```bash
API_KEY="用户Key" BASE_URL="用户URL" MODEL="用户模型" \
  "${SKILL_DIR}/scripts/gitnexus-wiki.sh" --workdir "$(pwd)"
```

## 输出信息

执行成功后告知用户：

- **Wiki 位置**：`.gitnexus/wiki/index.html`
- **查看方式**：`file://$(pwd)/.gitnexus/wiki/index.html`
- **检查进度**：`ls -lh .gitnexus/wiki/index.html`
- **常用命令**：
  - `gitnexus list` — 查看已索引仓库
  - `gitnexus status` — 查看索引状态
  - `cat .gitnexus/wiki.log` — 查看 Wiki 生成日志

## 质量标准

1. **配置发现**：成功从所有配置源读取
2. **全局持久化**：新配置正确保存到 `~/.gitnexus/config.json`
3. **进程防抖**：旧进程终止后才启动新进程
4. **状态检测**：正确识别现有 Wiki 生成状态
5. **异步执行**：生成任务在后台运行，不阻塞用户
6. **优雅降级**：配置缺失时给出清晰提示
7. **中文输出**：所有提示和说明使用简体中文

## 中文 Prompts 设计（prompts-zh.js）

GitNexus 默认 prompts 为英文，已被替换为中文版。核心设计：

- **Grouping**：分组为 5-15 个逻辑模块（按功能而非文件类型）
- **Module Doc**：引用实际函数名/类名，使用 Mermaid 图（≤10 节点）
- **Parent Module Doc**：综合子模块，不要重复源码
- **Overview**：高级架构图，新开发者 10 秒内掌握

## qclaw 适配说明

此 Skill 已从 auto-devnexus 项目移植到 qclaw workspace。

### 依赖

- `gitnexus` npm 包（全局安装）
- `.gitnexus/` 索引目录（需先运行 `gitnexus analyze`）

### 与 qclaw 的集成

- 配置文件：`~/.gitnexus/config.json`
- 输出目录：`.gitnexus/wiki/index.html`
- 日志文件：`.gitnexus/wiki.log`
- 进程 PID：`.gitnexus/wiki.pid`