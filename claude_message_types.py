# -*- coding: utf-8 -*-
"""
claude_message_types.py - Claude Code 系统消息类型枚举

来源: Claude Code utils/messages.ts (5513行)
       Claude Code services/claude.ts (3420行)

Claude Code 有20+种系统消息类型，每种都有特定格式和用途。

类型分类:
- Session: session生命周期
- Tool: 工具调用相关
- Hook: 钩子执行相关
- Cache: Prompt Cache相关
- Analytics: 使用量/指标
- Memory: 记忆相关
- State: 状态更新
- Error: 错误信息
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


class ClaudeMessageType(Enum):
    """
    Claude Code 20+ 系统消息类型。
    
    来源: Claude Code messages.ts SystemMessageType
    """
    # ─── Session ─────────────────────────────────────────
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_RESUMED = "session_resumed"
    
    # ─── Tool ─────────────────────────────────────────
    TOOL_USE_START = "tool_use_start"
    TOOL_USE_END = "tool_use_end"
    TOOL_USE_ERROR = "tool_use_error"
    TOOL_USE_RESULT = "tool_use_result"
    TOOL_USE_SUMMARY = "tool_use_summary"
    
    # ─── Hook ─────────────────────────────────────────
    HOOK_STARTED = "hook_started"
    HOOK_COMPLETED = "hook_completed"
    HOOK_FAILED = "hook_failed"
    HOOK_PERMISSION_REQUEST = "hook_permission_request"
    
    # ─── Cache ─────────────────────────────────────────
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_PARTIAL_HIT = "cache_partial_hit"
    
    # ─── Analytics ─────────────────────────────────────────
    API_METRICS = "api_metrics"          # candidates/cached/turns
    BRIDGE_STATUS = "bridge_status"        # 桥接状态
    REQUEST_START_EVENT = "request_start_event"
    AWAY_SUMMARY = "away_summary"          # 离开摘要
    TOMBSTONE = "tombstone"              # 占位符
    
    # ─── Memory ─────────────────────────────────────────
    MEMORY_SAVED = "memory_saved"
    MEMORY_LOADED = "memory_loaded"
    
    # ─── State ─────────────────────────────────────────
    STATE_UPDATE = "state_update"
    STOP_HOOK_SUMMARY = "stop_hook_summary"  # Stop钩子摘要
    
    # ─── Error ─────────────────────────────────────────
    ERROR_MESSAGE = "error"
    WARNING_MESSAGE = "warning"
    
    # ─── Claude Code 特有 ─────────────────────────────────────────
    STOP_REASON = "stop_reason"            # 为什么停止
    COMPLETION_PHRASE = "completion_phrase"  # 完成短语
    
    # ─── MCP 特有 ─────────────────────────────────────────
    MCP_TOOL_RESULT = "mcp_tool_result"
    MCP_SERVER_ERROR = "mcp_server_error"


# 类型元数据映射
MESSAGE_TYPE_META: Dict[ClaudeMessageType, Dict[str, Any]] = {
    ClaudeMessageType.SESSION_START: {
        "description": "会话开始",
        "fields": ["session_id", "timestamp", "model", "tools"],
        "category": "session",
    },
    ClaudeMessageType.SESSION_END: {
        "description": "会话结束",
        "fields": ["session_id", "duration_ms", "exit_code"],
        "category": "session",
    },
    ClaudeMessageType.TOOL_USE_START: {
        "description": "工具调用开始",
        "fields": ["tool_name", "tool_use_id", "input"],
        "category": "tool",
    },
    ClaudeMessageType.TOOL_USE_END: {
        "description": "工具调用结束",
        "fields": ["tool_name", "tool_use_id", "duration_ms", "output"],
        "category": "tool",
    },
    ClaudeMessageType.TOOL_USE_SUMMARY: {
        "description": "工具使用统计摘要",
        "fields": ["total_tools", "total_duration_ms", "success_count", "error_count"],
        "category": "tool",
    },
    ClaudeMessageType.API_METRICS: {
        "description": "API使用指标",
        "fields": ["candidates_tokens", "cached_tokens", "turns", "cache_hit_ratio"],
        "category": "analytics",
    },
    ClaudeMessageType.CACHE_HIT: {
        "description": "Prompt Cache命中",
        "fields": ["cached_tokens", "节省tokens"],
        "category": "cache",
    },
    ClaudeMessageType.CACHE_PARTIAL_HIT: {
        "description": "Prompt Cache部分命中",
        "fields": ["cached_tokens", "new_tokens"],
        "category": "cache",
    },
    ClaudeMessageType.HOOK_PERMISSION_REQUEST: {
        "description": "钩子权限请求（需用户确认）",
        "fields": ["hook_name", "tool_name", "reason"],
        "category": "hook",
    },
    ClaudeMessageType.STOP_HOOK_SUMMARY: {
        "description": "Stop钩子执行摘要",
        "fields": ["hook_result", "stop_reason", "summary"],
        "category": "hook",
    },
    ClaudeMessageType.MEMORY_SAVED: {
        "description": "记忆已保存",
        "fields": ["memory_type", "content_preview", "size_bytes"],
        "category": "memory",
    },
    ClaudeMessageType.TOMBSTONE: {
        "description": "占位符（历史记录保留标记）",
        "fields": ["original_timestamp", "reason"],
        "category": "state",
    },
    ClaudeMessageType.ERROR_MESSAGE: {
        "description": "错误信息",
        "fields": ["error_type", "message", "recoverable"],
        "category": "error",
    },
    ClaudeMessageType.WARNING_MESSAGE: {
        "description": "警告信息",
        "fields": ["warning_type", "message"],
        "category": "error",
    },
}


@dataclass
class SystemMessage:
    """系统消息"""
    type: ClaudeMessageType
    content: Any
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def category(self) -> str:
        return MESSAGE_TYPE_META.get(self.type, {}).get("category", "unknown")
    
    @property
    def description(self) -> str:
        return MESSAGE_TYPE_META.get(self.type, {}).get("description", self.type.value)


def parse_message(raw: Dict[str, Any]) -> SystemMessage:
    """
    解析原始消息字典为 SystemMessage。
    """
    type_str = raw.get("type", "")
    try:
        msg_type = ClaudeMessageType(type_str)
    except ValueError:
        msg_type = ClaudeMessageType.ERROR_MESSAGE
    
    return SystemMessage(
        type=msg_type,
        content=raw.get("content", ""),
        timestamp=raw.get("timestamp", ""),
        metadata=raw.get("metadata", {}),
    )


def get_messages_by_category(messages: List[SystemMessage], category: str) -> List[SystemMessage]:
    """按类别过滤消息"""
    return [m for m in messages if m.category == category]


def format_metrics_summary(messages: List[SystemMessage]) -> str:
    """格式化分析摘要（来自API_METRICS消息）"""
    metrics = [m for m in messages if m.type == ClaudeMessageType.API_METRICS]
    if not metrics:
        return "No API metrics available"
    
    latest = metrics[-1]
    content = latest.content if isinstance(latest.content, dict) else {}
    
    total = content.get("candidates_tokens", 0)
    cached = content.get("cached_tokens", 0)
    ratio = cached / total if total > 0 else 0
    
    lines = [
        "API Metrics:",
        f"  Total: {total:,} tokens",
        f"  Cached: {cached:,} tokens ({ratio:.0%})",
        f"  Cache hit ratio: {ratio:.0%}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Claude Code Message Types ===")
    print(f"Total types: {len(ClaudeMessageType)}")
    
    print("\nBy Category:")
    categories = {}
    for t in ClaudeMessageType:
        cat = MESSAGE_TYPE_META.get(t, {}).get("category", "unknown")
        categories.setdefault(cat, []).append(t)
    
    for cat, members in sorted(categories.items()):
        print(f"\n{cat.upper()} ({len(members)}):")
        for t in members:
            meta = MESSAGE_TYPE_META.get(t, {})
            print(f"  {t.value}: {meta.get('description', t.value)}")
    
    print("\n=== Parse Test ===")
    raw_msg = {"type": "api_metrics", "content": {"candidates_tokens": 50000, "cached_tokens": 37500}, "timestamp": "2026-04-14T12:00:00Z"}
    msg = parse_message(raw_msg)
    print(f"Type: {msg.type.value}, Category: {msg.category}, Description: {msg.description}")
    
    print("\n=== Metrics Summary ===")
    msgs = [SystemMessage(type=ClaudeMessageType.API_METRICS, content={"candidates_tokens": 100000, "cached_tokens": 75000})]
    print(format_metrics_summary(msgs))
