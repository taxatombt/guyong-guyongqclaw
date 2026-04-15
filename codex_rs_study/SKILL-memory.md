# codex_rs_study — Phase2 记忆整合深度指南

> 来源：OpenAI/codex-rs，core/templates/memories/consolidation_prompt.md（47KB）
> 用途：理解 Codex 的记忆整合方法，用于升级 qclaw evolver

---

## Phase2 consolidation 的核心角色

**谁来整合？**
→ 一个专用的整合子agent（consolidation sub-agent）
→ 不是主agent，不是root session，是独立的一次性agent

**整合什么？**
→ Phase1 输出（多个 rollout 的 structured_memory）
→ 输出：memory_summary.md / MEMORY.md / skills/ 三个文件

---

## 整合触发条件

```rust
// 从 codex-rs 推断的触发条件
fn should_consolidate(state: &StateDB) -> bool {
    !state.has_active_consolidation()
    && state.pending_memories().len() >= MIN_PENDING
    && state.last_consolidation() > MIN_INTERVAL
}
```

---

## Memory_summary.md（系统prompt永远加载）

**格式要求：**
- 永远在系统prompt中加载
- 高信息密度，不是原始记录
- 导航到具体文件，不要堆砌细节

```
# Memory Summary

## 核心信息（高信息密度）
## 记忆索引（skill/SKILL.md → 具体流程）
## 快速参考（入口命令、关键配置）
```

---

## MEMORY.md（手册条目）

```markdown
## 用户偏好（稳定偏好，重复dislike）
## 决策触发点（context where user chose X）
## 失败护盾（symptom → cause → fix + verification）
## Repo Orientation（入口/配置/命令）
## 工具捷径（quirks, reliable shortcuts）
## 验证计划（reproduction plans for known issues）
```

**遗忘机制：**
- Phase2 计算 selection diff：added / retained / removed
- removed 的 thread_id → 只删除该thread支撑的内容
- 不删除整个 block，保留 shared/still-supported 内容

---

## Skills（可复用流程）

```
skills/
├── skill-name/
│   ├── SKILL.md  ← 入口，描述何时使用
│   └── [支持文件]
```

**触发条件（在SKILL.md中）：**
- When to use（描述触发场景）
- What it does（做什么）
- Examples（用法示例）

---

## 质量规则（最重要）

**有价值的记忆：**
1. 稳定用户偏好 > 程序性知识
2. 减少未来用户steering > 减少agent搜索努力
3. 决策触发点（context where user chose X）
4. 失败护盾：symptom → cause → fix + verification
5. Repo orientation：入口/配置/命令
6. 工具quirks和可靠shortcuts
7. 验证性reproduction plans

**无价值：**
1. 泛泛建议（be careful）
2. 存secrets/credentials
3. 复制大段原始输出
4. 探索性讨论变永久记忆
5. 无意义更新（no-op allowed）

---

## Consolidation Prompt 核心指令

> Goal: 帮助未来agent：
> - 深刻理解用户（不需要重复指令）
> - 更少tool calls解决相似任务
> - 重用proven workflows和verification checklists
> - 避免已知landmines和failure modes

---

## 与Evolver对比

| 维度 | Codex Phase2 | Evolver |
|------|-------------|---------|
| 触发 | 启动时 + 积累阈值 | 每次任务后record |
| 整合 | 独立sub-agent | 无专门整合 |
| 输出 | 3文件（summary/MEMORY/skills） | 1文件（evolver_db.json） |
| 遗忘 | selection diff机制 | 无自动遗忘 |
| 格式 | markdown | JSON |

---

## 可移植设计

1. 两阶段分离：evolver.record() → 后台积累 → Phase2整合agent
2. 遗忘机制：按 thread_id 粒度清理 MEMORY.md
3. 3文件输出：summary（导航）+ MEMORY（详情）+ skills（流程）
4. 质量规则：明确什么值得记、什么不值得记

---

## 落地文件

- codex-rs_core_templates_memories_consolidation.md（47KB，原始prompt）
- SKILL.md（主架构文档）
- SKILL-memory.md OK（本文件，Phase2深度）
