"""Smart Model Router - Simple Query Detection

Based on Hermes smart_model_routing.py.
Detects simple queries and routes them to a cheap model instead of primary.
Conservative by design: only routes obvious simple cases.

Usage:
    from smart_model_router import choose_cheap_model_route, resolve_turn_route
    
    route = choose_cheap_model_route(user_message, routing_config)
    if route:
        # use cheap model
"""

from __future__ import annotations
import os
from typing import Any, Optional

_COMPLEX_KEYWORDS = {
    "debug", "debugging", "implement", "implementation", "refactor", "patch",
    "traceback", "stacktrace", "exception", "error", "analyze", "analysis",
    "investigate", "architecture", "design", "compare", "benchmark",
    "optimize", "optimise", "review", "terminal", "shell", "tool", "tools",
    "pytest", "test", "tests", "plan", "planning", "delegate", "subagent",
    "cron", "docker", "kubernetes",
}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def choose_cheap_model_route(
    user_message: str,
    routing_config: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Return cheap-model route if message looks simple enough.
    
    Conditions for cheap routing (ALL must be true):
    - len(text) <= max_simple_chars (default 160)
    - word_count <= max_simple_words (default 28)
    - newline_count <= 1
    - no code blocks
    - no URLs
    - no complex keywords
    """
    cfg = routing_config or {}
    if not _coerce_bool(cfg.get("enabled"), False):
        return None

    cheap_model = cfg.get("cheap_model") or {}
    if not isinstance(cheap_model, dict):
        return None
    provider = str(cheap_model.get("provider") or "").strip().lower()
    model = str(cheap_model.get("model") or "").strip()
    if not provider or not model:
        return None

    text = (user_message or "").strip()
    if not text:
        return None

    max_chars = _coerce_int(cfg.get("max_simple_chars"), 160)
    max_words = _coerce_int(cfg.get("max_simple_words"), 28)

    if len(text) > max_chars:
        return None
    if len(text.split()) > max_words:
        return None
    if text.count("\n") > 1:
        return None
    if "```" in text or "`" in text:
        return None
    if _has_url(text):
        return None

    words = {token.strip(".,:;!?()[]{}\"'`") for token in text.lower().split()}
    if words & _COMPLEX_KEYWORDS:
        return None

    route = dict(cheap_model)
    route["provider"] = provider
    route["model"] = model
    route["routing_reason"] = "simple_turn"
    return route


def _has_url(text: str) -> bool:
    import re
    return bool(re.search(r"https?://|www\.", text, re.IGNORECASE))


def resolve_turn_route(
    user_message: str,
    routing_config: Optional[dict[str, Any]],
    primary: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the effective model/runtime for one turn.
    
    Returns dict with model/runtime/signature/label fields.
    """
    route = choose_cheap_model_route(user_message, routing_config)
    if not route:
        return {
            "model": primary.get("model"),
            "runtime": {
                "api_key": primary.get("api_key"),
                "base_url": primary.get("base_url"),
                "provider": primary.get("provider"),
                "api_mode": primary.get("api_mode"),
                "command": primary.get("command"),
                "args": list(primary.get("args") or []),
            },
            "label": None,
        }

    return {
        "model": route.get("model"),
        "runtime": {
            "provider": route.get("provider"),
            "base_url": route.get("base_url"),
            "api_key": os.getenv(route.get("api_key_env", "")) or None,
        },
        "label": f"smart route -> {route.get('model')} ({route.get('provider')})",
    }


# Default routing config
DEFAULT_ROUTING_CONFIG = {
    "enabled": False,
    "cheap_model": {
        "provider": "openrouter",
        "model": "google/gemini-3-flash-preview",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "max_simple_chars": 160,
    "max_simple_words": 28,
}


if __name__ == "__main__":
    simple_tests = [
        "What is the capital of France?",
        "Hello! How are you today?",
        "Explain quantum physics",
        "Write a test for my function",
        "帮我查天气",
    ]
    for msg in simple_tests:
        route = choose_cheap_model_route(msg, DEFAULT_ROUTING_CONFIG)
        print(f"Message: {msg[:40]}")
        print(f"Route: {route['routing_reason'] if route else 'primary'}\n")
