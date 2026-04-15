# gstack_skills — 核心技能本地化

> 从 Garry Tan gstack (135k stars) 提炼，落地为 OpenClaw Skill 格式

---

## 核心原则：Boil the Lake（沸腾湖水）

> AI 让完整性成本趋近于零。推荐完整方案，而非捷径。
> 一个湖（100%覆盖）是可沸腾的；一个海洋（全量重写）不是。

**努力对照表：**

| 任务类型 | 人类团队 | CC+gstack | 压缩比 |
|---------|---------|-----------|--------|
| 样板代码 | 2天 | 15分钟 | ~100x |
| 测试 | 1天 | 15分钟 | ~50x |
| 功能 | 1周 | 30分钟 | ~30x |
| Bug修复 | 4小时 | 15分钟 | ~20x |

---

## 1. Office Hours（产品质疑）

**触发**：用户描述新产品想法、问"这个值得做吗"、想讨论设计决策

### 6个强制追问（Startup Mode）

1. **需求现实** — 谁有这个痛苦？给我一个具体的例子，不只是"用户"。
2. **现状替代** — 他们现在用什么？手动步骤是什么？
3. **绝望的具体性** — 他们愿意为什么付钱？而不是"愿意付费"这种模糊的。
4. **最窄切入点** — 如果只能解决一个问题，那是什么？
5. **观察** — 你观察到这个痛点多少次？通过什么方式观察到的？
6. **未来适配** — 如果你成功了，这个解决方案还能解决什么问题？

### AskUserQuestion 格式规范

```
1. **重新锚定**：说明项目、当前分支、当前计划/任务（1-2句）
2. **简化**：用普通英语解释，不用函数名，不用行话。用具体例子。
3. **推荐**：`RECOMMENDATION: Choose X because [一句话原因]`
   - 每次都附 `Completeness: X/10`（10=全覆盖，7=只走 happy path，3=捷径）
4. **选项**：字母选项 A) B) C)，涉及努力时显示双刻度 `(人: ~X / AI: ~Y)`
```

---

## 2. Investigate（根因调试）

**触发**：报错、500错误、"为什么坏了"、"昨天还能用"

**铁律**：没有根因就不要修复。

### 4阶段流程

```
Phase 1: Investigate（调查）
  → 收集证据：错误日志、堆栈跟踪、重现步骤
  → 问"这个问题在代码库的哪个部分？"
  → 问"这个问题是什么时候引入的？"

Phase 2: Analyze（分析）
  → 隔离变量：什么改变了？
  → 搜索 git blame：最近改了什么？
  → 检查依赖版本变化

Phase 3: Hypothesize（假设）
  → 提出可能的原因（至少2个）
  → 每个假设标注置信度
  → 设计验证实验

Phase 4: Implement（实施）
  → 从置信度最高的假设开始
  → 修复 → 验证 → 确认修复
  → 如果失败 → 返回 Phase 3 修正假设
```

### 调试输出格式

```
STATUS: BLOCKED | NEEDS_CONTEXT
REASON: [1-2句话说明问题]
ATTEMPTED: [已尝试的方法]
RECOMMENDATION: [用户应该做的下一步]
```

---

## 3. Review（多专家代码审查）

### 6个专家角色

| 专家 | 触发条件 | 关注点 |
|------|---------|--------|
| `security` | 认证代码 或 diff>100行含后端 | SQL注入、Auth绕过、XSS、CSRF |
| `testing` | 始终开启 | 负向测试、边界值、测试隔离、flaky模式 |
| `api-contract` | SCOPE_API=true | 破坏性变更、版本策略、文档漂移 |
| `data-migration` | 有DB变更 | 数据迁移安全、回滚计划 |
| `maintainability` | 始终开启 | 复杂度、重复代码、技术债务 |
| `red-team` | 始终开启 | LLM trust violation、prompt注入、对抗输入 |

### Review 输出格式（JSONL）

```json
{"severity":"CRITICAL|INFORMATIONAL","confidence":0.9,"path":"file","line":47,
 "category":"security","summary":"...","fix":"..."}
```

---

## 4. Retro（每周复盘）

**触发**：周末/冲刺结束时、问"我们发了什么"

### 3个维度

```
Ship（发了什么）
  → 统计：commit数、LOC增/删、PR数
  → 按文件/模块分类
  → 与上周对比

Health（健康度）
  → 新增测试覆盖率
  → 技术债务：解决了多少，新增了多少
  → Bug逃逸率

Pattern（模式识别）
  → 反复出现的同一类问题
  → 识别"花了很长时间但本可以避免"的情况
  → 提出改进建议
```

---

## 5. 通用 Skill 格式（OpenClaw）

```markdown
---
name: skill-name
description: |
  一句话描述触发条件。
  Use when asked to "..." or "...".
  Proactively suggest when ... (gstack)
allowed-tools:
  - Read
  - Bash
  - AskUserQuestion
---

## 触发检测
当用户说[...] → 执行这个skill

## 执行流程
1. ...
2. ...
3. ...

## 完成协议
- DONE：全部完成，提供每条结论的证据
- DONE_WITH_CONCERNS：完成但有用户应知道的问题
- BLOCKED：无法继续，说明阻塞原因和已尝试的方法
- NEEDS_CONTEXT：缺少必要信息，说明具体需要什么

## 自改进
完成前反思：
- 哪些命令意外失败？
- 是否走了弯路需要回退？
- 是否发现项目特定的坑？
如发现 → 记录操作学习：
~/.claude/skills/gstack/bin/gstack-learnings-log ...
```

---

## 6. PreToolUse Hook（安全护栏）

```yaml
hooks:
  PreToolUse:
    - matcher: "Edit"
      hooks:
        - type: command
          command: "bash ${SKILL_DIR}/../freeze/bin/check-freeze.sh"
          statusMessage: "检查冻结边界..."
    - matcher: "Write"
      hooks:
        - type: command
          command: "bash ${SKILL_DIR}/../freeze/bin/check-freeze.sh"
          statusMessage: "检查冻结边界..."
```

---

## Skill 路由（CLAUDE.md / AGENTS.md）

```markdown
## Skill routing

当用户请求匹配某个skill时，始终使用 Skill 工具作为第一步。
不要直接回答，不要先用其他工具。

- 产品想法、"值得做吗"、头脑风暴 → invoke office-hours
- Bug、报错、"为什么坏了" → invoke investigate
- 发版、部署、推送 → invoke ship
- QA、测试网站 → invoke qa
- 代码审查、检查diff → invoke review
- 文档更新 → invoke document-release
- 每周复盘 → invoke retro
- 设计系统、品牌 → invoke design-consultation
- 视觉审核 → invoke design-review
- 架构评审 → invoke plan-eng-review
- 健康检查 → invoke health
```
