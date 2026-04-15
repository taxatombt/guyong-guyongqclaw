# -*- coding: utf-8 -*-
"""
compact_llm_summary.py - LLM 驱动的上下文压缩

来源: 顾庸t workspace_tools/compact_llm_summary.py
参考: Claude Code context_compressor + Hermes context_compressor.py 778行

功能:
  当纯规则压缩不够时，使用 LLM 生成结构化摘要。
  
  压缩策略:
  1. 规则优先: snip → microcompact → collapse
  2. LLM 兜底: 当剩余内容仍超预算 → 调用 LLM 生成摘要
  3. 摘要格式: 结构化（RESOLVED/PENDING/DECISIONS/SYSTEM）
  
  注意: 本模块只定义摘要格式和调用接口，实际 LLM 调用由宿主执行。
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class CompactionStrategy(Enum):
    RULE_BASED = "rule"       # 纯规则
    LLM_SUMMARY = "llm"       # LLM 生成摘要
    HYBRID = "hybrid"         # 规则 + LLM 兜底


class CompressionLevel(Enum):
    LIGHT = "light"           # 10-20% 压缩
    MEDIUM = "medium"         # 40-60% 压缩
    HEAVY = "heavy"           # 70-90% 压缩


@dataclass
class CompressionResult:
    """压缩结果"""
    original_tokens: int
    compressed_tokens: int
    ratio: float  # compressed/original
    strategy: CompactionStrategy
    level: CompressionLevel
    sections_kept: List[str]
    sections_removed: List[str]


# 结构化摘要模板（HANDOVER 格式）
LLM_SUMMARY_TEMPLATE = """# Context Handover
*Compressed by {strategy} on {timestamp}*
*Original: {original_tokens} tokens → {compressed_tokens} tokens ({ratio:.0%})*

## RESOLVED
{resolved}

## PENDING
{pending}

## KEY DECISIONS
{decisions}

## SYSTEM STATE
{system_state}

## CONTINUE FROM HERE
{continuation_hint}
"""


class LLMCompactor:
    """LLM 驱动的压缩器"""
    
    def __init__(self, token_budget: int = 8000):
        self._token_budget = token_budget
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
    
    def _analyze_sections(self, text: str) -> Dict[str, Tuple[int, str]]:
        """分析文本中的段落"""
        sections = {}
        current_header = "_header"
        current_lines = []
        
        for line in text.split("\n"):
            if line.startswith("#"):
                if current_lines:
                    content = "\n".join(current_lines)
                    sections[current_header] = (self._estimate_tokens(content), content)
                current_header = line.strip()
                current_lines = []
            else:
                current_lines.append(line)
        
        # 最后一个段落
        if current_lines:
            content = "\n".join(current_lines)
            sections[current_header] = (self._estimate_tokens(content), content)
        
        return sections
    
    def rule_compact(self, text: str, level: CompressionLevel = CompressionLevel.MEDIUM) -> Tuple[str, CompressionResult]:
        """规则压缩"""
        sections = self._analyze_sections(text)
        original_tokens = sum(tokens for _, (tokens, _) in sections.items())
        
        # 按级别决定保留比例
        keep_ratios = {
            CompressionLevel.LIGHT: 0.8,
            CompressionLevel.MEDIUM: 0.5,
            CompressionLevel.HEAVY: 0.2,
        }
        target_tokens = original_tokens * keep_ratios[level]
        
        # 优先级排序: 保留 RESOLVED > DECISIONS > SYSTEM > PENDING > 其他
        priority = {
            "RESOLVED": 1, "DECISIONS": 2, "KEY DECISIONS": 2, "SYSTEM": 3,
            "PENDING": 4, "CONTINUE": 5, "_header": 0,
        }
        
        def section_priority(name: str) -> int:
            for key, pri in priority.items():
                if key in name.upper():
                    return pri
            return 6
        
        sorted_sections = sorted(
            sections.items(), key=lambda x: section_priority(x[0])
        )
        
        kept = []
        kept_tokens = 0
        removed = []
        
        for name, (tokens, content) in sorted_sections:
            if kept_tokens + tokens <= target_tokens:
                kept.append(name)
                kept_tokens += tokens
            else:
                removed.append(name)
        
        # Rebuild from kept sections
        result_parts = [content for name, (tokens, content) in sections.items() if name in kept]
        result = "\n\n".join(result_parts)
        
        compressed_tokens = self._estimate_tokens(result)
        
        return result, CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            ratio=compressed_tokens / original_tokens if original_tokens else 1,
            strategy=CompactionStrategy.RULE_BASED,
            level=level,
            sections_kept=kept,
            sections_removed=removed,
        )
    
    def generate_summary_prompt(self, text: str, target_tokens: int = 2000) -> str:
        """生成 LLM 摘要 prompt（供宿主调用）"""
        original_tokens = self._estimate_tokens(text)
        
        return f"""Please compress the following context into a structured summary.
Target: {target_tokens} tokens (current: {original_tokens} tokens).

Use this exact format:
## RESOLVED
(What has been completed and decided)

## PENDING
(What is still in progress or pending)

## KEY DECISIONS
(Important decisions made, with brief rationale)

## SYSTEM STATE
(Current state of relevant systems/files)

## CONTINUE FROM HERE
(What the next agent should focus on)

Context to compress:
---
{text}
---"""
    
    def apply_llm_summary(self, text: str, llm_output: str) -> Tuple[str, CompressionResult]:
        """应用 LLM 生成的摘要"""
        original_tokens = self._estimate_tokens(text)
        compressed_tokens = self._estimate_tokens(llm_output)
        
        return llm_output, CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            ratio=compressed_tokens / original_tokens if original_tokens else 1,
            strategy=CompactionStrategy.LLM_SUMMARY,
            level=CompressionLevel.HEAVY,
            sections_kept=["llm_summary"],
            sections_removed=["original_content"],
        )
    
    def hybrid_compact(self, text: str) -> Tuple[str, CompressionResult]:
        """混合压缩: 先规则，如果还不够再 LLM"""
        # Phase 1: 规则压缩到 MEDIUM
        result, comp = self.rule_compact(text, CompressionLevel.MEDIUM)
        
        # Phase 2: 检查是否还需要 LLM
        if comp.compressed_tokens > self._token_budget:
            # 生成 LLM prompt（但不调用，让宿主处理）
            prompt = self.generate_summary_prompt(result, target_tokens=self._token_budget // 2)
            comp.strategy = CompactionStrategy.HYBRID
            # 返回 prompt 而不是压缩结果
            return prompt, comp
        
        return result, comp


_compactor: Optional[LLMCompactor] = None

def get_llm_compactor() -> LLMCompactor:
    global _compactor
    if _compactor is None:
        _compactor = LLMCompactor()
    return _compactor
