# -*- coding: utf-8 -*-
"""
agents/agent_types.py — 多角色 Agent 定义

Claude Code 7原则落地：
- 原则2：把角色拆开 — Verification/Explore/Plan 三角色
- 原则1：不信任自觉性 — 每个角色有明确边界和制度

角色设计：
- AgentRole: 枚举所有角色
- AgentProfile: 每个角色的 system prompt + 工具集
- verify(task, changes): 对抗性验证
- explore(query): 只读代码探索
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable
import json

# ─── 角色枚举 ──────────────────────────────────────────────

class AgentRole(Enum):
    GENERAL = "general"       # 通用执行（主 Agent）
    VERIFY = "verify"          # 对抗性验证
    EXPLORE = "explore"        # 只读探索
    PLAN = "plan"              # 纯规划

# ─── 工具权限映射 ──────────────────────────────────────────

READ_ONLY_TOOLS = {
    "exec",          # 只读命令
    "read",          # 文件读取
    "glob",          # glob搜索
    "grep",          # 内容搜索
    "sessions_list", # 会话列表
    "sessions_history", # 会话历史
    "memory_search", # 记忆搜索
    "lcm_grep",      # LCM搜索
    "lcm_expand",    # LCM展开
    "lcm_describe",  # LCM描述
    "web_search",    # 网页搜索
    "web_fetch",     # 网页抓取
    "session_status",# 状态查询
}

READ_WRITE_TOOLS = {
    "exec", "read", "write", "edit",
    "glob", "grep", "sessions_list", "sessions_history",
    "memory_search", "memory_get",
    "lcm_grep", "lcm_expand", "lcm_describe",
    "web_search", "web_fetch",
    "message", "tts",
}

ALL_TOOLS = READ_WRITE_TOOLS | {
    "exec_batch", "subagents", "sessions_send",
    "process", "canvas",
}


@dataclass
class AgentProfile:
    """Agent 角色配置"""
    role: AgentRole
    name: str
    system_prompt: str
    allowed_tools: set[str]
    denied_tools: set[str] = field(default_factory=set)
    model_hint: Optional[str] = None
    max_turns: int = 20
    readonly: bool = False  # 纯读角色

    def can_use(self, tool: str) -> bool:
        if tool in self.denied_tools:
            return False
        if tool in self.allowed_tools:
            return True
        # Default: deny unknown tools
        return False


# ─── Agent Profiles ────────────────────────────────────────

VERIFICATION_PROMPT = """你是一个对抗性验证者（Verification Agent）。

你的职责：**想办法搞坏它**。不是找优点，是找漏洞。

## 两种常见验证失败模式（你必须避免）

1. **Verification avoidance**：只看代码，不实际运行检查，写个 PASS 就走人
2. **被前80%迷惑**：UI看着不错，测试也过了，就忽略剩下20%的问题

## 你必须做的事情

根据变更类型，选择对应策略：

**前端改动**：启动 dev server，用浏览器自动化点击验证实际效果
**后端改动**：curl 实际请求，验证返回值和数据结构
**CLI改动**：看 stdout / stderr / exit code
**数据库迁移**：测 up 和 down，测已有数据
**文件修改**：对比修改前后的 diff，运行受影响的部分

## 识别你自己的合理化倾向

当你这么想的时候，**实际意思是相反的**：

| 当你想说 | 实际意味着 | 正确做法 |
|---------|-----------|--------|
| "代码看起来是对的" | 没验证 | 跑一下 |
| "实现者测试通过了" | 实现者也是LLM | 独立验证 |
| "大概没问题" | 没验证 | 跑一下 |
| "这太费时间了" | 没权力决定 | 记录并报告 |

## 输出格式

每个检查项必须包含：
1. 实际执行的命令
2. 观察到的输出
3. 判断结果

最终给出结论：
```
VERDICT: PASS  — 所有检查通过
VERDICT: FAIL  — 发现明确问题
VERDICT: PARTIAL — 部分通过，有改进空间
```

## 你的边界

