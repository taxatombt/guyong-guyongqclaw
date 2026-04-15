"""Rate Limit Display - API Quota Tracking

Based on Hermes rate_limit_tracker.py (208 lines).
Parses 12 types of x-ratelimit headers, renders ASCII bars with 80% warnings.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RateLimitBucket:
    limit: int = 0
    remaining: int = 0
    reset_seconds: float = 0.0
    captured_at: float = 0.0

    @property
    def used(self) -> int:
        return max(0, self.limit - self.remaining)

    @property
    def usage_pct(self) -> float:
        if self.limit <= 0:
            return 0.0
        return (self.used / self.limit) * 100.0

    @property
    def remaining_seconds_now(self) -> float:
        elapsed = time.time() - self.captured_at
        return max(0.0, self.reset_seconds - elapsed)


@dataclass
class RateLimitState:
    requests_min: RateLimitBucket = field(default_factory=RateLimitBucket)
    requests_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_min: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    captured_at: float = 0.0
    provider: str = ""

    @property
    def has_data(self) -> bool:
        return self.captured_at > 0

    @property
    def age_seconds(self) -> float:
        if not self.has_data:
            return float("inf")
        return time.time() - self.captured_at


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_rate_limit_headers(
    headers: dict,
    provider: str = "",
) -> Optional[RateLimitState]:
    lowered = {k.lower(): v for k, v in headers.items()}
    has_any = any(k.startswith("x-ratelimit-") for k in lowered)
    if not has_any:
        return None

    now = time.time()

    def _bucket(resource: str, suffix: str = "") -> RateLimitBucket:
        tag = f"{resource}{suffix}"
        return RateLimitBucket(
            limit=_safe_int(lowered.get(f"x-ratelimit-limit-{tag}")),
            remaining=_safe_int(lowered.get(f"x-ratelimit-remaining-{tag}")),
            reset_seconds=_safe_float(lowered.get(f"x-ratelimit-reset-{tag}")),
            captured_at=now,
        )

    return RateLimitState(
        requests_min=_bucket("requests"),
        requests_hour=_bucket("requests", "-1h"),
        tokens_min=_bucket("tokens"),
        tokens_hour=_bucket("tokens", "-1h"),
        captured_at=now,
        provider=provider,
    )


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_seconds(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    return f"{m}m {sec}s" if sec else f"{m}m"


def _bar(pct: float, width: int = 20) -> str:
    filled = max(0, min(width, int(pct / 100.0 * width)))
    return f"[{'*' * filled}{'-' * (width - filled)}]"


def _bucket_line(label: str, bucket: RateLimitBucket, lw: int = 14) -> str:
    if bucket.limit <= 0:
        return f"  {label:<{lw}}  (no data)"
    pct = bucket.usage_pct
    used = _fmt_count(bucket.used)
    limit = _fmt_count(bucket.limit)
    remaining = _fmt_count(bucket.remaining)
    reset = _fmt_seconds(bucket.remaining_seconds_now)
    return f"  {label:<{lw}} {_bar(pct)} {pct:5.1f}%  {used}/{limit} ({remaining} left, resets {reset})"


def format_rate_limit_display(state: RateLimitState) -> str:
    if not state.has_data:
        return "No rate limit data yet."
    age = state.age_seconds
    freshness = "just now" if age < 5 else (f"{int(age)}s ago" if age < 60 else _fmt_seconds(age))
    prov = state.provider.title() if state.provider else "Provider"
    lines = [
        f"{prov} Rate Limits (captured {freshness}):",
        "",
        _bucket_line("RPM", state.requests_min),
        _bucket_line("RPH", state.requests_hour),
        "",
        _bucket_line("TPM", state.tokens_min),
        _bucket_line("TPH", state.tokens_hour),
    ]
    warnings = []
    for label, bucket in [
        ("rpm", state.requests_min), ("rph", state.requests_hour),
        ("tpm", state.tokens_min), ("tph", state.tokens_hour),
    ]:
        if bucket.limit > 0 and bucket.usage_pct >= 80:
            reset = _fmt_seconds(bucket.remaining_seconds_now)
            warnings.append(f"  [!] {label.upper()} at {bucket.usage_pct:.0f}% -- resets in {reset}")
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)


def format_rate_limit_compact(state: RateLimitState) -> str:
    if not state.has_data:
        return "No rate limit data."
    parts = []
    rm = state.requests_min
    if rm.limit > 0:
        parts.append(f"RPM: {rm.remaining}/{rm.limit}")
    rh = state.requests_hour
    if rh.limit > 0:
        parts.append(f"RPH: {_fmt_count(rh.remaining)}/{_fmt_count(rh.limit)} (resets {_fmt_seconds(rh.remaining_seconds_now)})")
    tm = state.tokens_min
    if tm.limit > 0:
        parts.append(f"TPM: {_fmt_count(tm.remaining)}/{_fmt_count(tm.limit)}")
    return " | ".join(parts)


if __name__ == "__main__":
    test = {
        "x-ratelimit-limit-requests": "60",
        "x-ratelimit-remaining-requests": "12",
        "x-ratelimit-reset-requests": "45",
        "x-ratelimit-limit-tokens": "100000",
        "x-ratelimit-remaining-tokens": "25000",
        "x-ratelimit-reset-tokens": "45",
    }
    state = parse_rate_limit_headers(test, "openrouter")
    if state:
        print(format_rate_limit_display(state))
