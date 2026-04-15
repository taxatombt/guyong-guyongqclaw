# -*- coding: utf-8 -*-
"""
token_overhead.py - Token 开销管理与计数

来源: Claude Code utils/analyzeContext.ts (3430行)
       Claude Code utils/tokenEstimation.ts

核心发现:
- TOOL_TOKEN_COUNT_OVERHEAD = 500 (每个工具调用的固定开销)
- Token计数三级联: API → Haiku fallback → rough estimation
- SYSTEM_PROMPT_DYNAMIC_BOUNDARY: 静态/动态 system prompt 分界线
- estimateSkillFrontmatterTokens(): skill frontmatter 也有开销

关键洞察:
Claude Code 在分析 token 使用时，会减去 TOOL_TOKEN_COUNT_OVERHEAD 来显示准确的工具内容大小。
当N个工具被分别计数时，每个调用都有这个 overhead，
导致总 overhead = N×500 而不是 1×500。
"""

import time
from typing import Optional, Tuple, Callable, List
from dataclasses import dataclass

# ─── 常量 ─────────────────────────────

# 每个工具调用的 API overhead (Claude Code TOOL_TOKEN_COUNT_OVERHEAD)
TOOL_TOKEN_COUNT_OVERHEAD = 500

# API token 计数超时的 fallback 阈值
TOKEN_API_TIMEOUT_MS = 5000  # 5秒

# Rough estimation: 字符数 / CHARS_PER_TOKEN
CHARS_PER_TOKEN = 4

# System prompt 动态边界标识（Claude Code SYSTEM_PROMPT_DYNAMIC_BOUNDARY）
DYNAMIC_BOUNDARY_MARKER = "<!-- DYNAMIC_BOUNDARY -->"


# ─── Token 计数策略 ─────────────────────────────

def count_tokens_haiku(messages: list, tools: list = None) -> Optional[int]:
    """
    Haiku fallback: 使用便宜的 Haiku 模型估算 token 数。
    
    用途: 当 API token 计数不可用或超时时，用 Haiku 估算。
    Claude Code analyzeContext.ts: countTokensViaHaikuFallback()
    """
    # TODO: 实际调用 Haiku API
    # 目前返回 rough estimation
    total = 0
    for msg in messages:
        content = msg.get("content", "") or ""
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    total += rough_token_count(block["text"])
        else:
            total += rough_token_count(str(content))
    return total


def rough_token_count(text: str) -> int:
    """
    粗略 token 估算 (最后兜底)
    
    Claude Code: roughTokenCountEstimation()
    策略: 字符数 / 4
    """
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def count_tokens_with_fallback(
    messages: list,
    tools: list = None,
    api_fn: Optional[Callable] = None,
    timeout_ms: int = TOKEN_API_TIMEOUT_MS,
) -> Tuple[int, str]:
    """
    Token 计数三级联策略。
    
    1. 尝试 API 直接计数 (最快最准)
    2. API 超时 → Haiku fallback (便宜快速)
    3. Haiku 失败 → rough estimation (保底)
    
    Returns: (token_count, strategy_used)
    """
    # Step 1: API 直接计数
    if api_fn:
        try:
            # 减去每个工具的 overhead 来显示准确大小
            result = api_fn(messages, tools)
            if result is not None:
                return result, "api"
        except TimeoutError:
            pass  # 超时，继续 fallback
        except Exception:
            pass  # 失败，继续 fallback
    
    # Step 2: Haiku fallback
    try:
        result = count_tokens_haiku(messages, tools)
        if result is not None and result > 0:
            return result, "haiku"
    except Exception:
        pass
    
    # Step 3: Rough estimation (保底)
    return rough_total_tokens(messages), "rough"


