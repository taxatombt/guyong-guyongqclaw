# -*- coding: utf-8 -*-
"""
token_budget.py — Token 预算管理

来源: Claude Code src/query/tokenBudget.ts + Hermes tools/budget_config.py
用途: 管理 LLM 调用的 token 预算，检测收益递减

不修改任何现有系统代码，纯新建模块。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ===== 常量（参考 Claude Code tokenBudget.ts）=====

COMPLETION_THRESHOLD = 0.9  # 90% 预算触发判断
DIMINISHING_THRESHOLD = 500  # 连续3次 delta < 500 → 收益递减
DIMINISHING_CONSECUTIVE = 3  # 连续次数阈值


# ===== 预算配置（参考 Hermes budget_config.py）=====

@dataclass(frozen=True)
class BudgetConfig:
    """不可变预算配置"""
    max_context_tokens: int = 200_000        # 上下文窗口上限
    completion_threshold: float = COMPLETION_THRESHOLD
    diminishing_threshold: int = DIMINISHING_THRESHOLD
    diminishing_consecutive: int = DIMINISHING_CONSECUTIVE
    # 3层持久化（参考 Hermes）
    default_result_size: int = 100_000       # 单结果字符上限
    turn_budget: int = 200_000               # 单轮总字符预算
    preview_size: int = 1_500                # 预览字符数
    pinned_thresholds: dict = field(default_factory=lambda: {
        "read_file": float("inf"),  # 防止 persist→read→persist 循环
    })
    tool_overrides: dict = field(default_factory=dict)


DEFAULT_BUDGET = BudgetConfig()


class TokenBudget:
    """
    Token 预算管理器
    
    参考 Claude Code tokenBudget.ts:
    - 90% 阈值触发判断
    - 收益递减检测（连续3次 delta < 500）
    - 两种决策：continue / stop
    """
    
    def __init__(self, config: BudgetConfig = None):
        self.config = config or DEFAULT_BUDGET
        self._history: List[Tuple[int, int]] = []  # (prompt_tokens, completion_tokens)
        self._deltas: List[int] = []  # 连续 delta 记录
        self._total_prompt = 0
        self._total_completion = 0
    
    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """记录一次使用"""
        self._history.append((prompt_tokens, completion_tokens))
        self._total_prompt += prompt_tokens
        self._total_completion += completion_tokens
        
        # 计算 delta（本次比上次的增长）
        if len(self._history) >= 2:
            delta = completion_tokens - self._history[-2][1]
            self._deltas.append(delta)
    
    @property
    def usage_ratio(self) -> float:
        """当前使用比率（0.0-1.0）"""
        if self.config.max_context_tokens == 0:
            return 0.0
        return self._total_prompt / self.config.max_context_tokens
    
    @property
    def is_near_limit(self) -> bool:
        """是否接近预算上限（90%）"""
        return self.usage_ratio >= self.config.completion_threshold
    
    @property
    def is_diminishing(self) -> bool:
        """是否收益递减"""
        if len(self._deltas) < self.config.diminishing_consecutive:
            return False
        
        recent = self._deltas[-self.config.diminishing_consecutive:]
        return all(abs(d) < self.config.diminishing_threshold for d in recent)
    
    def should_stop(self) -> Tuple[bool, str]:
        """
        判断是否应该停止
        
        Returns:
            (should_stop, reason)
        """
        if self.is_near_limit and self.is_diminishing:
            return True, (
                f"Token budget {self.usage_ratio:.0%} used with diminishing returns "
                f"(last {self.config.diminishing_consecutive} deltas < "
                f"{self.config.diminishing_threshold}). Recommend stopping."
            )
        
        if self.is_near_limit:
            return False, (
                f"Token budget {self.usage_ratio:.0%} used. "
                f"Consider wrapping up soon."
            )
        
        if self.is_diminishing:
            return False, (
                f"Diminishing returns detected (last {self.config.diminishing_consecutive} "
                f"deltas < {self.config.diminishing_threshold}). "
                f"Consider summarizing progress."
            )
        
        return False, ""
    
    def resolve_threshold(self, tool_name: str) -> int | float:
        """
        解析工具的持久化阈值
        
        优先级: pinned > overrides > default
        参考 Hermes BudgetConfig.resolve_threshold()
        """
        if tool_name in self.config.pinned_thresholds:
            return self.config.pinned_thresholds[tool_name]
        if tool_name in self.config.tool_overrides:
            return self.config.tool_overrides[tool_name]
        return self.config.default_result_size
    
    @property
    def summary(self) -> str:
        """预算状态摘要"""
        should_stop, reason = self.should_stop()
        return (
            f"Token Budget: {self._total_prompt:,}/{self.config.max_context_tokens:,} "
            f"({self.usage_ratio:.1%}) | "
            f"Completions: {self._total_completion:,} | "
            f"Turns: {len(self._history)} | "
            f"{'STOP' if should_stop else 'CONTINUE'}"
            f"{f' | {reason}' if reason else ''}"
        )


if __name__ == "__main__":
    # 测试
    budget = TokenBudget()
    
    # 模拟使用
    usages = [
        (50000, 2000),
        (55000, 2200),
        (60000, 2300),
        (160000, 2400),  # 接近90%
        (165000, 2410),  # 递减
        (170000, 2420),  # 递减
        (175000, 2430),  # 递减 → 触发
    ]
    
    for prompt, completion in usages:
        budget.record_usage(prompt, completion)
        should_stop, reason = budget.should_stop()
        print(budget.summary)
        if should_stop:
            print(f"  >>> RECOMMEND STOP: {reason}")
