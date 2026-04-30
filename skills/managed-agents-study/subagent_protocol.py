# -*- coding: utf-8 -*-
"""
subagent_protocol.py — Subagent 通信协议（Anthropic Managed Agents 落地）

对应 CMA 的 Subagent 机制：
- 分而治之：主 Agent 将子任务委派给 Subagent
- 隔离上下文：子 Agent 有独立 context + 工具集 + 权限
- 结果压缩：子 Agent 输出需压缩后返回主 Agent

核心设计：
- SubagentRequest/Response 标准协议
- 权限隔离：DELEGATE_BLOCKED_TOOLS（子 Agent 禁用工具列表）
- MAX_DEPTH=2（最多2层委派）
- MAX_CONCURRENT=3（最多3个并行子 Agent）
- 结果压缩：truncate 大输出 + extract_key_findings()

与 CMA 对照：
  CMA: session → sub-agent → result → session.resume
  qclaw: SubagentRequest → sessions_spawn → SubagentResponse
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

log = logging.getLogger("qclaw.subagent_protocol")

# ─── 安全约束 ─────────────────────────────────────────────

# 子 Agent 禁用的工具列表（参考 Hermes DELEGATE_BLOCKED_TOOLS）
DELEGATE_BLOCKED_TOOLS = {
    "subagents",        # 禁止进一步委派（防止无限递归）
    "sessions_send",    # 禁止跨会话通信
    "exec",             # 禁止 shell 执行（子 Agent 只读）
    "edit",             # 禁止文件修改
    "write",            # 禁止文件写入
    "process",          # 禁止进程管理
    "canvas",           # 禁止 UI 操作
}

MAX_DELEGATE_DEPTH = 2        # 最多2层委派
MAX_CONCURRENT_CHILDREN = 3   # 最多3个并行子 Agent
RESULT_MAX_CHARS = 4000       # 结果压缩阈值


# ─── 子 Agent 角色 ────────────────────────────────────────

class SubagentRole(Enum):
    """子 Agent 角色（与 agents/agent_types.py 对齐）"""
    EXPLORE = "explore"     # 只读探索
    VERIFY = "verify"       # 对抗性验证
    PLAN = "plan"           # 纯规划
    EXECUTE = "execute"     # 执行（需要额外权限）


# ─── 请求/响应协议 ────────────────────────────────────────

@dataclass
class SubagentRequest:
    """
    主 Agent → 子 Agent 的请求
    
    对应 CMA 的 sub-agent 委派模式：
    - 父 Agent 定义任务 + 上下文 + 工具限制
    - 子 Agent 独立执行，返回压缩结果
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_session_id: str = ""
    task: str = ""                          # 子任务描述
    role: SubagentRole = SubagentRole.EXPLORE
    context: str = ""                       # 上下文注入（从父 Agent 的 Session 提取）
    allowed_tools: List[str] = field(default_factory=list)  # 空=只读工具
    max_depth: int = 1                      # 委派深度（0=不可委派）
    timeout_seconds: int = 120              # 超时时间
    priority: int = 0                       # 优先级（0=普通，1=高）

    def validate(self) -> Optional[str]:
        """验证请求合法性"""
        if not self.task:
            return "Task description is required"
        if self.max_depth > MAX_DELEGATE_DEPTH:
            return f"Max delegation depth exceeded: {self.max_depth} > {MAX_DELEGATE_DEPTH}"
        # 检查工具权限
        blocked = set(self.allowed_tools) & DELEGATE_BLOCKED_TOOLS
        if blocked and self.role != SubagentRole.EXECUTE:
            return f"Blocked tools requested for non-execute role: {blocked}"
        return None


@dataclass
class SubagentResponse:
    """
    子 Agent → 主 Agent 的响应
    
    对应 CMA 的 session.resume 模式：
    - 子 Agent 完成后，结果被压缩返回给父 Agent
    - 父 Agent 只看到 compressed_result，不看到子 Agent 的完整上下文
    """
    request_id: str = ""
    subagent_session_id: str = ""
    success: bool = False
    compressed_result: str = ""         # 压缩后的结果
    key_findings: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "success": self.success,
            "compressed_result": self.compressed_result[:200],  # 进一步截断
            "key_findings": self.key_findings[:5],
            "tools_used": self.tools_used,
            "error": self.error,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


