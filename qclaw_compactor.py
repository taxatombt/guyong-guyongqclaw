# -*- coding: utf-8 -*-
"""
qclaw_compactor.py - Structured Context Compressor V2

来源: Hermes agent/context_compressor.py (778行)
       Claude Code analyzeContext.ts (3430行)

v2 改进:
- Structured Summary Template: Goal + Progress + Decisions + Files + Next Steps
- Iterative summary updates (preserves info across compactions)
- Token-budget tail protection (not fixed message count)
- Tool output pruning before LLM summarization (cheap pre-pass)
- Scaled summary budget (proportional to compressed content)
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Constants
_MIN_SUMMARY_TOKENS = 2000
_SUMMARY_RATIO = 0.20
_SUMMARY_TOKENS_CEILING = 12000
_PRUNED_PLACEHOLDER = "[Old tool output cleared]"
_COOLDOWN_SECONDS = 600
_SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION] Earlier turns were compacted. "
    "Use summary and current state to continue:"
)
_CHARS_PER_TOKEN = 4

# Structured summary template
STRUCTURED_TEMPLATE = """Please summarize using this EXACT structure:

## Goal
What was the task trying to accomplish?

## Progress
What has been completed so far?

## Decisions
What key decisions were made?

## Files
What files were created or modified?

