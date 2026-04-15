# -*- coding: utf-8 -*-
"""
fork_tracker.py - Fork 参数追踪与 Cache-safe 参数管理

来源: Claude Code utils/forkedAgent.ts (690行)
       tools/AgentTool/forkSubagent.ts (211行)

用途: 管理子代理 fork 的参数，确保 Prompt Cache 兼容性

核心洞察（Claude Code forkedAgent.ts）：
- Anthropic API cache key = system_prompt + tools + model + messages(prefix) + thinking_config
- 任何参数改变 → cache miss
- fork 传递"已渲染的 system prompt 字节"而不是重新计算
- cloned FileStateCache → 父和子文件系统状态隔离

Cache-safe 参数必须与父请求完全一致：
1. system_prompt（已渲染字节，不是重新计算）
2. user_context（影响 cache）
3. system_context（影响 cache）
4. tool_use_context（工具+模型+选项）
5. fork_context_messages（父上下文消息）
6. thinking_config（思考配置）
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ForkState(Enum):
    """Fork 状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ForkParams:
    """
    Cache-safe 参数（必须与父请求一致以确保 cache 命中）
    
    Claude Code forkedAgent.ts CacheSafeParams:
    - system_prompt: 必须与父一致才能 cache 命中
    - user_context: prepended to messages，影响 cache
    - system_context: appended to system prompt，影响 cache
    - tool_use_context: 工具+模型+选项
    - fork_context_messages: 父上下文消息
    - thinking_config: 思考配置
    """
    task: str
    parent_session_id: str = ""
    system_prompt_bytes: str = ""   # 已渲染字节，不重新计算
    user_context: Dict[str, str] = field(default_factory=dict)
    system_context: Dict[str, str] = field(default_factory=dict)
    model: str = ""
    thinking_config: Optional[Dict[str, Any]] = None
    
    # 文件状态（隔离克隆）
    file_state_snapshot: Optional[str] = None
    
    # 使用量追踪
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hits: int = 0


@dataclass
class ForkEvent:
    """Fork 执行事件"""
    timestamp: str
    fork_id: str
    params: ForkParams
    state: ForkState
    duration_ms: float = 0.0
    cache_hit: bool = False
    error: Optional[str] = None


