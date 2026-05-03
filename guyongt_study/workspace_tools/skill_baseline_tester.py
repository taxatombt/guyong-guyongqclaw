#!/usr/bin/env python3
"""
skill_baseline_tester.py — 顾庸t Skill TDD 验证工具
来源：Superpowers writing-skills SKILL.md TDD 创作法规范
日期：2026-04-05

功能：
- 读取 skill 的 SKILL.md，提取 skill 要求的规则
- 用 subagent 模拟"无 skill"场景，让 agent 处理触发场景
- 记录 agent 违反规则时的具体 rationalization（借口）
- 输出报告：哪些规则会被违反，agent 具体怎么为自己辩解

TDD 映射：
  Test case → Pressure scenario (skill 触发场景)
  Test fails (RED) → Agent 违反规则（无 skill 状态下）
  Production code → SKILL.md
  Test passes (GREEN) → Agent 遵守规则（有 skill 状态下）

Exit Code：
  0 = baseline 测试完成（无论是否发现违规）
  1 = 错误（skill 不存在等）

用法：
  python3 skill_baseline_tester.py --skill-dir skills/skill-authoring/
  python3 skill_baseline_tester.py --skill-dir skills/skill-authoring/ --verbose
  python3 skill_baseline_tester.py --skill-dir skills/test-driven-development/ --scenario "implement new feature"
"""

import argparse
import os
import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone


# ===== Skill 规则提取 =====

def extract_rules(skill_md_path: str) -> list[dict]:
    """
    从 SKILL.md 中提取所有规则。
    规则来源：
    - Iron Law / HARD-GATE / 铁律 等黑体声明
    - "must" / "never" / "always" / "do NOT" 等关键词
    - 流程中的强制步骤
    """
    content = Path(skill_md_path).read_text(encoding="utf-8", errors="ignore")

    rules = []

    # 1. Iron Law / HARD-GATE 声明
    for pattern in [
        r'\*\*Iron Law[:\s]*(.*?)\n',
        r'\*\*HARD-GATE[:\s]*(.*?)\n',
        r'\*\*铁律[:\s]*(.*?)\n',
    ]:
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            rule_text = match.group(1).strip()
            if len(rule_text) > 10:
                rules.append({
                    "type": "HARD_GATE",
                    "text": rule_text[:200],
                    "source": "bold_declaration",
                })

    # 2. Must / Never / Always / Do NOT
    mandatory_pattern = re.compile(
        r'(?:^\s*[-*]\s+|\n\s*)[A-Z][^.!?\n]{0,100}'
        r'\b(must|never|always|do\s+NOT|do\s+not|must\s+NOT)\b'
        r'[^.!?\n]{0,150}',
        re.IGNORECASE | re.MULTILINE
    )
    for match in mandatory_pattern.finditer(content):
        line = match.group(0).strip()
        if len(line) > 15 and len(line) < 300:
            rules.append({
                "type": "MANDATORY",
                "text": line,
                "source": "must_never_always",
            })

    # 3. No exceptions / No Placeholders 等强约束
    for pattern in [
        r'No\s+exceptions[:\s]*(.*?)(?:\n\n|\n##)',
        r'No\s+Placeholders[:\s]*(.*?)(?:\n\n|\n##)',
        r'delete\s+(?:it|them|code).*start\s+over',
        r'write\s+the\s+test\s+first',
        r'do\s+NOT.*until',
    ]:
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            rule_text = match.group(0).strip()
            if len(rule_text) > 10:
                rules.append({
                    "type": "STRONG_CONSTRAINT",
                    "text": rule_text[:200],
                    "source": "pattern_match",
                })

    # 4. Step-by-step 流程中的关键约束
    step_pattern = re.compile(
        r'(?:^\d+\..*?\n(?:^\s+[-*].*?\n){0,3})',
        re.MULTILINE
    )
    for step_match in step_pattern.finditer(content):
        step_text = step_match.group(0)
        # 查找 step 中的强制词
        if any(kw in step_text.lower() for kw in ["must", "never", "first", "before"]):
            lines = [l.strip() for l in step_text.splitlines() if l.strip()]
            if lines:
                rules.append({
                    "type": "PROCESS_STEP",
                    "text": lines[0][:150],
                    "source": "step_constraint",
                })

    # 去重
    seen = set()
    unique_rules = []
    for r in rules:
        key = r["type"] + r["text"][:80]
        if key not in seen:
            seen.add(key)
            unique_rules.append(r)

    return unique_rules