- **不能**修改任何文件
- **不能**创建新文件
- **不能**运行破坏性命令
- 只读工具集：{read_only_tools}

如果检查过程中需要用到写操作，立即停止并报告。
"""


EXPLORE_PROMPT = """你是一个只读代码探索者（Explore Agent）。

你的职责：**在不动任何东西的情况下，理解代码在做什么**。

## 铁律（违反即报错）

- **禁止**创建新文件（任何形式）
- **禁止**修改已有文件
- **禁止**删除文件
- **禁止**用重定向写文件
- **禁止**运行任何改变系统状态的命令
- **禁止**提交 git
- **禁止**安装包

## 你能用的工具

纯读操作：
- `exec`: ls, git status, git log, find, wc 等读命令
- `read`: 读文件内容
- `glob`: 搜索文件路径
- `grep`: 搜索内容
- `sessions_list/history`: 查看会话
- `memory_search`: 搜索记忆

## 性能优化

- 外部用户默认用轻量模型（速度优先）
- 内部用户可用主模型
- 探索阶段不需要最强推理能力，速度更重要

## 输出格式

```
探索报告：
- 代码结构：...
- 关键逻辑：...
- 依赖关系：...
- 潜在问题：...
- 建议：...
```
"""


PLAN_PROMPT = """你是一个纯规划Agent（Plan Agent）。

你的职责：**分析任务，制定执行计划，不执行任何操作**。

## 你的能力

- 读取文件和代码（了解现状）
- 分析和推理（制定计划）
- 输出结构化计划（让其他Agent执行）

## 输出格式

```
# 执行计划

## 目标
[任务描述]

## 分析
[对现状的分析]

## 步骤
1. [步骤1]
2. [步骤2]
...

## 风险点
- [风险1]
- [风险2]

## 验证方法
[如何验证计划执行成功]
```

## 你的边界

- **不执行**任何写操作
- **不运行**需要确认的命令
- 只输出计划，不输出代码（除非是计划中的示例）
"""


GENERAL_PROMPT = """你是一个通用任务执行Agent（General Purpose Agent）。

你是主Agent，负责实际执行任务。

## 你需要遵守的行为规范

来自 Claude Code 的 getSimpleDoingTasksSection():
- 不要加用户没要求的功能
- 不要过度抽象，三行重复代码好过一个不成熟的抽象
- 不要给你没改的代码加注释和文档字符串
- 不要做不必要的错误处理和兜底逻辑
- 不要设计面向未来的抽象
- **先读代码再改代码**
- 不要轻易建新文件
- 不要给时间估计
- 方法失败了先诊断，不要盲目重试，也不要一次失败就放弃
- 结果要如实汇报，没跑过的不要说跑过了

## 你的工具集

可使用全部已授权工具。

## 任务执行流程

1. 理解任务
2. 探索现状（读代码/查文档）
3. 制定方案
4. 执行
5. **自我验证**（不只是说"完成了"，要实际验证）
6. 如实报告结果
"""


# ─── Profile 工厂 ─────────────────────────────────────────

def get_profile(role: AgentRole, workspace: str = None) -> AgentProfile:
    """根据角色获取对应的 Agent 配置"""
    profiles = {
        AgentRole.VERIFY: AgentProfile(
            role=AgentRole.VERIFY,
            name="Verification Agent",
            system_prompt=VERIFICATION_PROMPT,
            allowed_tools=READ_ONLY_TOOLS,
            denied_tools=READ_WRITE_TOOLS - READ_ONLY_TOOLS,
            readonly=True,
            max_turns=15,
        ),
        AgentRole.EXPLORE: AgentProfile(
            role=AgentRole.EXPLORE,
            name="Explore Agent",
            system_prompt=EXPLORE_PROMPT,
            allowed_tools=READ_ONLY_TOOLS,
            denied_tools=READ_WRITE_TOOLS - READ_ONLY_TOOLS,
            readonly=True,
            max_turns=10,
        ),
        AgentRole.PLAN: AgentProfile(
            role=AgentRole.PLAN,
            name="Plan Agent",
            system_prompt=PLAN_PROMPT,
            allowed_tools=READ_ONLY_TOOLS,
            denied_tools=READ_WRITE_TOOLS - READ_ONLY_TOOLS,
            readonly=True,
            max_turns=8,
        ),
        AgentRole.GENERAL: AgentProfile(
            role=AgentRole.GENERAL,
            name="General Agent",
            system_prompt=GENERAL_PROMPT,
            allowed_tools=ALL_TOOLS,
            readonly=False,
            max_turns=30,
        ),
    }
    return profiles.get(role, profiles[AgentRole.GENERAL])


# ─── 便捷调用函数 ─────────────────────────────────────────

def verify(task: str, changes: str = "", context: str = "") -> str:
    """
    启动验证Agent，对变更进行对抗性验证。
    
    返回验证报告，包含 VERDICT: PASS / FAIL / PARTIAL
    """
    profile = get_profile(AgentRole.VERIFY)
    prompt = f"""## 验证任务

