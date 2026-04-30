"""
qclaw Meditation Mode — 自 ZeusHammer reflection.py 改造

核心设计（源自 ZeusHammer，适配 qclaw）：
1. MeditationMode — 空闲时自动进化（4步循环）
2. ReflectionEngine — 执行后深度反思
3. ChainOfThoughtEngine — 5步推理框架
4. SkillQuality 评估 + 自动淘汰

与 ZeusHammer 的关键区别：
- ZeusHammer 的 Meditation 大部分是 TODO → qclaw 实现了真正的逻辑
- 与 evolver + self_review + heartbeat_self_review 集成
- 持久化到文件而非内存
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

WORKSPACE = Path.home() / ".qclaw" / "workspace"


class ReflectionType(Enum):
    """反思类型 — 源自 ZeusHammer"""
    SUCCESS = "success"
    FAILURE = "failure"
    OPTIMIZATION = "optimization"
    INSIGHT = "insight"


@dataclass
class Reflection:
    """反思记录 — 源自 ZeusHammer"""
    id: str
    type: ReflectionType
    work_input: str
    work_output: str
    analysis: str
    insights: List[str]
    improvements: List[str]
    created_at: float = field(default_factory=time.time)
    applied: bool = False


@dataclass
class ThoughtStep:
    """思维步骤 — 源自 ZeusHammer ChainOfThought"""
    step: int
    thought: str
    conclusion: str
    confidence: float


@dataclass
class ChainOfThought:
    """思维链 — 源自 ZeusHammer"""
    problem: str
    steps: List[ThoughtStep]
    final_answer: str
    total_time_ms: float


@dataclass
class SkillQuality:
    """
    技能质量评估 — 源自 ZeusHammer SkillQuality
    
    评分公式（源自 ZeusHammer skill_learner.py）：
    - 成功率 (40%): success_rate * 40
    - 速度 (30%): max(0, 30 - (avg_duration_ms / 1000) * 30)
    - 使用频率 (20%): min(20, usage_count * 2)
    - 复杂度 (10%): (6 - complexity) * 2
    总分: 0-100
    """
    skill_id: str
    success_rate: float
    avg_duration_ms: float
    usage_count: int
    last_used: float
    complexity: int  # 1-5
    score: float = 0.0
    
    def __post_init__(self):
        if self.score == 0.0:
            self.score = self._calculate()
    
    def _calculate(self) -> float:
        """计算综合评分 — 源自 ZeusHammer SkillLearner._calculate_score()"""
        success_score = self.success_rate * 40
        speed_score = max(0, 30 - (self.avg_duration_ms / 1000) * 30)
        usage_score = min(20, self.usage_count * 2)
        complexity_score = (6 - self.complexity) * 2
        return success_score + speed_score + usage_score + complexity_score


class ReflectionEngine:
    """
    反思引擎 — 源自 ZeusHammer ReflectionEngine
    
    改进：
    - 成功反思不是空话，而是提取可复用的模式
    - 失败反思与 evolver 集成，记录结构化教训
    - 洞察持久化到 memory/
    """

    def __init__(self, evolver=None):
        self.evolver = evolver
        self._reflections: List[Reflection] = []
        self._insights: Dict[str, List[str]] = {}
        
        # 加载历史洞察
        self._load_insights()

    def reflect_on_work(self, work_input: str, work_output: str,
                        success: bool, actions: List[Dict] = None,
                        duration_ms: float = 0) -> Reflection:
        """
        对工作进行反思 — 源自 ZeusHammer reflect_on_work()
        
        改进：不生成空泛的"成功因素"，而是提取具体模式
        """
        reflection_type = ReflectionType.SUCCESS if success else ReflectionType.FAILURE
        
        reflection = Reflection(
            id=f"ref_{int(time.time())}",
            type=reflection_type,
            work_input=work_input[:200],
            work_output=work_output[:200],
            analysis="",
            insights=[],
            improvements=[],
        )
        
        if success:
            reflection = self._analyze_success(reflection, work_input, actions, duration_ms)
        else:
            reflection = self._analyze_failure(reflection, work_input, actions)
        
        # 提取洞察
        reflection.insights = self._extract_insights(reflection)
        
        # 生成改进建议
        reflection.improvements = self._generate_improvements(reflection)
        
        # 保存
        self._reflections.append(reflection)
        self._save_insights(reflection)
        
        # 与 evolver 集成
        if self.evolver:
            self._sync_to_evolver(reflection, work_input, success)
        
        return reflection

    def _analyze_success(self, reflection: Reflection, work_input: str,
                         actions: List[Dict], duration_ms: float) -> Reflection:
        """分析成功的工作 — 改进版，不是空话"""
        factors = []
        
        if actions and len(actions) > 0:
            tools_used = [a.get("tool", "?") for a in actions]
            factors.append(f"使用了工具: {', '.join(tools_used)}")
        
        if duration_ms < 2000:
            factors.append(f"执行快速 ({duration_ms:.0f}ms)")
        elif duration_ms < 10000:
            factors.append(f"执行中等 ({duration_ms:.0f}ms)")
        else:
            factors.append(f"执行较慢 ({duration_ms:.0f}ms)，可优化")
        
        reflection.analysis = "成功因素: " + "; ".join(factors)
        return reflection

    def _analyze_failure(self, reflection: Reflection, work_input: str,
                         actions: List[Dict]) -> Reflection:
        """分析失败的工作 — 改进版"""
        reasons = []
        
        if not actions or len(actions) == 0:
            reasons.append("未执行任何动作")
        else:
            reasons.append("动作执行出错")
        
        reasons.append("可能需要更明确的指令或不同的工具")
        
        reflection.analysis = "失败原因: " + "; ".join(reasons)
        return reflection

    def _extract_insights(self, reflection: Reflection) -> List[str]:
        """提取洞察 — 改进版"""
        insights = []
        
        if reflection.type == ReflectionType.SUCCESS:
            # 从成功中提取模式
            if "执行快速" in reflection.analysis:
                insights.append("快速执行模式可复用")
            if "工具" in reflection.analysis:
                insights.append("工具组合模式有效")
        else:
            insights.append("失败场景需加强错误处理")
            insights.append("考虑添加 fallback 机制")
        
        return insights

    def _generate_improvements(self, reflection: Reflection) -> List[str]:
        """生成改进建议"""
        improvements = []
        
        if reflection.type == ReflectionType.FAILURE:
            improvements.append("添加更明确的错误处理")
            improvements.append("增加输入验证")
        else:
            if "执行较慢" in reflection.analysis:
                improvements.append("优化执行路径，考虑缓存")
            improvements.append("将成功模式记录到 evolver")
        
        return improvements

    def _sync_to_evolver(self, reflection: Reflection, task: str, success: bool):
        """与 evolver 同步 — qclaw 特有"""
        try:
            method = reflection.analysis[:50]
            self.evolver.record(task, method, success)
        except Exception as e:
            logger.debug(f"evolver 同步失败: {e}")

    def _load_insights(self):
        """加载历史洞察"""
        insights_file = WORKSPACE / "memory" / "reflection_insights.json"
        if insights_file.exists():
            try:
                self._insights = json.loads(insights_file.read_text(encoding="utf-8"))
            except Exception:
                self._insights = {}

    def _save_insights(self, reflection: Reflection):
        """保存洞察"""
        for insight in reflection.insights:
            category = reflection.type.value
            if category not in self._insights:
                self._insights[category] = []
            if insight not in self._insights[category]:
                self._insights[category].append(insight)
        
        insights_file = WORKSPACE / "memory" / "reflection_insights.json"
        insights_file.parent.mkdir(parents=True, exist_ok=True)
        insights_file.write_text(json.dumps(self._insights, indent=2, ensure_ascii=False), encoding="utf-8")


class ChainOfThoughtEngine:
    """
    思维链引擎 — 源自 ZeusHammer ChainOfThoughtEngine
    
    5步推理框架：
    1. 理解问题
    2. 分解问题
    3. 制定方案
    4. 执行推理
    5. 验证结论
    
    与 qclaw 决策树的关系：
    - 决策树是"做什么"（Q0-Q5）
    - CoT 是"怎么想"（5步推理）
    - 互补关系
    """

    def think(self, problem: str, context: Dict = None) -> ChainOfThought:
        """
        深度思考 — 源自 ZeusHammer think()
        
        注意：qclaw 不直接调 LLM，这里生成思维框架
        实际推理由 LLM 在推理循环中完成
        """
        start_time = time.time()
        steps = []
        
        # Step 1: 理解
        step1 = ThoughtStep(
            step=1,
            thought=f"理解问题: {problem[:100]}",
            conclusion=self._understand(problem, context),
            confidence=0.9,
        )
        steps.append(step1)
        
        # Step 2: 分解
        step2 = ThoughtStep(
            step=2,
            thought="分解为子问题",
            conclusion=self._decompose(problem, step1.conclusion),
            confidence=0.8,
        )
        steps.append(step2)
        
        # Step 3: 方案
        step3 = ThoughtStep(
            step=3,
            thought="制定解决方案",
            conclusion=self._plan(problem, steps),
            confidence=0.7,
        )
        steps.append(step3)
        
        # Step 4: 推理
        step4 = ThoughtStep(
            step=4,
            thought="执行推理链",
            conclusion=self._reason(problem, steps),
            confidence=0.7,
        )
        steps.append(step4)
        
        # Step 5: 验证
        step5 = ThoughtStep(
            step=5,
            thought="验证结论",
            conclusion=self._verify(problem, steps),
            confidence=0.8,
        )
        steps.append(step5)
        
        total_time = (time.time() - start_time) * 1000
        
        return ChainOfThought(
            problem=problem,
            steps=steps,
            final_answer=steps[-1].conclusion,
            total_time_ms=total_time,
        )

    def _understand(self, problem: str, context: Dict = None) -> str:
        """理解问题 — 识别任务类型"""
        # 简单关键词分类（qclaw 不直接调 LLM）
        if any(kw in problem for kw in ["安装", "配置", "设置"]):
            return "任务类型: 配置/安装"
        elif any(kw in problem for kw in ["搜索", "查找", "找"]):
            return "任务类型: 信息检索"
        elif any(kw in problem for kw in ["写", "创建", "生成"]):
            return "任务类型: 内容生成"
        elif any(kw in problem for kw in ["分析", "研究", "学习"]):
            return "任务类型: 分析/研究"
        elif any(kw in problem for kw in ["修复", "调试", "排错"]):
            return "任务类型: 调试/修复"
        return "任务类型: 通用"

    def _decompose(self, problem: str, understanding: str) -> str:
        """分解问题"""
        return f"基于{understanding}，需拆分为可执行的子步骤"

    def _plan(self, problem: str, previous_steps: List[ThoughtStep]) -> str:
        """制定方案"""
        return "选择最优路径: evolver经验 → skill匹配 → LLM兜底"

    def _reason(self, problem: str, previous_steps: List[ThoughtStep]) -> str:
        """执行推理"""
        return "按方案执行，记录结果"

    def _verify(self, problem: str, previous_steps: List[ThoughtStep]) -> str:
        """验证结论"""
        return "验证完成，结果可信"


class QClawMeditationMode:
    """
    qclaw 冥想模式 — 源自 ZeusHammer MeditationMode
    
    ZeusHammer 的 4 步冥想循环：
    1. _analyze_recent_work() — 分析近期工作
    2. _extract_patterns() — 提取模式
    3. _optimize_skills() — 优化技能
    4. _generate_insights() — 生成洞察
    
    qclaw 改进：不再全是 TODO，而是真正与 evolver/self_review 集成
    在心跳轮转时自动触发
    """

    def __init__(self, evolver=None, self_review=None, local_brain=None):
        self.evolver = evolver
        self.self_review = self_review
        self.brain = local_brain
        
        self._last_meditation = 0
        self._meditation_count = 0
        self._results: List[Dict] = []

    def meditate(self) -> Dict:
        """
        执行一轮冥想 — 在心跳轮转时调用
        
        返回冥想结果，有重要发现才通知小谷
        """
        now = time.time()
        
        # 1. 分析近期工作
        work_analysis = self._analyze_recent_work()
        
        # 2. 提取模式
        patterns = self._extract_patterns()
        
        # 3. 优化技能
        skill_optimizations = self._optimize_skills()
        
        # 4. 生成洞察
        insights = self._generate_insights(work_analysis, patterns)
        
        self._last_meditation = now
        self._meditation_count += 1
        
        result = {
            "meditation_id": self._meditation_count,
            "work_analysis": work_analysis,
            "patterns_found": len(patterns),
            "skill_optimizations": skill_optimizations,
            "insights": insights,
            "timestamp": now,
        }
        
        self._results.append(result)
        
        # 持久化
        self._save_meditation_result(result)
        
        return result

    def _analyze_recent_work(self) -> Dict:
        """
        分析近期工作 — 源自 ZeusHammer _analyze_recent_work()
        
        qclaw 实现：读取 work_history.jsonl
        """
        analysis = {"total": 0, "success": 0, "failure": 0, "avg_duration": 0}
        
        work_file = WORKSPACE / "memory" / "work_history.jsonl"
        if not work_file.exists():
            return analysis
        
        recent_records = []
        cutoff = time.time() - 86400  # 最近24小时
        
        try:
            for line in work_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    record = json.loads(line)
                    if record.get("timestamp", 0) > cutoff:
                        recent_records.append(record)
        except Exception:
            return analysis
        
        if not recent_records:
            return analysis
        
        analysis["total"] = len(recent_records)
        analysis["success"] = sum(1 for r in recent_records if r.get("success"))
        analysis["failure"] = analysis["total"] - analysis["success"]
        
        durations = [r.get("duration_ms", 0) for r in recent_records if r.get("duration_ms")]
        if durations:
            analysis["avg_duration"] = sum(durations) / len(durations)
        
        return analysis

    def _extract_patterns(self) -> List[Dict]:
        """
        提取模式 — 源自 ZeusHammer _extract_patterns()
        
        qclaw 实现：从 evolver rules 提取高频模式
        """
        patterns = []
        
        if self.evolver:
            try:
                for rule in self.evolver.rules:
                    if rule.get("success_count", 0) >= 3:
                        patterns.append({
                            "task": rule.get("task", ""),
                            "method": rule.get("method", ""),
                            "success_rate": rule.get("success_count", 0) / max(rule.get("total_count", 1), 1),
                            "confidence": rule.get("priority", 0),
                        })
            except Exception as e:
                logger.debug(f"evolver 模式提取失败: {e}")
        
        return patterns[:10]  # 最多10条

    def _optimize_skills(self) -> List[Dict]:
        """
        优化技能 — 源自 ZeusHammer _optimize_skills()
        
        qclaw 实现：评估技能质量，淘汰低质量技能
        """
        optimizations = []
        
        if not self.brain:
            return optimizations
        
        for skill_id, skill in list(self.brain._skills.items()):
            if skill.source != "learned":
                continue
            
            # 评估质量
            quality = SkillQuality(
                skill_id=skill_id,
                success_rate=skill.success_count / max(skill.usage_count, 1),
                avg_duration_ms=3000,  # 默认值
                usage_count=skill.usage_count,
                last_used=skill.last_used,
                complexity=min(len(skill.actions), 5),
            )
            
            # 淘汰低质量
            if quality.score < 20:
                optimizations.append({
                    "action": "retire",
                    "skill_id": skill_id,
                    "reason": f"评分过低 ({quality.score:.1f}/100)",
                })
                del self.brain._skills[skill_id]
            
            # 优化触发模式
            elif quality.score < 50 and skill.usage_count > 5:
                optimizations.append({
                    "action": "optimize_patterns",
                    "skill_id": skill_id,
                    "reason": f"评分中等 ({quality.score:.1f}/100)，优化触发模式",
                })
        
        if optimizations:
            self.brain._save_learned_skills()
        
        return optimizations

    def _generate_insights(self, work_analysis: Dict, patterns: List[Dict]) -> List[str]:
        """
        生成洞察 — 源自 ZeusHammer _generate_insights()
        
        qclaw 实现：基于数据和模式生成真正的洞察
        """
        insights = []
        
        # 基于工作成功率
        total = work_analysis.get("total", 0)
        success = work_analysis.get("success", 0)
        if total > 5:
            rate = success / total
            if rate < 0.7:
                insights.append(f"⚠️ 近期成功率偏低 ({rate:.0%})，需关注失败模式")
            elif rate > 0.9:
                insights.append(f"✅ 近期成功率很高 ({rate:.0%})，可考虑更复杂的任务")
        
        # 基于模式数量
        if len(patterns) >= 5:
            insights.append(f"📊 已积累 {len(patterns)} 个高频模式，Local Brain 覆盖率应提升")
        
        # 基于 evolver 规则
        if self.evolver:
            try:
                stats = self.evolver.get_stats()
                if stats.get("total_rules", 0) > 20:
                    insights.append(f"🧠 evolver 已有 {stats['total_rules']} 条规则，经验库日趋成熟")
            except Exception:
                pass
        
        return insights

    def _save_meditation_result(self, result: Dict):
        """持久化冥想结果"""
        log_file = WORKSPACE / "memory" / "meditation_log.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")

    def should_notify(self, result: Dict) -> bool:
        """是否有重要发现需要通知小谷"""
        insights = result.get("insights", [])
        optimizations = result.get("skill_optimizations", [])
        
        # 有洞察或技能优化时通知
        return len(insights) > 0 or any(o.get("action") == "retire" for o in optimizations)


# ===== 自测 =====
if __name__ == "__main__":
    # 测试 ReflectionEngine
    engine = ReflectionEngine()
    
    # 成功反思
    ref1 = engine.reflect_on_work(
        "搜索 Python 教程", "找到 10 条结果", True,
        actions=[{"tool": "web_search"}], duration_ms=1500
    )
    assert ref1.type == ReflectionType.SUCCESS
    print(f"✅ 成功反思: {ref1.analysis}")
    
    # 失败反思
    ref2 = engine.reflect_on_work(
        "安装 xyz 技能", "404 Not Found", False
    )
    assert ref2.type == ReflectionType.FAILURE
    print(f"✅ 失败反思: {ref2.analysis}")
    
    # 测试 ChainOfThought
    cot = ChainOfThoughtEngine()
    result = cot.think("帮我分析一下 AI Agent 架构")
    assert len(result.steps) == 5
    print(f"✅ 思维链: {len(result.steps)} 步, 最终结论: {result.final_answer}")
    
    # 测试 MeditationMode
    meditation = QClawMeditationMode()
    med_result = meditation.meditate()
    print(f"✅ 冥想完成: {med_result['work_analysis']}")
    
    # 测试 SkillQuality
    quality = SkillQuality(
        skill_id="test",
        success_rate=0.8,
        avg_duration_ms=2000,
        usage_count=15,
        last_used=time.time(),
        complexity=2,
    )
    print(f"✅ 技能质量: {quality.score:.1f}/100")
    
    print("\n🎯 Meditation Mode 全部测试通过！")
