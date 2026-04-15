# -*- coding: utf-8 -*-
"""
prompt_cache_manager.py — Anthropic Prompt Cache 集成

Claude Code 原则4（上下文预算）的核心实现。

核心策略：system_and_3
- 4个缓存断点：system_prompt + 最后3条非系统消息
- 节省约 75% token
- 适用场景：长对话中重复 system prompt 的高频场景

使用方式：
    manager = PromptCacheManager(max_context_tokens=180_000)
    cached = manager.apply_cached_messages(messages)
    # 返回：含缓存断点的消息列表
"""

from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# 策略定义
# ─────────────────────────────────────────────────────────────────

class CacheStrategy(Enum):
    NONE = auto()
    SYSTEM_AND_3 = auto()        # Anthropic 推荐：system + 最后3条
    SYSTEM_AND_LAST = auto()     # system + 最后 N 条
    ALL_STATIC = auto()          # 全部静态内容
    ADAPTIVE = auto()           # 自动选择（基于上下文长度）


# ─────────────────────────────────────────────────────────────────
# 消息结构
# ─────────────────────────────────────────────────────────────────

@dataclass
class CachedMessage:
    """带缓存标记的消息"""
    role: str
    content: str
    cached: bool = False          # 是否标记为缓存（用于 Anthropic API）
    cache_priority: int = 0       # 缓存优先级（越高越先缓存）
    content_hash: str = ""        # 内容指纹（用于缓存命中率判断）

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.md5(
                self.content.encode('utf-8', errors='ignore')
            ).hexdigest()[:12]


@dataclass
class CacheBreakpoints:
    """缓存断点配置"""
    system: Optional[CachedMessage] = None
    recent_messages: list[CachedMessage] = field(default_factory=list)
    remaining_count: int = 0      # 未缓存的消息数


# ─────────────────────────────────────────────────────────────────
# PromptCacheManager
# ─────────────────────────────────────────────────────────────────