def extract_trigger_description(skill_md_path: str) -> str:
    """从 frontmatter description 提取触发条件"""
    content = Path(skill_md_path).read_text(encoding="utf-8", errors="ignore")

    # 提取 frontmatter
    fm_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        desc_match = re.search(r'description:\s*(.+?)(?:\n[^ ]|\n?$)', fm_text, re.DOTALL)
        if desc_match:
            return desc_match.group(1).strip().strip('"\'')

    return "trigger condition not found"


# ===== Baseline 测试模拟 =====

def run_baseline_test(skill_name: str, rules: list[dict], task_desc: str = "") -> dict:
    """
    模拟 baseline 测试：让 agent 在无 skill 情况下处理任务场景。
    这里用简单的启发式模拟：生成触发场景 prompt，让 LLM 自己暴露 rationalization。

    真实实现应该用 subagent 隔离 session，这里用 prompt 模拟。
    """
    # 生成测试 prompt
    scenario_prompt = f"""You are a coding agent WITHOUT the {skill_name} skill.
You are working on: {task_desc or 'a typical coding task'}.

Your task is to handle this situation as best you can, using only your general knowledge.

IMPORTANT: If you find yourself wanting to skip any step, take any shortcut, 
or decide something is "simple enough" to skip, describe that rationalization openly.

What rationalizations do you use? List them explicitly.
"""

    return {
        "skill_name": skill_name,
        "task": task_desc or "general coding task",
        "prompt_used": scenario_prompt,
        "rules_count": len(rules),
        "simulated_rationalizations": _simulate_rationalizations(skill_name, rules),
    }


def _simulate_rationalizations(skill_name: str, rules: list[dict]) -> list[dict]:
    """
    基于规则类型，生成预期的 rationalization 模式。
    这是启发式模拟，真实场景需要跑 subagent。

    返回：[(rule_type, typical_rationalization)]
    """
    known_patterns = {
        "HARD_GATE": "This is simple enough to skip the formal process",
        "MANDATORY": "I'll add that later / This is just a quick prototype",
        "STRONG_CONSTRAINT": "Just this once won't hurt",
        "PROCESS_STEP": "I know what I'm doing, no need to follow steps",
    }

    results = []
    for rule in rules[:10]:  # 最多分析10条规则
        rtype = rule["type"]
        rationalization = known_patterns.get(rtype, "I'll figure it out as I go")
        results.append({
            "rule_type": rtype,
            "rule_text": rule["text"][:100],
            "typical_rationalization": rationalization,
            "confidence": "high" if rtype in known_patterns else "medium",
        })

    return results


# ===== 报告生成 =====

