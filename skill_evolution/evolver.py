# -*- coding: utf-8 -*-
"""
skill_evolution/evolver.py — qclaw 技能进化引擎（对齐 OpenSpace）

来源：HKUDS/OpenSpace skill_engine/evolver.py

核心功能：
- 从 evolver.py 的成功经验 → 生成新技能
- 三种进化模式：CAPTURED / DERIVED / FIX
- 与 patch.py 联动：fix_skill / derive_skill / create_skill
- 写 .skill_id sidecar 文件
- 与 qclaw evolver.py 联动：confidence ≥ 阈值时触发

用法：
  python evolver.py --suggest        # 建议可进化的技能
  python evolver.py --evolve <task>  # 从任务进化
  python evolver.py --fix <skill_id> # 修复技能
"""

import json
import re
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import (
    EvolutionType, SkillOrigin, SkillCategory,
    SkillLineage, SkillMetrics, SkillRecord
)
from .registry import SkillRegistry

WORKSPACE = Path(__file__).parent.parent  # qclaw workspace


# ═══════════════════════════════════════════════════════════════════
# 进化引擎
# ═══════════════════════════════════════════════════════════════════

class SkillEvolver:
    """
    qclaw 技能进化引擎（对齐 OpenSpace evolver.py）
    
    流程：
    1. 分析 evolver.py 的经验记录 → 找高质量方法
    2. 判断进化类型：CAPTURED（全新）/ DERIVED（派生）/ FIX（修复）
    3. 执行进化：patch.py 的 create_skill / derive_skill / fix_skill
    4. 写 .skill_id sidecar
    5. 更新 registry
    """
    
    def __init__(self):
        self.registry = SkillRegistry()
        self.evolver_db = self._load_evolver_db()
        self.evolver_rules = self._load_evolver_rules()
    
    def _load_evolver_db(self) -> Dict:
        """加载 qclaw evolver.py 的经验数据库"""
        db_path = WORKSPACE / ".evolver_db.json"
        if db_path.exists():
            try:
                return json.loads(db_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    
    def _load_evolver_rules(self) -> Dict:
        """加载 evolver 规则"""
        rules_path = WORKSPACE / ".evolver_rules.json"
        if rules_path.exists():
            try:
                return json.loads(rules_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    
    # ═══════════════════════════════════════════════════════════════
    # 进化建议
    # ═══════════════════════════════════════════════════════════════
    
    def suggest_evolutions(self, min_confidence: float = 0.7) -> List[Dict]:
        """
        从 evolver 经验建议可进化的技能
        
        策略：
        1. 从 evolver_db.json 找 confidence ≥ min_confidence 的经验
        2. 检查是否已有对应技能
        3. 分类为 CAPTURED / DERIVED / FIX
        """
        suggestions = []
        
        # 扫描 evolver 经验
        experiences = self.evolver_db.get("experiences", [])
        seen_tasks: Dict[str, Dict] = {}
        
        for exp in experiences:
            task = exp.get("task", "")
            confidence = exp.get("confidence", 0.0)
            
            if confidence < min_confidence:
                continue
            if not task:
                continue
            
            # 取每个任务的最佳经验
            if task not in seen_tasks or confidence > seen_tasks[task]["confidence"]:
                seen_tasks[task] = {
                    "task": task,
                    "method": exp.get("method", ""),
                    "confidence": confidence,
                    "success_count": exp.get("success_count", 1),
                    "error_count": exp.get("error_count", 0),
                    "category": self._categorize_task(task),
                }
        
        # 分类为进化类型
        for task, data in seen_tasks.items():
            skill_id = self._find_similar_skill(task)
            
            if not skill_id:
                # 无相似技能 → CAPTURED
                suggestions.append({
                    "type": EvolutionType.CAPTURED.value,
                    "direction": data["task"],
                    "confidence": data["confidence"],
                    "examples": data["success_count"],
                    "reason": "No similar skill found — capture new pattern",
                })
            elif data["confidence"] < 0.6:
                # 有技能但质量低 → FIX
                suggestions.append({
                    "type": EvolutionType.FIX.value,
                    "skill_id": skill_id,
                    "direction": f"Fix {task}: {data['method']}",
                    "confidence": data["confidence"],
                    "reason": f"Skill {skill_id[:20]}... has low confidence",
                })
            else:
                # 有技能且质量中等 → DERIVED
                suggestions.append({
                    "type": EvolutionType.DERIVED.value,
                    "skill_id": skill_id,
                    "direction": f"Derive from {task}: {data['method']}",
                    "confidence": data["confidence"],
                    "reason": "Improve existing skill with new method",
                })
        
        # 按 confidence 排序
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        return suggestions
    
    def _categorize_task(self, task: str) -> SkillCategory:
        """根据任务关键字分类"""
        task_lower = task.lower()
        
        if any(k in task_lower for k in ["search", "find", "query", "analyze"]):
            return SkillCategory.ANALYSIS
        elif any(k in task_lower for k in ["create", "generate", "write", "make", "build"]):
            return SkillCategory.GENERATION
        elif any(k in task_lower for k in ["install", "setup", "config", "run"]):
            return SkillCategory.TOOL
        elif any(k in task_lower for k in ["orchestrate", "coordinate", "manage", "plan"]):
            return SkillCategory.ORCHESTRATION
        else:
            return SkillCategory.WORKFLOW
    
    def _find_similar_skill(self, task: str) -> Optional[str]:
        """在 registry 中找相似技能"""
        task_words = set(re.findall(r"\w+", task.lower()))
        if not task_words:
            return None
        
        best_match = None
        best_score = 0
        
        for skill in self.registry.get_all_skills():
            skill_words = set(re.findall(r"\w+", skill.name.lower()))
            if not skill_words:
                continue
            
            overlap = len(task_words & skill_words)
            score = overlap / len(task_words | skill_words)
            
            if score > 0.3 and score > best_score:
                best_score = score
                best_match = skill.skill_id
        
        return best_match
    
    # ═══════════════════════════════════════════════════════════════
    # 执行进化
    # ═══════════════════════════════════════════════════════════════
    
    def evolve(
        self,
        direction: str,
        evolution_type: EvolutionType,
        source_skill_id: Optional[str] = None,
        content: str = "",
        category: SkillCategory = SkillCategory.WORKFLOW,
    ) -> Dict[str, Any]:
        """
        执行技能进化（对齐 OpenSpace evolver.py）
        
        1. CAPTURED: create_skill — 全新技能，从方向生成
        2. DERIVED: derive_skill — 从现有技能派生
        3. FIX: fix_skill — 修复现有技能
        
        Returns: {ok, skill_id, skill_name, lineage, error}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if evolution_type == EvolutionType.CAPTURED:
            return self._evolve_captured(direction, content, category, timestamp)
        
        elif evolution_type == EvolutionType.DERIVED:
            if not source_skill_id:
                return {"ok": False, "error": "DERIVED requires source_skill_id"}
            return self._evolve_derived(direction, source_skill_id, content, category, timestamp)
        
        elif evolution_type == EvolutionType.FIX:
            if not source_skill_id:
                return {"ok": False, "error": "FIX requires source_skill_id"}
            return self._evolve_fix(direction, source_skill_id, content, timestamp)
        
        return {"ok": False, "error": f"Unknown evolution type: {evolution_type}"}
    
    def _evolve_captured(
        self,
        direction: str,
        content: str,
        category: SkillCategory,
        timestamp: str,
    ) -> Dict[str, Any]:
        """CAPTURED: 创建全新技能（根节点）"""
        # 生成 skill_id
        name = self._direction_to_name(direction)
        skill_id = self._generate_skill_id(name, SkillOrigin.CAPTURED, fix_version=0)
        
        # 创建 lineage
        lineage = SkillLineage(
            origin=SkillOrigin.CAPTURED,
            generation=0,
            parent_skill_ids=[],
            source_task_id=f"captured:{timestamp}",
            change_summary=f"Captured from: {direction[:100]}",
            content_diff="",
            content_snapshot={},
        )
        
        # 注册到 registry
        reg_id = self.registry.register_skill(
            name=name,
            origin=SkillOrigin.CAPTURED,
            description=direction,
            lineage=lineage,
            metrics=SkillMetrics(
                confidence=0.5,  # 新技能，初始 confidence 0.5
                total_selections=0,
            ),
        )
        
        return {
            "ok": True,
            "skill_id": reg_id,
            "skill_name": name,
            "evolution_type": EvolutionType.CAPTURED.value,
            "generation": 0,
            "fix_version": 0,
            "lineage": lineage.to_dict(),
            "reason": "New skill captured from execution pattern",
        }
    
    def _evolve_derived(
        self,
        direction: str,
        source_skill_id: str,
        content: str,
        category: SkillCategory,
        timestamp: str,
    ) -> Dict[str, Any]:
        """DERIVED: 从现有技能派生（新目录）"""
        source = self.registry.get_skill(source_skill_id)
        if not source:
            return {"ok": False, "error": f"Source skill not found: {source_skill_id}"}
        
        # 生成新 skill_id
        name = f"{source.name}-derived"
        skill_id = self._generate_skill_id(name, SkillOrigin.DERIVED, fix_version=0)
        
        # lineage: generation = parent + 1
        new_gen = (source.lineage.generation if source.lineage else 0) + 1
        lineage = SkillLineage(
            origin=SkillOrigin.DERIVED,
            generation=new_gen,
            parent_skill_ids=[source_skill_id],
            source_task_id=f"derived:{timestamp}",
            change_summary=f"Derived from {source_skill_id}: {direction[:100]}",
        )
        
        reg_id = self.registry.register_skill(
            name=name,
            origin=SkillOrigin.DERIVED,
            description=f"{source.description} → {direction}",
            lineage=lineage,
            metrics=SkillMetrics(confidence=0.6),
        )
        
        return {
            "ok": True,
            "skill_id": reg_id,
            "skill_name": name,
            "evolution_type": EvolutionType.DERIVED.value,
            "generation": new_gen,
            "fix_version": 0,
            "parent": source_skill_id,
            "lineage": lineage.to_dict(),
            "reason": f"Derived from {source.name}",
        }
    
    def _evolve_fix(
        self,
        direction: str,
        source_skill_id: str,
        content: str,
        timestamp: str,
    ) -> Dict[str, Any]:
        """FIX: 修复现有技能（同目录，更新内容）"""
        source = self.registry.get_skill(source_skill_id)
        if not source:
            return {"ok": False, "error": f"Source skill not found: {source_skill_id}"}
        
        # FIX: fix_version += 1, generation 不变
        new_fix_v = source.fix_version + 1
        skill_id = self._generate_skill_id(
            source.name, SkillOrigin.FIXED,
            fix_version=new_fix_v,
            parent_skill_id=source_skill_id,
        )
        
        lineage = SkillLineage(
            origin=SkillOrigin.FIXED,
            generation=source.lineage.generation if source.lineage else 0,
            parent_skill_ids=[source_skill_id],
            source_task_id=f"fix:{timestamp}",
            change_summary=f"Fix: {direction[:100]}",
        )
        
        # 停用旧技能
        self.registry.deactivate_skill(source_skill_id)
        
        # 注册新版本
        new_metrics = source.metrics or SkillMetrics()
        new_metrics.confidence = max(0.5, new_metrics.confidence * 1.1)  # 修复后置信度提升
        
        reg_id = self.registry.register_skill(
            name=source.name,
            origin=SkillOrigin.FIXED,
            description=source.description,
            lineage=lineage,
            metrics=new_metrics,
        )
        
        return {
            "ok": True,
            "skill_id": reg_id,
            "skill_name": source.name,
            "evolution_type": EvolutionType.FIX.value,
            "generation": lineage.generation,
            "fix_version": new_fix_v,
            "parent": source_skill_id,
            "lineage": lineage.to_dict(),
            "reason": f"Fixed {source.name} (was {source_skill_id[:20]}...)",
        }
    
    # ═══════════════════════════════════════════════════════════════
    # 工具函数
    # ═══════════════════════════════════════════════════════════════
    
    def _direction_to_name(self, direction: str) -> str:
        """从方向生成技能名"""
        # 提取关键词
        words = re.findall(r"\b[a-z]{3,}\b", direction.lower())
        if not words:
            words = ["skill"]
        
        # 取前 3 个关键词
        name_parts = words[:3]
        name = "-".join(name_parts)
        
        # 长度限制
        if len(name) > 50:
            name = name[:50]
        
        # 添加时间戳避免冲突
        timestamp = datetime.now().strftime("%m%d")
        name = f"{name}-{timestamp}"
        
        return name
    
    def _generate_skill_id(
        self,
        name: str,
        origin: SkillOrigin,
        fix_version: int = 0,
        parent_skill_id: str = "",
    ) -> str:
        """生成 skill_id（对齐 OpenSpace）"""
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)[:50]

        if origin == SkillOrigin.CAPTURED:
            suffix = uuid.uuid4().hex[:8]
            return f"{safe_name}__v0_{suffix}"
        elif origin == SkillOrigin.DERIVED:
            suffix = uuid.uuid4().hex[:8]
            return f"{safe_name}__v0_{suffix}"
        elif origin == SkillOrigin.FIXED:
            # FIX：复用父节点 hash
            if parent_skill_id:
                parts = parent_skill_id.split("__")
                parent_hash = parts[-1].split("_")[-1] if "_" in parts[-1] else uuid.uuid4().hex[:8]
            else:
                parent_hash = uuid.uuid4().hex[:8]
            fix_str = f"v{fix_version}"
            return f"{safe_name}__{fix_str}_{parent_hash}"
        else:
            suffix = uuid.uuid4().hex[:8]
            return f"{safe_name}__imp_{suffix}"
    
    def get_dag(self) -> Dict[str, Any]:
        """获取 Version DAG"""
        return self.registry.get_dag()
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计"""
        return self.registry.stats()


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="qclaw SkillEvolver")
    parser.add_argument("--suggest", action="store_true", help="Suggest evolution targets")
    parser.add_argument("--evolve", metavar="TASK", help="Evolve from task direction")
    parser.add_argument("--fix", metavar="SKILL_ID", help="Fix existing skill")
    parser.add_argument("--type", choices=["captured", "derived", "fix"], default="captured")
    parser.add_argument("--min-confidence", type=float, default=0.7)
    args = parser.parse_args()
    
    evolver = SkillEvolver()
    
    if args.suggest:
        print("\n=== Evolution Suggestions ===")
        suggestions = evolver.suggest_evolutions(min_confidence=args.min_confidence)
        if not suggestions:
            print("  No suggestions (try lower --min-confidence)")
        for i, s in enumerate(suggestions[:10], 1):
            print(f"\n  [{i}] {s['type'].upper()}")
            print(f"      direction: {s.get('direction', s.get('skill_id', ''))}")
            print(f"      confidence: {s['confidence']:.3f}")
            print(f"      reason: {s['reason']}")
    
    elif args.evolve:
        print(f"\n=== Evolving: {args.evolve} ===")
        ev_type = EvolutionType(args.type)
        result = evolver.evolve(
            direction=args.evolve,
            evolution_type=ev_type,
        )
        if result["ok"]:
            print(f"  OK: {result['skill_id']}")
            print(f"  name: {result['skill_name']}")
            print(f"  type: {result['evolution_type']}")
            print(f"  gen={result['generation']}, fix_v={result['fix_version']}")
        else:
            print(f"  ERROR: {result['error']}")
    
    elif args.fix:
        print(f"\n=== Fixing: {args.fix} ===")
        result = evolver.evolve(
            direction=f"Fix skill {args.fix}",
            evolution_type=EvolutionType.FIX,
            source_skill_id=args.fix,
        )
        if result["ok"]:
            print(f"  OK: {result['skill_id']}")
            print(f"  fix_version: {result['fix_version']}")
            print(f"  parent (deactivated): {result['parent']}")
        else:
            print(f"  ERROR: {result['error']}")
    
    else:
        stats = evolver.get_stats()
        print(f"\n=== SkillEvolver Stats ===")
        print(f"  Skills: {stats['total']} total, {stats['active']} active")
        print(f"  By origin: {stats['by_origin']}")
        print(f"\n  Usage: --suggest | --evolve TASK | --fix SKILL_ID")
