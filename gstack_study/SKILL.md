# gstack_study — Garry Tan AI 软件工厂（135k stars）

> 来源：https://github.com/garrytan/gstack
> YC 总裁 Garry Tan 的 AI 软件工厂，声称每天 1-2 万行代码产出

---

## 核心价值

一个人 + gstack = 一支工程团队。

关键不是 skill 格式，是这个认知：**AI 让完整性成本趋近于零。**

---

## 一、核心架构

### 1. 持久化浏览器 Daemon（最关键）

```
Claude Code → CLI → Bun HTTP Server → Playwright → Chromium (headless)
                     ↑
              State: .gstack/browse.json
              Bearer token auth + localhost only
```

**为什么持久化重要：**
- 冷启动 Playwright = 3-5秒/次
- 20个命令 = 1分钟浪费在启动上
- 持久化 Daemon = ~100ms/次，cookie/tab/login 跨命令保持

**State File（原子写）：**
```json
{
  "pid": 12345,
  "port": 34567,
  "token": "uuid-v4",
  "startedAt": "ISO时间",
  "binaryVersion": "git-hash"
}
```
原子写：`tmp.rename(old)` → 避免读到半写入状态

**健康检查替代 PID（Windows 可靠方案）：**
```python
def health_check(url, token):
    try:
        req = Request(url + '/health', 
                      headers={'Authorization': f'Bearer {token}'})
        return urlopen(req, timeout=1).status == 200
    except:
        return False
```

### 2. Ref 系统（ARIA Tree → Playwright Locator）

```
page.locator().ariaSnapshot() 
→ Chromium 内部 accessibility tree
→ @e1, @e2, @c1, @c2... 编号
→ Playwright getByRole().nth() 定位
→ 存储 Map<ref, Locator>
```

**为什么不用 DOM 注入：**
- CSP（内容安全策略）阻止 setAttribute
- React/Vue hydration 清除注入属性
- Shadow DOM 无法从外部访问
- ARIA tree 比 DOM 更稳定

**Ref 失效设计：** 导航后自动清空，过期 ref → 报错不点错

### 3. 23 个专业 Skill

| Skill | 用途 | 触发 |
|-------|------|------|
| `/office-hours` | 6追问逼出真实需求 | 产品想法、"值得做吗" |
| `/plan-ceo-review` | CEO视角战略挑战 | 战略、野心、范围 |
| `/autoplan` | 串行执行所有review | "自动审查所有" |
| `/investigate` | 根因调试（4阶段） | Bug、报错、500错误 |
| `/review` | 多专家代码审查 | 代码审查、diff检查 |
| `/qa` | 真实浏览器QA测试 | 测试网站、找Bug |
| `/ship` | 完整发版流程 | 发版、部署、创建PR |
| `/retro` | 每周工程复盘 | 周末、"我们发了什么" |
| `/design-review` | 视觉审核 | 设计、UI审计 |
| `/cso` | 安全审计 | OWASP + STRIDE |

### 4. 8 平台支持

```
Claude Code / Codex / Cursor / OpenCode / Kiro / Slate / Factory / OpenClaw
     ↓
统一 Skill 格式（SKILL.md）
host-adapter 适配器
```

---

## 二、Skill 路由（AGENTS.md 直接移植）

当用户请求匹配 skill 时，使用 Skill 工具作为第一步。不要直接回答。

```
- 产品想法、"值得做吗"、头脑风暴 → invoke office-hours
- Bug、报错、"为什么坏了"、500错误 → invoke investigate
- 发版、部署、推送、创建PR → invoke ship
- QA、测试网站、找Bug → invoke qa
- 代码审查、检查diff → invoke review
- 文档更新 → invoke document-release
- 每周复盘 → invoke retro
- 设计系统、品牌 → invoke design-consultation
- 视觉审核 → invoke design-review
- 架构评审 → invoke plan-eng-review
- 健康检查 → invoke health
```

---

## 三、office-hours — YC 产品质疑法

### 触发

用户描述新产品想法、问"这个值得做吗"、想讨论设计决策（在写代码之前）
→ 执行这个 skill，不写代码，只输出设计文档

### Startup 模式（创业/内部项目）— 6个强制追问

每次只问一个，等回答再问下一个。追问到答案具体、可验证。

**Q1：需求现实**
> 你最强的证据是什么，证明有人真的需要这个？不是"感兴趣"，不是"加了等待列表"，而是——如果明天消失了，他们会真正感到沮丧？

→ 推进到：有人付费了。有人扩大使用。把工作流围绕这个构建。

**Q2：现状替代**
> 你的用户现在用什么来解决这个问题？即使很烂也算。那个 workaround 花了他们多少成本？