{context}

## 变更内容

{changes or '(无详细变更描述)'}

## 请执行对抗性验证

{task}
"""
    # 这里需要调用实际的 Agent 运行时
    # 暂时返回结构化 prompt，实际执行由 multi_agent_dispatcher.py 负责
    return prompt


def explore(query: str, workspace: str = "") -> str:
    """
    启动只读探索Agent，理解代码结构。
    
    返回探索报告。
    """
    profile = get_profile(AgentRole.EXPLORE)
    prompt = f"""## 探索任务

{query}

工作区：{workspace or '默认工作区'}
"""
    return prompt


def plan(task: str) -> str:
    """
    启动纯规划Agent，制定执行计划。
    """
    profile = get_profile(AgentRole.PLAN)
    prompt = f"""## 规划任务

{task}
"""
    return prompt


# ─── 主入口：打印所有 Agent 配置 ───────────────────────────

def get_system_prompt(role: AgentRole) -> str:
    """获取角色的 system prompt"""
    return get_profile(role).system_prompt


def get_task_prompt(
    role: AgentRole,
    context: str,
    task_specific: str = "",
) -> str:
    """
    构建角色的任务 prompt。
    
    各角色的 task prompt 格式：
    - VERIFY: context + task_specific（对抗性验证指令）
    - EXPLORE: context + 代码分析任务
    - PLAN: context + 规划指令
    - GENERAL: context + 任务描述
    """
    SEP = "\n" + "="*40 + "\n"
    
    if role == AgentRole.VERIFY:
        return (
            f"{SEP}【验证任务】\n"
            f"{SEP}任务背景：\n{context}\n"
            f"{SEP}具体要求：\n{task_specific or '执行对抗性验证'}"
        )
    elif role == AgentRole.EXPLORE:
        return (
            f"{SEP}【探索任务】\n"
            f"理解以下代码/需求：\n{context}\n"
            f"{SEP}分析要求：\n{task_specific or '提供代码结构摘要和关键逻辑分析'}"
        )
    elif role == AgentRole.PLAN:
        return (
            f"{SEP}【规划任务】\n"
            f"分析以下任务并制定执行计划：\n{context}\n"
            f"{SEP}计划要求：\n{task_specific or '输出结构化步骤 + 风险点'}"
        )
    elif role == AgentRole.GENERAL:
        return (
            f"{SEP}【执行任务】\n"
            f"{context}\n"
            f"{SEP}执行指令：\n{task_specific or '执行并验证结果'}"
        )
    return context


def main():
    for role in AgentRole:
        p = get_profile(role)
        print(f"\n{'='*60}")
        print(f"Agent: {p.name} ({p.role.value})")
        print(f"Readonly: {p.readonly}")
        print(f"Max turns: {p.max_turns}")
        print(f"Allowed tools: {', '.join(sorted(p.allowed_tools))}")
        print(f"Denied tools: {', '.join(sorted(p.denied_tools))}")


if __name__ == "__main__":
    main()
