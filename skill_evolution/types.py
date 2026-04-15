# -*- coding: utf-8 -*-
"""
skill_evolution/types.py — OpenSpace 风格技能类型系统（适配 qclaw）

来自 HKUDS/OpenSpace skill_engine/types.py

核心类型：
- EvolutionType: FIX / DERIVED / CAPTURED 三种进化模式
- SkillOrigin: IMPORTED / CAPTURED / DERIVED / FIXED 技能来源
- SkillLineage: 技能谱系（Version DAG 节点）
- SkillMetrics: 技能质量指标（qclaw 适配版）
- ExecutionAnalysis: 执行分析（对话压缩后输入 LLM）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# 进化类型（对齐 OpenSpace）
# ═══════════════════════════════════════════════════════════════════

class EvolutionType(str, Enum):
    """
    三种进化模式（来自 OpenSpace evolver.py）
    
    FIX     — 修复：同名同路径，generation=父+1，fix_version递增
    DERIVED — 派生：新名字新目录，1+父节点，generation=max(父)+1
    CAPTURED — 捕获：全新技能，无父节点，generation=0
    """
    FIX = "fix"
    DERIVED = "derived"
    CAPTURED = "captured"


class SkillOrigin(str, Enum):
    """
    技能来源（来自 OpenSpace registry.py）
    
    区分技能的初始来源和进化来源
    """
    IMPORTED = "imported"    # 手动导入
    CAPTURED = "captured"   # 从执行轨迹捕获
    DERIVED = "derived"     # 从现有技能派生
    FIXED = "fixed"         # 从现有技能修复


class SkillCategory(str, Enum):
    """技能分类"""
    WORKFLOW = "workflow"   # 工作流
    TOOL = "tool"           # 工具封装
    ANALYSIS = "analysis"    # 分析技能
    GENERATION = "generation"  # 生成技能
    ORCHESTRATION = "orchestration"  # 编排技能


# ═══════════════════════════════════════════════════════════════════
# 谱系（对齐 OpenSpace SkillLineage）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillLineage:
    """
    技能谱系（Version DAG 节点，来自 OpenSpace types.py）
    
    记录技能的进化历史和父子关系
    
    generation = DERIVED 深度（从根往下数）
    fix_version = FIX 次数（每次修复递增，编码进 skill_id）
    
    示例：
    CAPTURED: generation=0, parent=[]
    DERIVED:  generation=1, parent=[cap_xxx]
    FIX:      generation=1, parent=[drv_xxx], fix_version += 1
    """
    origin: SkillOrigin
    generation: int = 0
    parent_skill_ids: List[str] = field(default_factory=list)
    source_task_id: str = ""
    change_summary: str = ""
    content_diff: str = ""        # git diff 格式
    content_snapshot: Dict[str, str] = field(default_factory=dict)
    created_by: str = "skill_evolution"
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin.value,
            "generation": self.generation,
            "parent_skill_ids": self.parent_skill_ids,
            "source_task_id": self.source_task_id,
            "change_summary": self.change_summary,
            "content_diff": self.content_diff,
            "content_snapshot": self.content_snapshot,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillLineage":
        origin = SkillOrigin(data.get("origin", "imported"))
        return cls(
            origin=origin,
            generation=data.get("generation", 0),
            parent_skill_ids=data.get("parent_skill_ids", []),
            source_task_id=data.get("source_task_id", ""),
            change_summary=data.get("change_summary", ""),
            content_diff=data.get("content_diff", ""),
            content_snapshot=data.get("content_snapshot", {}),
            created_by=data.get("created_by", "skill_evolution"),
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at") else datetime.now(),
        )


# ═══════════════════════════════════════════════════════════════════
# 质量指标（qclaw 适配版）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillMetrics:
    """
    技能质量指标（来自 OpenSpace SkillRecord.metrics）
    
    qclaw 适配：
    - 用 evolver.py 的 confidence 代替 OpenSpace 的轨迹分析
    - 保留核心指标：selections, completions, fallbacks
    """
    # 基础指标
    total_selections: int = 0       # 被选为最佳方法的次数
    applied_count: int = 0          # 实际应用的次数
    completions: int = 0            # 成功完成的次数
    fallbacks: int = 0              # 回退到其他方法的次数
    
    # 计算指标
    applied_rate: float = 0.0       # applied_count / total_selections
    completion_rate: float = 0.0    # completions / applied_count
    effective_rate: float = 0.0     # completions / total_selections
    fallback_rate: float = 0.0      # fallbacks / applied_count
    
    # qclaw 特有
    confidence: float = 0.0         # evolver 的置信度（0-1）
    examples: List[Dict] = field(default_factory=list)  # 成功案例
    last_used: Optional[str] = None  # 上次使用时间
    
    def update_rates(self):
        """更新计算指标"""
        if self.total_selections > 0:
            self.applied_rate = self.applied_count / self.total_selections
            self.effective_rate = self.completions / self.total_selections
        if self.applied_count > 0:
            self.completion_rate = self.completions / self.applied_count
            self.fallback_rate = self.fallbacks / self.applied_count
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_selections": self.total_selections,
            "applied_count": self.applied_count,
            "completions": self.completions,
            "fallbacks": self.fallbacks,
            "applied_rate": round(self.applied_rate, 3),
            "completion_rate": round(self.completion_rate, 3),
            "effective_rate": round(self.effective_rate, 3),
            "fallback_rate": round(self.fallback_rate, 3),
            "confidence": round(self.confidence, 3),
            "examples": self.examples[-10:],  # 保留最近10条
            "last_used": self.last_used,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillMetrics":
        examples = data.get("examples", [])
        if isinstance(examples, list) and examples and isinstance(examples[0], dict):
            examples = examples
        return cls(
            total_selections=data.get("total_selections", 0),
            applied_count=data.get("applied_count", 0),
            completions=data.get("completions", 0),
            fallbacks=data.get("fallbacks", 0),
            applied_rate=data.get("applied_rate", 0.0),
            completion_rate=data.get("completion_rate", 0.0),
            effective_rate=data.get("effective_rate", 0.0),
            fallback_rate=data.get("fallback_rate", 0.0),
            confidence=data.get("confidence", 0.0),
            examples=examples,
            last_used=data.get("last_used"),
        )


# ═══════════════════════════════════════════════════════════════════
# 技能记录
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillRecord:
    """
    技能记录（qclaw 版本）
    
    对齐 OpenSpace SkillRecord，适配 qclaw 的 evolver 系统
    """
    skill_id: str
    name: str
    description: str = ""
    path: str = ""
    category: SkillCategory = SkillCategory.WORKFLOW
    lineage: Optional[SkillLineage] = None
    metrics: Optional[SkillMetrics] = None
    is_active: bool = True
    version: str = "v1.0"
    fix_version: int = 0
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "category": self.category.value,
            "lineage": self.lineage.to_dict() if self.lineage else {},
            "metrics": self.metrics.to_dict() if self.metrics else {},
            "is_active": self.is_active,
            "version": self.version,
            "fix_version": self.fix_version,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillRecord":
        lineage_data = data.get("lineage", {})
        metrics_data = data.get("metrics", {})
        lineage = SkillLineage.from_dict(lineage_data) if lineage_data else None
        metrics = SkillMetrics.from_dict(metrics_data) if metrics_data else None
        cat = SkillCategory(data.get("category", "workflow"))
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            description=data.get("description", ""),
            path=data.get("path", ""),
            category=cat,
            lineage=lineage,
            metrics=metrics,
            is_active=data.get("is_active", True),
            version=data.get("version", "v1.0"),
            fix_version=data.get("fix_version", 0),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at") else datetime.now(),
        )


# ═══════════════════════════════════════════════════════════════════
# 执行分析（qclaw 适配版）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EvolutionSuggestion:
    """
    进化建议（来自 OpenSpace EvolutionSuggestion）
    
    由 LLM 分析执行轨迹后生成
    """
    evolution_type: EvolutionType
    target_skill_ids: List[str] = field(default_factory=list)
    direction: str = ""        # 进化方向描述
    category: SkillCategory = SkillCategory.WORKFLOW
    confidence: float = 0.5     # LLM 对此建议的置信度
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "evolution_type": self.evolution_type.value,
            "target_skill_ids": self.target_skill_ids,
            "direction": self.direction,
            "category": self.category.value,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "EvolutionSuggestion":
        ev_type = EvolutionType(data.get("evolution_type", "captured"))
        cat = SkillCategory(data.get("category", "workflow"))
        return cls(
            evolution_type=ev_type,
            target_skill_ids=data.get("target_skill_ids", []),
            direction=data.get("direction", ""),
            category=cat,
            confidence=data.get("confidence", 0.5),
        )


@dataclass
class ExecutionAnalysis:
    """
    执行分析结果（来自 OpenSpace ExecutionAnalysis）
    
    用于 LLM 分析的对话上下文，由 conversation_formatter 生成
    """
    task_completed: bool = False
    execution_note: str = ""
    tool_issues: List[str] = field(default_factory=list)
    skill_judgments: List[Dict] = field(default_factory=list)
    evolution_suggestions: List[EvolutionSuggestion] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_completed": self.task_completed,
            "execution_note": self.execution_note,
            "tool_issues": self.tool_issues,
            "skill_judgments": self.skill_judgments,
            "evolution_suggestions": [s.to_dict() for s in self.evolution_suggestions],
        }
