# Hermes Agent V2 Study

{
  "title": "Hermes V2 Study SKILL",
  "date": "2026-04-15",
  "sources": [
    "prompt_builder.py (988l)",
    "approval.py (923l)",
    "checkpoint_manager.py",
    "subdirectory_hints.py (195l)",
    "smart_model_routing.py",
    "redact.py (193l)",
    "rate_limit_tracker.py (208l)",
    "error_classifier.py (811l)",
    "hermes_state.py (1238l)",
    "trajectory_compressor.py (1458l)",
    "mixture_of_agents_tool.py",
    "session_search_tool.py",
    "gateway_hooks.py",
    "hermes_constants.py",
    "AGENTS.md"
  ],
  "modules_to_land": [
    "shadow_git_checkpoints.py",
    "approval_patterns.py",
    "subdirectory_hint_tracker.py",
    "secret_redactor.py",
    "rate_limit_display.py",
    "fts5_session_store.py",
    "trajectory_compress.py",
    "smart_model_router.py",
    "moa_ensemble.py"
  ],
  "key_findings": {
    "two_tier_skills_cache": "L1 LRU + L2 disk snapshot with mtime manifest",
    "contextvar_session_isolation": "contextvars.ContextVar for concurrent approval queues",
    "shadow_git_repos": "GIT_DIR + GIT_WORK_TREE separation, sha256 hash path",
    "progressive_hints": "tool call triggered subdirectory context discovery",
    "self_termination_protection": "prevent agent from killing own process",
    "smart_model_routing": "simple queries go to cheap model",
    "secret_redaction": "31 API key prefix patterns, import-time snapshot",
    "rate_limit_tracking": "12 header types, 4 buckets, 80pct warning",
    "error_classifier": "7-stage pipeline, 18 failover reasons",
    "trajectory_compression": "protect head+tail, summarize middle region",
    "moa_ensemble": "4 reference models + aggregator synthesis"
  }
}