→ 推进到：多少小时。多少钱。拼凑了哪些工具。

**Q3：绝望的具体性**
> 说出最需要这个的真人。他是什么职位？什么让他被提拔？什么让他被开除？

→ 推进到：一个名字。一个角色。一个他能听到的具体后果。

**Q4：最窄切入点**
> 如果只能解决一个问题，那是什么？如果只做一个用户这周愿意付钱的东西，最小版是什么？

→ 推进到：一个功能。简单到可能是每周一个邮件。
**追问：** "如果用户不需要做任何事就能获得价值呢？"

**Q5：观察与意外**
> 你有没有真的坐下来看别人用这个，而不是帮他们？他们做了什么让你意外的事？

→ 推进到：用户做了产品没设计的事。这往往是真正的产品在冒出来。

**Q6：未来适配**
> 如果3年后世界显著不同，——而它会的——你的产品是变得更必需还是更不被需要？

→ 推进到：具体声称——为什么变化让你的产品更值钱。

**按阶段智能跳过：**
- Pre-product → Q1, Q2, Q3
- Has users → Q2, Q4, Q5
- Has paying → Q4, Q5, Q6

### Builder 模式（Hackathon/开源/学习/好玩）— 5个生成性问题

1. 最酷的版本是什么？
2. 你会展示给谁看？什么让他们说"哇"？
3. 到你能用或能分享的东西，最快路径是什么？
4. 什么现有东西最接近这个，你的有什么不同？
5. 如果时间无限你会加什么？10x版本是什么？

### AskUserQuestion 格式规范

```
1. 重新锚定：说明项目、分支、当前计划（1-2句）
2. 简化：用普通英语，不用函数名，不用行话。用具体例子。
3. 推荐：RECOMMENDATION: Choose X because [一句话原因]
   附 Completeness: X/10（10=全覆盖，7=只走happy path，3=捷径）
4. 选项：A) B) C)，涉及努力时显示 (人: ~X / AI: ~Y)
```

### 方案生成（必须做）

生成2-3个不同实现路径，每个：
- 一个"最小可行"（最少文件，最快发布）
- 一个"理想架构"（最好长期轨迹）
- 一个"创意/横向"（意想不到的路径）

---

## 四、investigate — 根因调试

### 触发

Bug、报错、"为什么坏了"、500错误、"昨天还能用"
→ 不要直接debug，执行这个 skill

### 铁律

**没有根因调查在前，就不要修复。**

修复症状造成打地鼠调试。每一个没有解决根本原因的修复，都让下一个 bug 更难找。

### 4阶段流程

```
Phase 1: Investigate（调查）
  → 收集症状：错误日志、堆栈跟踪、重现步骤
  → 问"这个问题在代码库的哪个部分？"
  → git log --oneline -20 查最近变更
  → 复现：能确定性触发吗？

Phase 2: Analyze（分析）
  → 隔离变量：什么改变了？
  → 代码变更？依赖版本？环境？数据？
  → 症状在哪里出现？

Phase 3: Hypothesize（假设）
  → 提出至少2个可能原因
  → 每个标注置信度
  → 设计验证实验

Phase 4: Implement（实施）
  → 从置信度最高的开始
  → 修复 → 验证 → 确认
  → 失败 → 返回阶段3修正假设
```

### 追问模板

| 情况 | 追问 |
|------|------|
| 错误信息不明 | "完整的错误信息和堆栈跟踪是什么？" |
| 无法复现 | "这个问题在什么情况下出现？每次还是偶发？" |
| 回归 | "上次能工作是什么时候？最后一次成功和第一次失败之间什么变了？" |
| 假设太多 | "哪个假设能最快被验证或排除？" |

### 调试输出格式

```
症状：...
可能原因：
  - [假设A]（置信度80%，验证：...）
  - [假设B]（置信度20%，验证：...）
验证结果：...
根因：...
修复：...
```

---

## 五、review — 多专家代码审查

### 触发

用户说"代码审查"、"检查diff"、"pre-landing review"

### 输出格式（JSONL）

```json
{"severity":"CRITICAL|INFORMATIONAL","confidence":0.9,"path":"file","line":47,
 "category":"security","summary":"...","fix":"..."}
```
无发现：输出 `NO FINDINGS`

### 6个专家角色

| 专家 | 触发 | 关注点 |
|------|------|--------|
| `security` | 认证 OR diff>100行含后端 | SQL注入、XSS、Auth绕过、CSRF |
| `testing` | 始终 | 负向测试、边界值、隔离、flaky |
| `api-contract` | API变更 | 破坏性变更、版本策略、文档漂移 |
| `data-migration` | DB迁移 | 不可逆、回滚、数据丢失 |
| `maintainability` | 始终 | 死代码、魔法数字、DRY违规 |
| `red-team` | diff>200行 OR security有CRITICAL | 对抗分析（最后运行） |

