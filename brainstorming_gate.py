# -*- coding: utf-8 -*-
"""
brainstorming_gate.py - brainstorming 强制门控

来源: 顾庸t workspace_tools/brainstorming_gate.py
参考: Superpowers HARD-GATE

核心功能:
  在执行任何"头脑风暴"类任务前，强制检查是否已明确定义 spec。
  
  门控条件:
  1. 是否有明确的 spec/requirement 定义？
  2. spec 是否包含可验证的成功标准？
  3. spec 是否有约束/限制说明？
  
  如果门控不通过 → 拒绝执行，返回改进建议。
  如果门控通过 → 放行执行。
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GateResult:
    """门控结果"""
    passed: bool
    score: float  # 0.0 ~ 1.0
    issues: List[str]
    suggestions: List[str]


# Spec 质量检查模式
SPEC_PATTERNS = {
    "has_goal": (
        r"(目标|goal|目的|objective|要实现|完成|deliverable)",
        "缺少明确目标定义"
    ),
    "has_requirements": (
        r"(需求|requirement|功能|feature|需要|must|should|shall)",
        "缺少需求列表"
    ),
    "has_success_criteria": (
        r"(成功标准|验收|acceptance|success criteria|done when|完成条件)",
        "缺少可验证的成功标准"
    ),
    "has_constraints": (
        r"(约束|constraint|限制|不能|不允许|must not|限制条件|边界)",
        "缺少约束/限制说明"
    ),
    "has_scope": (
        r"(范围|scope|不包括|out of scope|只做|仅限)",
        "缺少范围界定"
    ),
}

GATE_THRESHOLD = 0.4  # 低于此分数则拒绝


def evaluate_spec(spec_text: str) -> GateResult:
    """
    评估 spec 质量。
    
    参数: spec_text — 任务描述或 spec 文档
    返回: GateResult
    """
    issues = []
    suggestions = []
    score = 0.0
    
    for key, (pattern, message) in SPEC_PATTERNS.items():
        if re.search(pattern, spec_text, re.IGNORECASE):
            score += 0.2
        else:
            issues.append(message)
    
    score = min(1.0, score)
    
    # 生成建议
    if "缺少明确目标定义" in issues:
        suggestions.append(
            "添加明确目标: '目标: [具体可衡量的结果]'"
        )
    if "缺少需求列表" in issues:
        suggestions.append(
            "列出具体需求: '需求1: ... 需求2: ...'"
        )
    if "缺少可验证的成功标准" in issues:
        suggestions.append(
            "定义验收条件: '完成标准: [可验证的条件]'"
        )
    if "缺少约束/限制说明" in issues:
        suggestions.append(
            "说明限制: '约束: [不能做什么/技术限制]'"
        )
    if "缺少范围界定" in issues:
        suggestions.append(
            "界定范围: '范围: [只做什么 / 不做什么]'"
        )
    
    passed = score >= GATE_THRESHOLD
    
    return GateResult(
        passed=passed,
        score=score,
        issues=issues,
        suggestions=suggestions,
    )


def format_gate_result(result: GateResult) -> str:
    """格式化门控结果"""
    status = "PASSED" if result.passed else "BLOCKED"
    lines = [
        f"Brainstorming Gate: {status}",
        f"Spec Quality Score: {result.score:.0%}",
        f"Threshold: {GATE_THRESHOLD:.0%}",
    ]
    
    if result.issues:
        lines.append(f"\nIssues ({len(result.issues)}):")
        for i, issue in enumerate(result.issues, 1):
            lines.append(f"  {i}. {issue}")
    
    if result.suggestions:
        lines.append(f"\nSuggestions:")
        for i, sug in enumerate(result.suggestions, 1):
            lines.append(f"  {i}. {sug}")
    
    return "\n".join(lines)
