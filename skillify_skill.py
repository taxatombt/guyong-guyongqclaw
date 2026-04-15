# -*- coding: utf-8 -*-
"""
skillify_skill.py — 从会话自动创建 Skill

来源: Claude Code /skillify 命令
用途: 分析会话历史，识别可重复流程，3轮面试生成 SKILL.md

不修改任何现有系统代码，纯新建模块。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class SkillCandidate:
    """候选 Skill"""
    name: str = ""
    description: str = ""
    trigger: str = ""           # 触发条件
    steps: List[str] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    success_criteria: str = ""
    user_corrections: List[str] = field(default_factory=list)
    is_inline: bool = True      # inline vs forked
    save_path: str = ""


@dataclass
class InterviewRound:
    """面试轮次"""
    round_num: int
    question: str
    user_answer: str = ""


def analyze_conversation(messages: List[dict]) -> List[SkillCandidate]:
    """
    分析会话历史，识别可重复流程
    
    参考Claude Code /skillify：分析 session_memory + user_messages
    """
    candidates = []
    
    # 提取用户指令和助手响应的模式
    user_cmds = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user" and content.strip():
            user_cmds.append(content)
    
    # 识别可重复模式
    patterns = _detect_patterns(user_cmds)
    for pattern in patterns:
        candidate = SkillCandidate(
            name=pattern["name"],
            description=pattern["description"],
            trigger=pattern["trigger"],
            steps=pattern["steps"],
            parameters=pattern.get("parameters", []),
        )
        candidates.append(candidate)
    
    return candidates


def _detect_patterns(user_cmds: List[str]) -> List[dict]:
    """检测可重复指令模式"""
    patterns = []
    
    # 检测重复出现的指令类型
    cmd_categories = {}
    for cmd in user_cmds:
        category = _categorize_command(cmd)
        if category:
            if category not in cmd_categories:
                cmd_categories[category] = []
            cmd_categories[category].append(cmd)
    
    # 重复出现≥2次的类别视为候选
    for category, cmds in cmd_categories.items():
        if len(cmds) >= 2:
            patterns.append({
                "name": category.lower().replace(" ", "-"),
                "description": f"Auto-detected {category} workflow",
                "trigger": f"User requests {category.lower()}",
                "steps": [f"Step: {cmd[:80]}" for cmd in cmds[:5]],
                "parameters": [],
            })
    
    return patterns


def _categorize_command(cmd: str) -> Optional[str]:
    """分类指令"""
    cmd_lower = cmd.lower()
    
    categories = [
        (r"(deploy|发布|上线)", "Deployment"),
        (r"(test|测试|验证)", "Testing"),
        (r"(debug|调试|排查)", "Debugging"),
        (r"(review|审查|检查)", "Code Review"),
        (r"(document|文档|说明)", "Documentation"),
        (r"(refactor|重构|优化)", "Refactoring"),
        (r"(install|安装|配置)", "Installation"),
        (r"(search|搜索|查找)", "Research"),
        (r"(create|创建|新建)", "Creation"),
        (r"(fix|修复|解决)", "Bug Fix"),
    ]
    
    for pattern, name in categories:
        if re.search(pattern, cmd_lower):
            return name
    
    return None


def generate_interview_questions(candidate: SkillCandidate) -> List[InterviewRound]:
    """
    生成3轮面试问题
    
    参考Claude Code /skillify 的3轮 AskUserQuestion：
    - Round 1: 确认名称/描述/目标
    - Round 2: 步骤列表+参数+inline/forked+保存位置
    - Round 3: 每步详细拆解
    """
    rounds = [
        InterviewRound(
            round_num=1,
            question=(
                f"I detected a potential skill: **{candidate.name}**\n"
                f"Description: {candidate.description}\n"
                f"Trigger: {candidate.trigger}\n\n"
                f"Is this correct? Please confirm or adjust:\n"
                f"1. Skill name (e.g., 'deploy-check')\n"
                f"2. One-line description\n"
                f"3. When should this skill trigger?"
            ),
        ),
        InterviewRound(
            round_num=2,
            question=(
                f"Let's refine **{candidate.name}**:\n\n"
                f"Current steps:\n"
                + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(candidate.steps))
                + f"\n\nPlease review:\n"
                f"1. Add/remove/reorder steps\n"
                f"2. What parameters does each step need?\n"
                f"3. Inline (run in current session) or Forked (sub-agent)?\n"
                f"4. Save location?"
            ),
        ),
        InterviewRound(
            round_num=3,
            question=(
                f"Final details for **{candidate.name}**:\n\n"
                f"For each step, please specify:\n"
                f"1. What it produces (output)\n"
                f"2. Success criteria (how to verify)\n"
                f"3. Needs user confirmation? (Y/N)\n"
                f"4. Can it run in parallel with other steps?"
            ),
        ),
    ]
    
    return rounds


def generate_skill_md(candidate: SkillCandidate) -> str:
    """
    生成 SKILL.md 文件内容
    
    参考Claude Code /skillify 的输出格式
    """
    steps_md = "\n".join(
        f"{i+1}. **{step}**\n"
        f"   - Output: \n"
        f"   - Verify: \n"
        for i, step in enumerate(candidate.steps)
    )
    
    params_md = ""
    if candidate.parameters:
        params_md = "\n## Parameters\n\n" + "\n".join(
            f"- `{p}`: " for p in candidate.parameters
        )
    
    content = f"""# {candidate.name}

{candidate.description}

## Trigger

{candidate.trigger}

## Steps

{steps_md}
{params_md}

## Success Criteria

{candidate.success_criteria or "All steps complete without errors"}

## Notes

- Auto-generated by skillify
- Mode: {'inline' if candidate.is_inline else 'forked'}
"""
    return content


if __name__ == "__main__":
    # 测试
    test_messages = [
        {"role": "user", "content": "帮我部署到staging环境"},
        {"role": "assistant", "content": "开始部署..."},
        {"role": "user", "content": "测试一下API端点"},
        {"role": "assistant", "content": "测试通过"},
        {"role": "user", "content": "再部署一次到production"},
        {"role": "assistant", "content": "部署完成"},
        {"role": "user", "content": "帮我调试这个bug"},
    ]
    
    candidates = analyze_conversation(test_messages)
    print(f"Found {len(candidates)} candidates")
    for c in candidates:
        print(f"  {c.name}: {c.description}")
        questions = generate_interview_questions(c)
        print(f"  Questions: {len(questions)} rounds")
        md = generate_skill_md(c)
        print(f"  SKILL.md: {len(md)} chars")