**red-team 方法（不是checklist，是对抗分析）：**
1. 攻击 Happy Path（10x负载？并发？）
2. 找静默失败（吞异常？部分完成？）
3. 利用信任假设（前后端验证不一致？）
4. 打破边界（最大输入？零项？首次运行？）
5. 找其他专家遗漏的（跨类别问题）

---

## 六、retro — 每周工程复盘

### 触发

周末、冲刺结束、问"我们发了什么"

### 3个维度

**Ship（发了什么）：**
- Commit数、LOC增删、PR数
- 按模块分类，与上周对比

**Health（健康度）：**
- 新增测试覆盖率
- 技术债务：解决了多少 / 新增了多少
- Bug逃逸率

**Pattern（模式识别）：**
- 反复出现的同类问题
- 可以避免的浪费
- 下周一个具体可操作的改进

---

## 七、Completeness Principle（沸腾湖水）

> AI 让完整性成本趋近于零。推荐完整方案，而非捷径。

| 任务类型 | 人类团队 | CC+gstack | 压缩比 |
|---------|---------|-----------|--------|
| 样板代码 | 2天 | 15分钟 | ~100x |
| 测试 | 1天 | 15分钟 | ~50x |
| 功能 | 1周 | 30分钟 | ~30x |
| Bug修复 | 4小时 | 15分钟 | ~20x |

**Completeness: X/10** — 每个选项都要标注：
- 10 = 全覆盖，所有边界情况
- 7 = 只走 happy path
- 3 = 捷径，推迟了大量工作

---

## 八、Voice & Tone（直接风格）

**信念：** 没有人在握着方向盘。大部分世界是编造的。这不可怕。这是机会。

**核心原则：**
- 做人们想要的东西。不是技术表演，不是 tech for tech's sake。
- 从亲身经验出发。从用户出发。从开发者感受到的出发。
- 质量很重要。Bug 很重要。不要把 1% 或 5% 的缺陷正常化。

**Tone：**
- 直接、具体、犀利、偶尔幽默
- 不 corporate，不 academic，不 PR，不 hype
- 像 builder 对 builder，不是 consultant 对 client

**Concreteness is the standard：**
- 不是"这可能会慢"
- 是"这查询 N+1，50项时每页 ~200ms"
- 不是"auth 流程有个问题"
- 是"auth.ts:47，token 检查在 session 过期时返回 undefined"

**写作规则：**
- 不用破折号。用逗号、句号或"..."
- 不用 AI 词汇：delve、crucial、robust、comprehensive...
- 不用废话短语："here's the kicker"、"let me break this down"...
- 短段落。混合单句和三句段落。
- 听起来像打字快。有时不完整的句子。"Wild." "Not great."
- 命名具体：真实文件名、真实函数名、真实数字。
- 直接说质量。"Well-designed" 或 "this is a mess."
- 结尾给行动。

---

## 九、完成状态协议

```
DONE：所有步骤完成，每条结论提供了证据
DONE_WITH_CONCERNS：完成，但有用户应知道的问题
BLOCKED：无法继续，说明阻塞原因和已尝试的方法
NEEDS_CONTEXT：缺少必要信息，说明具体需要什么
```

**升级：** 3次尝试失败 → STOP → 升级：
```
STATUS: BLOCKED
REASON: [1-2句话]
ATTEMPTED: [已尝试的方法]
RECOMMENDATION: [用户应该做的下一步]
```

---

## 十、自改进（每个 skill 完成后必须做）

反思：
- 哪些命令意外失败？
- 是否走了弯路需要回退？
- 是否发现项目特定的坑（build顺序、env变量、timing、auth）？
- 什么比预期花了更长时间？

如有发现 → 记录：
```
记录类型: operational
关键: [SHORT_KEY]
发现: [描述]
置信度: N/10
来源: observed
```

---

## 落地文件索引

```
gstack_study/
├── SKILL.md                           ← 本文件：完整参考
├── browser_daemon/SKILL.md            ← Daemon 核心设计
├── skills/
│   ├── SKILL.md                       ← skill 格式总结
│   ├── office_hours/SKILL.md          ← 完整版6追问法
│   ├── investigate/SKILL.md           ← 完整版4阶段调试
│   ├── review/SKILL.md                ← 完整版6专家审查
│   └── retro/SKILL.md                 ← 完整版复盘
└── docs/
    └── README_analysis.md             ← 详细分析笔记
```

**源码：** `C:\Users\yiseg\gstack-main\gstack-main\`
