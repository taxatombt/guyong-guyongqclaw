# -*- coding: utf-8 -*-
"""
agents/event_bus.py — qclaw 事件总线

参考 Codex protocol.rs EventMsg 设计：
- tagged enum + 推送式事件
- 所有生命周期节点都是事件
- 支持历史查询和 JSONL 导出

使用方式：
    from agents import EventType, EventBus, get_event_bus, emit
    from agents import ToolStartedEvent, ToolCompletedEvent, TurnUsageEvent
    
    bus = get_event_bus()
    bus.emit(ToolStartedEvent(tool_name="exec", tool_input={"command": "ls"}))
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable, Literal
from enum import Enum


# ─── 事件类型枚举 ─────────────────────────────────────────

class EventType(Enum):
    # === 生命周期 ===
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    TURN_STARTED = "turn_started"
    TURN_COMPLETED = "turn_completed"
    
    # === 工具执行 ===
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    
    # === Hook ===
    HOOK_STARTED = "hook_started"
    HOOK_COMPLETED = "hook_completed"
    
    # === 任务 ===
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    
    # === 上下文 ===
    CONTEXT_COMPACTED = "context_compacted"


# ─── 基类 ────────────────────────────────────────────────

@dataclass
class Event:
    """所有事件的基类（参考 Codex EventMsg 的 serde tag 模式）"""
    type: EventType
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        d = {"type": self.type.value, "timestamp": self.timestamp}
        if self.session_id:
            d["session_id"] = self.session_id
        if self.turn_id:
            d["turn_id"] = self.turn_id
        return d


# ─── 具体事件类 ───────────────────────────────────────────

@dataclass
class TurnStartedEvent(Event):
    """Turn 开始事件"""
    model_context_window: Optional[int] = None
    type: EventType = field(default=EventType.TURN_STARTED, init=False)


@dataclass
class TurnCompletedEvent(Event):
    """Turn 完成事件"""
    duration_ms: float = 0.0
    last_agent_message: Optional[str] = None
    type: EventType = field(default=EventType.TURN_COMPLETED, init=False)


@dataclass
class ToolStartedEvent(Event):
    """工具开始执行"""
    tool_name: str = ""
    tool_input: Any = None
    mutating: bool = False
    type: EventType = field(default=EventType.TOOL_STARTED, init=False)


@dataclass
class ToolCompletedEvent(Event):
    """工具执行完成"""
    tool_name: str = ""
    duration_ms: float = 0.0
    success: bool = True
    output_preview: str = ""   # 前200字符
    output_tokens: int = 0
    cached_tokens: int = 0      # KV-Cache命中（不计入成本）
    risk_level: str = "safe"
    type: EventType = field(default=EventType.TOOL_COMPLETED, init=False)


@dataclass
class ToolFailedEvent(Event):
    """工具执行失败"""
    tool_name: str = ""
    error: str = ""
    duration_ms: float = 0.0
    type: EventType = field(default=EventType.TOOL_FAILED, init=False)


@dataclass
class TurnUsageEvent(Event):
    """
    Token使用量事件（参考 Codex TokenUsage）
    
    billing = input_tokens - cached_input_tokens + output_tokens
    """
    input_tokens: int = 0
    cached_input_tokens: int = 0   # KV-Cache命中，不计入成本
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    type: EventType = field(default=EventType.TURN_COMPLETED, init=False)


@dataclass
class HookStartedEvent(Event):
    """Hook 开始"""
    hook_name: str = ""
    hook_event: str = ""          # "pre_tool_use" / "after_tool_use" / "after_agent"
    tool_name: str = ""
    type: EventType = field(default=EventType.HOOK_STARTED, init=False)


@dataclass
class HookCompletedEvent(Event):
    """Hook 完成"""
    hook_name: str = ""
    hook_event: str = ""
    tool_name: str = ""
    duration_ms: float = 0.0
    status: str = "success"       # "success" / "failed_continue" / "failed_abort"
    stop_reason: Optional[str] = None
    type: EventType = field(default=EventType.HOOK_COMPLETED, init=False)


@dataclass
class ContextCompactedEvent(Event):
    """上下文压缩"""
    reason: str = ""               # "auto" / "manual" / "token_limit"
    tokens_removed: int = 0
    tokens_remaining: int = 0
    type: EventType = field(default=EventType.CONTEXT_COMPACTED, init=False)


# ─── 事件总线 ──────────────────────────────────────────────

class EventBus:
    """
    qclaw 事件总线
    - 发布/订阅模式
    - 自动记录 session 内所有事件
    - 支持实时推送和历史查询
    
    参考 Codex protocol.rs EventMsg 的设计哲学：
    所有生命周期节点都是事件，不是日志
    """
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._handlers: dict[EventType, list] = {et: [] for et in EventType}
        self._history: list[Event] = []
        self._turn_counter = 0
    
    def emit(self, event: Event) -> None:
        """发布事件（同步）"""
        event.session_id = self.session_id
        self._history.append(event)
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception:
                pass  # 订阅者异常不阻断事件发布
    
    def on(self, event_type: EventType, handler: Callable[[Event], None]) -> Callable:
        """订阅事件，返回取消订阅的函数"""
        self._handlers[event_type].append(handler)
        def unsubscribe():
            self._handlers[event_type].remove(handler)
        return unsubscribe
    
    def once(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """一次性订阅（触发后自动取消）"""
        def wrapper(event: Event):
            handler(event)
            self._handlers[event_type].remove(wrapper)
        self._handlers[event_type].append(wrapper)
    
    def get_history(self, event_type: Optional[EventType] = None) -> list[Event]:
        """查询历史事件"""
        if event_type:
            return [e for e in self._history if e.type == event_type]
        return list(self._history)
    
    def next_turn_id(self) -> str:
        """生成下一个 turn ID"""
        self._turn_counter += 1
        return f"turn_{self._turn_counter}"
    
    def export_jsonl(self, path: str) -> int:
        """导出为 JSONL 格式（用于分析）"""
        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for e in self._history:
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
                count += 1
        return count
    
    def summary(self) -> dict:
        """事件统计摘要"""
        counts: dict[str, int] = {}
        for e in self._history:
            key = e.type.value
            counts[key] = counts.get(key, 0) + 1
        return {
            "session_id": self.session_id,
            "total_events": len(self._history),
            "by_type": counts,
        }


# ─── 全局默认实例 ─────────────────────────────────────────

_default_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    """获取全局事件总线实例"""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus

def emit(event: Event) -> None:
    """快捷发布函数"""
    get_event_bus().emit(event)
