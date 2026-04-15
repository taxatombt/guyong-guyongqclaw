# -*- coding: utf-8 -*-
"""
debate_pattern.py - 双模型辩论式推理

来源: 顾庸t workspace_tools/debate_pattern.py
参考: Superpowers debate + Claude Code verification anti-rationalization

功能:
  让两个"角色"对同一问题进行辩论，最终综合得出结论。

  流程:
  1. Topic 提出 → Model A (支持方) 论证
  2. Model B (反对方) 反驳
  3. Model A 再反驳 → Model B 再反驳
  4. Judge 综合判定

  用途: 重大决策、方案选择、风险分析
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class DebatePhase(Enum):
    PROPOSAL = "proposal"
    REBUTTAL_1 = "rebuttal_1"  # B反驳A
    REBUTTAL_2 = "rebuttal_2"  # A反驳B
    CROSS_EXAM = "cross_exam"  # 交叉质询
    VERDICT = "verdict"


@dataclass
class DebateArgument:
    """辩论论点"""
    speaker: str  # "proponent" / "opponent" / "judge"
    content: str
    phase: DebatePhase
    timestamp: float = field(default_factory=time.time)
    supporting_evidence: List[str] = field(default_factory=list)


@dataclass
class Verdict:
    """判决"""
    decision: str  # "accept" / "reject" / "conditional"
    confidence: float  # 0.0 ~ 1.0
    summary: str
    conditions: List[str] = field(default_factory=list)  # conditional时的条件
    strongest_pro: str = ""
    strongest_con: str = ""


class DebateSession:
    """辩论会话"""
    
    def __init__(self, topic: str, max_rounds: int = 3):
        self.topic = topic
        self.max_rounds = max_rounds
        self._arguments: List[DebateArgument] = []
        self._phase = DebatePhase.PROPOSAL
        self._verdict: Optional[Verdict] = None
    
    @property
    def phase(self) -> DebatePhase:
        return self._phase
    
    def add_argument(self, speaker: str, content: str,
                     evidence: Optional[List[str]] = None) -> DebateArgument:
        """添加论点"""
        arg = DebateArgument(
            speaker=speaker,
            content=content,
            phase=self._phase,
            supporting_evidence=evidence or [],
        )
        self._arguments.append(arg)
        self._advance_phase()
        return arg
    
    def _advance_phase(self) -> None:
        """推进辩论阶段"""
        phase_order = list(DebatePhase)
        current_idx = phase_order.index(self._phase)
        
        if current_idx < len(phase_order) - 1:
            self._phase = phase_order[current_idx + 1]
    
    def set_verdict(self, verdict: Verdict) -> None:
        """设置判决"""
        self._verdict = verdict
        self._phase = DebatePhase.VERDICT
    
    def get_arguments(self, phase: Optional[DebatePhase] = None,
                      speaker: Optional[str] = None) -> List[DebateArgument]:
        """获取论点"""
        args = self._arguments
        if phase:
            args = [a for a in args if a.phase == phase]
        if speaker:
            args = [a for a in args if a.speaker == speaker]
        return args
    
    def to_markdown(self) -> str:
        """导出为 Markdown"""
        lines = [
            f"# Debate: {self.topic}",
            f"Phase: {self._phase.value}",
            "",
        ]
        
        for arg in self._arguments:
            speaker_label = arg.speaker.upper()
            lines.append(f"## [{speaker_label}] ({arg.phase.value})")
            lines.append(arg.content)
            if arg.supporting_evidence:
                lines.append("\nEvidence:")
                for e in arg.supporting_evidence:
                    lines.append(f"  - {e}")
            lines.append("")
        
        if self._verdict:
            lines.append("## Verdict")
            lines.append(f"Decision: **{self._verdict.decision.upper()}**")
            lines.append(f"Confidence: {self._verdict.confidence:.0%}")
            lines.append(f"Summary: {self._verdict.summary}")
            if self._verdict.conditions:
                lines.append("\nConditions:")
                for c in self._verdict.conditions:
                    lines.append(f"  - {c}")
            if self._verdict.strongest_pro:
                lines.append(f"\nStrongest Pro: {self._verdict.strongest_pro}")
            if self._verdict.strongest_con:
                lines.append(f"Strongest Con: {self._verdict.strongest_con}")
        
        return "\n".join(lines)


class DebatePattern:
    """辩论模式管理"""
    
    def __init__(self):
        self._sessions: Dict[str, DebateSession] = {}
    
    def create(self, topic: str, max_rounds: int = 3) -> DebateSession:
        session = DebateSession(topic, max_rounds)
        self._sessions[topic] = session
        return session
    
    def get(self, topic: str) -> Optional[DebateSession]:
        return self._sessions.get(topic)
    
    def list_sessions(self) -> List[Dict[str, str]]:
        return [
            {"topic": t, "phase": s.phase.value, "args": len(s._arguments)}
            for t, s in self._sessions.items()
        ]


_pattern: Optional[DebatePattern] = None

def get_debate_pattern() -> DebatePattern:
    global _pattern
    if _pattern is None:
        _pattern = DebatePattern()
    return _pattern
