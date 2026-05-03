# Claude Code 记忆系统深度分析

**来源**: E:\ai\学习\10src-claudecode\src\services\extractMemories\
**落地时间**: 2026-05-01

## 核心架构

### extractMemories 服务

**功能**: 从当前会话记录中提取持久记忆，写入 auto-memory 目录

**关键设计**:

1. **Fork Agent模式**
   - 使用 `runForkedAgent` 运行记忆提取子agent
   - 和主对话完全一样的fork，共享父进程的prompt cache
   - 跳过transcript记录，避免和主线程的竞争条件
   - maxTurns=5（5轮限制，防止验证 rabbit-holes）

2. **工具权限控制** (createAutoMemCanUseTool)
   - 只允许 Read/Grep/Glob（无限制）
   - 只允许只读Bash命令（通过 `tool.isReadOnly()` 验证）
   - 只允许在 auto-memory 目录内 Edit/Write
   - 其他全部拒绝

3. **状态管理（闭包内）**
   ```
   - inFlightExtractions: Set<Promise>，追踪进行中的提取
   - lastMemoryMessageUuid: 游标，只处理新增消息
   - inProgress: 互斥标志，防止重叠运行
   - turnsSinceLastExtraction: 节流计数器
   - pendingContext: 待处理的上下文（用于 trailing run）
   ```

4. **互斥机制**
   - 如果主agent已经写了记忆，跳过fork提取
   - 主agent和background agent是互斥的

5. **Trailing Run机制**
   - 如果在运行中有新调用，stash上下文
   - 当前运行结束后，用最新的stash上下文运行trailing extraction
   - trailing run跳过节流检查

6. **两轮高效策略**
   ```
   Turn 1: 并行发出所有 Read 调用
   Turn 2: 并行发出所有 Write/Edit 调用
   不要交叉轮次
   ```

---

## 四类记忆类型

### memoryTypes.ts 核心设计

**四种类型**:

1. **user** - 用户角色、目标、偏好、知识
   - 何时保存: 了解用户的角色、偏好、责任、知识时
   - 示例: 数据科学家、10年Go首次接触React

2. **feedback** - 用户的指导（纠正+确认）
   - 何时保存: 用户纠正 OR 确认非显而易见的方法有效时
   - 结构: 规则本身 + **Why:** + **How to apply:**
   - 注意: 失败和成功两者都要记录

3. **project** - 项目上下文、进行中的工作
   - 何时保存: 了解谁在做什么、为什么、什么时候
   - 注意: 把相对日期转换为绝对日期

4. **reference** - 外部系统指针
   - 何时保存: 了解外部资源及其用途时
   - 示例: Linear项目、Grafana面板

### MEMORY.md 是索引，不是记忆

```
- 每条 <150 字符
- 最多 200 行（超过截断）
- 内容在单独的文件里
```

### 明确什么不该保存

- 代码模式、架构、文件路径（可从当前状态推导）
- Git历史（`git log`/`git blame`是权威）
- 调试方案（修复在代码里）
- CLAUDE.md已有的内容
- 临时状态和进行中的工作

### 访问记忆的时机

- 当记忆似乎相关，或用户引用先前对话工作时
- 用户明确要求检查/回忆/记住时必须访问
- 用户说"忽略"记忆时 → 完全当作MEMORY.md是空的

### 信任记忆的原则

- 记忆可能过时
- 记忆提到的文件/函数/标志名是历史声明，需要验证
- "记忆说X存在" ≠ "X现在存在"
- 如果用户要基于记忆行动，必须先验证

### Frontmatter格式

```markdown
---
name: {{memory name}}
description: {{one-line description — used to decide relevance}}
type: {{user, feedback, project, reference}}
---

{{memory content}}
```

---

## qclaw 可移植点

### 1. 四类记忆类型系统
Claude Code的四类记忆类型是精心设计的，qclaw可以采用：

| Claude Code | qclaw现状 | 建议 |
|------------|----------|------|
| user | 部分在MEMORY.md | 扩展user类型 |
| feedback | evolver记录部分 | 整合feedback类型 |
| project | 无 | 新增project类型 |
| reference | 无 | 新增reference类型 |

### 2. 两步骤记忆保存
Claude Code的"写单独文件 + 更新索引"非常高效：
- 避免记忆内容膨胀导致MEMORY.md超过200行限制
- qclaw的memory/日期.md已经是这个思路

### 3. Fork Agent后台提取
qclaw目前没有后台记忆提取机制：
- 可以用sessions_spawn实现轻量级fork
- 共享父session的context cache

### 4. 严格的工具白名单
extractMemories的工具白名单设计非常值得借鉴：
- Read/Grep/Glob无限制
- Bash只读命令
- Edit/Write限制目录

### 5. Trailing Run机制
避免在主agent工作时打扰，而是在完成后处理pending的请求。

### 6. 记忆漂移检测
TRUSTING_RECAL_SECTION的设计：
- 记忆是历史快照，不是当前状态
- 引用具体文件/函数前必须验证

---

## 关键代码位置

| 文件 | 大小 | 内容 |
|------|------|------|
| `extractMemories.ts` | 21KB | 记忆提取核心服务 |
| `prompts.ts` | 7.6KB | 提取prompt模板 |
| `memoryTypes.ts` | 23KB | 四类记忆类型定义 |
| `memdir.ts` | 21KB | 主入口 |
| `findRelevantMemories.ts` | 5KB | 找相关记忆 |
| `memoryScan.ts` | 3KB | 扫描记忆文件 |

---

## 重要认知

1. **记忆不是日志**: 记忆是提炼的洞察，不是流水账
2. **索引即入口**: MEMORY.md是导航，不是百科全书
3. **工具即边界**: 限制工具就是限制能力范围
4. **时间漂移**: 所有记忆都有时效性，引用前需验证