# ─── 结果压缩 ─────────────────────────────────────────────

def compress_result(raw_output: str, max_chars: int = RESULT_MAX_CHARS) -> str:
    """
    压缩子 Agent 的原始输出
    
    策略：
    1. 如果 < max_chars，直接返回
    2. 否则：提取关键行 + 截断
    """
    if len(raw_output) <= max_chars:
        return raw_output

    # 提取关键行（含关键词的行 + 前后文）
    key_patterns = [
        r"(?i)(error|fail|success|pass|found|result|conclusion|verdict)",
        r"(?i)(TODO|FIXME|HACK|BUG)",
        r"^\s*[\-\*]\s+",  # 列表项
        r"^\s*\d+\.\s+",   # 编号列表
    ]
    
    lines = raw_output.split("\n")
    key_lines = []
    for i, line in enumerate(lines):
        for pat in key_patterns:
            if re.search(pat, line):
                # 取当前行 + 前后各1行
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                for j in range(start, end):
                    if lines[j] not in key_lines:
                        key_lines.append(lines[j])
                break
    
    result = "\n".join(key_lines)
    if len(result) > max_chars:
        result = result[:max_chars - 50] + "\n\n[... truncated ...]"
    
    return result


def extract_key_findings(raw_output: str) -> List[str]:
    """
    从子 Agent 输出中提取关键发现
    
    规则：
    - 以 "VERDICT:" 开头的行
    - 以数字编号开头的结论行
    - 包含 "found"/"error"/"pass"/"fail" 的行
    """
    import re
    findings = []
    for line in raw_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("VERDICT:"):
            findings.append(line)
        elif re.match(r"^\d+\.\s", line) and len(line) > 10:
            findings.append(line)
        elif re.search(r"(?i)(found|error|pass|fail|conclusion)", line) and len(line) > 15:
            findings.append(line)
    return findings[:10]  # 最多10条


# ─── Subagent 调度器 ──────────────────────────────────────

class SubagentDispatcher:
    """
    Subagent 调度器
    
    管理子 Agent 的创建、执行、结果回收。
    对应 CMA 的 multi-agent 协调模式。
    """

    def __init__(self):
        self._active_children: Dict[str, SubagentRequest] = {}
        self._completed: List[SubagentResponse] = []

    def can_spawn(self) -> bool:
        """检查是否可以创建新的子 Agent"""
        return len(self._active_children) < MAX_CONCURRENT_CHILDREN

    def dispatch(self, request: SubagentRequest) -> Optional[str]:
        """
        委派子任务给子 Agent
        
        Returns: 子 Agent 的 session_id，或 None（如果无法委派）
        """
        # 验证请求
        error = request.validate()
        if error:
            log.error(f"Subagent request validation failed: {error}")
            return None

        # 检查并发限制
        if not self.can_spawn():
            log.warning(f"Max concurrent children reached: {MAX_CONCURRENT_CHILDREN}")
            return None

        session_id = f"sub_{request.request_id}_{uuid.uuid4().hex[:4]}"
        self._active_children[session_id] = request
        log.info(f"Dispatched subagent {session_id}: {request.task[:50]}...")
        return session_id

    def complete(self, session_id: str, raw_output: str,
                 success: bool, error: str = None) -> SubagentResponse:
        """
        子 Agent 完成，压缩结果并回收
        """
        request = self._active_children.pop(session_id, None)
        if not request:
            log.warning(f"Unknown subagent session: {session_id}")
            return SubagentResponse(success=False, error="Unknown session")

        response = SubagentResponse(
            request_id=request.request_id,
            subagent_session_id=session_id,
            success=success,
            compressed_result=compress_result(raw_output),
            key_findings=extract_key_findings(raw_output),
            error=error,
        )
        self._completed.append(response)
        return response

    def get_active_count(self) -> int:
        return len(self._active_children)

    def get_completed_results(self) -> List[SubagentResponse]:
        return self._completed.copy()


# ─── 便捷函数 ─────────────────────────────────────────────

_dispatcher: Optional[SubagentDispatcher] = None

def get_dispatcher() -> SubagentDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SubagentDispatcher()
    return _dispatcher
