# -*- coding: utf-8 -*-
"""
conversation_formatter.py — 优先级截断格式化器

来自 HKUDS/OpenSpace skill_engine/conversation_formatter.py

功能：将 action_log.jsonl 条目转换为 LLM 可读的文本块
使用优先级截断（而非简单尾部截断）

优先级（来自 OpenSpace）：
  0 CRITICAL — 用户指令（从不截断）
  1 CRITICAL — 最后一次回复（从不截断）
  2 HIGH     — 工具调用 + 工具错误（配对保留）
  3 HIGH     — 非最终推理 + 含摘要的工具结果
  4 MEDIUM   — 工具成功结果
  5 LOW      — 系统消息
  SKIP       — Skill注入文本、详细系统提示
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


# 截断限制（与 analyzer 常量保持同步）
TOOL_ERROR_MAX_CHARS = 1000
TOOL_SUCCESS_MAX_CHARS = 800
TOOL_ARGS_MAX_CHARS = 500
TOOL_SUMMARY_MAX_CHARS = 1500


def format_conversations(
    conversations: List[Dict[str, Any]],
    budget: int,
) -> str:
    """
    将 conversations 条目格式化为可读文本块
    
    使用优先级截断，当总长度超过 budget 时：
      1. 包含所有优先级 ≤ 3（CRITICAL + HIGH）段落
      2. 添加 MEDIUM + LOW 直到 budget 耗尽
      3. 如果 HIGH 内容仍超 budget，保留 0-1，全部预算给优先级 2
    """
    segments: List[Dict[str, Any]] = []
    
    for conv in conversations:
        conv_type = conv.get("type", "")
        if conv_type == "setup":
            _collect_setup_segments(conv, segments)
        elif conv_type == "iteration":
            _collect_iteration_segments(conv, len(conversations), segments)
    
    return _assemble_with_budget(segments, budget)


def _collect_setup_segments(
    conv: Dict[str, Any],
    segments: List[Dict[str, Any]],
) -> None:
    """
    从 type="setup" 条目提取段落
    
    只提取用户指令。系统提示（包括 skill 注入文本和工具描述）
    会被跳过 — 它们在分析提示中单独提供。
    """
    for msg in conv.get("messages", []):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        
        if role == "user":
            segments.append({
                "priority": 0,  # CRITICAL — always keep
                "text": f"[USER INSTRUCTION]\n{content}",
                "role": "user",
            })


def _collect_iteration_segments(
    conv: Dict[str, Any],
    total_iters: int,
    segments: List[Dict[str, Any]],
) -> None:
    """
    从 type="iteration" 条目提取段落
    
    关键设计：
    - 工具调用和工具错误共享同一优先级（2）
    - 工具成功结果为 MEDIUM（4）
    - 含 "Execution Summary" 的 shell agent 结果为 HIGH（3）
    """
    iteration = conv.get("iteration", "?")
    is_last = (iteration == total_iters) if isinstance(iteration, int) else False
    
    for msg in conv.get("delta_messages", []):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        
        if role == "assistant":
            # 推理内容
            if content:
                priority = 1 if is_last else 3
                segments.append({
                    "priority": priority,
                    "text": f"[Iter {iteration}] ASSISTANT: {content[:500]}",
                    "role": "assistant",
                })
            
            # 工具调用
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                fn_name = fn.get("name", "?")
                fn_args = fn.get("arguments", "")
                if isinstance(fn_args, str) and len(fn_args) > TOOL_ARGS_MAX_CHARS:
                    fn_args = fn_args[:TOOL_ARGS_MAX_CHARS] + "..."
                segments.append({
                    "priority": 2,  # HIGH — paired with tool results/errors
                    "text": f"[Iter {iteration}] TOOL_CALL: {fn_name}({fn_args})",
                    "role": "tool_call",
                })
        
        elif role == "tool":
            is_error = _is_error_result(content)
            
            if is_error:
                truncated = content[:TOOL_ERROR_MAX_CHARS]
                if len(content) > TOOL_ERROR_MAX_CHARS:
                    truncated += f"... [truncated, total {len(content)} chars]"
                segments.append({
                    "priority": 2,  # HIGH — errors are critical
                    "text": f"[Iter {iteration}] TOOL_ERROR: {truncated}",
                    "role": "tool_error",
                })
            else:
                # 工具成功结果
                truncated = content[:TOOL_SUCCESS_MAX_CHARS]
                if len(content) > TOOL_SUCCESS_MAX_CHARS:
                    truncated += f"... [truncated {len(content) - TOOL_SUCCESS_MAX_CHARS} chars]"
                
                # 含 Execution Summary 的为 HIGH
                priority = 3 if "_EXECUTION_SUMMARY" in content or "Execution Summary" in content else 4
                
                segments.append({
                    "priority": priority,
                    "text": f"[Iter {iteration}] TOOL_RESULT: {truncated}",
                    "role": "tool_result",
                })


def _is_error_result(content: str) -> bool:
    """判断工具结果是否为错误"""
    error_indicators = [
        "error", "failed", "failure", "exception",
        "Traceback", "Error:", "FAILED", "not found",
        "PermissionError", "FileNotFoundError", "TimeoutError",
    ]
    content_lower = content.lower()
    return any(indicator.lower() in content_lower for indicator in error_indicators)


def _assemble_with_budget(
    segments: List[Dict[str, Any]],
    budget: int,
) -> str:
    """
    按优先级组装文本，在 budget 内截断
    
    策略：
    - 优先级 0-1（CRITICAL）：无条件保留
    - 优先级 2（HIGH）：完整保留
    - 优先级 3（HIGH）：可截断
    - 优先级 4-5（MEDIUM/LOW）：在 budget 内保留
    """
    # 按优先级排序（低优先级先放，高优先级优先）
    segments.sort(key=lambda x: (x.get("priority", 9), x.get("role", "")))
    
    result_parts = []
    current_len = 0
    
    for seg in segments:
        priority = seg.get("priority", 9)
        text = seg.get("text", "")
        text_len = len(text)
        
        # CRITICAL (0-1)：无条件保留
        if priority <= 1:
            if current_len + text_len <= budget:
                result_parts.append(text)
                current_len += text_len
            else:
                # 强制截断保留
                remaining = max(0, budget - current_len)
                result_parts.append(text[:remaining])
                current_len = budget
                break
        
        # HIGH (2-3)：尽量保留
        elif priority <= 3:
            if current_len + text_len <= budget:
                result_parts.append(text)
                current_len += text_len
            elif priority == 2 and current_len < budget:
                # 工具调用对优先保留（哪怕截断）
                remaining = max(0, budget - current_len)
                result_parts.append(text[:remaining])
                current_len = budget
                break
            else:
                break
        
        # MEDIUM/LOW (4-5)：在剩余空间内放
        else:
            if current_len + text_len <= budget:
                result_parts.append(text)
                current_len += text_len
            else:
                break
    
    return "\n\n".join(result_parts)


# ═══════════════════════════════════════════════════════════════════
# guyong-juhuo 专用：格式化 action_log
# ═══════════════════════════════════════════════════════════════════

def format_action_log(entries: List[Dict], budget: int = 3000) -> str:
    """
    将 guyong-juhuo 的 action_log.jsonl 格式化为 LLM 分析文本
    
    转换格式：
    action_log.jsonl → {type, messages/delta_messages, iteration}
    """
    # 转换为 conversations 格式
    conversations = []
    
    current_iter = {"type": "setup", "messages": []}
    iter_count = 0
    
    for entry in entries:
        role = entry.get("role", "tool")
        content = entry.get("content", "")
        iteration = entry.get("iteration", 0)
        
        if iteration != iter_count:
            if current_iter["messages"]:
                conversations.append(current_iter)
            iter_count = iteration
            current_iter = {"type": "iteration", "iteration": iteration, "delta_messages": []}
        
        if role == "user":
            current_iter.setdefault("messages", []).append({"role": "user", "content": content})
        elif role == "assistant":
            current_iter["delta_messages"].append({
                "role": "assistant",
                "content": content,
                "tool_calls": entry.get("tool_calls", []),
            })
        elif role == "tool":
            current_iter["delta_messages"].append({
                "role": "tool",
                "content": content,
            })
    
    if current_iter["messages"] or current_iter["delta_messages"]:
        conversations.append(current_iter)
    
    if not conversations:
        return "[No action log entries]"
    
    return format_conversations(conversations, budget)
