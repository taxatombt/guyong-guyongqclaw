# -*- coding: utf-8 -*-
"""
remember_skill.py — 记忆审查提升

来源: Claude Code /remember 命令
用途: 审查 auto-memory，提出提升/清理建议

不修改任何现有系统代码，纯新建模块。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class MemoryLayer(Enum):
    """记忆层级（参考Claude Code四类型）"""
    CLAUDE_MD = "claude_md"       # 项目级约定（团队共享）
    LOCAL_MD = "local_md"         # 个人指令（不提交VCS）
    USER = "user"                 # 用户角色/偏好（永远private）
    FEEDBACK = "feedback"         # 工作指导（纠正+确认）
    PROJECT = "project"           # 项目上下文（非代码可推导）
    REFERENCE = "reference"       # 外部系统指针


class MemoryAction(Enum):
    """记忆操作"""
    PROMOTE = "promote"           # 提升：auto-memory → 目标层
    DEMOTE = "demote"             # 降级：高层 → 低层
    MERGE = "merge"               # 合并：重复条目合并
    REMOVE = "remove"             # 删除：过时/冲突
    KEEP = "keep"                 # 保留


@dataclass
class MemoryEntry:
    """单条记忆"""
    content: str
    source: str = ""              # 来源文件
    line_num: int = 0
    layer: MemoryLayer = MemoryLayer.PROJECT
    age_days: int = 0             # 天数
    last_used_days: int = 0       # 最后使用天数


@dataclass
class MemoryReview:
    """记忆审查建议"""
    entry: MemoryEntry
    action: MemoryAction
    target_layer: Optional[MemoryLayer] = None
    reason: str = ""
    merged_with: Optional[List[str]] = None


def classify_entry(content: str) -> MemoryLayer:
    """
    分类记忆条目到合适的层级
    
    参考Claude Code记忆四类型：
    - user: 用户角色/偏好/知识
    - feedback: 纠正+确认
    - project: 非代码可推导的项目上下文
    - reference: 外部系统指针
    """
    content_lower = content.lower()
    
    # 用户偏好模式
    user_patterns = [
        r'(?:喜欢|偏好|prefer|like|always|never)\s',
        r'(?:不用|不要|don\'t|avoid)',
        r'(?:我的|my)\s+(?:风格|style|习惯|preference)',
    ]
    for p in user_patterns:
        if re.search(p, content_lower):
            return MemoryLayer.USER
    
    # 反馈/纠正模式
    feedback_patterns = [
        r'(?:纠正|correction|fix|should\s+be|正确的是)',
        r'(?:注意|remember\s+to|务必|must)',
        r'(?:不要忘|don\'t\s+forget|重要)',
    ]
    for p in feedback_patterns:
        if re.search(p, content_lower):
            return MemoryLayer.FEEDBACK
    
    # 外部引用模式
    reference_patterns = [
        r'https?://',
        r'(?:Linear|Jira|Grafana|Slack|Discord)',
        r'(?:API\s+endpoint|dashboard|monitor)',
    ]
    for p in reference_patterns:
        if re.search(p, content_lower):
            return MemoryLayer.REFERENCE
    
    return MemoryLayer.PROJECT


def detect_duplicates(entries: List[MemoryEntry]) -> List[Tuple[int, int, float]]:
    """
    检测重复/相似条目
    
    Returns: List of (idx1, idx2, similarity) tuples
    """
    duplicates = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            sim = _compute_similarity(entries[i].content, entries[j].content)
            if sim > 0.7:  # 70%相似度
                duplicates.append((i, j, sim))
    return duplicates


def detect_outdated(entries: List[MemoryEntry], max_age_days: int = 90) -> List[int]:
    """检测过时条目"""
    return [i for i, e in enumerate(entries) if e.age_days > max_age_days]


def review_memory(entries: List[MemoryEntry]) -> List[MemoryReview]:
    """
    完整记忆审查
    
    参考 Claude Code /remember：
    1. 分类每条 auto-memory → 目标层
    2. 识别重复/过时/冲突
    3. 提出提升/清理/解决建议
    """
    reviews = []
    
    # 1. 分类
    for entry in entries:
        suggested_layer = classify_entry(entry.content)
        if suggested_layer != entry.layer:
            reviews.append(MemoryReview(
                entry=entry,
                action=MemoryAction.PROMOTE,
                target_layer=suggested_layer,
                reason=f"Suggested layer: {suggested_layer.value} (currently: {entry.layer.value})",
            ))
        else:
            reviews.append(MemoryReview(
                entry=entry,
                action=MemoryAction.KEEP,
                reason="Correct layer",
            ))
    
    # 2. 重复检测
    duplicates = detect_duplicates(entries)
    for i, j, sim in duplicates:
        reviews.append(MemoryReview(
            entry=entries[j],
            action=MemoryAction.MERGE,
            target_layer=entries[i].layer,
            reason=f"Duplicate of entry at line {entries[i].line_num} (similarity: {sim:.0%})",
            merged_with=[entries[i].content[:50]],
        ))
    
    # 3. 过时检测
    outdated = detect_outdated(entries)
    for idx in outdated:
        reviews.append(MemoryReview(
            entry=entries[idx],
            action=MemoryAction.REMOVE,
            reason=f"Outdated ({entries[idx].age_days} days old, last used {entries[idx].last_used_days} days ago)",
        ))
    
    return reviews


def format_review_report(reviews: List[MemoryReview]) -> str:
    """格式化审查报告"""
    lines = ["# Memory Review Report\n"]
    
    actions = {}
    for r in reviews:
        actions[r.action.value] = actions.get(r.action.value, 0) + 1
    
    lines.append("## Summary\n")
    for action, count in sorted(actions.items()):
        lines.append(f"- {action}: {count}")
    
    lines.append("\n## Suggestions\n")
    for r in reviews:
        if r.action != MemoryAction.KEEP:
            lines.append(f"- [{r.action.value.upper()}] {r.entry.content[:60]}...")
            lines.append(f"  Reason: {r.reason}")
            if r.target_layer:
                lines.append(f"  Target: {r.target_layer.value}")
    
    return "\n".join(lines)


def _compute_similarity(text1: str, text2: str) -> float:
    """Jaccard相似度"""
    if not text1 or not text2:
        return 0.0
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


if __name__ == "__main__":
    # 测试
    entries = [
        MemoryEntry("User prefers Python over JavaScript", layer=MemoryLayer.PROJECT, age_days=5),
        MemoryEntry("Always use type hints in Python", layer=MemoryLayer.PROJECT, age_days=10),
        MemoryEntry("Project uses FastAPI for backend", layer=MemoryLayer.PROJECT, age_days=30),
        MemoryEntry("User prefers Python over JS", layer=MemoryLayer.PROJECT, age_days=3),  # 重复
        MemoryEntry("Old deployment URL: https://old.example.com", layer=MemoryLayer.PROJECT, age_days=120),  # 过时
    ]
    
    reviews = review_memory(entries)
    report = format_review_report(reviews)
    print(report)
