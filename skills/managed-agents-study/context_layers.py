# -*- coding: utf-8 -*-
"""
context_layers.py — 三层上下文体系（Anthropic Managed Agents 落地）

对应 CMA / Claude Code 的三层上下文管理：
1. 持久层（Session）— append-only JSONL，永不丢数据
2. 管理层（Compact）— 压缩/裁剪/变换，策略可切换
3. 视图层（Context Window）— LLM 实际看到的消息序列

核心原则：
- Session ≠ Context Window
- Session 是完整的执行事实流，Context Window 是它的一个变换视图
- 不做不可逆的上下文丢弃决策

参考：
- Claude Code sessionStorage.ts / recordTranscript()
- Claude Code services/compact/ 11个文件
- Claude Code normalizeMessagesForAPI()
- "Scaling Managed Agents" 官方工程博客
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

log = logging.getLogger("qclaw.context_layers")

# ─── 上下文层枚举 ─────────────────────────────────────────

class ContextLayer(Enum):
    PERSIST = "persist"       # 持久层：Session，append-only
    COMPACT = "compact"       # 管理层：压缩/裁剪/变换
    VIEW = "view"             # 视图层：Context Window


# ─── 压缩策略 ─────────────────────────────────────────────

class CompactStrategy(Enum):
    """Claude Code 的4种压缩策略（Feature Gate 控制）"""
    AUTO_COMPACT = "auto_compact"           # 超阈值自动摘要
    MICRO_COMPACT = "micro_compact"         # 每轮轻压缩
    REACTIVE_COMPACT = "reactive_compact"   # 响应式动态压缩
    HISTORY_SNIP = "history_snip"           # 基于标记的历史裁剪


# ─── 持久层：Session Event ────────────────────────────────

@dataclass
class PersistEvent:
    """持久层事件（append-only，不可修改）"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    role: str = ""                  # user / assistant / tool / system
    content: str = ""
    tool_name: Optional[str] = None
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Optional[str] = None
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── 管理层：Compact Boundary ─────────────────────────────

@dataclass
class CompactBoundary:
    """
    压缩边界标记（参考 Claude Code createCompactBoundaryMessage）
    
    关键设计：压缩后原始消息仍然在 Session 中，
    preservedSegment 确保可以回溯到原始消息。
    """
    boundary_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    strategy: CompactStrategy = CompactStrategy.AUTO_COMPACT
    events_before: int = 0          # 压缩前的事件数
    events_after: int = 0           # 压缩后的事件数
    tokens_before: int = 0          # 压缩前 token 数
    tokens_after: int = 0           # 压缩后 token 数
    preserved_segment: str = ""     # 保留片段（可回溯）
    summary: str = ""               # 压缩摘要
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


# ─── 视图层：Context Window Message ───────────────────────

@dataclass
class ViewMessage:
    """视图层消息（LLM 实际看到的内容）"""
    role: str = ""          # system / user / assistant
    content: str = ""
    token_count: int = 0
    is_compact_boundary: bool = False
    original_event_ids: List[str] = field(default_factory=list)  # 可回溯到原始事件


# ─── 三层上下文管理器 ─────────────────────────────────────

