# -*- coding: utf-8 -*-
"""
skill_evolution/integrate.py — evolver.py ↔ skill_evolution 集成

融会贯通：把 OpenSpace 的 skill self-evolution 接入 qclaw 的 evolver 闭环

核心打通：
evolver.record()  →  skill_registry.update_metrics()
confidence ≥ 0.7  →  skill_evolver.evolve()
evolution_types →  融入 evolver_types

来源：HKUDS/OpenSpace + qclaw evolver.py v2.2
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

WORKSPACE = Path(__file__).parent.parent  # qclaw workspace

# ── 集成点 1: evolver.py 调用 skill_evolution ─────────────────────

def evolver_to_skill_metrics(evolver_db_path: Path) -> list:
    """
    从 evolver.py 的经验数据库，提取技能级质量指标

    evolver_db.json 格式：
      {rules: [{id, task, method, success_count, total_count, priority, is_active, ...}]}

    skill 指标：{total_selections, completions, fallbacks, confidence}

    策略：
    - success_count → completions
    - (total_count - success_count) → fallbacks
    - confidence 按 evolver.py 公式计算：
        base = success_rate
        confidence = base * (0.7 + 0.2*sample_weight + 0.1*priority_weight)
    - confidence ≥ 0.7 → total_selections
    """
    if not evolver_db_path.exists():
        return []

    try:
        db = json.loads(evolver_db_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    rules = db.get("rules", [])
    if not rules:
        return []

    metrics = []
    for rule in rules:
        task = rule.get("task", "")
        method = rule.get("method", "")
        sc = rule.get("success_count", 0)
        tc = rule.get("total_count", 0)
        priority = rule.get("priority", 0)

        completions = sc
        fallbacks = tc - sc
        success_rate = sc / tc if tc > 0 else 0.0

        # evolver.py 的 confidence 公式
        sample_weight = min(tc / 10, 1.0)
        priority_weight = (priority + 1) / 10
        confidence = success_rate * (0.7 + 0.2 * sample_weight + 0.1 * priority_weight)

        metrics.append({
            "task": task,
            "method": method,
            "total_selections": completions if confidence >= 0.7 else 0,
            "applied_count": tc,
            "completions": completions,
            "fallbacks": fallbacks,
            "effective_rate": success_rate,
            "confidence": round(confidence, 3),
            "success_rate": round(success_rate, 3),
        })

    return metrics


def sync_to_registry():
    """
    同步 evolver 经验 → skill_registry
    
    从 evolver_db.json 读取经验 → 更新每个技能的 metrics
    confidence ≥ 0.7 的经验 → 标记为可进化
    """
    # 延迟导入避免循环
    from . import SkillRegistry, SkillEvolver, EvolutionType
    
    evolver_db_path = WORKSPACE / ".evolver_db.json"
    skill_metrics = evolver_to_skill_metrics(evolver_db_path)
    
    if not skill_metrics:
        return {"ok": True, "synced": 0, "message": "No experiences to sync"}
    
    registry = SkillRegistry()
    synced = 0
    candidates = []
    
    for m in skill_metrics:
        # 找相似技能
        task = m["task"]
        method = m["method"]
        confidence = m["confidence"]
        
        # 在 registry 中找 task 关键字相似的技能
        skill_id = _find_skill_by_task(registry, task)
        
        if skill_id:
            # 更新已有技能
            registry.update_metrics(
                skill_id,
                total_selections=m["total_selections"],
                applied_count=m["applied_count"],
                completions=m["completions"],
                fallbacks=m["fallbacks"],
                confidence=m["confidence"],
            )
            synced += 1
        elif confidence >= 0.7:
            # 无相似技能且 confidence 高 → 候选进化
            candidates.append({
                "task": task,
                "method": method,
                "confidence": confidence,
                "effective_rate": m["effective_rate"],
            })
    
    return {
        "ok": True,
        "synced": synced,
        "candidates": candidates,
        "message": f"Synced {synced} skills, {len(candidates)} evolution candidates",
    }


def _find_skill_by_task(registry, task: str) -> Optional[str]:
    """从 task 关键字找 registry 中的相似技能"""
    import re
    task_words = set(re.findall(r"\w{3,}", task.lower()))
    if not task_words:
        return None
    
    best_score = 0
    best_id = None
    
    for skill in registry.get_all_skills():
        skill_words = set(re.findall(r"\w{3,}", skill.name.lower()))
        if not skill_words:
            continue
        
        overlap = len(task_words & skill_words)
        score = overlap / len(task_words | skill_words)
        
        if score > 0.25 and score > best_score:
            best_score = score
            best_id = skill.skill_id
    
    return best_id


# ── 集成点 2: evolver 的进化触发 ──────────────────────────────────

def suggest_from_evolver(min_confidence: float = 0.7) -> list:
    """
    从 evolver 经验生成进化建议
    与 evolver.py 的 recall 联动
    """
    evolver_db_path = WORKSPACE / ".evolver_db.json"
    skill_metrics = evolver_to_skill_metrics(evolver_db_path)
    
    suggestions = []
    for m in skill_metrics:
        if m["confidence"] < min_confidence:
            continue
        
        suggestions.append({
            "type": "captured" if m["applied_count"] < 5 else "fix",
            "direction": f"{m['task']}: {m['method']}",
            "confidence": m["confidence"],
            "effective_rate": m["effective_rate"],
            "reason": f"confidence={m['confidence']:.2f}, effective_rate={m['effective_rate']:.2f}",
        })
    
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    return suggestions


# ── 集成点 3: skill_evolution → evolver 的 feedback ───────────────

def skill_to_evolver_rule(skill_record) -> dict:
    """
    把 skill_record 转为 evolver.py 的规则格式
    
    用于：skill 注册后 → 自动写入 evolver rules
    """
    if not skill_record:
        return {}
    
    rule = {
        "task_pattern": skill_record.name.replace("-", " "),
        "method": f"skill:{skill_record.skill_id}",
        "confidence": skill_record.metrics.confidence if skill_record.metrics else 0.5,
        "origin": "skill_evolution",
        "skill_id": skill_record.skill_id,
        "skill_category": skill_record.category.value if skill_record.category else "workflow",
    }
    return rule


# ── 集成点 4: qclaw evolver.py 的工具观察 → skill 指标 ──────────

def tool_to_skill_metric(tool_name: str, outcome: str) -> dict:
    """
    把单次工具调用转为 skill 级指标更新
    
    用于：ToolObserver 观察 → skill_registry 联动
    """
    return {
        "tool": tool_name,
        "outcome": outcome,  # "success" | "failure"
        "timestamp": datetime.now().isoformat(),
    }


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="evolver ↔ skill_evolution 集成")
    parser.add_argument("--sync", action="store_true", help="同步 evolver → registry")
    parser.add_argument("--suggest", action="store_true", help="从 evolver 经验建议进化")
    parser.add_argument("--min-confidence", type=float, default=0.7)
    args = parser.parse_args()
    
    if args.sync:
        result = sync_to_registry()
        print(f"\n=== Sync Result ===")
        print(f"  OK: {result['ok']}")
        print(f"  Synced: {result['synced']}")
        print(f"  Candidates: {len(result['candidates'])}")
        for c in result["candidates"][:5]:
            print(f"    [{c['type']}] conf={c['confidence']:.2f} {c['direction'][:50]}")
    
    elif args.suggest:
        suggestions = suggest_from_evolver(min_confidence=args.min_confidence)
        print(f"\n=== Evolution Suggestions from evolver ===")
        print(f"  Total: {len(suggestions)}")
        for s in suggestions[:10]:
            print(f"  [{s['type']}] conf={s['confidence']:.2f} {s['direction'][:50]}")
    
    else:
        print("Usage: --sync | --suggest [--min-confidence 0.7]")
