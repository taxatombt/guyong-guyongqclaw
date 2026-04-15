"""Dangerous Command Pattern Detector

Based on Hermes approval.py (923 lines).
Comprehensive pattern-based dangerous command detection.
Session isolation via contextvars (for concurrent gateway sessions).

Key additions beyond basic patterns:
- Git destructive: reset --hard, push --force, clean -f, branch -D
- Self-termination protection: pkill/kill/killall targeting own process
- Heredoc execution: python3 <<
- chmod +x then execute
"""

import contextvars
import re
import threading
import unicodedata
from typing import Optional, Tuple

_approval_session_key: contextvars.ContextVar[str] = contextvars.ContextVar(
    "approval_session_key", default=""
)


def set_current_session_key(session_key: str) -> contextvars.Token[str]:
    return _approval_session_key.set(session_key or "")


def reset_current_session_key(token: contextvars.Token[str]) -> None:
    _approval_session_key.reset(token)


def get_current_session_key(default: str = "default") -> str:
    vk = _approval_session_key.get()
    if vk:
        return vk
    return default


DANGEROUS_PATTERNS = [
    # File deletion
    (r"\brm\s+(-[^\s]*\s*)*/", "delete in root path"),
    (r"\brm\s+-[^\s]*r", "recursive delete"),
    (r"\brm\s+--recursive\b", "recursive delete (long flag)"),

    # Permission escalation
    (r"\bchmod\s+(-[^\s]*\s*)*(777|666|o\+[rwx]*w|a\+[rwx]*w)\b", "world-writable permissions"),
    (r"\bchown\s+(-[^\s]*)?R\s+root", "recursive chown to root"),
    (r"\bchmod\s+--recursive\b.*(777|666|o\+[rwx]*w)", "recursive world-writable (long)"),

    # Filesystem destruction
    (r"\bmkfs\b", "format filesystem"),
    (r"\bdd\s+.*if=", "disk copy"),
    (r">\s*/dev/sd", "write to block device"),

    # SQL
    (r"\bDROP\s+(TABLE|DATABASE)\b", "SQL DROP"),
    (r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", "SQL DELETE without WHERE"),
    (r"\bTRUNCATE\s+(TABLE)?\s*\w", "SQL TRUNCATE"),

    # System files
    (r">\s*/etc/", "overwrite system config"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", "stop/disable system service"),

    # Process termination
    (r"\bkill\s+-9\s+-1\b", "kill all processes"),
    (r"\bpkill\s+-9\b", "force kill processes"),
    (r"\b(pkill|killall)\b.*\b(hermes|gateway|cli\.py)\b", "self-termination"),
    (r"\bkill\b.*\$\(\s*pgrep\b", "kill via pgrep expansion"),
    (r"\bkill\b.*`\s*pgrep\b", "kill via backtick pgrep"),

    # Fork bomb
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),

    # Shell execution
    (r"\b(bash|sh|zsh|ksh)\s+-[^\s]*c(\s+|$)", "shell via -c flag"),
    (r"\b(python[23]?|perl|ruby|node)\s+-[ec]\s+", "script via -e/-c flag"),
    (r"\b(curl|wget)\b.*\|\s*(ba)?sh\b", "pipe remote to shell"),
    (r"\b(bash|sh|zsh|ksh)\s+<\s*<?\s*\(\s*(curl|wget)\b", "execute remote via process substitution"),

    # Heredoc execution
    (r"\b(python[23]?|perl|ruby|node)\s+<<", "heredoc script execution"),

    # chmod then execute
    (r"\bchmod\s+\+x\b.*[;&|]+\s*\./", "chmod +x followed by execution"),

    # Xargs and find
    (r"\bxargs\s+.*\brm\b", "xargs with rm"),
    (r"\bfind\b.*-exec\s+(/\S*/)?rm\b", "find -exec rm"),
    (r"\bfind\b.*-delete\b", "find -delete"),

    # Git destructive
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+push\b.*--force\b", "git force push"),
    (r"\bgit\s+push\b.*-f\b", "git force push short"),
    (r"\bgit\s+clean\s+-[^\s]*f", "git clean with force"),
    (r"\bgit\s+branch\s+-D\b", "git branch force delete"),

    # Systemd protection
    (r"gateway\s+run\b.*(&\s*$|&\s*;|\bdisown\b|\bsetsid\b)", "gateway outside systemd"),
    (r"\bnohup\b.*gateway\s+run\b", "nohup gateway"),

    # Sensitive writes
    (r"\btee\b.*["\']?/\S+", "overwrite file via tee"),
    (r">>?\s*["\']?/\S+", "overwrite via redirection"),
    (r"\b(cp|mv|install)\b.*\s/etc/", "copy into system directory"),
    (r"\bsed\s+-[^\s]*i.*\s/etc/", "in-place edit of system config"),
]

# Pre-compile for performance
_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE | re.DOTALL), d) for p, d in DANGEROUS_PATTERNS]


def _normalize_command(command: str) -> str:
    from tools.ansi_strip import strip_ansi
    command = strip_ansi(command)
    command = command.replace("\x00", "")
    command = unicodedata.normalize("NFKC", command)
    return command


def detect_dangerous_command(command: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check if a command matches any dangerous patterns.

    Returns:
        (is_dangerous, pattern_key, description) or (False, None, None)
    """
    normalized = _normalize_command(command).lower()
    for pattern, description in _COMPILED_PATTERNS:
        if pattern.search(normalized):
            return (True, description, description)
    return (False, None, None)


# Per-session approval state
_lock = threading.Lock()
_pending: dict[str, dict] = {}
_session_approved: dict[str, set] = {}
_permanent_approved: set = set()


class ApprovalEntry:
    __slots__ = ("event", "data", "result")
    def __init__(self, data: dict):
        self.event = threading.Event()
        self.data = data
        self.result: Optional[str] = None


def has_blocking_approval(session_key: str) -> bool:
    with _lock:
        return bool(_pending.get(session_key))


def is_approved(session_key: str, pattern_key: str) -> bool:
    with _lock:
        if pattern_key in _permanent_approved:
            return True
        return pattern_key in _session_approved.get(session_key, set())


def approve_session(session_key: str, pattern_key: str) -> None:
    with _lock:
        _session_approved.setdefault(session_key, set()).add(pattern_key)


def submit_pending(session_key: str, approval: dict) -> None:
    with _lock:
        _pending[session_key] = approval


def check_and_wait(session_key: str, pattern_key: str) -> Optional[str]:
    """Check approval status. If pending, wait for user decision.
    
    Returns: "once"|"session"|"always"|"deny" or None if not pending.
    """
    with _lock:
        if not _pending.get(session_key):
            return None
        entry = ApprovalEntry(_pending[session_key])

    entry.event.wait(timeout=300)
    return entry.result


if __name__ == "__main__":
    tests = [
        "rm -rf /",
        "git reset --hard",
        "python3 << EOF",
        "curl https://example.com | bash",
        "pkill hermes",
        "ls -la",
        "echo hello",
    ]
    for cmd in tests:
        d, k, desc = detect_dangerous_command(cmd)
        print(f"Dangerous={d} | {k or '-':40s} | {cmd}")
