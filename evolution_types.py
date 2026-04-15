# -*- coding: utf-8 -*-
"""
evolution_types.py — OpenSpace 风格进化类型系统

移植自 HKUDS/OpenSpace skill_engine/types.py
核心设计：Version DAG + 三种进化模式 + 质量指标

来源：HKUDS/OpenSpace skill_engine/types.py
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


# ═══════════════════════════════════════════════════════════════════
# 进化类型 — 三种进化模式
# ═══════════════════════════════════════════════════════════════════

class EvolutionType(str, Enum):
    """
    三种进化模式（来自 OpenSpace）
    
    FIX     — Skill 有 bug？自己修，自动升版本
    DERIVED — 需要针对特定场景？从父 Skill 派生一个专门的
    CAPTURED — 发现新的高效工作流？直接提取成新 Skill
    """
    FIX = "fix"        # 修复：同技能同名，新版本号
    DERIVED = "derived"  # 派生：从现有技能创建专精版
    CAPTURED = "captured"  # 捕获：全新发现，无父技能


class SkillOrigin(str, Enum):
    """
    技能来源（来自 OpenSpace SkillOrigin）
    
    Version DAG 模型 — 每次变更创建新节点：
    - IMPORTED / CAPTURED → 根节点，无父节点 generation=0
    - DERIVED → 1+ 个父节点，新名字新目录
    - FIXED → 1 个父节点，同名同路径，generation=父+1
    """
    IMPORTED = "imported"  # 初始导入，无父节点
    CAPTURED = "captured"  # 从成功执行中捕获，无父节点
    DERIVED = "derived"     # 从现有技能派生，1+ 个父节点
    FIXED = "fixed"         # 修复现有技能，1 个父节点


class SkillCategory(str, Enum):
    """技能分类"""
    WORKFLOW = "workflow"     # 端到端工作流
    TOOL_GUIDE = "tool_guide"  # 工具指南
    REFERENCE = "reference"    # 参考知识


# ═══════════════════════════════════════════════════════════════════
# SkillLineage — 技能进化谱系
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillLineage:
    """
    追踪技能的进化谱系（来自 OpenSpace SkillLineage）
    
    parent_skill_ids 可包含多个父节点（用于 DERIVED）
    generation = 从根节点的距离，由进化逻辑设置：
    - IMPORTED / CAPTURED → generation = 0
    - FIXED → generation = parent.generation + 1
    - DERIVED → generation = max(parent.generations) + 1
    
    content_diff 存储 git-diff 格式的完整变更
    content_snapshot 存储完整目录快照
    """
    origin: SkillOrigin           # 起源类型
    generation: int = 0         # 距离根的距离
    
    # 父节点（IMPORTED/CAPTURED 为空，FIXED 为 1 个，DERIVED 为 1+ 个）
    parent_skill_ids: List[str] = field(default_factory=list)
    
    # 触发这次进化的任务（用于追踪）
    source_task_id: Optional[str] = None
    
    # LLM 生成的变更摘要
    change_summary: str = ""
    
    # git-diff 格式的完整 diff（FIXED/单父 DERIVED 用）
    content_diff: str = ""
    
    # 完整目录快照 {relative_path: content}（FIXED 用，保留旧版本）
    content_snapshot: Dict[str, str] = field(default_factory=dict)
    
    # 元信息
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""  # "human" | model name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin.value,
            "generation": self.generation,
            "parent_skill_ids": self.parent_skill_ids,
            "source_task_id": self.source_task_id,
            "change_summary": self.change_summary,
            "content_diff": self.content_diff,
            # content_snapshot 太大，单独存储
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SkillLineage":
        return cls(
            origin=SkillOrigin(data.get("origin", "imported")),
            generation=data.get("generation", 0),
            parent_skill_ids=data.get("parent_skill_ids", []),
            source_task_id=data.get("source_task_id"),
            change_summary=data.get("change_summary", ""),
            content_diff=data.get("content_diff", ""),
            content_snapshot=data.get("content_snapshot", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            created_by=data.get("created_by", ""),
        )

    def get_evolve_type(self) -> EvolutionType:
        """根据 origin 反推进化类型"""
        mapping = {
            SkillOrigin.FIXED: EvolutionType.FIX,
            SkillOrigin.DERIVED: EvolutionType.DERIVED,
            SkillOrigin.CAPTURED: EvolutionType.CAPTURED,
            SkillOrigin.IMPORTED: EvolutionType.CAPTURED,
        }
        return mapping.get(self.origin, EvolutionType.CAPTURED)


# ═══════════════════════════════════════════════════════════════════
# SkillMetrics — 技能质量指标
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillMetrics:
    """
    技能质量指标（来自 OpenSpace SkillRecord 的 quality metrics）
    
    追踪每个技能的执行统计数据，用于判断是否需要进化
    """
    total_selections: int = 0   # 被选中次数
    total_applied: int = 0     # 实际应用次数
    total_completions: int = 0 # 任务完成次数
    total_fallbacks: int = 0   # 回退次数（失败后跳过）

    @property
    def applied_rate(self) -> float:
        """应用率 = applied / selections"""
        return self.total_applied / self.total_selections if self.total_selections else 0.0

    @property
    def completion_rate(self) -> float:
        """完成率 = completions / applied"""
        return self.total_completions / self.total_applied if self.total_applied else 0.0

    @property
    def effectiveness_rate(self) -> float:
        """有效率 = completions / selections"""
        return self.total_completions / self.total_selections if self.total_selections else 0.0

    @property
    def fallback_rate(self) -> float:
        """回退率 = fallbacks / selections"""
        return self.total_fallbacks / self.total_selections if self.total_selections else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_selections": self.total_selections,
            "total_applied": self.total_applied,
            "total_completions": self.total_completions,
            "total_fallbacks": self.total_fallbacks,
            "applied_rate": round(self.applied_rate, 3),
            "completion_rate": round(self.completion_rate, 3),
            "effectiveness_rate": round(self.effectiveness_rate, 3),
            "fallback_rate": round(self.fallback_rate, 3),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SkillMetrics":
        return cls(
            total_selections=data.get("total_selections", 0),
            total_applied=data.get("total_applied", 0),
            total_completions=data.get("total_completions", 0),
            total_fallbacks=data.get("total_fallbacks", 0),
        )


# ═══════════════════════════════════════════════════════════════════
# EvolutionSuggestion — 进化建议
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EvolutionSuggestion:
    """
    一个进化建议（来自 OpenSpace EvolutionSuggestion）
    
    由 LLM 分析执行轨迹后生成
    """
    evolution_type: EvolutionType
    target_skill_ids: List[str]   # 目标技能（FIX=1个，DERIVED=1+，CAPTURED=空）
    category: Optional[SkillCategory] = None  # 期望的结果技能分类
    direction: str = ""          # 自由文本：具体要做什么

    @property
    def primary_target(self) -> str:
        """主目标技能 ID"""
        return self.target_skill_ids[0] if self.target_skill_ids else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.evolution_type.value,
            "target_skills": self.target_skill_ids,
            "primary_target": self.primary_target,
            "category": self.category.value if self.category else None,
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EvolutionSuggestion":
        ev_type = EvolutionType(data["type"])
        cat = None
        if data.get("category"):
            try:
                cat = SkillCategory(data["category"])
            except ValueError:
                pass
        return cls(
            evolution_type=ev_type,
            target_skill_ids=data.get("target_skills", data.get("target_skill_ids", [])),
            category=cat,
            direction=data.get("direction", ""),
        )


# ═══════════════════════════════════════════════════════════════════
# ExecutionAnalysis — 执行分析
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ExecutionAnalysis:
    """
    一次执行的完整分析（来自 OpenSpace ExecutionAnalysis）
    
    由 LLM 分析 action_log.jsonl 后生成
    """
    task_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 任务级判断
    task_completed: bool = False
    execution_note: str = ""
    tool_issues: List[str] = field(default_factory=list)
    
    # 每个判断的元数据
    complexity: str = ""
    checked_dimensions: int = 0
    
    # 进化建议（0-N 个）
    evolution_suggestions: List[EvolutionSuggestion] = field(default_factory=list)
    
    # 分析元数据
    analyzed_by: str = ""  # model name

    @property
    def has_evolution_suggestions(self) -> bool:
        return len(self.evolution_suggestions) > 0

    def suggestions_by_type(self, ev_type: EvolutionType) -> List[EvolutionSuggestion]:
        return [s for s in self.evolution_suggestions if s.evolution_type == ev_type]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "task_completed": self.task_completed,
            "execution_note": self.execution_note,
            "tool_issues": self.tool_issues,
            "complexity": self.complexity,
            "checked_dimensions": self.checked_dimensions,
            "evolution_suggestions": [s.to_dict() for s in self.evolution_suggestions],
            "analyzed_by": self.analyzed_by,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ExecutionAnalysis":
        suggestions = []
        for s in data.get("evolution_suggestions", []):
            try:
                suggestions.append(EvolutionSuggestion.from_dict(s))
            except Exception:
                pass
        return cls(
            task_id=data["task_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            task_completed=data.get("task_completed", False),
            execution_note=data.get("execution_note", ""),
            tool_issues=data.get("tool_issues", []),
            complexity=data.get("complexity", ""),
            checked_dimensions=data.get("checked_dimensions", 0),
            evolution_suggestions=suggestions,
            analyzed_by=data.get("analyzed_by", ""),
        )


# ═══════════════════════════════════════════════════════════════════
# SkillRecord — 完整技能记录
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillRecord:
    """
    完整技能记录（来自 OpenSpace SkillRecord）
    
    包含：身份 + 谱系 + 质量指标
    """
    skill_id: str
    name: str                   # 逻辑技能名（跨版本共享）
    description: str = ""
    path: str = ""               # SKILL.md 路径
    
    # 分类和标签
    category: SkillCategory = SkillCategory.WORKFLOW
    tags: List[str] = field(default_factory=list)
    
    # 进化谱系
    lineage: SkillLineage = field(
        default_factory=lambda: SkillLineage(origin=SkillOrigin.IMPORTED)
    )
    
    # 质量指标
    metrics: SkillMetrics = field(default_factory=SkillMetrics)
    
    # 版本信息
    is_active: bool = True       # 只有最新版本 is_active=True
    version: str = "v1.0"
    fix_version: int = 0         # FIX次数（v{n}，每次FIX递增）
    
    # 元信息
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "category": self.category.value,
            "tags": self.tags,
            "lineage": self.lineage.to_dict(),
            "metrics": self.metrics.to_dict(),
            "is_active": self.is_active,
            "version": self.version,
            "fix_version": self.fix_version,  # V2: 保存FIX版本
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SkillRecord":
        lineage_data = data.get("lineage", {})
        metrics_data = data.get("metrics", {})
        cat = SkillCategory.WORKFLOW
        if data.get("category"):
            try:
                cat = SkillCategory(data["category"])
            except ValueError:
                pass
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            description=data.get("description", ""),
            path=data.get("path", ""),
            category=cat,
            tags=data.get("tags", []),
            lineage=SkillLineage.from_dict(lineage_data) if lineage_data else SkillLineage(origin=SkillOrigin.IMPORTED),
            metrics=SkillMetrics.from_dict(metrics_data) if metrics_data else SkillMetrics(),
            is_active=data.get("is_active", True),
            version=data.get("version", "v1.0"),
            fix_version=data.get("fix_version", 0),  # V2: 读取FIX版本
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
        )