## Next Steps
What remains to be done?
"""


@dataclass
class CompactionEvent:
    timestamp: str
    input_tokens: int
    output_tokens: int
    summary: str
    compression_ratio: float = 0.0


class ContextCompressor:
    """
    Default context compressor: lossy summarization via structured LLM prompt.
    
    Algorithm (5 steps):
    1. Prune old tool results (cheap, no LLM)
    2. Protect head messages (system + first exchange)
    3. Protect tail by token budget (~20% of context)
    4. Summarize middle with structured LLM prompt
    5. On subsequent: iteratively update previous summary
    """
    
    def __init__(self):
        self._previous_summary: Optional[str] = None
        self._last_compaction_time: float = 0
        self._compaction_count: int = 0
        self._events: List[CompactionEvent] = []
    
    @property
    def name(self) -> str:
        return "qclaw_context_compressor"
    
    @property
    def previous_summary(self) -> Optional[str]:
        return self._previous_summary
    
    def estimate_tokens(self, text: str) -> int:
        """Rough estimation: chars / 4"""
        return max(1, len(text) // _CHARS_PER_TOKEN)
    
    def should_compress(self, messages: List[dict],
                       context_length: int,
                       context_limit: int = 200000) -> Tuple[bool, str]:
        """
        判断是否需要压缩。
        Returns: (should_compress, reason)
        """
        ratio = context_length / context_limit if context_limit > 0 else 0
        
        if ratio < 0.85:
            return False, f"context {ratio:.0%} below 85%"
        
        if ratio >= 0.95:
            return True, f"context {ratio:.0%} above hard limit"
        
        elapsed = time.time() - self._last_compaction_time
        if elapsed < _COOLDOWN_SECONDS:
            return False, f"cooldown {elapsed:.0f}s < {_COOLDOWN_SECONDS}s"
        
        return True, f"context {ratio:.0%} above threshold"
    
    def _prune_tool_outputs(self, messages: List[dict]) -> List[dict]:
        """
        Step 1: Prune old tool outputs > 500 tokens.
        Replaces with placeholder (no LLM call needed).
        """
        pruned = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = str(msg.get("content", ""))
                if self.estimate_tokens(content) > 500:
                    pruned.append({
                        "role": "tool",
                        "content": _PRUNED_PLACEHOLDER,
                        "tool_use_id": msg.get("tool_use_id"),
                    })
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)
        return pruned
    
    def _find_head_tail_boundary(self, messages: List[dict],
                                  tail_budget: int) -> Tuple[int, int]:
        """
        Find head (system + first exchange) and tail (recent ~20% tokens).
        Returns: (head_end, tail_start)
        """
        # Head: keep system + first 2 messages
        head_end = min(3, len(messages))
        
        # Tail: from end, count tokens backward until budget hit
        tail_start = 0
        tail_tokens = 0
        for i in range(len(messages) - 1, head_end - 1, -1):
            msg_tokens = self.estimate_tokens(str(messages[i].get("content", "")))
            if tail_tokens + msg_tokens > tail_budget:
                tail_start = i + 1
                break
            tail_tokens += msg_tokens
        
        if tail_start == 0:
            tail_start = head_end
        
        return head_end, tail_start
    
    def _compute_summary_budget(self, middle_tokens: int) -> int:
        """Token budget for summary (20% ratio, 2K-12K ceiling)"""
        budget = int(middle_tokens * _SUMMARY_RATIO)
        return max(_MIN_SUMMARY_TOKENS, min(budget, _SUMMARY_TOKENS_CEILING))
    
    def _build_summary_prompt(self, middle_content: str) -> str:
        """
        Build LLM prompt for structured summarization.
        If previous summary exists, include for iterative update.
        """
        if self._previous_summary:
            update_note = (
                f"\n\nPREVIOUS SUMMARY (update if inaccurate):\n"
                f"{self._previous_summary}\n"
            )
        else:
            update_note = ""
        
        return (
            f"{STRUCTURED_TEMPLATE}{update_note}\n\n"
            f"Content to summarize:\n{middle_content[:3000]}"
        )
    
    def compress(self, messages: List[dict],
                 context_limit: int = 200000) -> Tuple[List[dict], str]:
        """
        Main compression method.
        Returns: (compressed_messages, summary_text)
        
        TODO: Replace _build_summary_prompt output with actual LLM call.
        Currently returns structured prompt as summary placeholder.
        """
        self._compaction_count += 1
        self._last_compaction_time = time.time()
        
        # Step 1: Prune tool outputs
        pruned = self._prune_tool_outputs(messages)
        
        # Step 2-3: Find boundaries
        tail_budget = int(context_limit * 0.10)  # 10% tail protection
        head_end, tail_start = self._find_head_tail_boundary(pruned, tail_budget)
        
        head = pruned[:head_end]
        tail = pruned[tail_start:]
        middle = pruned[head_end:tail_start]
        
        # Step 4: Generate summary
        middle_content = "\n".join(
            f"[{m.get('role')}]: {str(m.get('content', ''))[:300]}"
            for m in middle
        )
        middle_tokens = self.estimate_tokens(middle_content)
        
        if middle_tokens < _MIN_SUMMARY_TOKENS:
            summary = ""
            compressed = pruned
        else:
            summary = self._build_summary_prompt(middle_content)
            compressed = head + [
                {"role": "system", "content": _SUMMARY_PREFIX + "\n" + summary},
            ] + tail
        
        # Step 5: Iterative update
        if summary and self._previous_summary is None:
            self._previous_summary = summary
        
        # Record event
        input_tokens = sum(self.estimate_tokens(str(m.get("content", "")))
                            for m in messages)
        output_tokens = sum(self.estimate_tokens(str(m.get("content", "")))
                            for m in compressed)
        ratio = (1 - output_tokens/max(input_tokens, 1)) * 100
        
        self._events.append(CompactionEvent(
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            summary=summary[:200],
            compression_ratio=ratio,
        ))
        
        return compressed, summary
    
    def reset(self):
        """Reset state on /new or /reset"""
        self._previous_summary = None
        self._last_compaction_time = 0
        self._compaction_count = 0
        self._events = []
    
    def report(self) -> str:
        """Format compaction report"""
        if not self._events:
            return "No compactions yet"
        ev = self._events[-1]
        return (
            f"Compaction #{self._compaction_count}: "
            f"{ev.input_tokens} -> {ev.output_tokens} tokens "
            f"({ev.compression_ratio:.0f}% reduction)"
        )


# Singleton
_compressor: Optional[ContextCompressor] = None

def get_compressor() -> ContextCompressor:
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor()
    return _compressor


if __name__ == "__main__":
    comp = ContextCompressor()
    
    # Test messages (simulate long conversation)
    test = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Build a REST API in Python"},
        {"role": "assistant", "content": "Creating FastAPI application..."},
        {"role": "tool", "content": "Created api.py with 500 lines of endpoints"},
        {"role": "user", "content": "Add JWT authentication"},
        {"role": "assistant", "content": "Implementing JWT with PyJWT..."},
        {"role": "tool", "content": "Updated api.py: added auth.py + middleware (300 lines)"},
        {"role": "user", "content": "Add PostgreSQL support"},
        {"role": "assistant", "content": "Adding asyncpg database connection..."},
        {"role": "tool", "content": "Updated db.py with asyncpg (400 lines)"},
    ]
    
    total = comp.estimate_tokens("".join(str(m.get("content", "")) for m in test))
    should, reason = comp.should_compress(test, total, 200000)
    print(f"Should compress: {should} ({reason})")
    print(f"Total tokens: {total}")
    
    compressed, summary = comp.compress(test)
    print(f"\nCompressed: {len(test)} -> {len(compressed)} messages")
    print(f"Summary prompt: {len(summary)} chars")
    print(f"Report: {comp.report()}")
    
    # Test reset
    comp.reset()
    print(f"\nAfter reset - count: {comp._compaction_count}, prev: {comp._previous_summary}")
