# -*- coding: utf-8 -*-
"""
agents/ — qclaw 多角色 Agent 系统

Claude Code 7原则完整落地 + 运行时实现。

模块：
    agent_types.py           — 角色定义（Verify/Explore/Plan/General）
    tool_pipeline.py         — 工具执行管道（15步，含三层防护）
    exec_adapter.py          — exec适配器 + cleanup chain
    multi_agent_dispatcher.py — Agent运行时调度器 ← 新增
    tool_registry.py         — qclaw工具注册表 ← 新增
    prompt_cache_manager.py  — Prompt Cache管理器 ← 新增

使用方式：
    from agents import (
        AgentRole, get_profile,
        MultiAgentDispatcher, create_dispatcher,
        ToolRegistry, get_tool_registry,
        PromptCacheManager, apply_prompt_cache,
    )
"""

# ── 角色系统 ──────────────────────────────────────────────────
from .agent_types import (
    AgentRole,
    AgentProfile,
    READ_ONLY_TOOLS,
    READ_WRITE_TOOLS,
    get_profile,
    get_system_prompt,
    get_task_prompt,
    # 便捷函数
    verify,
    explore,
    plan,
)

# ── 工具执行 ─────────────────────────────────────────────────
from .tool_pipeline import (
    RiskLevel,
    PipelineContext,
    PipelineResult,
    PipelineStep,
    HookResult,           # v2.0: FailedAbort级联
    HookResponse,         # v2.0: Hook执行响应
    HookOutcome,         # v2.2: 泛型分发outcome
    ConfiguredHandler,   # v2.2: hook配置单元
    HookDispatcher,      # v2.2: 泛型分发器
    PromptDecision,      # v2.0: ASK弹窗决策
    PromptRequest,       # v2.0: ASK弹窗请求
    execute_tool,
    execute_pipeline,
)

# ── Cleanup / Session ────────────────────────────────────────
from .exec_adapter import (
    exec_command,
    exec_background,
    kill_process_tree,
    cleanup_session,
    cleanup_all,
    cleanup_stale_processes,
    save_session_state,
    load_session_state,
    get_active_processes,
)

# ── 调度器 ───────────────────────────────────────────────────
from .multi_agent_dispatcher import (
    MultiAgentDispatcher,
    TaskContext,
    TaskStatus,
    AgentOutput,
    create_dispatcher,
    create_qclaw_dispatcher,
    create_qclaw_dispatcher_with_bridge,
)

# ── 工具注册表 ───────────────────────────────────────────────
from .tool_registry import (
    Tool,
    ToolCategory,
    ToolRegistry,
    get_tool_registry,
    reset_tool_registry,
    execute_tool_with_registry,
)

# ── Prompt Cache ─────────────────────────────────────────────
from .prompt_cache_manager import (
    CacheStrategy,
    PromptCacheManager,
    get_cache_manager,
    apply_prompt_cache,
    estimate_cache_saving,
)

# ── 事件总线 ───────────────────────────────────────────────
from .event_bus import (
    EventType,
    Event,
    EventBus,
    TurnStartedEvent,
    TurnCompletedEvent,
    TurnUsageEvent,
    ToolStartedEvent,
    ToolCompletedEvent,
    ToolFailedEvent,
    HookStartedEvent,
    HookCompletedEvent,
    ContextCompactedEvent,
    get_event_bus,
    emit,
)

# ── Managed Agents 桥接 ───────────────────────────────────
from .managed_bridge import (
    WorkflowMode,
    recommend_workflow,
    CredentialConfig,
    create_credential_vault,
    SessionEventLogger,
    ContextBridge,
    HITL_DANGEROUS_OPERATIONS,
    requires_human_approval,
    discover_skills_for_registry,
    create_protocol_dispatcher,
    ManagedBridgeConfig,
    ManagedBridge,
    create_bridge,
)

__all__ = [
    # agent_types
    "AgentRole", "AgentProfile", "get_profile",
    "get_system_prompt", "get_task_prompt",
    "verify", "explore", "plan",
    "READ_ONLY_TOOLS", "READ_WRITE_TOOLS",
    # tool_pipeline
    "RiskLevel", "PipelineContext", "PipelineResult", "PipelineStep",
    "HookResult", "HookResponse", "HookOutcome", "ConfiguredHandler", "HookDispatcher",
    "PromptDecision", "PromptRequest",
    "execute_tool", "execute_pipeline",
    # exec_adapter
    "exec_command", "exec_background", "kill_process_tree",
    "cleanup_session", "cleanup_all", "cleanup_stale_processes",
    "save_session_state", "load_session_state", "get_active_processes",
    # dispatcher
    "MultiAgentDispatcher", "TaskContext", "TaskStatus", "AgentOutput",
    "create_dispatcher", "create_qclaw_dispatcher", "create_qclaw_dispatcher_with_bridge",
    # registry
    "Tool", "ToolCategory", "ToolRegistry",
    "get_tool_registry", "reset_tool_registry",
    "execute_tool_with_registry",
    # cache
    "CacheStrategy", "PromptCacheManager",
    "get_cache_manager", "apply_prompt_cache", "estimate_cache_saving",
    # event_bus
    "EventType", "Event", "EventBus",
    "TurnStartedEvent", "TurnCompletedEvent", "TurnUsageEvent",
    "ToolStartedEvent", "ToolCompletedEvent", "ToolFailedEvent",
    "HookStartedEvent", "HookCompletedEvent", "ContextCompactedEvent",
    "get_event_bus", "emit",
    # managed_bridge
    "WorkflowMode", "recommend_workflow",
    "CredentialConfig", "create_credential_vault",
    "SessionEventLogger", "ContextBridge",
    "HITL_DANGEROUS_OPERATIONS", "requires_human_approval",
    "discover_skills_for_registry", "create_protocol_dispatcher",
    "ManagedBridgeConfig", "ManagedBridge", "create_bridge",
]

__version__ = "2.0.0"
