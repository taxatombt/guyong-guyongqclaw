# -*- coding: utf-8 -*-
"""
hindsight_recall.py - 事后回顾式记忆召回

来源: 顾庸t workspace_tools/hindsight_recall.py
参考: Claude Code memory recall + Hermes hindsight analysis

功能:
  1. 分析过去的错误/失败记录
  2. 提取通用教训（不是具体场景，而是可迁移的模式）
  3. 遇到新任务时，主动检查是否有相关教训
  4. 教训按置信度排序

与 evolver 的区别:
  - evolver: 记录成功方法，下次直接用
  - hindsight: 分析失败原因，提取可泛化的教训
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")


@dataclass
class HindsightLesson:
    """事后教训"""
    id: str
    pattern: str  # 通用模式描述
    lesson: str   # 教训
    trigger_keywords: List[str]  # 触发关键词
    confidence: float  # 0.0 ~ 1.0
    source_task: str  # 来源任务
    occurrence_count: int = 1


# 内置教训（从已知的失败中提取）
BUILTIN_LESSONS: List[Dict[str, Any]] = [
    {
        "pattern": "PowerShell encoding issue with Chinese text",
        "lesson": "Always use Python scripts for file operations involving Chinese text on Windows. Never use PowerShell heredoc or inline -c for writing files with non-ASCII content.",
        "trigger_keywords": ["powershell", "write", "chinese", "encoding", "utf-8", "gbk", "乱码"],
        "confidence": 0.95,
        "source_task": "Multiple file write failures",
    },
    {
        "pattern": "Write tool vs edit tool parameter confusion",
        "lesson": "write tool uses 'content' parameter. edit tool uses 'oldText'/'newText'. Mixing them causes parameter errors.",
        "trigger_keywords": ["write", "edit", "parameter", "newText", "content", "validation failed"],
        "confidence": 0.90,
        "source_task": "Tool parameter errors",
    },
    {
        "pattern": "Editing core system files without backup",
        "lesson": "Always backup before modifying core files. Use FileSnapshot for atomic operations with rollback capability.",
        "trigger_keywords": ["modify", "core", "system", "backup", "rollback", "agents"],
        "confidence": 0.85,
        "source_task": "tool_pipeline.py corruption incident",
    },
    {
        "pattern": "f-string multiline syntax error",
        "lesson": "Python f-strings cannot span multiple lines without explicit continuation. Use string concatenation or parenthesized expressions.",
        "trigger_keywords": ["f-string", "syntax error", "multiline", "f'"],
        "confidence": 0.85,
        "source_task": "Multiple f-string bugs",
    },
    {
        "pattern": "Docker/pipe command injection risk",
        "lesson": "Never pipe curl/wget output directly to shell. Always download to file first, inspect, then execute.",
        "trigger_keywords": ["curl", "pipe", "bash", "install", "script"],
        "confidence": 0.80,
        "source_task": "Security review",
    },
    {
        "pattern": "Assuming skill exists without checking",
        "lesson": "Before any task, check if a relevant skill exists. Red Flag: 'I think skill X is not needed' → always verify.",
        "trigger_keywords": ["skill", "check", "assume", "trigger"],
        "confidence": 0.90,
        "source_task": "SOUL.md Red Flags",
    },
]


class HindsightRecall:
    """事后回顾式记忆召回"""
    
    def __init__(self):
        self._lessons: Dict[str, HindsightLesson] = {}
        self._load_builtins()
    
    def _load_builtins(self) -> None:
        for i, data in enumerate(BUILTIN_LESSONS):
            lesson = HindsightLesson(
                id=f"builtin-{i:03d}",
                pattern=data["pattern"],
                lesson=data["lesson"],
                trigger_keywords=data["trigger_keywords"],
                confidence=data["confidence"],
                source_task=data["source_task"],
            )
            self._lessons[lesson.id] = lesson
    
    def add_lesson(self, pattern: str, lesson: str,
                   trigger_keywords: Optional[List[str]] = None,
                   source_task: str = "manual",
                   confidence: float = 0.5) -> HindsightLesson:
        """添加新教训"""
        lesson_id = f"custom-{len(self._lessons):03d}"
        hl = HindsightLesson(
            id=lesson_id,
            pattern=pattern,
            lesson=lesson,
            trigger_keywords=trigger_keywords or [],
            confidence=confidence,
            source_task=source_task,
        )
        self._lessons[lesson_id] = hl
        return hl
    
    def recall(self, context: str, threshold: float = 0.3) -> List[HindsightLesson]:
        """根据上下文召回相关教训"""
        context_lower = context.lower()
        scored = []
        
        for lesson in self._lessons.values():
            score = 0.0
            for kw in lesson.trigger_keywords:
                if kw.lower() in context_lower:
                    score += 0.2
            
            if score > 0:
                # 综合得分 = 匹配分 × 置信度
                final_score = min(1.0, score) * lesson.confidence
                if final_score >= threshold:
                    scored.append((lesson, final_score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [lesson for lesson, _ in scored]
    
    def reinforce(self, lesson_id: str) -> Optional[HindsightLesson]:
        """强化教训（出现次数+1，可能提升置信度）"""
        lesson = self._lessons.get(lesson_id)
        if lesson:
            lesson.occurrence_count += 1
            if lesson.confidence < 0.95:
                lesson.confidence = min(0.95, lesson.confidence + 0.05)
        return lesson
    
    def list_lessons(self) -> List[Dict[str, Any]]:
        """列出所有教训"""
        return sorted(
            [
                {
                    "id": l.id,
                    "pattern": l.pattern,
                    "confidence": round(l.confidence, 2),
                    "occurrences": l.occurrence_count,
                    "keywords": l.trigger_keywords[:3],
                }
                for l in self._lessons.values()
            ],
            key=lambda x: x["confidence"],
            reverse=True,
        )
    
    def format_recall(self, lessons: List[HindsightLesson]) -> str:
        """格式化召回结果"""
        if not lessons:
            return "No relevant lessons found."
        
        lines = [f"# Hindsight Recall: {len(lessons)} relevant lesson(s)\n"]
        for i, l in enumerate(lessons, 1):
            lines.append(f"## {i}. {l.pattern}")
            lines.append(f"Confidence: {l.confidence:.0%} | Occurrences: {l.occurrence_count}")
            lines.append(f"Lesson: {l.lesson}")
            lines.append("")
        
        return "\n".join(lines)


_hindsight: Optional[HindsightRecall] = None

def get_hindsight() -> HindsightRecall:
    global _hindsight
    if _hindsight is None:
        _hindsight = HindsightRecall()
    return _hindsight
