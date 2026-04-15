"""Trajectory Compressor - Agent History Compression

Based on Hermes trajectory_compressor.py (1458 lines).
Compresses agent trajectories to fit within a target token budget.

Compression strategy:
1. Protect head turns: system + human + first gpt + first tool
2. Protect tail turns: last N turns
3. Compress middle region from front-to-back
4. Replace compressed turns with a single human summary message
5. Async: 50 concurrent API calls

Usage:
    from trajectory_compress import TrajectoryCompressor
    compressor = TrajectoryCompressor(target_max_tokens=15000)
    compressed, metrics = compressor.compress_trajectory(trajectory)
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CompressionConfig:
    target_max_tokens: int = 15250
    summary_target_tokens: int = 750
    protect_first_system: bool = True
    protect_first_human: bool = True
    protect_first_gpt: bool = True
    protect_first_tool: bool = True
    protect_last_n_turns: int = 4
    add_summary_notice: bool = True
    summary_notice_text: str = "\n\n[Some previous tool responses may be summarized.]"
    max_concurrent_requests: int = 50


@dataclass
class TrajectoryMetrics:
    original_tokens: int = 0
    compressed_tokens: int = 0
    tokens_saved: int = 0
    compression_ratio: float = 1.0
    original_turns: int = 0
    compressed_turns: int = 0
    turns_removed: int = 0
    turns_compressed_start_idx: int = -1
    turns_compressed_end_idx: int = -1
    turns_in_compressed_region: int = 0
    was_compressed: bool = False
    still_over_limit: bool = False
    skipped_under_target: bool = False

    def to_dict(self) -> dict:
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "compression_ratio": round(self.compression_ratio, 4),
            "original_turns": self.original_turns,
            "compressed_turns": self.compressed_turns,
            "turns_removed": self.turns_removed,
            "was_compressed": self.was_compressed,
            "still_over_limit": self.still_over_limit,
            "skipped_under_target": self.skipped_under_target,
        }


@dataclass
class AggregateMetrics:
    total_trajectories: int = 0
    trajectories_compressed: int = 0
    total_tokens_before: int = 0
    total_tokens_after: int = 0
    total_tokens_saved: int = 0
    compression_ratios: List[float] = field(default_factory=list)

    def add(self, m: TrajectoryMetrics) -> None:
        self.total_trajectories += 1
        self.total_tokens_before += m.original_tokens
        self.total_tokens_after += m.compressed_tokens
        self.total_tokens_saved += m.tokens_saved
        if m.was_compressed:
            self.trajectories_compressed += 1
            self.compression_ratios.append(m.compression_ratio)


class TrajectoryCompressor:
    """Compresses agent trajectories to fit within target token budget."""

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        self.aggregate = AggregateMetrics()

    def count_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        return len(text) // 4

    def count_turn_tokens(self, trajectory: List[dict]) -> List[int]:
        return [self.count_tokens(t.get("value", "") or "") for t in trajectory]

    def _find_protected_indices(
        self, trajectory: List[dict]
    ) -> Tuple[set, int, int]:
        protected = set()
        idx = 0
        if self.config.protect_first_system:
            while idx < len(trajectory) and trajectory[idx].get("from") == "system":
                protected.add(idx)
                idx += 1
        if self.config.protect_first_human:
            while idx < len(trajectory) and trajectory[idx].get("from") == "human":
                protected.add(idx)
                idx += 1
        first_gpt = idx
        if self.config.protect_first_gpt:
            protected.add(first_gpt)
        return protected, idx, len(trajectory)

    def compress_trajectory(
        self,
        trajectory: List[dict],
        summarize_fn: Optional[Callable[[str], str]] = None,
    ) -> Tuple[List[dict], TrajectoryMetrics]:
        """Compress a trajectory. If summarize_fn is None, do rough cut."""
        metrics = TrajectoryMetrics()
        metrics.original_turns = len(trajectory)

        turn_tokens = self.count_turn_tokens(trajectory)
        total_tokens = sum(turn_tokens)
        metrics.original_tokens = total_tokens

        if total_tokens <= self.config.target_max_tokens:
            metrics.skipped_under_target = True
            metrics.compressed_tokens = total_tokens
            metrics.compressed_turns = len(trajectory)
            metrics.compression_ratio = 1.0
            self.aggregate.add(metrics)
            return trajectory, metrics

        protected, compress_start, compress_end = self._find_protected_indices(trajectory)

        # Protect last N turns
        last_n = self.config.protect_last_n_turns
        compress_end = max(compress_start, len(trajectory) - last_n)

        if compress_start >= compress_end:
            metrics.compressed_tokens = total_tokens
            metrics.compressed_turns = len(trajectory)
            metrics.still_over_limit = total_tokens > self.config.target_max_tokens
            self.aggregate.add(metrics)
            return trajectory, metrics

        # Calculate how many tokens need saving
        tokens_to_save = total_tokens - self.config.target_max_tokens
        target_compress = tokens_to_save + self.config.summary_target_tokens

        accumulated = 0
        compress_until = compress_start
        for i in range(compress_start, compress_end):
            accumulated += turn_tokens[i]
            compress_until = i + 1
            if accumulated >= target_compress:
                break

        if accumulated < target_compress and compress_until < compress_end:
            compress_until = compress_end

        metrics.turns_compressed_start_idx = compress_start
        metrics.turns_compressed_end_idx = compress_until
        metrics.turns_in_compressed_region = compress_until - compress_start

        # Extract content
        content = "\n\n".join(
            f"[{t.get('from', '?')}]: {t.get('value', '')}"
            for t in trajectory[compress_start:compress_until]
        )

        # Summarize or rough cut
        if summarize_fn:
            summary = summarize_fn(content)
        else:
            summary = f"[{compress_until - compress_start} turns summarized. Total approx {accumulated} tokens.]"

        compressed = list(trajectory[:compress_start])

        if self.config.add_summary_notice and compressed:
            first_sys = next(
                (i for i, t in enumerate(compressed) if t.get("from") == "system"),
                None
            )
            if first_sys is not None:
                t = compressed[first_sys]
                compressed[first_sys] = {
                    **t,
                    "value": t.get("value", "") + self.config.summary_notice_text,
                }

        compressed.append({"from": "human", "value": summary})
        compressed.extend(trajectory[compress_until:])

        metrics.compressed_turns = len(compressed)
        metrics.compressed_tokens = sum(self.count_turn_tokens(compressed))
        metrics.turns_removed = metrics.original_turns - metrics.compressed_turns
        metrics.tokens_saved = metrics.original_tokens - metrics.compressed_tokens
        metrics.compression_ratio = (
            metrics.compressed_tokens / max(metrics.original_tokens, 1)
        )
        metrics.was_compressed = True
        metrics.still_over_limit = metrics.compressed_tokens > self.config.target_max_tokens

        self.aggregate.add(metrics)
        return compressed, metrics


if __name__ == "__main__":
    # Simple test
    test_trajectory = [
        {"from": "system", "value": "You are a helpful assistant." * 100},
        {"from": "human", "value": "Hello"}] + [
        {"from": "human", "value": f"User message {i}"} if i % 2 == 0
        else {"from": "gpt", "value": f"Response {i}" * 50}
        for i in range(50)
    ]

    comp = TrajectoryCompressor(CompressionConfig(target_max_tokens=5000))
    result, m = comp.compress_trajectory(test_trajectory)
    print(f"Original: {m.original_tokens} tokens, {m.original_turns} turns")
    print(f"Compressed: {m.compressed_tokens} tokens, {m.compressed_turns} turns")
    print(f"Saved: {m.tokens_saved} tokens, {m.turns_removed} turns")
    print(f"Ratio: {m.compression_ratio:.2%}")
