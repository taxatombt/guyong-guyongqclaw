# -*- coding: utf-8 -*-
"""
tool_result_budget.py - 工具结果 Token 预算控制

来源: 顾庸t workspace_tools/tool_result_budget.py
参考: Claude Code TOOL_TOKEN_COUNT_OVERHEAD=500 + Hermes BudgetConfig

核心功能:
  1. 每个工具调用有 token 上限
  2. 超限自动截断（保留首尾）
  3. PINNED 模式: 关键工具（read_file）不限
  4. 统计追踪: 总 token 消耗

预算策略:
  - 默认: 4000 tokens
  - 搜索类: 6000 tokens（需要完整结果）
  - 执行类: 2000 tokens（只需要输出）
  - PINNED: 无限制（read_file / memory_search）
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


class BudgetMode(Enum):
    DEFAULT = "default"
    SEARCH = "search"
    EXEC = "exec"
    PINNED = "pinned"


# 工具 → 预算模式映射
TOOL_BUDGET_MAP: Dict[str, BudgetMode] = {
    "read": BudgetMode.PINNED,
    "memory_search": BudgetMode.PINNED,
    "memory_get": BudgetMode.PINNED,
    "web_search": BudgetMode.SEARCH,
    "web_fetch": BudgetMode.SEARCH,
    "browser": BudgetMode.SEARCH,
    "exec": BudgetMode.EXEC,
    "write": BudgetMode.EXEC,
    "edit": BudgetMode.EXEC,
    "message": BudgetMode.EXEC,
    "lcm_grep": BudgetMode.SEARCH,
    "lcm_expand": BudgetMode.SEARCH,
}

# 模式 → token 上限
MODE_LIMITS: Dict[BudgetMode, int] = {
    BudgetMode.DEFAULT: 4000,
    BudgetMode.SEARCH: 6000,
    BudgetMode.EXEC: 2000,
    BudgetMode.PINNED: float("inf"),
}


@dataclass
class BudgetStats:
    """预算统计"""
    tool_name: str
    mode: BudgetMode
    limit: int
    original_tokens: int
    final_tokens: int
    truncated: bool


class ToolResultBudget:
    """工具结果预算控制器"""
    
    def __init__(self, custom_limits: Optional[Dict[BudgetMode, int]] = None):
        self._limits = dict(MODE_LIMITS)
        if custom_limits:
            self._limits.update(custom_limits)
        self._stats: List[BudgetStats] = []
        self._total_consumed: int = 0
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
    
    def _get_mode(self, tool_name: str) -> BudgetMode:
        return TOOL_BUDGET_MAP.get(tool_name, BudgetMode.DEFAULT)
    
    def _get_limit(self, mode: BudgetMode) -> int:
        return self._limits.get(mode, MODE_LIMITS[BudgetMode.DEFAULT])
    
    def apply(self, tool_name: str, result: Any) -> tuple:
        """
        对工具结果应用预算。
        返回: (处理后结果, BudgetStats)
        
        result 可以是 str 或 dict。
        """
        mode = self._get_mode(tool_name)
        limit = self._get_limit(mode)
        
        # 将结果转为文本
        if isinstance(result, str):
            text = result
        elif isinstance(result, dict):
            text = str(result)
        elif hasattr(result, "__str__"):
            text = str(result)
        else:
            text = ""
        
        original_tokens = self._estimate_tokens(text)
        truncated = False
        final_tokens = original_tokens
        
        if mode == BudgetMode.PINNED or original_tokens <= limit:
            pass  # 不截断
        else:
            # 截断: 保留首尾
            char_limit = limit * 4
            head_chars = char_limit // 2
            tail_chars = char_limit - head_chars
            
            if len(text) > char_limit:
                head = text[:head_chars]
                tail = text[-tail_chars:] if len(text) > tail_chars else ""
                removed_chars = len(text) - head_chars - len(tail)
                text = (
                    f"{head}\n"
                    f"\n... [{removed_chars} chars truncated (budget: {limit} tokens)] ...\n"
                    f"\n{tail}"
                )
                truncated = True
                final_tokens = self._estimate_tokens(text)
        
        stats = BudgetStats(
            tool_name=tool_name,
            mode=mode,
            limit=limit,
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            truncated=truncated,
        )
        self._stats.append(stats)
        self._total_consumed += final_tokens
        
        return text, stats
    
    def total_consumed(self) -> int:
        """总 token 消耗"""
        return self._total_consumed
    
    def summary(self) -> Dict[str, Any]:
        """预算使用摘要"""
        truncated_count = sum(1 for s in self._stats if s.truncated)
        return {
            "total_calls": len(self._stats),
            "total_tokens": self._total_consumed,
            "truncated_calls": truncated_count,
            "saved_tokens": sum(
                s.original_tokens - s.final_tokens 
                for s in self._stats if s.truncated
            ),
        }
    
    def by_tool(self) -> Dict[str, Dict[str, Any]]:
        """按工具分组统计"""
        grouped: Dict[str, Dict[str, Any]] = {}
        for s in self._stats:
            if s.tool_name not in grouped:
                grouped[s.tool_name] = {
                    "calls": 0,
                    "tokens": 0,
                    "truncated": 0,
                }
            grouped[s.tool_name]["calls"] += 1
            grouped[s.tool_name]["tokens"] += s.final_tokens
            if s.truncated:
                grouped[s.tool_name]["truncated"] += 1
        return grouped


_budget: Optional[ToolResultBudget] = None

def get_budget() -> ToolResultBudget:
    global _budget
    if _budget is None:
        _budget = ToolResultBudget()
    return _budget