def rough_total_tokens(messages: list) -> int:
    """
    对整个消息列表做 rough token 估算。
    
    不区分消息类型，统一用字符数/4估算。
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "") or ""
        if isinstance(content, str):
            total += rough_token_count(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    total += rough_token_count(text)
    return total


def adjust_for_tool_overhead(
    token_counts: list,
    tool_names: list,
) -> list:
    """
    减去每个工具的 TOOL_TOKEN_COUNT_OVERHEAD。
    
    Claude Code analyzeContext.ts:
    "The API adds a tool prompt preamble (~500 tokens) once per API call
    when tools are present. When we count tools individually via the token
    counting API, each call includes this overhead, leading to N×500 overhead
    instead of 1×500 for N tools."
    
    Returns: adjusted token counts (每个工具的准确内容大小)
    """
    adjusted = []
    for i, count in enumerate(token_counts):
        tool_name = tool_names[i] if i < len(tool_names) else "unknown"
        if count > TOOL_TOKEN_COUNT_OVERHEAD:
            adjusted.append(count - TOOL_TOKEN_COUNT_OVERHEAD)
        else:
            adjusted.append(count)
    return adjusted


# ─── System Prompt 动态边界 ─────────────────────────────

def split_static_dynamic(system_prompt: str) -> Tuple[str, str]:
    """
    将 system prompt 拆分为静态部分和动态部分。
    
    Claude Code: SYSTEM_PROMPT_DYNAMIC_BOUNDARY
    - 静态: 基本原则、能力描述 (不常变)
    - 动态: 任务上下文、记忆注入 (每次变)
    
    策略: 找到 DYNAMIC_BOUNDARY_MARKER 位置，
    或按行数比例拆分（前30%静态，后70%动态）
    """
    marker = DYNAMIC_BOUNDARY_MARKER
    
    if marker in system_prompt:
        parts = system_prompt.split(marker, 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    
    # Fallback: 按比例拆分
    lines = system_prompt.split("\n")
    split_point = max(1, int(len(lines) * 0.3))
    static_lines = lines[:split_point]
    dynamic_lines = lines[split_point:]
    
    return "\n".join(static_lines), "\n".join(dynamic_lines)


def estimate_skill_frontmatter_tokens(frontmatter: str) -> int:
    """
    Skill frontmatter 的 token 开销估算。
    
    Claude Code: estimateSkillFrontmatterTokens()
    Skill 文件的 YAML frontmatter 也会占用 token。
    """
    if not frontmatter:
        return 0
    return rough_token_count(frontmatter)


# ─── Context 预算管理 ─────────────────────────────

@dataclass
class TokenBudget:
    """Token 预算追踪器"""
    context_limit: int = 200000
    used_tokens: int = 0
    tool_overhead_total: int = 0
    
    # 阈值
    soft_threshold: float = 0.85   # 85% 软警告
    hard_threshold: float = 0.95   # 95% 硬截断
    
    @property
    def usage_ratio(self) -> float:
        return self.used_tokens / self.context_limit if self.context_limit > 0 else 0
    
    @property
    def remaining(self) -> int:
        return max(0, self.context_limit - self.used_tokens)
    
    def record_tool_call(self, tool_name: str, content_tokens: int) -> None:
        """记录一次工具调用（含 overhead）"""
        self.used_tokens += content_tokens + TOOL_TOKEN_COUNT_OVERHEAD
        self.tool_overhead_total += TOOL_TOKEN_COUNT_OVERHEAD
    
    def should_warn(self) -> Tuple[bool, str]:
        """是否应该发出警告"""
        ratio = self.usage_ratio
        if ratio >= self.hard_threshold:
            return True, f"HARD LIMIT {ratio:.0%} ({self.remaining} tokens remaining)"
        if ratio >= self.soft_threshold:
            return True, f"soft warning {ratio:.0%} ({self.remaining} tokens remaining)"
        return False, ""
    
    def summary(self) -> str:
        """预算摘要"""
        warn, msg = self.should_warn()
        return (
            f"Token Budget: {self.used_tokens:,}/{self.context_limit:,} "
            f"({self.usage_ratio:.0%}) | "
            f"Remaining: {self.remaining:,} | "
            f"Tool overhead: {self.tool_overhead_total:,} | "
            f"{'[WARNING] ' + msg if warn else 'OK'}"
        )


if __name__ == "__main__":
    # 测试
    budget = TokenBudget(context_limit=200000)
    
    # 模拟工具调用
    tool_calls = [
        ("read", 500),
        ("write", 1200),
        ("exec", 800),
        ("browser", 3000),
    ]
    
    print("=== Token Overhead Test ===")
    for tool, tokens in tool_calls:
        before = budget.used_tokens
        budget.record_tool_call(tool, tokens)
        after = budget.used_tokens
        overhead = after - before - tokens
        warn, msg = budget.should_warn()
        print(f"{tool}: +{tokens} content +{overhead} overhead = {after} total {msg[:30] if warn else ''}")
    
    print(f"\n{budget.summary()}")
    
    # 测试工具 overhead 调整
    counts = [2000, 1500, 800, 300]
    names = ["read", "write", "exec", "browser"]
    adjusted = adjust_for_tool_overhead(counts, names)
    print(f"\n=== Tool Overhead Adjustment ===")
    for name, orig, adj in zip(names, counts, adjusted):
        print(f"  {name}: {orig} -> {adj} (overhead: {orig - adj})")
    
    # 测试 rough vs haiku
    test_text = "This is a test message with some content."
    print(f"\nrough_token_count('{test_text}'): {rough_token_count(test_text)}")
    
    # 测试 static/dynamic split
    prompt = "You are helpful.\n\n<!-- DYNAMIC_BOUNDARY -->\n\nTask: build a REST API"
    static, dynamic = split_static_dynamic(prompt)
    print(f"\nStatic: {len(static)} chars")
    print(f"Dynamic: {len(dynamic)} chars")