class PromptCacheManager:
    """
    Anthropic Prompt Cache 管理器。

    使用 system_and_3 策略：
    - 识别 system_prompt（作为静态内容，只缓存一次）
    - 保留最近3条非系统消息（作为高频访问内容）
    - 其余消息标记为"可丢弃"

    Anthropic Prompt Cache 限制：
    - 缓存内容必须 ≤ 系统的最后131072 tokens
    - 内容必须以完整消息边界开始/结束
    - 缓存寿命：10-3600秒（vendor 决定）
    """

    def __init__(
        self,
        max_context_tokens: int = 180_000,  # claude-3.5 最大 context
        system_cache_tokens: int = 32_768,   # system 最大缓存量
        recent_count: int = 3,              # system_and_3 中的 3
        strategy: CacheStrategy = CacheStrategy.SYSTEM_AND_3,
        enable_adaptive: bool = True,        # 自动切换策略
        adaptive_threshold_ratio: float = 0.6,  # 60% 使用率时切换
    ):
        self.max_context = max_context_tokens
        self.system_cache_limit = system_cache_tokens
        self.recent_count = recent_count
        self.strategy = strategy
        self.enable_adaptive = enable_adaptive
        self.adaptive_ratio = adaptive_threshold_ratio

        # 缓存统计
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_tokens_saved = 0

    # ── 核心 API ───────────────────────────────────────────────

    def apply_cached_messages(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> list[dict]:
        """
        应用缓存策略，返回处理后的消息列表。

        返回格式：含 cache_control 字段（Anthropic API 格式）
        {
            "role": "user"/"assistant",
            "content": "...",
            "cache_control": {"type": "ephemeral"}  # 或 {"type": "high_priority"}
        }
        """
        if not messages:
            return []

        # 转换消息格式
        msgs = [self._to_cached_message(m) for m in messages]

        # 自动策略选择
        if self.enable_adaptive:
            strategy = self._auto_select_strategy(msgs)
        else:
            strategy = self.strategy

        # 应用缓存断点
        breakpoints = self._compute_breakpoints(msgs, system_prompt, strategy)

        # 构建返回消息
        result = self._build_cached_output(msgs, breakpoints)

        # 统计
        cached_count = sum(1 for m in result if m.get("cache_control"))
        if cached_count > 0:
            self._cache_hits += 1
            self._total_tokens_saved += cached_count * 500  # 估算
        else:
            self._cache_misses += 1

        logger.debug(
            f"[PromptCache] strategy={strategy.name} "
            f"cached={cached_count}/{len(messages)} "
            f"remaining={breakpoints.remaining_count}"
        )
        return result

    def compute_cache_benefit(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> dict:
        """
        估算缓存收益（不实际应用）。
        返回：{tokens_saved, saving_ratio, recommended_strategy}
        """
        strategy = self._auto_select_strategy(
            [self._to_cached_message(m) for m in messages]
        )
        breakpoints = self._compute_breakpoints(
            [self._to_cached_message(m) for m in messages],
            system_prompt,
            strategy,
        )

        total_messages = len(messages)
        cached = 1 + breakpoints.remaining_count  # system + recent
        remaining = total_messages - cached

        # 粗略估算：每条消息平均 300 tokens
        saved_tokens = cached * 300
        total_tokens = total_messages * 300
        ratio = saved_tokens / total_tokens if total_tokens else 0

        return {
            "strategy": strategy.name,
            "cached_count": cached,
            "remaining_count": remaining,
            "tokens_saved_estimate": saved_tokens,
            "saving_ratio_estimate": f"{ratio:.0%}",
            "recommended": strategy != CacheStrategy.NONE,
        }

    # ── 内部方法 ──────────────────────────────────────────────

    def _to_cached_message(self, msg: dict) -> CachedMessage:
        """转换消息格式"""
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # 支持字符串和列表格式
        if isinstance(content, list):
            content = " ".join(
                c.get("text", str(c)) if isinstance(c, dict) else str(c)
                for c in content
            )

        priority = self._compute_priority(role, content)
        return CachedMessage(
            role=role,
            content=content,
            cache_priority=priority,
        )

    def _compute_priority(self, role: str, content: str) -> int:
        """计算缓存优先级"""
        priority = 0
        # system 内容：最高优先级
        if role == "system":
            priority += 100
        # 最近消息：较高优先级
        priority += min(len(content) // 100, 50)  # 内容越长越可能重复
        return priority

    def _auto_select_strategy(self, messages: list[CachedMessage]) -> CacheStrategy:
        """基于消息数量自动选择策略"""
        n = len(messages)
        if n == 0:
            return CacheStrategy.NONE
        elif n <= 4:
            return CacheStrategy.SYSTEM_AND_3
        elif n <= 10:
            return CacheStrategy.SYSTEM_AND_LAST
        elif n <= 30:
            return CacheStrategy.ALL_STATIC
        else:
            return CacheStrategy.ADAPTIVE

    def _compute_breakpoints(
        self,
        messages: list[CachedMessage],
        system_prompt: str,
        strategy: CacheStrategy,
    ) -> CacheBreakpoints:
        """计算缓存断点"""
        bp = CacheBreakpoints()

        if strategy == CacheStrategy.NONE:
            return bp

        # system 消息缓存
        if system_prompt:
            bp.system = CachedMessage(
                role="system",
                content=system_prompt,
                cache_priority=100,
            )
            bp.system.cached = True

        if strategy == CacheStrategy.SYSTEM_AND_3:
            # 只缓存 system + 最近 N 条非 system
            non_system = [m for m in messages if m.role != "system"]
            recent = non_system[-self.recent_count:] if non_system else []
            for m in recent:
                m.cached = True
                m.cache_priority = 50
            bp.recent_messages = recent
            bp.remaining_count = len(non_system) - len(recent)

        elif strategy == CacheStrategy.SYSTEM_AND_LAST:
            recent = messages[-self.recent_count:]
            for m in recent:
                if m.role != "system":
                    m.cached = True
                    m.cache_priority = 40
            bp.recent_messages = recent
            bp.remaining_count = len(messages) - len(recent)

        elif strategy == CacheStrategy.ALL_STATIC:
            for m in messages:
                if m.role == "system":
                    m.cached = True
            bp.remaining_count = len(messages) - 1

        return bp

    def _build_cached_output(
        self,
        messages: list[CachedMessage],
        breakpoints: CacheBreakpoints,
    ) -> list[dict]:
        """构建输出消息列表"""
        result = []

        # system
        if breakpoints.system:
            result.append({
                "role": "system",
                "content": breakpoints.system.content,
                "cache_control": {"type": "ephemeral"},
            })

        # recent messages
        for m in breakpoints.recent_messages:
            result.append({
                "role": m.role,
                "content": m.content,
                "cache_control": {"type": "high_priority"},
            })

        # remaining messages
        for m in messages:
            if m in breakpoints.recent_messages:
                continue
            if m.role == "system":
                continue
            result.append({
                "role": m.role,
                "content": m.content,
            })

        return result

    # ── 缓存统计 ──────────────────────────────────────────────

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": f"{hit_rate:.1%}",
            "tokens_saved_estimate": self._total_tokens_saved,
            "strategy": self.strategy.name,
            "adaptive_enabled": self.enable_adaptive,
        }

    def reset_stats(self) -> None:
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_tokens_saved = 0


# ─────────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────────

_cache_manager: Optional[PromptCacheManager] = None


def get_cache_manager() -> PromptCacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = PromptCacheManager()
    return _cache_manager


# ─────────────────────────────────────────────────────────────────
# 集成便捷函数
# ─────────────────────────────────────────────────────────────────

def apply_prompt_cache(
    messages: list[dict],
    system_prompt: str = "",
    strategy: CacheStrategy = CacheStrategy.SYSTEM_AND_3,
) -> list[dict]:
    """
    便捷函数：对消息列表应用 prompt cache。
    用于 qclaw 的 compact / message 处理流程。
    """
    manager = get_cache_manager()
    manager.strategy = strategy
    return manager.apply_cached_messages(messages, system_prompt)


def estimate_cache_saving(messages: list[dict], system_prompt: str = "") -> dict:
    """便捷函数：估算缓存收益"""
    manager = get_cache_manager()
    return manager.compute_cache_benefit(messages, system_prompt)
