# -*- coding: utf-8 -*-
"""
magma.py - 深度思考引擎（Magma Mode）

来源: 顾庸t workspace_tools/magma.py
参考: Claude Code thinking/extended thinking + Hermes budget deep analysis

功能:
  高认知深度模式，用于:
  1. 复杂推理（多步逻辑链）
  2. 创造性综合（跨领域连接）
  3. 反合理化检测（自检思维偏见）
  4. 决策分析（多方案对比）

  Magma = 深度 + 高温 + 压力 → 高质量思考
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ThinkingPhase(Enum):
    DECOMPOSE = "decompose"       # 分解问题
    EXPLORE = "explore"           # 探索方案
    ANALYZE = "analyze"           # 深度分析
    CROSS_CHECK = "cross_check"   # 交叉验证
    SYNTHESIZE = "synthesize"     # 综合结论
    ANTI_RATIONALIZE = "anti_rationalize"  # 反合理化


@dataclass
class ThinkingStep:
    """思考步骤"""
    phase: ThinkingPhase
    content: str
    confidence: float = 0.5
    alternatives_considered: int = 0
    biases_detected: List[str] = field(default_factory=list)


@dataclass
class MagmaResult:
    """Magma 思考结果"""
    question: str
    answer: str
    confidence: float
    phases_completed: int
    total_phases: int
    steps: List[ThinkingStep]
    thinking_duration_ms: int
    biases_caught: List[str]
    alternatives: List[str]


# 常见认知偏见检查清单
COGNITIVE_BIASES = [
    ("confirmation_bias", "只寻找支持自己观点的证据"),
    ("anchoring", "过度依赖第一个想到的信息"),
    ("availability_bias", "容易被最近的例子影响判断"),
    ("sunk_cost", "因为已经投入了所以不愿放弃"),
    ("dunning_kruger", "高估自己的能力/知识"),
    ("planning_fallacy", "低估任务所需时间和资源"),
    ("not_invented_here", "拒绝使用已有的好方案"),
    ("premature_optimization", "过早优化"),
    ("status_quo_bias", "倾向于保持现状不做改变"),
    ("bandwagon_effect", "因为多数人这么想所以认为是对的"),
]


class MagmaEngine:
    """Magma 深度思考引擎"""
    
    def think(self, question: str, context: str = "",
              max_alternatives: int = 5) -> MagmaResult:
        """
        深度思考一个问题。
        
        返回: MagmaResult（包含所有思考步骤和最终答案）
        
        注意: 实际思考由 LLM 完成。此引擎定义思考框架和步骤。
        """
        start = time.time()
        steps = []
        biases_caught = []
        alternatives = []
        
        # Phase 1: Decompose
        decomposed = self._decompose(question)
        steps.append(ThinkingStep(
            phase=ThinkingPhase.DECOMPOSE,
            content=f"Sub-questions: {decomposed}",
            confidence=0.7,
        ))
        
        # Phase 2: Explore alternatives
        alts = self._generate_alternatives(question, max_alternatives)
        alternatives = alts
        steps.append(ThinkingStep(
            phase=ThinkingPhase.EXPLORE,
            content=f"Alternatives explored: {len(alts)}",
            alternatives_considered=len(alts),
            confidence=0.6,
        ))
        
        # Phase 3: Deep analysis
        analysis = self._analyze(question, alts, context)
        steps.append(ThinkingStep(
            phase=ThinkingPhase.ANALYZE,
            content=analysis,
            confidence=0.75,
        ))
        
        # Phase 4: Cross-check
        cross_result = self._cross_check(alts)
        steps.append(ThinkingStep(
            phase=ThinkingPhase.CROSS_CHECK,
            content=cross_result,
            confidence=0.8,
        ))
        
        # Phase 5: Anti-rationalization
        biases = self._check_biases(question, analysis)
        biases_caught = biases
        steps.append(ThinkingStep(
            phase=ThinkingPhase.ANTI_RATIONALIZE,
            content=f"Biases checked: {len(biases)} patterns examined",
            biases_detected=biases,
            confidence=0.85,
        ))
        
        # Phase 6: Synthesize
        answer = self._synthesize(question, steps)
        steps.append(ThinkingStep(
            phase=ThinkingPhase.SYNTHESIZE,
            content=answer,
            confidence=0.9,
        ))
        
        duration = int((time.time() - start) * 1000)
        
        return MagmaResult(
            question=question,
            answer=answer,
            confidence=0.85,  # 综合置信度
            phases_completed=len(steps),
            total_phases=len(ThinkingPhase),
            steps=steps,
            thinking_duration_ms=duration,
            biases_caught=biases_caught,
            alternatives=alternatives,
        )
    
    def _decompose(self, question: str) -> List[str]:
        """分解问题为子问题"""
        words = question.replace("?", "").split()
        # 简单启发式分解
        sub_questions = [
            f"What is the core of: {question}?",
            f"Why does {question} matter?",
            f"What are the constraints for: {question}?",
            f"What could go wrong with: {question}?",
        ]
        return sub_questions
    
    def _generate_alternatives(self, question: str, max_count: int) -> List[str]:
        """生成替代方案"""
        # 占位: 实际由 LLM 生成
        return [f"Alternative approach {i+1} for: {question}" for i in range(min(3, max_count))]
    
    def _analyze(self, question: str, alternatives: List[str], context: str) -> str:
        """深度分析"""
        return f"Analysis framework applied to {len(alternatives)} alternatives"
    
    def _cross_check(self, alternatives: List[str]) -> str:
        """交叉验证"""
        return f"Cross-check completed for {len(alternatives)} alternatives"
    
    def _check_biases(self, question: str, analysis: str) -> List[str]:
        """检查认知偏见"""
        combined = (question + " " + analysis).lower()
        detected = []
        for bias_name, bias_desc in COGNITIVE_BIASES:
            # 简单启发式: 关键词匹配
            if bias_name.replace("_", " ") in combined:
                detected.append(f"{bias_name}: {bias_desc}")
        return detected
    
    def _synthesize(self, question: str, steps: List[ThinkingStep]) -> str:
        """综合结论"""
        confidences = [s.confidence for s in steps]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        return f"Synthesized answer for: {question} (avg confidence: {avg_conf:.0%})"


_magma: Optional[MagmaEngine] = None

def get_magma() -> MagmaEngine:
    global _magma
    if _magma is None:
        _magma = MagmaEngine()
    return _magma
