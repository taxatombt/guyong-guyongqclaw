# -*- coding: utf-8 -*-
"""
context_hygiene.py - 4层上下文压缩管线

来源: Claude Code context_compressor.ts + 顾庸t context_hygiene.py

4层压缩，由浅入深:

Level 1: snip        — 切除超长工具输出 (>500 tokens)，保留首尾
Level 2: microcompact — 合并连续同类消息 (3+ user/assistant 回合)
Level 3: collapse    — 折叠早于 N 轮的历史，替换为摘要标记
Level 4: autocompact — 完整 LLM 压缩，生成 HANDOVER 格式

触发阈值:
  snip:        无条件 (pre-pass)
  microcompact: >50 条消息
  collapse:    >80 条消息 或 上下文 >60%
  autocompact: >100 条消息 或 上下文 >85%
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import time

SNIP_THRESHOLD = 500   # tokens
MICRO_THRESHOLD = 50  # messages
COLLAPSE_THRESHOLD = 80  # messages or 60% context
AUTO_THRESHOLD = 100  # messages or 85% context


class HygieneLevel(Enum):
    SNIP = 1
    MICRO = 2
    COLLAPSE = 3
    AUTO = 4


@dataclass
class HygieneResult:
    level: HygieneLevel
    original_count: int
    final_count: int
    reduction_ratio: float
    applied: List[str]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ─── Level 1: Snip ───────────────────────────────────

def snip_tool_outputs(messages: List[Dict[str, Any]], 
                       threshold: int = SNIP_THRESHOLD) -> List[Dict[str, Any]]:
    """
    切除超长工具输出，保留首尾。
    无条件执行 (pre-pass)。
    """
    result = []
    for msg in messages:
        if msg.get("role") == "tool":
            content = str(msg.get("content", ""))
            tokens = _estimate_tokens(content)
            if tokens > threshold:
                # 保留首尾各 100 chars
                head = content[:200]
                tail = content[-200:] if len(content) > 200 else ""
                pruned = head + f"\n... [{tokens - 2} tokens removed] ...\n" + tail
                result.append({**msg, "content": pruned, "_snipped": True})
            else:
                result.append(msg)
        else:
            result.append(msg)
    return result


# ─── Level 2: Microcompact ────────────────────────────

def collapse_consecutive(messages: List[Dict[str, Any]], 
                        min_repeat: int = 3) -> List[Dict[str, Any]]:
    """
    合并连续 3+ 个同 role 消息为一个。
    保留最后 2 条的内容摘要。
    """
    if len(messages) < min_repeat * 2:
        return messages
    
    result = []
    buffer: List[Dict] = []
    last_role = None
    
    for msg in messages:
        role = msg.get("role")
        if role == last_role and role in ("user", "assistant"):
            buffer.append(msg)
        else:
            if len(buffer) >= min_repeat:
                # 合并
                combined = _summarize_buffer(buffer)
                result.append(combined)
            else:
                result.extend(buffer)
            buffer = [msg]
            last_role = role
    
    if buffer:
        if len(buffer) >= min_repeat and last_role in ("user", "assistant"):
            combined = _summarize_buffer(buffer)
            result.append(combined)
        else:
            result.extend(buffer)
    
    return result


def _summarize_buffer(buffer: List[Dict]) -> Dict[str, Any]:
    """把多条消息合并为一条摘要"""
    role = buffer[0].get("role", "assistant")
    count = len(buffer)
    preview = str(buffer[-1].get("content", ""))[:100]
    return {
        "role": role,
        "content": f"[{count} consecutive {role} messages collapsed] {preview}",
        "_collapsed": True,
    }


# ─── Level 3: Collapse ───────────────────────────────

def collapse_old_turns(messages: List[Dict[str, Any]], 
                        keep_recent: int = 20) -> List[Dict[str, Any]]:
    """
    折叠早期消息，保留最近的 N 轮。
    插入结构化折叠标记。
    """
    if len(messages) <= keep_recent:
        return messages
    
    recent = messages[-keep_recent:]
    old = messages[:-keep_recent]
    
    old_tokens = sum(_estimate_tokens(str(m.get("content", ""))) for m in old)
    old_tools = sum(1 for m in old if m.get("role") == "tool")
    
    marker = {
        "role": "system",
        "content": (
            f"[{len(old)} turns collapsed — "
            f"~{old_tokens} tokens, {old_tools} tool calls. "
            "See prior context for details.]"
        ),
        "_collapsed": True,
    }
    
    return [marker] + recent


# ─── Level 4: Autocompact (stub) ─────────────────────

def autocompact(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """
    完整 LLM 压缩 (需接入 LLM)。
    返回: (压缩后消息, 压缩摘要)
    
    当前返回占位符，实际需接入 LLM。
    """
    # Placeholder: 返回 collapse level 作为降级
    collapsed = collapse_old_turns(messages, keep_recent=15)
    summary = "[Autocompact placeholder - connect to LLM for full HANDOVER generation]"
    return collapsed, summary


# ─── Main Pipeline ─────────────────────────────────────

def compute_hygiene_level(messages: List[Dict], context_tokens: int, 
                           limit: int = 200000) -> HygieneLevel:
    """
    根据消息数量和上下文使用率，推荐压缩级别。
    """
    count = len(messages)
    ratio = context_tokens / limit if limit > 0 else 0
    
    if count > AUTO_THRESHOLD or ratio > 0.85:
        return HygieneLevel.AUTO
    elif count > COLLAPSE_THRESHOLD or ratio > 0.60:
        return HygieneLevel.COLLAPSE
    elif count > MICRO_THRESHOLD:
        return HygieneLevel.MICRO
    else:
        return HygieneLevel.SNIP


def run_pipeline(messages: List[Dict[str, Any]], 
                  target_level: Optional[HygieneLevel] = None) -> HygieneResult:
    """
    执行完整的上下文卫生管线。
    返回: HygieneResult
    
    默认自动检测级别。
    """
    if target_level is None:
        total_tokens = sum(_estimate_tokens(str(m.get("content", ""))) for m in messages)
        target_level = compute_hygiene_level(messages, total_tokens)
    
    original_count = len(messages)
    applied = []
    current = messages
    
    # Level 1: snip (always)
    current = snip_tool_outputs(current)
    applied.append("snip")
    
    # Level 2: microcompact
    if target_level.value >= HygieneLevel.MICRO.value:
        before = len(current)
        current = collapse_consecutive(current)
        if len(current) < before:
            applied.append("microcompact")
    
    # Level 3: collapse
    if target_level.value >= HygieneLevel.COLLAPSE.value:
        before = len(current)
        current = collapse_old_turns(current, keep_recent=15)
        if len(current) < before:
            applied.append("collapse")
    
    # Level 4: autocompact
    if target_level.value >= HygieneLevel.AUTO.value:
        current, _ = autocompact(current)
        applied.append("autocompact")
    
    reduction = (1 - len(current) / original_count) if original_count > 0 else 0
    
    return HygieneResult(
        level=target_level,
        original_count=original_count,
        final_count=len(current),
        reduction_ratio=reduction,
        applied=applied,
    )