class ContextManager:
    """
    三层上下文管理器
    
    对应 Claude Code 的 transcript → compact → normalizeForAPI 管道。
    
    持久层：完整记录一切事件，永不丢数据
    管理层：多种压缩策略可切换，压缩后不丢失原始数据
    视图层：生成 LLM 实际看到的上下文，支持 Prompt Cache
    """

    def __init__(self, max_context_tokens: int = 128000,
                 compact_threshold: float = 0.85,
                 max_consecutive_failures: int = 3):
        self.max_context_tokens = max_context_tokens
        self.compact_threshold = compact_threshold    # 85% 触发压缩
        self.max_consecutive_failures = max_consecutive_failures
        
        # 持久层
        self._events: List[PersistEvent] = []
        # 管理层
        self._boundaries: List[CompactBoundary] = []
        self._current_strategy = CompactStrategy.AUTO_COMPACT
        self._consecutive_failures = 0
        # 视图层缓存
        self._view_cache: Optional[List[ViewMessage]] = None
        self._view_dirty = True

    # ─── 持久层：追加事件 ─────────────────────────────────

    def append_event(self, role: str, content: str,
                     tool_name: str = None, tool_input: Dict = None,
                     tool_output: str = None, token_count: int = 0) -> PersistEvent:
        """
        追加事件到持久层（append-only，不可修改）
        
        对应 Claude Code: recordTranscript()
        """
        event = PersistEvent(
            role=role,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input or {},
            tool_output=tool_output,
            token_count=token_count,
        )
        self._events.append(event)
        self._view_dirty = True
        return event

    def get_events(self, from_index: int = 0, to_index: int = None) -> List[PersistEvent]:
        """获取持久层事件切片（positional slicing）"""
        if to_index:
            return self._events[from_index:to_index]
        return self._events[from_index:]

    # ─── 管理层：压缩策略 ─────────────────────────────────

    def check_compact_needed(self) -> bool:
        """检查是否需要压缩（超过阈值）"""
        total_tokens = sum(e.token_count for e in self._events)
        return total_tokens > self.max_context_tokens * self.compact_threshold

    def compact(self, strategy: CompactStrategy = None,
                summary_fn=None) -> Optional[CompactBoundary]:
        """
        执行上下文压缩
        
        对应 Claude Code compact service 的4种策略。
        
        Args:
            strategy: 压缩策略（None=使用当前策略）
            summary_fn: 外部摘要函数（传入 LLM 生成摘要）
                        签名: (events: List[PersistEvent]) -> str
        
        关键：压缩后原始事件仍在 self._events 中，不删除。
        CompactBoundary 的 preserved_segment 确保可回溯。
        """
        if strategy:
            self._current_strategy = strategy
        else:
            strategy = self._current_strategy
        
        events_before = len(self._events)
        tokens_before = sum(e.token_count for e in self._events)
        
        # 确定要压缩的事件范围
        if strategy == CompactStrategy.AUTO_COMPACT:
            # 压缩除了最近10条之外的所有事件
            compact_start = 0
            compact_end = max(0, len(self._events) - 10)
        elif strategy == CompactStrategy.MICRO_COMPACT:
            # 只压缩当前轮
            compact_start = max(0, len(self._events) - 3)
            compact_end = len(self._events)
        elif strategy == CompactStrategy.HISTORY_SNIP:
            # 基于标记裁剪（找最后一个 boundary 之前的事件）
            if self._boundaries:
                compact_start = 0
                compact_end = self._boundaries[-1].events_before
            else:
                compact_start = 0
                compact_end = max(0, len(self._events) - 10)
        else:  # REACTIVE_COMPACT
            compact_start = 0
            compact_end = max(0, len(self._events) - 5)
        
        if compact_end <= compact_start:
            return None
        
        # 生成摘要
        compacted_events = self._events[compact_start:compact_end]
        if summary_fn:
            summary = summary_fn(compacted_events)
        else:
            # 默认摘要：提取关键事件
            summary = self._default_summary(compacted_events)
        
        # 保留片段（可回溯）
        preserved = "\n".join(
            f"[{e.role}] {e.content[:100]}" 
            for e in compacted_events[:5]
        )
        
        boundary = CompactBoundary(
            strategy=strategy,
            events_before=events_before,
            events_after=len(self._events),  # 原始事件不删除
            tokens_before=tokens_before,
            tokens_after=tokens_before,      # 实际压缩在视图层
            preserved_segment=preserved,
            summary=summary,
        )
        self._boundaries.append(boundary)
        self._view_dirty = True
        
        # 熔断器：连续失败 max_consecutive_failures 次停止
        if not summary:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.max_consecutive_failures:
                log.warning("Compact circuit breaker triggered: %d consecutive failures",
                            self._consecutive_failures)
        else:
            self._consecutive_failures = 0
        
        return boundary

    def _default_summary(self, events: List[PersistEvent]) -> str:
        """默认摘要逻辑（不调用 LLM 时的降级方案）"""
        lines = []
        for e in events:
            if e.role == "user":
                lines.append(f"User: {e.content[:80]}")
            elif e.role == "assistant":
                lines.append(f"Assistant: {e.content[:80]}")
            elif e.role == "tool" and e.tool_name:
                result = (e.tool_output or "")[:50]
                lines.append(f"Tool({e.tool_name}): {result}")
        return "\n".join(lines[:20])

    # ─── 视图层：生成 LLM 上下文 ──────────────────────────

    def render_view(self, system_prompt: str = "") -> List[ViewMessage]:
        """
        生成视图层消息序列（LLM 实际看到的上下文）
        
        对应 Claude Code: normalizeMessagesForAPI()
        
        流程：
        1. System prompt
        2. Compact boundary summaries（替换被压缩的事件）
        3. 未压缩的原始事件
        4. Token 预算控制
        """
        if not self._view_dirty and self._view_cache is not None:
            return self._view_cache
        
        messages = []
        
        # System prompt
        if system_prompt:
            messages.append(ViewMessage(
                role="system",
                content=system_prompt,
                token_count=len(system_prompt) // 4,
            ))
        
        # 确定哪些事件已被压缩
        compacted_ranges = []
        last_end = 0
        for boundary in self._boundaries:
            # 插入压缩摘要
            messages.append(ViewMessage(
                role="system",
                content=f"[Context Compacted - {boundary.strategy.value}]\n{boundary.summary}",
                token_count=len(boundary.summary) // 4,
                is_compact_boundary=True,
            ))
            last_end = boundary.events_before
        
        # 未压缩的原始事件
        for event in self._events[last_end:]:
            content = event.content
            if event.tool_name:
                content = f"[Tool: {event.tool_name}] {event.tool_output or event.content}"
            messages.append(ViewMessage(
                role=event.role,
                content=content,
                token_count=event.token_count,
                original_event_ids=[event.event_id],
            ))
        
        # Token 预算控制
        total_tokens = sum(m.token_count for m in messages)
        if total_tokens > self.max_context_tokens:
            # 从最早的 non-system 消息开始截断
            while total_tokens > self.max_context_tokens * 0.9 and len(messages) > 2:
                removed = messages.pop(1)  # 不删 system prompt 和最后一条
                total_tokens -= removed.token_count
        
        self._view_cache = messages
        self._view_dirty = False
        return messages

    # ─── 大输出持久化 ─────────────────────────────────────

    def persist_large_output(self, event_id: str, output: str,
                             max_chars: int = 8000) -> Tuple[str, str]:
        """
        大输出持久化（参考 Claude Code PERSISTED_OUTPUT_TAG）
        
        当工具输出超过阈值时：
        1. 将完整输出持久化到磁盘
        2. 在 Context Window 中只放摘要
        
        Returns: (persisted_path, summary_text)
        """
        if len(output) <= max_chars:
            return "", output
        
        # 持久化到文件
        persist_dir = Path(r"C:\Users\yiseg\.qclaw\persisted_output")
        persist_dir.mkdir(parents=True, exist_ok=True)
        filepath = persist_dir / f"{event_id}.txt"
        filepath.write_text(output, encoding="utf-8")
        
        # 生成摘要
        summary = f"[PERSISTED_OUTPUT: {filepath}]\n{output[:200]}...\n(Use FileRead to access full output)"
        return str(filepath), summary

    # ─── 统计信息 ─────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取上下文统计信息"""
        total_tokens = sum(e.token_count for e in self._events)
        return {
            "total_events": len(self._events),
            "total_tokens": total_tokens,
            "compact_boundaries": len(self._boundaries),
            "current_strategy": self._current_strategy.value,
            "consecutive_failures": self._consecutive_failures,
            "compact_needed": self.check_compact_needed(),
            "token_usage_pct": round(total_tokens / self.max_context_tokens * 100, 1),
        }
