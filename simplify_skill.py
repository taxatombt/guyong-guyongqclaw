# -*- coding: utf-8 -*-
"""
simplify_skill.py — 三Agent并行代码审查

来源: Claude Code /simplify 命令
用途: 同时启动3个审查Agent（复用+质量+效率），聚合结果

不修改任何现有系统代码，纯新建模块。
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class ReviewType(Enum):
    REUSE = "reuse"         # 复用审查：搜索现有工具/函数替代
    QUALITY = "quality"     # 质量审查：冗余状态、参数蔓延等
    EFFICIENCY = "efficiency"  # 效率审查：不必要工作、错过并发等


@dataclass
class ReviewFinding:
    """审查发现"""
    review_type: ReviewType
    severity: str = "info"      # info / warning / critical
    location: str = ""          # 文件:行号
    description: str = ""
    suggestion: str = ""
    auto_fixable: bool = False


@dataclass
class SimplifyResult:
    """审查结果"""
    reuse_findings: List[ReviewFinding] = field(default_factory=list)
    quality_findings: List[ReviewFinding] = field(default_factory=list)
    efficiency_findings: List[ReviewFinding] = field(default_factory=list)
    
    @property
    def total_findings(self) -> int:
        return (len(self.reuse_findings) + len(self.quality_findings) + 
                len(self.efficiency_findings))
    
    @property
    def critical_count(self) -> int:
        all_findings = self.reuse_findings + self.quality_findings + self.efficiency_findings
        return sum(1 for f in all_findings if f.severity == "critical")


# ===== Agent 1: 复用审查 =====

REUSE_CHECKS = [
    ("duplicate_code", "Search for existing utility functions before writing new ones"),
    ("existing_import", "Check if similar functionality is already imported"),
    ("standard_library", "Prefer standard library over custom implementations"),
    ("npm_package", "Check if an npm package already solves this problem"),
    ("internal_api", "Check if an internal API already provides this functionality"),
]


def check_reuse(code: str, file_path: str = "") -> List[ReviewFinding]:
    """
    Agent 1: 复用审查
    
    参考 Claude Code /simplify Agent 1：
    搜索现有工具/函数替代新代码
    """
    findings = []
    
    # 检测常见的重复实现模式
    patterns = [
        (r'def\s+read_file\s*\(', "read_file", 
         "Consider using existing file reading utility"),
        (r'def\s+format_date\s*\(', "format_date",
         "Consider using datetime.strftime or existing date formatter"),
        (r'requests\.(get|post)\s*\(', "http_request",
         "Consider using existing HTTP client utility with retry/error handling"),
        (r'json\.loads?\s*\(\s*\w+\.read\(\)', "json_file_read",
         "Consider using existing JSON file reader with error handling"),
        (r'os\.path\.join\s*\(', "path_join",
         "Consider using pathlib.Path for path operations"),
    ]
    
    import re
    for pattern, name, suggestion in patterns:
        if re.search(pattern, code):
            findings.append(ReviewFinding(
                review_type=ReviewType.REUSE,
                severity="warning",
                location=file_path,
                description=f"Potential duplicate implementation: {name}",
                suggestion=suggestion,
                auto_fixable=False,
            ))
    
    return findings


# ===== Agent 2: 质量审查 =====

QUALITY_CHECKS = [
    ("redundant_state", "Multiple variables tracking the same concept"),
    ("parameter_creep", "Function with too many parameters (>5)"),
    ("copy_paste", "Similar code blocks in multiple locations"),
    ("leaky_abstraction", "Implementation details exposed in interface"),
    ("string_typing", "Using strings instead of enums/constants"),
    ("unnecessary_comments", "Comments that just restate the code"),
]


def check_quality(code: str, file_path: str = "") -> List[ReviewFinding]:
    """
    Agent 2: 质量审查
    
    参考 Claude Code /simplify Agent 2：
    冗余状态、参数蔓延、复制粘贴、泄露抽象、字符串类型、不必要注释
    """
    findings = []
    import re
    
    # 参数过多
    func_pattern = r'def\s+\w+\s*\(([^)]*)\)'
    for match in re.finditer(func_pattern, code):
        params = [p.strip() for p in match.group(1).split(',') if p.strip()]
        if len(params) > 5:
            findings.append(ReviewFinding(
                review_type=ReviewType.QUALITY,
                severity="warning",
                location=file_path,
                description=f"Parameter creep: {len(params)} parameters",
                suggestion="Consider grouping related parameters into a config object",
                auto_fixable=False,
            ))
    
    # 字符串魔法值
    string_constants = re.findall(r'["\']([A-Z_]{3,})["\']', code)
    if len(string_constants) > 3:
        findings.append(ReviewFinding(
            review_type=ReviewType.QUALITY,
            severity="info",
            location=file_path,
            description=f"String typing: {len(string_constants)} string constants",
            suggestion="Consider using enums or named constants",
            auto_fixable=True,
        ))
    
    # 不必要注释
    comment_pattern = r'#\s*(return|print|if|for|while)\s'
    unnecessary = re.findall(comment_pattern, code)
    if unnecessary:
        findings.append(ReviewFinding(
            review_type=ReviewType.QUALITY,
            severity="info",
            location=file_path,
            description=f"Unnecessary comments: {len(unnecessary)} restating code",
            suggestion="Remove comments that just restate what the code does",
            auto_fixable=True,
        ))
    
    return findings


# ===== Agent 3: 效率审查 =====

EFFICIENCY_CHECKS = [
    ("unnecessary_work", "Computing something that's never used"),
    ("missed_concurrency", "Sequential operations that could be parallel"),
    ("hot_path_bloat", "Expensive operations in frequently-called code"),
    ("no_op_updates", "Writing unchanged data (wasting I/O)"),
    ("toctou", "Time-of-check-time-of-use race conditions"),
]


def check_efficiency(code: str, file_path: str = "") -> List[ReviewFinding]:
    """
    Agent 3: 效率审查
    
    参考 Claude Code /simplify Agent 3：
    不必要工作、错过并发、热路径膨胀、无操作更新、TOCTOU
    """
    findings = []
    import re
    
    # 同步阻塞操作
    sync_patterns = [
        (r'time\.sleep\s*\(', "Blocking sleep in main thread"),
        (r'requests\.(get|post)\s*\(', "Synchronous HTTP request (consider async)"),
    ]
    for pattern, desc in sync_patterns:
        if re.search(pattern, code):
            findings.append(ReviewFinding(
                review_type=ReviewType.EFFICIENCY,
                severity="info",
                location=file_path,
                description=desc,
                suggestion="Consider using async alternatives for better concurrency",
                auto_fixable=False,
            ))
    
    # TOCTOU
    toctou_pattern = r'os\.path\.exists\s*\([^)]+\)[\s\S]*?open\s*\('
    if re.search(toctou_pattern, code):
        findings.append(ReviewFinding(
            review_type=ReviewType.EFFICIENCY,
            severity="critical",
            location=file_path,
            description="TOCTOU: check-then-use race condition",
            suggestion="Use atomic operations (open with O_CREAT|O_EXCL, or try/except)",
            auto_fixable=False,
        ))
    
    return findings


def run_simplify(code: str, file_path: str = "") -> SimplifyResult:
    """
    运行三Agent并行审查
    
    参考 Claude Code /simplify：同时启动3个Explore Agent
    - Agent 1 复用审查
    - Agent 2 质量审查
    - Agent 3 效率审查
    """
    result = SimplifyResult()
    
    # 并行（模拟）运行三个审查
    result.reuse_findings = check_reuse(code, file_path)
    result.quality_findings = check_quality(code, file_path)
    result.efficiency_findings = check_efficiency(code, file_path)
    
    return result


def format_simplify_report(result: SimplifyResult) -> str:
    """格式化审查报告"""
    lines = [
        f"# Simplify Report\n",
        f"**Total findings**: {result.total_findings}",
        f"**Critical**: {result.critical_count}\n",
    ]
    
    for review_type, findings in [
        ("Reuse", result.reuse_findings),
        ("Quality", result.quality_findings),
        ("Efficiency", result.efficiency_findings),
    ]:
        if findings:
            lines.append(f"\n## {review_type} ({len(findings)})\n")
            for f in findings:
                icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}.get(f.severity, "•")
                lines.append(f"{icon} **{f.description}**")
                if f.suggestion:
                    lines.append(f"   → {f.suggestion}")
                if f.auto_fixable:
                    lines.append(f"   → 🔧 Auto-fixable")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    test_code = '''
import requests
import time
import os

def process_data(url, param1, param2, param3, param4, param5, param6):
    """process data and return result"""
    # return the result
    if os.path.exists("data.json"):
        with open("data.json") as f:
            data = json.loads(f.read())
    time.sleep(5)
    response = requests.get(url)
    return response.json()
'''
    
    result = run_simplify(test_code, "example.py")
    report = format_simplify_report(result)
    print(report)
