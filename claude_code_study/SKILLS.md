# Claude Code Skills 系统研究

_来源: E:\ai\资源\10src-claudecode\src\skills\_

## 核心 Skills 一览

| Skill | 用途 | 价值 |
|-------|------|------|
| `/loop` | 定时循环执行（5m/30m/2h/1d）→ cron | ⭐⭐⭐⭐⭐ qclaw 缺这个 |
| `/remember` | 审查 auto-memory，提出提升/清理建议 | ⭐⭐⭐⭐ 记忆卫生 |
| `/stuck` | 诊断卡住的 Claude Code 进程 | ⭐⭐ 运维 |
| `/skillify` | 从会话历史自动创建 skill | ⭐⭐⭐⭐⭐ 自动化进化 |
| `/simplify` | 三 Agent 并行代码审查（复用+质量+效率） | ⭐⭐⭐⭐ 代码质量 |
| `/batch` | 并行工作编排（5-30个 agent + worktree 隔离） | ⭐⭐⭐⭐⭐ 大规模变更 |
| `/verify` | 验证代码变更效果 | ⭐⭐⭐⭐ |
| `/debug` | 调试 skill | ⭐⭐⭐ |
| `/claudeApi` | Claude API 调用 | ⭐⭐ |

## 关键设计模式

### 1. `/skillify` — 自动创建 Skill

**流程**：
1. 分析会话历史（session_memory + user_messages）
2. 识别可重复流程：步骤、输入/参数、成功标准、用户修正点
3. 面试用户（3轮 AskUserQuestion）：
   - Round 1：确认名称/描述/目标
   - Round 2：步骤列表 + 参数 + inline/forked 选择 + 保存位置
   - Round 3：每步详细拆解（产出、成功标准、是否需确认、并行性）
4. 生成 SKILL.md

**关键洞察**：skill 是**人机协作产物**，不是纯自动生成。面试确保 skill 符合用户意图。

### 2. `/simplify` — 三 Agent 并行审查

同时启动 3 个 Explore Agent：
- **Agent 1 复用审查**：搜索现有工具/函数替代新代码
- **Agent 2 质量审查**：冗余状态、参数蔓延、复制粘贴、泄露抽象、字符串类型、不必要注释
- **Agent 3 效率审查**：不必要工作、错过并发、热路径膨胀、无操作更新、TOCTOU

**模式**：一个 skill 启动多个并行 agent，聚合结果后直接修复。

### 3. `/batch` — 并行工作编排

**三阶段**：
1. **Research & Plan**：进入 Plan Mode → 研究 → 分解为 5-30 个独立单元 → e2e 验证配方
2. **Spawn Workers**：每个单元一个后台 agent + worktree 隔离 → 并行执行
3. **Track Progress**：状态表追踪每个 worker 的 PR

**Worker 指令模板**：
```
1. Simplify — 调用 /simplify 清理代码
2. Run unit tests — 运行测试套件
3. Test e2e — 按配方端到端验证
4. Commit & push — 提交并创建 PR
5. Report — 输出 "PR: <url>"
```

### 4. `/loop` — 循环执行

**解析规则**（优先级）：
1. 前缀 token：`5m /foo` → 间隔 5m，prompt /foo
2. 尾部 "every"：`check deploy every 20m` → 间隔 20m，prompt check deploy
3. 默认 10m

**Cron 转换**：
| 间隔 | Cron |
|------|------|
| Nm (N≤59) | */N * * * * |
| Nm (N≥60) | 0 */H * * * |
| Nh | 0 */N * * * |
| Nd | 0 0 */N * * |

**关键**：立即执行一次，不等首次 cron 触发。

### 5. `/remember` — 记忆审查

**四层记忆结构**：
- **CLAUDE.md**：项目级约定（团队共享）
- **CLAUDE.local.md**：个人指令（不提交 VCS）
- **Team memory**：跨仓库组织知识
- **Auto-memory**：工作笔记/临时上下文

**操作**：
1. 分类每条 auto-memory → 目标层
2. 识别重复/过时/冲突
3. 提出提升/清理/解决建议

## 与 qclaw 的差距和可落地项

| 模式 | Claude Code | qclaw 落地 | 优先级 |
|------|------------|-----------|--------|
| /loop | cron + 立即执行 | qclaw-cron-skill 已有，需加"立即执行" | 🔴 |
| /skillify | 从会话自动创建 | 新建 `skillify_skill.py` | 🔴 |
| /simplify | 三Agent并行审查 | 新建 `simplify_skill.py` | 🟡 |
| /batch | 并行工作编排 | 新建 `batch_skill.py` | 🟡 |
| /remember | 记忆审查提升 | 新建 `remember_skill.py` | 🔴 |
| Verification prompt | 反合理化策略 | 整合到 agent_types.py VERIFY | 🔴 |
| Token budget | 90%+递减检测 | 新建 `token_budget.py` | 🟡 |
