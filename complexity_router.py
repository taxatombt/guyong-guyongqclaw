# -*- coding: utf-8 -*-
"""
complexity_router.py - 任务复杂度路由

来源: 顾庸t workspace_tools/complexity_router.py
参考: Claude Code 分支路由 + Hermes BudgetConfig

复杂度分级:
  Level 0: trivial    — 简单问答，不需要工具
  Level 1: simple     — 1-2步操作
  Level 2: moderate   — 多步骤，涉及多个文件/模块
  Level 3: complex    — 跨模块，需要验证
  Level 4: critical   — 高风险，需要确认

每级对应的 Agent 策略:
  L0: 直接回答
  L1: 单 Agent 直接执行
  L2: Execute Agent + 后验证
  L3: Plan → Explore → Execute → Verify
  L4: Plan → Review → Confirm → Execute → Verify
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import IntEnum


class ComplexityLevel(IntEnum):
    TRIVIAL = 0
    SIMPLE = 1
    MODERATE = 2
    COMPLEX = 3
    CRITICAL = 4


@dataclass
class ComplexityAssessment:
    """复杂度评估结果"""
    level: ComplexityLevel
    score: float  # 0.0 ~ 1.0
    signals: List[str]  # 触发信号
    recommendation: str  # Agent 策略建议


# 复杂度信号权重
SIGNALS = {
    # +1 信号
    "multi_file": ("涉及多个文件", 0.15),
    "cross_module": ("跨模块操作", 0.20),
    "has_write": ("包含写操作", 0.10),
    "has_delete": ("包含删除操作", 0.20),
    "has_network": ("涉及网络请求", 0.15),
    "has_execute": ("涉及命令执行", 0.15),
    "has_git": ("涉及 git 操作", 0.10),
    
    # +2 信号
    "system_modification": ("修改系统配置", 0.25),
    "database_operation": ("数据库操作", 0.20),
    "concurrent_access": ("并发操作", 0.20),
    "irreversible": ("不可逆操作", 0.30),
    
    # +3 信号
    "production_impact": ("影响生产环境", 0.35),
    "credential_access": ("涉及凭证", 0.30),
    "user_data_modify": ("修改用户数据", 0.25),
}


# 模式匹配
PATTERNS = [
    # 高风险模式
    (r"(rm|del|remove|delete|drop)\s", "has_delete", 0.20),
    (r"(sudo|admin|root|elevated)", "has_execute", 0.20),
    (r"(password|secret|token|key|credential)", "credential_access", 0.30),
    (r"(git\s+(push|rebase|reset|force))", "has_git", 0.10),
    (r"(curl|wget|pip\s+install|npm\s+install)", "has_network", 0.15),
    (r"(production|prod|deploy|release)", "production_impact", 0.35),
    
    # 多文件/跨模块
    (r"(多个文件|multi.file|all\s+files)", "multi_file", 0.15),
    (r"(跨模块|cross.module|整个项目|all\s+modules)", "cross_module", 0.20),
    
    # 写操作
    (r"(写入|保存|创建|写入文件|write|create|save)", "has_write", 0.10),
    (r"(修改|编辑|更新|edit|modify|update)", "has_write", 0.10),
    
    # 系统
    (r"(系统|配置|registry|config|environment)", "system_modification", 0.25),
    (r"(数据库|database|sql|sqlite|mysql)", "database_operation", 0.20),
]


def assess_complexity(task_description: str) -> ComplexityAssessment:
    """
    评估任务复杂度。
    返回: ComplexityAssessment
    """
    query = task_description.lower()
    score = 0.0
    signals = []
    
    for pattern, signal_key, weight in PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            score += weight
            signals.append(signal_key)
    
    # 基础分: 有任何信号至少是 SIMPLE
    if score > 0:
        score = max(0.15, score)
    
    # 确定级别
    if score < 0.15:
        level = ComplexityLevel.TRIVIAL
    elif score < 0.30:
        level = ComplexityLevel.SIMPLE
    elif score < 0.50:
        level = ComplexityLevel.MODERATE
    elif score < 0.70:
        level = ComplexityLevel.COMPLEX
    else:
        level = ComplexityLevel.CRITICAL
    
    recommendation = _recommendation(level)
    
    return ComplexityAssessment(
        level=level,
        score=min(1.0, score),
        signals=signals,
        recommendation=recommendation,
    )


def _recommendation(level: ComplexityLevel) -> str:
    """返回 Agent 策略建议"""
    recs = {
        ComplexityLevel.TRIVIAL: "直接回答，不需要工具",
        ComplexityLevel.SIMPLE: "单 Agent 直接执行，1-2 步",
        ComplexityLevel.MODERATE: "Execute Agent 执行 + 后验证",
        ComplexityLevel.COMPLEX: "Plan → Explore → Execute → Verify",
        ComplexityLevel.CRITICAL: "Plan → Review → Confirm → Execute → Verify",
    }
    return recs.get(level, "未知")


def format_assessment(assessment: ComplexityAssessment) -> str:
    """格式化评估结果"""
    signal_names = [SIGNALS.get(s, (s, 0))[0] for s in assessment.signals]
    lines = [
        f"Complexity: L{assessment.level} ({assessment.level.name})",
        f"Score: {assessment.score:.2f}",
        f"Signals: {', '.join(signal_names) if signal_names else 'None'}",
        f"Strategy: {assessment.recommendation}",
    ]
    return "\n".join(lines)