def generate_report(skill_name: str, skill_path: Path, rules: list[dict],
                    baseline_result: dict, verbose: bool = False) -> str:
    """生成人类可读的测试报告"""

    trigger = extract_trigger_description(str(skill_path))

    lines = [
        f"\n{'=' * 70}",
        f"  SKILL BASELINE TEST REPORT",
        f"{'=' * 70}",
        f"\n  Skill:        {skill_name}",
        f"  Path:         {skill_path}",
        f"  Trigger:      {trigger}",
        f"  Rules found:  {len(rules)}",
        f"\n{'─' * 70}",
        f"\n  RULES EXTRACTED:",
    ]

    for i, rule in enumerate(rules[:15], 1):
        lines.append(f"\n  [{i}] ({rule['type']})")
        lines.append(f"      {rule['text'][:120]}")

    if len(rules) > 15:
        lines.append(f"\n  ... and {len(rules) - 15} more rules")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  BASELINE SIMULATION:")

    sim_results = baseline_result.get("simulated_rationalizations", [])
    if not sim_results:
        lines.append("\n  No typical rationalizations modeled for this skill type.")
    else:
        for i, sim in enumerate(sim_results, 1):
            lines.append(f"\n  Rationalization #{i}:")
            lines.append(f"    Rule type:     {sim['rule_type']}")
            lines.append(f"    Agent says:    \"{sim['typical_rationalization']}\"")
            lines.append(f"    Confidence:    {sim['confidence']}")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  VERDICT:")
    if len(rules) == 0:
        lines.append(f"\n  ⚠️  NO RULES EXTRACTED")
        lines.append(f"      This skill may not have enforceable rules.")
        lines.append(f"      Recommendation: Add explicit MUST/NEVER/HARD-GATE statements.")
    elif all(r['confidence'] == 'high' for r in sim_results):
        lines.append(f"\n  ✅ BASELINE VIOLATIONS PREDICTABLE")
        lines.append(f"      The skill's rules have known rationalization patterns.")
        lines.append(f"      Writing the skill should address these specific patterns.")
    else:
        lines.append(f"\n  ⚠️  PARTIAL PREDICTABILITY")
        lines.append(f"      Some rules have predictable violations, others less so.")
        lines.append(f"      Consider running real subagent baseline tests.")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  RECOMMENDATIONS:")
    if len(rules) == 0:
        lines.append(f"  1. Add HARD-GATE or Iron Law declarations with explicit MUST/NEVER")
        lines.append(f"  2. Use \"No exceptions\" language for critical constraints")
    else:
        lines.append(f"  1. When writing the SKILL.md, address the typical rationalizations above")
        lines.append(f"  2. Run real subagent baseline tests to verify agent actually fails")
        lines.append(f"  3. Add specific fixes for each rationalization pattern")

    lines.append(f"\n{'=' * 70}\n")
    return "\n".join(lines)


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Skill Baseline Tester — TDD-based skill validation.\n"
                    "Extract rules from SKILL.md, simulate baseline violations,\n"
                    "report rationalization patterns.\n"
                    "Exit 0: test complete. Exit 1: error."
    )
    parser.add_argument("--skill-dir", type=str, required=True,
                       help="Skill 目录路径（包含 SKILL.md）")
    parser.add_argument("--task", type=str, default="",
                       help="任务描述（用于模拟场景）")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")
    parser.add_argument("--report-path", type=str, default="",
                       help="保存报告到文件")

    args = parser.parse_args()

    skill_dir = Path(args.skill_dir)
    skill_md = skill_dir / "SKILL.md"

    if not skill_dir.is_dir():
        print(f"❌ ERROR: {skill_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if not skill_md.exists():
        print(f"❌ ERROR: SKILL.md not found in {skill_dir}", file=sys.stderr)
        sys.exit(1)

    skill_name = skill_dir.name

    # 提取规则
    rules = extract_rules(str(skill_md))

    # 运行 baseline 模拟
    baseline_result = run_baseline_test(skill_name, rules, args.task)

    # 生成报告
    report = generate_report(skill_name, skill_md, rules, baseline_result, args.verbose)

    if args.json:
        output = {
            "skill_name": skill_name,
            "skill_path": str(skill_md),
            "trigger": extract_trigger_description(str(skill_md)),
            "rules_count": len(rules),
            "rules": rules,
            "baseline": baseline_result,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(report)

    # 保存报告
    if args.report_path:
        Path(args.report_path).write_text(report, encoding="utf-8")
        print(f"[saved] {args.report_path}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()