class ForkTracker:
    """
    Fork 参数追踪器
    
    管理所有 fork 操作的 Cache-safe 参数，确保子代理与父请求的 cache 兼容性。
    
    Claude Code forkedAgent.ts 模式：
    1. saveCacheSafeParams() — 保存当前请求的 cache-safe 参数
    2. getLastCacheSafeParams() — 获取最近一次参数
    3. 每次 fork 调用时记录到事件日志
    """
    
    def __init__(self):
        self._last_params: Optional[ForkParams] = None
        self._active_forks: Dict[str, ForkParams] = {}
        self._events: List[ForkEvent] = []
        self._fork_count: int = 0
    
    def save_params(self, params: ForkParams) -> None:
        """保存 cache-safe 参数（fork 前调用）"""
        self._last_params = params
    
    def get_last_params(self) -> Optional[ForkParams]:
        """获取最近一次保存的参数"""
        return self._last_params
    
    def start_fork(self, task: str, parent_session: str = "") -> str:
        """
        开始一个 fork。
        
        Returns: fork_id
        """
        self._fork_count += 1
        fork_id = f"fork_{self._fork_count}_{int(time.time())}"
        
        params = ForkParams(
            task=task,
            parent_session_id=parent_session,
            system_prompt_bytes=self._last_params.system_prompt_bytes if self._last_params else "",
            user_context=self._last_params.user_context.copy() if self._last_params else {},
            system_context=self._last_params.system_context.copy() if self._last_params else {},
            model=self._last_params.model if self._last_params else "",
            thinking_config=self._last_params.thinking_config.copy() if self._last_params and self._last_params.thinking_config else None,
        )
        
        self._active_forks[fork_id] = params
        
        self._events.append(ForkEvent(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            fork_id=fork_id,
            params=params,
            state=ForkState.PENDING,
        ))
        
        return fork_id
    
    def complete_fork(self, fork_id: str, 
                      prompt_tokens: int = 0,
                      completion_tokens: int = 0,
                      cache_hit: bool = False,
                      error: str = None) -> None:
        """
        记录 fork 完成（成功或失败）
        """
        if fork_id not in self._active_forks:
            return
        
        params = self._active_forks[fork_id]
        params.prompt_tokens = prompt_tokens
        params.completion_tokens = completion_tokens
        
        # 更新事件
        for ev in reversed(self._events):
            if ev.fork_id == fork_id:
                ev.state = ForkState.COMPLETED if not error else ForkState.FAILED
                ev.cache_hit = cache_hit
                ev.error = error
                ev.params = params
                ev.duration_ms = 0  # TODO: 计算 duration
                break
    
    def check_cache_compatibility(self, params: ForkParams) -> Dict[str, Any]:
        """
        检查参数是否与最后一次保存的参数 cache 兼容。
        
        Returns: {
            "compatible": bool,
            "diff": dict of changed fields
        }
        """
        if not self._last_params:
            return {"compatible": False, "reason": "no_previous_params"}
        
        last = self._last_params
        diff = {}
        
        checks = [
            ("system_prompt_bytes", params.system_prompt_bytes, last.system_prompt_bytes),
            ("model", params.model, last.model),
            ("thinking_config", str(params.thinking_config), str(last.thinking_config)),
        ]
        
        for name, new_val, old_val in checks:
            if new_val != old_val:
                diff[name] = {"new": str(new_val)[:50], "old": str(old_val)[:50]}
        
        return {
            "compatible": len(diff) == 0,
            "diff": diff,
        }
    
    def format_fork_summary(self) -> str:
        """格式化 fork 摘要（用于日志/报告）"""
        if not self._events:
            return "No forks recorded"
        
        total = len(self._events)
        completed = sum(1 for e in self._events if e.state == ForkState.COMPLETED)
        cache_hits = sum(1 for e in self._events if e.cache_hit)
        failed = sum(1 for e in self._events if e.state == ForkState.FAILED)
        
        total_prompt = sum(e.params.prompt_tokens for e in self._events)
        total_completion = sum(e.params.completion_tokens for e in self._events)
        
        return (
            f"Fork Summary: {completed}/{total} completed, "
            f"{cache_hits} cache hits, {failed} failed\n"
            f"Total tokens: {total_prompt:,} prompt + {total_completion:,} completion"
        )


# Singleton
_tracker: Optional[ForkTracker] = None

def get_fork_tracker() -> ForkTracker:
    global _tracker
    if _tracker is None:
        _tracker = ForkTracker()
    return _tracker


if __name__ == "__main__":
    # 测试
    tracker = ForkTracker()
    
    # 模拟父请求参数
    parent_params = ForkParams(
        task="Build REST API",
        system_prompt_bytes="[SYSTEM PROMPT 500 tokens...]",
        user_context={"file": "api.py"},
        model="claude-sonnet-4-20250514",
        thinking_config={"type": "enabled", "budget_tokens": 10000},
    )
    
    # 保存父参数
    tracker.save_params(parent_params)
    print("Parent params saved")
    
    # 检查兼容性
    same = tracker.check_cache_compatibility(parent_params)
    print(f"Same params compatible: {same['compatible']}")
    
    # 创建 fork
    fork_id = tracker.start_fork("Add JWT auth", "session-123")
    print(f"Fork started: {fork_id}")
    
    # 完成 fork
    tracker.complete_fork(fork_id, prompt_tokens=50000, completion_tokens=3000, cache_hit=True)
    
    # 不兼容的 fork（不同 model）
    bad_params = ForkParams(
        task="Add JWT auth",
        system_prompt_bytes="[DIFFERENT SYSTEM PROMPT]",
        model="claude-opus-4",  # 不同 model
    )
    compat = tracker.check_cache_compatibility(bad_params)
    print(f"Different model compatible: {compat['compatible']}")
    print(f"Diff: {compat['diff']}")
    
    # 摘要
    print(f"\n{tracker.format_fork_summary()}")
