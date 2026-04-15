# -*- coding: utf-8 -*-
"""
dual_model_voter.py - 双模型投票器

来源: 顾庸t workspace_tools/dual_model_voter.py
参考: Hermes dual-model + Claude Code verification

功能:
  同一任务交给两个模型执行，比较结果，投票决定最终输出。

  流程:
  1. Model A 执行任务 → result_a
  2. Model B 执行任务 → result_b
  3. 比较结果 → agreement / disagreement
  4. 如果一致 → 直接采用
  5. 如果不一致 → 第三方仲裁或合并
"""

import re
import difflib
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Callable
from enum import Enum


class VoteResult(Enum):
    AGREEMENT = "agreement"
    PARTIAL = "partial"
    DISAGREEMENT = "disagreement"
    ERROR = "error"


@dataclass
class ComparisonResult:
    """比较结果"""
    vote: VoteResult
    similarity: float  # 0.0 ~ 1.0
    result_a: str
    result_b: str
    final_result: str
    differences: List[str]
    arbitrator_used: bool = False


def _text_similarity(a: str, b: str) -> float:
    """计算两段文本相似度"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _extract_differences(a: str, b: str, max_diffs: int = 10) -> List[str]:
    """提取差异"""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    diff = list(difflib.unified_diff(a_lines, b_lines, lineterm="", n=1))
    
    diffs = []
    for line in diff[:max_diffs]:
        if line.startswith("+") and not line.startswith("+++"):
            diffs.append(f"B has: {line[1:][:80]}")
        elif line.startswith("-") and not line.startswith("---"):
            diffs.append(f"A has: {line[1:][:80]}")
    
    return diffs if diffs else ["No line-level differences detected"]


class DualModelVoter:
    """双模型投票器"""
    
    def __init__(self, similarity_threshold: float = 0.85,
                 arbitrator: Optional[Callable] = None):
        self._threshold = similarity_threshold
        self._arbitrator = arbitrator  # Optional: 第三方仲裁函数
        self._history: List[ComparisonResult] = []
    
    def compare(self, result_a: str, result_b: str) -> ComparisonResult:
        """比较两个模型的结果"""
        similarity = _text_similarity(result_a, result_b)
        differences = _extract_differences(result_a, result_b)
        
        if similarity >= self._threshold:
            vote = VoteResult.AGREEMENT
            final = result_a  # 任选其一
        elif similarity >= 0.5:
            vote = VoteResult.PARTIAL
            final = result_a  # 默认取A
        else:
            vote = VoteResult.DISAGREEMENT
            # 尝试仲裁
            if self._arbitrator:
                try:
                    final = self._arbitrator(result_a, result_b)
                except Exception:
                    final = self._merge(result_a, result_b)
            else:
                final = self._merge(result_a, result_b)
        
        result = ComparisonResult(
            vote=vote,
            similarity=similarity,
            result_a=result_a,
            result_b=result_b,
            final_result=final,
            differences=differences,
            arbitrator_used=(vote != VoteResult.AGREEMENT and self._arbitrator is not None),
        )
        
        self._history.append(result)
        return result
    
    def _merge(self, a: str, b: str) -> str:
        """简单合并策略: 取较长的"""
        return a if len(a) >= len(b) else b
    
    def set_arbitrator(self, func: Callable[[str, str], str]) -> None:
        """设置仲裁函数"""
        self._arbitrator = func
    
    def history(self) -> List[Dict[str, Any]]:
        """投票历史"""
        return [
            {
                "vote": r.vote.value,
                "similarity": round(r.similarity, 3),
                "diffs": len(r.differences),
            }
            for r in self._history[-20:]
        ]
    
    def stats(self) -> Dict[str, Any]:
        """统计"""
        total = len(self._history)
        if total == 0:
            return {"total": 0}
        
        agreement = sum(1 for r in self._history if r.vote == VoteResult.AGREEMENT)
        partial = sum(1 for r in self._history if r.vote == VoteResult.PARTIAL)
        disagreement = sum(1 for r in self._history if r.vote == VoteResult.DISAGREEMENT)
        avg_sim = sum(r.similarity for r in self._history) / total
        
        return {
            "total": total,
            "agreement": agreement,
            "partial": partial,
            "disagreement": disagreement,
            "agreement_rate": round(agreement/total, 2),
            "avg_similarity": round(avg_sim, 3),
        }


_voter: Optional[DualModelVoter] = None

def get_voter() -> DualModelVoter:
    global _voter
    if _voter is None:
        _voter = DualModelVoter()
    return _voter
