# -*- coding: utf-8 -*-
"""
skill_evolution — OpenSpace 风格技能进化系统（qclaw 版）

来源：HKUDS/OpenSpace skill_engine/

包含：
- types.py: EvolutionType, SkillLineage, SkillMetrics, SkillRecord
- registry.py: SkillRegistry — 发现和管理 qclaw 技能
- evolver.py: SkillEvolver — 三种进化模式（CAPTURED / DERIVED / FIX）
- integrate.py: evolver.py ↔ skill_evolution 集成

用法：
```python
from skill_evolution import (
    SkillRegistry, SkillEvolver, EvolutionType,
    sync_to_registry, suggest_from_evolver,
)

# 发现 qclaw 技能
registry = SkillRegistry()

# 从 evolver 经验同步
sync_to_registry()

# 从 evolver 经验生成进化建议
suggestions = suggest_from_evolver()

# 执行进化
evolver = SkillEvolver()
result = evolver.evolve("task description", EvolutionType.CAPTURED)
```
"""

from .types import (
    EvolutionType, SkillOrigin, SkillCategory,
    SkillLineage, SkillMetrics, SkillRecord,
    EvolutionSuggestion, ExecutionAnalysis,
)
from .registry import SkillRegistry
from .evolver import SkillEvolver
from .integrate import (
    evolver_to_skill_metrics,
    sync_to_registry,
    suggest_from_evolver,
    skill_to_evolver_rule,
)

__all__ = [
    # Types
    "EvolutionType", "SkillOrigin", "SkillCategory",
    "SkillLineage", "SkillMetrics", "SkillRecord",
    "EvolutionSuggestion", "ExecutionAnalysis",
    # Core
    "SkillRegistry",
    "SkillEvolver",
    # Integration
    "evolver_to_skill_metrics",
    "sync_to_registry",
    "suggest_from_evolver",
    "skill_to_evolver_rule",
]
