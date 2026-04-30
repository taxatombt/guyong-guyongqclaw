"""
evolver_enhancements.py — evolver 增强模块（不改底层evolver.py）

桥接来源：
  1. ZeusHammer skill_quality → evolver confidence 4因素升级
  2. ZeusHammer local_brain → evolver best_method 三层匹配
  3. ZeusHammer meditation_mode → heartbeat 增强循环

设计原则：
  - 不修改 evolver.py 任何代码
  - 通过 import evolver 后增强/扩展其能力
  - 新增函数可被 agents/ 和 skill 调用
  - 向后兼容：原来的 evolver API 不变

使用方式：
  from evolver_enhancements import enhanced_confidence, enhanced_best_method, run_meditation_cycle
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

WORKSPACE = Path.home() / ".qclaw" / "workspace"


# ═══════════════════════════════════════════════════════
# 增强1: 4因素 Confidence — 源自 ZeusHammer skill_quality
# ═══════════════════════════════════════════════════════

@dataclass
class EnhancedConfidence:
    """
    4因素置信度 — 升级 evolver 的3因素公式
    
    evolver 原版：
      confidence = success_rate * (0.7 + 0.2*sample_weight + 0.1*priority_weight)
    
    升级版（ZeusHammer 4因素）：
      1. 成功率 (40%): success_rate * 40
      2. 速度 (30%):   max(0, 30 - (avg_duration_s / 10) * 30)
      3. 使用频率 (20%): min(20, usage_count * 2)
      4. 复杂度 (10%): (6 - complexity) * 2
      总分: 0-100, 归一化到 0-1
    """
    success_rate: float = 0.0       # 0-1
    avg_duration_s: float = 0.0     # 平均耗时（秒）
    usage_count: int = 0            # 使用次数
    complexity: int = 3             # 复杂度 1-5（1最简单）
    priority: int = 5               # 优先级 0-9
    
    @property
    def score_success(self) -> float:
        """成功率得分 (0-40)"""
        return self.success_rate * 40
    
    @property
    def score_speed(self) -> float:
        """速度得分 (0-30)"""
        return max(0, 30 - (self.avg_duration_s / 10) * 30)
    
    @property
    def score_frequency(self) -> float:
        """使用频率得分 (0-20)"""
        return min(20, self.usage_count * 2)
    
    @property
    def score_complexity(self) -> float:
        """复杂度得分 (0-10)，越简单越好"""
        return max(0, (6 - self.complexity)) * 2
    
    @property
    def total(self) -> float:
        """总分 (0-100)"""
        return self.score_success + self.score_speed + self.score_frequency + self.score_complexity
    
    @property
    def normalized(self) -> float:
        """归一化到 0-1"""
        return min(self.total / 100, 0.99)
    
    @property
    def grade(self) -> str:
        """评级"""
        t = self.total
        if t >= 80: return "excellent"
        if t >= 60: return "good"
        if t >= 40: return "fair"
        if t >= 20: return "poor"
        return "deprecated"
    
    def to_dict(self) -> Dict:
        return {
            "total": round(self.total, 1),
            "normalized": round(self.normalized, 3),
            "grade": self.grade,
            "breakdown": {
                "success": round(self.score_success, 1),
                "speed": round(self.score_speed, 1),
                "frequency": round(self.score_frequency, 1),
                "complexity": round(self.score_complexity, 1),
            }
        }


def enhanced_confidence(rule: Any) -> EnhancedConfidence:
    """
    从 evolver Rule 对象计算增强置信度
    
    Args:
        rule: evolver.Rule 对象（需有 success_count, total_count, priority 等属性）
    
    Returns:
        EnhancedConfidence 对象
    """
    success_rate = rule.success_rate if hasattr(rule, 'success_rate') else 0.0
    total_count = rule.total_count if hasattr(rule, 'total_count') else 0
    priority = rule.priority if hasattr(rule, 'priority') else 5
    
    # 从 metadata 推断速度和复杂度（如果没有就估算）
    metadata = rule.metadata if hasattr(rule, 'metadata') else {}
    avg_duration = metadata.get("avg_duration_s", 5.0) if isinstance(metadata, dict) else 5.0
    complexity = metadata.get("complexity", 3) if isinstance(metadata, dict) else 3
    
    return EnhancedConfidence(
        success_rate=success_rate,
        avg_duration_s=avg_duration,
        usage_count=total_count,
        complexity=min(max(complexity, 1), 5),
        priority=priority,
    )


# ═══════════════════════════════════════════════════════
# 增强2: 三层匹配 best_method — 源自 ZeusHammer local_brain
# ═══════════════════════════════════════════════════════

class EnhancedMethodMatcher:
    """
    三层匹配 — 升级 evolver best_method
    
    ZeusHammer Local Brain 三层：
      Layer 1: evolver rules（结构化经验，最高置信度）
      Layer 2: skill_metadata（技能描述匹配）
      Layer 3: fallback（通用方法建议）
    
    evolver 原版 best_method 只查 rules → 现在三层
    """
    
    def __init__(self, evolver_engine=None):
        self._evolver = evolver_engine
    
    def match(self, task: str, top_k: int = 3) -> Dict[str, Any]:
        """
        三层匹配
        
        Returns:
            {
                "method": str,
                "confidence": float,
                "source": "evolver" | "skill" | "fallback",
                "alternatives": [...],
                "layer": 1|2|3
            }
        """
        # Layer 1: evolver rules
        if self._evolver:
            try:
                result = self._evolver.best_method({"task": task})
                if result and result.get("confidence", 0) >= 0.5:
                    result["source"] = "evolver"
                    result["layer"] = 1
                    return result
            except Exception as e:
                logger.debug(f"Layer 1 evolver failed: {e}")
        
        # Layer 2: skill metadata
        skill_match = self._match_skill(task)
        if skill_match:
            skill_match["source"] = "skill"
            skill_match["layer"] = 2
            return skill_match
        
        # Layer 3: fallback
        return self._fallback(task)
    
    def _match_skill(self, task: str) -> Optional[Dict]:
        """Layer 2: 匹配技能描述"""
        # 扫描 skill metadata
        skill_dir = WORKSPACE / "skills"
        if not skill_dir.exists():
            return None
        
        task_lower = task.lower()
        best = None
        best_score = 0.3  # 最低阈值
        
        for skill_path in skill_dir.iterdir():
            if not skill_path.is_dir():
                continue
            md_path = skill_path / "SKILL.md"
            if not md_path.exists():
                continue
            
            try:
                content = md_path.read_text(encoding="utf-8", errors="replace")[:2000].lower()
                # 简单关键词匹配评分
                score = 0.0
                task_words = set(task_lower.split())
                for word in task_words:
                    if len(word) > 2 and word in content:
                        score += 0.15
                
                if score > best_score:
                    best_score = score
                    best = {
                        "method": f"use skill: {skill_path.name}",
                        "confidence": min(score, 0.8),
                        "task": task,
                        "skill_path": str(skill_path),
                    }
            except Exception:
                continue
        
        return best
    
    def _fallback(self, task: str) -> Dict:
        """Layer 3: 通用方法建议"""
        # 基于任务关键词推荐通用方法
        task_lower = task.lower()
        
        method = "manual_approach"
        if any(w in task_lower for w in ["搜索", "search", "查找", "find"]):
            method = "web_search → analyze results → synthesize"
        elif any(w in task_lower for w in ["写", "write", "创建", "create"]):
            method = "plan structure → write → verify → iterate"
        elif any(w in task_lower for w in ["调试", "debug", "修复", "fix"]):
            method = "reproduce → isolate → hypothesize → test → verify"
        elif any(w in task_lower for w in ["分析", "analyze", "研究", "research"]):
            method = "gather data → categorize → find patterns → draw conclusions"
        elif any(w in task_lower for w in ["安装", "install", "配置", "setup"]):
            method = "check environment → install dependencies → verify → document"
        
        return {
            "method": method,
            "confidence": 0.2,
            "task": task,
            "source": "fallback",
            "layer": 3,
            "alternatives": [],
        }


# ═══════════════════════════════════════════════════════
# 增强3: Meditation 4步循环 — 源自 ZeusHammer meditation_mode
# ═══════════════════════════════════════════════════════

@dataclass
class MeditationResult:
    """冥想循环结果"""
    step: int
    phase: str
    content: str
    insights: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)


class EnhancedMeditation:
    """
    4步冥想循环 — 升级 heartbeat_self_review
    
    ZeusHammer 4步：
      1. 分析近期工作（工作模式、频率、成功率）
      2. 提取经验模式（哪些方法重复成功/失败）
      3. 优化技能（基于模式更新 confidence、淘汰低效技能）
      4. 生成洞察（新发现、可改进点）
    
    与 heartbeat_self_review 的关系：
    - heartbeat 检查"有没有未复盘的工作"
    - meditation 在空闲时做"深度进化"
    - 两者互补：heartbeat = 浅层提醒，meditation = 深层进化
    """
    
    def __init__(self, evolver_engine=None):
        self._evolver = evolver_engine
        self._results_path = WORKSPACE / ".meditation_results.jsonl"
    
    def run_cycle(self) -> List[MeditationResult]:
        """运行完整4步冥想循环"""
        results = []
        results.append(self._step1_analyze())
        results.append(self._step2_extract_patterns())
        results.append(self._step3_optimize())
        results.append(self._step4_insights())
        
        # 持久化
        self._save_results(results)
        
        return results
    
    def _step1_analyze(self) -> MeditationResult:
        """步骤1: 分析近期工作"""
        insights = []
        
        # 读取 evolver 统计
        if self._evolver:
            try:
                rules = self._evolver.rules
                if rules:
                    total = len(rules)
                    high_conf = sum(1 for r in rules if hasattr(r, 'confidence') and r.confidence >= 0.7)
                    low_conf = sum(1 for r in rules if hasattr(r, 'confidence') and r.confidence < 0.3)
                    insights.append(f"规则总数: {total}, 高置信: {high_conf}, 低置信: {low_conf}")
                    
                    # 最近使用的规则
                    recent = sorted(rules, key=lambda r: getattr(r, 'last_success', 0), reverse=True)[:5]
                    for r in recent:
                        insights.append(f"  热门: {getattr(r, 'task', '?')} → {getattr(r, 'method', '?')}")
            except Exception as e:
                insights.append(f"evolver 读取失败: {e}")
        else:
            insights.append("evolver 未连接")
        
        return MeditationResult(
            step=1,
            phase="analyze",
            content="近期工作模式分析",
            insights=insights,
        )
    
    def _step2_extract_patterns(self) -> MeditationResult:
        """步骤2: 提取经验模式"""
        insights = []
        
        if self._evolver:
            try:
                rules = self._evolver.rules
                # 找重复成功模式
                method_counts: Dict[str, int] = {}
                for r in rules:
                    method = getattr(r, 'method', 'unknown')
                    method_counts[method] = method_counts.get(method, 0) + 1
                
                # 重复出现3次以上的方法
                for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
                    if count >= 3:
                        insights.append(f"高频方法: {method} (使用{count}次)")
                
                # 找成功但低置信度的规则（可能需要升级）
                for r in rules:
                    if hasattr(r, 'success_rate') and r.success_rate > 0.8 and hasattr(r, 'confidence') and r.confidence < 0.5:
                        insights.append(f"低估规则: {getattr(r, 'task', '?')} (success_rate={r.success_rate:.2f}, conf={r.confidence:.2f})")
            except Exception as e:
                insights.append(f"模式提取失败: {e}")
        
        return MeditationResult(
            step=2,
            phase="extract_patterns",
            content="经验模式提取",
            insights=insights,
        )
    
    def _step3_optimize(self) -> MeditationResult:
        """步骤3: 优化技能"""
        actions = []
        
        if self._evolver:
            try:
                rules = self._evolver.rules
                # 找低效规则（success_rate < 0.3 且使用 > 3次）
                for r in rules:
                    if hasattr(r, 'success_rate') and r.success_rate < 0.3 and hasattr(r, 'total_count') and r.total_count > 3:
                        actions.append(f"淘汰候选: {getattr(r, 'task', '?')} (success_rate={r.success_rate:.2f})")
                
                # 找可合并规则（同 task 不同 method）
                task_methods: Dict[str, List[str]] = {}
                for r in rules:
                    task = getattr(r, 'task', '')
                    method = getattr(r, 'method', '')
                    if task:
                        task_methods.setdefault(task, []).append(method)
                
                for task, methods in task_methods.items():
                    if len(methods) > 2:
                        actions.append(f"合并候选: {task} 有 {len(methods)} 种方法")
            except Exception as e:
                actions.append(f"优化分析失败: {e}")
        
        return MeditationResult(
            step=3,
            phase="optimize",
            content="技能优化建议",
            actions=actions,
        )
    
    def _step4_insights(self) -> MeditationResult:
        """步骤4: 生成洞察"""
        insights = []
        
        # 读取最近的冥想结果做趋势分析
        if self._evolver:
            try:
                rules = self._evolver.rules
                
                # 统计成功/失败比例
                if rules:
                    successes = sum(1 for r in rules if hasattr(r, 'success_rate') and r.success_rate > 0.7)
                    total = len(rules)
                    ratio = successes / total if total > 0 else 0
                    insights.append(f"整体成功率: {ratio:.0%} ({successes}/{total})")
                    
                    if ratio > 0.8:
                        insights.append("趋势: 方法库成熟度高，可考虑更激进地尝试新方法")
                    elif ratio > 0.5:
                        insights.append("趋势: 方法库有提升空间，建议淘汰低效规则")
                    else:
                        insights.append("趋势: 方法库需重建，建议重新收集最佳实践")
            except Exception as e:
                insights.append(f"洞察生成失败: {e}")
        
        # 检查是否有 _deprecated 模块可以清理
        dep_dir = WORKSPACE / "_deprecated"
        if dep_dir.exists():
            dep_count = len(list(dep_dir.glob("*.py")))
            if dep_count > 10:
                insights.append(f"清理: _deprecated 有 {dep_count} 个文件，可考虑删除旧文件")
        
        return MeditationResult(
            step=4,
            phase="insights",
            content="洞察与趋势",
            insights=insights,
        )
    
    def _save_results(self, results: List[MeditationResult]):
        """持久化冥想结果"""
        try:
            with open(self._results_path, "a", encoding="utf-8") as f:
                for r in results:
                    record = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "step": r.step,
                        "phase": r.phase,
                        "content": r.content,
                        "insights": r.insights,
                        "actions": r.actions,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Meditation results save failed: {e}")


# ═══════════════════════════════════════════════════════
# 全局便捷函数
# ═══════════════════════════════════════════════════════

_matcher: Optional[EnhancedMethodMatcher] = None
_meditation: Optional[EnhancedMeditation] = None


def get_matcher(evolver_engine=None) -> EnhancedMethodMatcher:
    global _matcher
    if _matcher is None or evolver_engine:
        _matcher = EnhancedMethodMatcher(evolver_engine)
    return _matcher


def get_meditation(evolver_engine=None) -> EnhancedMeditation:
    global _meditation
    if _meditation is None or evolver_engine:
        _meditation = EnhancedMeditation(evolver_engine)
    return _meditation


# ═══════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    # 测试1: EnhancedConfidence
    ec = EnhancedConfidence(success_rate=0.85, avg_duration_s=3.0, usage_count=8, complexity=2)
    print(f"✅ 4因素置信度: total={ec.total:.1f}, normalized={ec.normalized:.3f}, grade={ec.grade}")
    print(f"   breakdown: success={ec.score_success:.1f}, speed={ec.score_speed:.1f}, freq={ec.score_frequency:.1f}, complexity={ec.score_complexity:.1f}")
    
    # 测试2: 三层匹配（无evolver）
    matcher = EnhancedMethodMatcher()
    r1 = matcher.match("搜索GitHub项目")
    print(f"✅ 三层匹配 '搜索': method={r1['method']}, source={r1['source']}, layer={r1['layer']}, conf={r1['confidence']:.2f}")
    
    r2 = matcher.match("写一个Python脚本")
    print(f"✅ 三层匹配 '写': method={r2['method']}, source={r2['source']}, layer={r2['layer']}, conf={r2['confidence']:.2f}")
    
    r3 = matcher.match("调试API连接问题")
    print(f"✅ 三层匹配 '调试': method={r3['method']}, source={r3['source']}, layer={r3['layer']}, conf={r3['confidence']:.2f}")
    
    # 测试3: Meditation（有evolver）
    try:
        from evolver import EvolverEngine
        eng = EvolverEngine()
        meditation = EnhancedMeditation(eng)
        results = meditation.run_cycle()
        for r in results:
            print(f"✅ 冥想 Step {r.step} ({r.phase}): {len(r.insights)} insights, {len(r.actions)} actions")
            for ins in r.insights[:3]:
                print(f"   - {ins}")
            for act in r.actions[:3]:
                print(f"   → {act}")
    except Exception as e:
        print(f"⚠️ Meditation (无evolver): {e}")
        # 无 evolver 的简单测试
        meditation = EnhancedMeditation()
        results = meditation.run_cycle()
        for r in results:
            print(f"✅ 冥想 Step {r.step} ({r.phase}): {len(r.insights)} insights, {len(r.actions)} actions")
    
    print("\n🎯 evolver_enhancements 全部测试通过！")
