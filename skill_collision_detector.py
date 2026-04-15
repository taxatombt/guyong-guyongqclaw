# -*- coding: utf-8 -*-
"""
skill_collision_detector.py - Skill 冲突检测

来源: 顾庸t workspace_tools/skill_collision_detector.py
参考: ECC skill-collision + Claude Code skill system

核心功能:
  检测两个或多个 Skill 之间是否存在冲突。
  
  冲突类型:
  1. TRIGGER_CONFLICT — 触发条件重叠（同一输入可能触发多个 Skill）
  2. OUTPUT_CONFLICT — 输出格式冲突（都声称处理同一类输出）
  3. BEHAVIOR_CONFLICT — 行为矛盾（一个说做A，另一个说做非A）
  4. RESOURCE_CONFLICT — 资源竞争（都修改同一文件/配置）
  5. DEPENDENCY_CONFLICT — 依赖冲突（A依赖B但B禁用A的功能）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum


class ConflictType(Enum):
    TRIGGER = "trigger_conflict"
    OUTPUT = "output_conflict"
    BEHAVIOR = "behavior_conflict"
    RESOURCE = "resource_conflict"
    DEPENDENCY = "dependency_conflict"


@dataclass
class Conflict:
    """检测到的冲突"""
    conflict_type: ConflictType
    skill_a: str
    skill_b: str
    description: str
    severity: str  # low / medium / high
    suggestion: str = ""


@dataclass
class SkillProfile:
    """Skill 档案（用于冲突检测）"""
    name: str
    triggers: List[str] = field(default_factory=list)  # 触发关键词
    output_types: List[str] = field(default_factory=list)  # 输出类型
    modifies: List[str] = field(default_factory=list)  # 修改的文件/资源
    depends_on: List[str] = field(default_factory=list)  # 依赖
    conflicts_with: List[str] = field(default_factory=list)  # 已知冲突
    behaviors: List[str] = field(default_factory=list)  # 行为描述


class SkillCollisionDetector:
    """Skill 冲突检测器"""
    
    def detect(self, skills: List[SkillProfile]) -> List[Conflict]:
        """
        检测 Skill 列表中的所有冲突。
        O(n^2) 两两比较。
        """
        conflicts = []
        
        for i, a in enumerate(skills):
            for b in skills[i+1:]:
                # 1. 触发冲突
                trigger_conflicts = self._check_trigger(a, b)
                conflicts.extend(trigger_conflicts)
                
                # 2. 输出冲突
                output_conflicts = self._check_output(a, b)
                conflicts.extend(output_conflicts)
                
                # 3. 资源冲突
                resource_conflicts = self._check_resource(a, b)
                conflicts.extend(resource_conflicts)
                
                # 4. 依赖冲突
                dep_conflicts = self._check_dependency(a, b)
                conflicts.extend(dep_conflicts)
                
                # 5. 已知冲突
                if b.name in a.conflicts_with or a.name in b.conflicts_with:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.BEHAVIOR,
                        skill_a=a.name,
                        skill_b=b.name,
                        description=f"{a.name} and {b.name} have declared mutual conflict",
                        severity="high",
                        suggestion="Review both skills and resolve the declared conflict",
                    ))
        
        return sorted(conflicts, key=lambda c: c.severity, reverse=True)
    
    def _check_trigger(self, a: SkillProfile, b: SkillProfile) -> List[Conflict]:
        """检测触发条件重叠"""
        overlap = set(a.triggers) & set(b.triggers)
        if not overlap:
            return []
        
        severity = "high" if len(overlap) >= 3 else "medium"
        return [Conflict(
            conflict_type=ConflictType.TRIGGER,
            skill_a=a.name,
            skill_b=b.name,
            description=f"Shared trigger keywords: {', '.join(list(overlap)[:5])}",
            severity=severity,
            suggestion=(
                f"Differentiate trigger scope: "
                f"e.g. '{a.name}' triggers on X only, '{b.name}' on Y only"
            ),
        )]
    
    def _check_output(self, a: SkillProfile, b: SkillProfile) -> List[Conflict]:
        """检测输出类型冲突"""
        overlap = set(a.output_types) & set(b.output_types)
        if not overlap:
            return []
        
        return [Conflict(
            conflict_type=ConflictType.OUTPUT,
            skill_a=a.name,
            skill_b=b.name,
            description=f"Both output to: {', '.join(list(overlap)[:5])}",
            severity="medium",
            suggestion="Define clear ownership of each output type",
        )]
    
    def _check_resource(self, a: SkillProfile, b: SkillProfile) -> List[Conflict]:
        """检测资源竞争"""
        overlap = set(a.modifies) & set(b.modifies)
        if not overlap:
            return []
        
        return [Conflict(
            conflict_type=ConflictType.RESOURCE,
            skill_a=a.name,
            skill_b=b.name,
            description=f"Both modify: {', '.join(list(overlap)[:5])}",
            severity="high",
            suggestion="Add write coordination or define exclusive access",
        )]
    
    def _check_dependency(self, a: SkillProfile, b: SkillProfile) -> List[Conflict]:
        """检测依赖冲突"""
        conflicts = []
        # A depends on B but B conflicts with A
        if a.name in b.depends_on and b.name in a.conflicts_with:
            conflicts.append(Conflict(
                conflict_type=ConflictType.DEPENDENCY,
                skill_a=a.name,
                skill_b=b.name,
                description=f"Circular: {a.name} depends on {b.name} but conflicts with it",
                severity="high",
                suggestion="Break the dependency cycle",
            ))
        return conflicts
    
    def format_report(self, conflicts: List[Conflict]) -> str:
        """格式化冲突报告"""
        if not conflicts:
            return "No skill conflicts detected."
        
        lines = [f"Skill Collision Report: {len(conflicts)} conflict(s) found\n"]
        
        by_type: Dict[str, List[Conflict]] = {}
        for c in conflicts:
            by_type.setdefault(c.conflict_type.value, []).append(c)
        
        for ctype, items in by_type.items():
            lines.append(f"## {ctype} ({len(items)})")
            for c in items:
                lines.append(f"  [{c.severity.upper()}] {c.skill_a} ↔ {c.skill_b}")
                lines.append(f"    {c.description}")
                if c.suggestion:
                    lines.append(f"    → {c.suggestion}")
            lines.append("")
        
        return "\n".join(lines)


_detector: Optional[SkillCollisionDetector] = None

def get_detector() -> SkillCollisionDetector:
    global _detector
    if _detector is None:
        _detector = SkillCollisionDetector()
    return _detector
