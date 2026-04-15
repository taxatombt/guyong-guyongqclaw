"""Shadow Git Checkpoints - Transparent Filesystem Snapshots

Based on Hermes checkpoint_manager.py.
Creates shadow git repos outside the working directory.
Transparent to the user, no pollution of user project.

Architecture:
    ~/.qclaw/checkpoints/{sha256(abs_dir)[:16]}/  <- shadow repo
        HEAD, refs/, objects/                       <- git internals
        HERMES_WORKDIR                              <- original workdir path

Usage:
    cm = CheckpointManager(enabled=True)
    cm.new_turn()
    cm.ensure_checkpoint("/path/to/project", reason="auto")
    checkpoints = cm.list_checkpoints("/path/to/project")
    diff = cm.diff("/path/to/project", "abc123")
    cm.restore("/path/to/project", "abc123", "src/main.py")
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

CHECKPOINT_BASE = Path.home() / ".qclaw" / "checkpoints"

DEFAULT_EXCLUDES = [
    "node_modules/", "dist/", "build/", ".env", ".env.*", ".env.local",
    "__pycache__/", "*.pyc", ".DS_Store", "*.log", ".cache/", ".next/",
    ".nuxt/", "coverage/", ".pytest_cache/", ".venv/", "venv/", ".git/",
]

_GIT_TIMEOUT = 30
_MAX_FILES = 50_000
_COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


def _normalize_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve()


def _shadow_repo_path(working_dir: str) -> Path:
    abs_path = str(_normalize_path(working_dir))
    dir_hash = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
    return CHECKPOINT_BASE / dir_hash


def _git_env(shadow_repo: Path, working_dir: str) -> dict:
    env = os.environ.copy()
    env["GIT_DIR"] = str(shadow_repo)
    env["GIT_WORK_TREE"] = str(_normalize_path(working_dir))
    env.pop("GIT_INDEX_FILE", None)
    env.pop("GIT_NAMESPACE", None)
    return env


def _run_git(
    args: List[str],
    shadow_repo: Path,
    working_dir: str,
    timeout: int = _GIT_TIMEOUT,
    allowed_returncodes: Optional[Set[int]] = None,
) -> tuple:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_git_env(shadow_repo, working_dir),
        )
        ok = result.returncode == 0
        if not ok and (allowed_returncodes is None or result.returncode not in allowed_returncodes):
            logger.debug("git %s failed: %s", args[0], result.stderr.strip())
        return ok, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except FileNotFoundError:
        return False, "", "git not found"
    except Exception as e:
        return False, "", str(e)


def _validate_hash(h: str) -> Optional[str]:
    if not h or not h.strip(): return "Empty hash"
    if h.startswith("-"): return f"Invalid: starts with dash: {h!r}"
    if not _COMMIT_HASH_RE.match(h): return f"Invalid hash: {h!r}"
    return None


def _validate_file_path(fp: str, workdir: str) -> Optional[str]:
    if not fp or not fp.strip(): return "Empty path"
    if os.path.isabs(fp): return f"Must be relative, got: {fp!r}"
    abs_wd = _normalize_path(workdir)
    resolved = (abs_wd / fp).resolve()
    try:
        resolved.relative_to(abs_wd)
    except ValueError:
        return f"Path escapes workdir: {fp!r}"
    return None


@dataclass
class CheckpointResult:
    success: bool
    hash: Optional[str] = None
    short_hash: Optional[str] = None
    files_changed: int = 0
    error: Optional[str] = None


class CheckpointManager:
    """Manages transparent shadow git checkpoints per working directory."""

    def __init__(self, enabled: bool = False, max_snapshots: int = 50):
        self.enabled = enabled
        self.max_snapshots = max_snapshots
        self._checkpointed_dirs: Set[str] = set()
        self._git_available: Optional[bool] = None

    def new_turn(self) -> None:
        """Reset per-turn dedup. Call at start of each agent iteration."""
        self._checkpointed_dirs.clear()

    def ensure_checkpoint(self, working_dir: str, reason: str = "auto") -> bool:
        """Take a checkpoint if not already done this turn."""
        if not self.enabled:
            return False
        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
        if not self._git_available:
            return False
        abs_dir = str(_normalize_path(working_dir))
        if abs_dir in ("/", str(Path.home())):
            return False
        if abs_dir in self._checkpointed_dirs:
            return False
        self._checkpointed_dirs.add(abs_dir)
        try:
            return self._take(abs_dir, reason)
        except Exception as e:
            logger.debug("Checkpoint failed: %s", e)
            return False

    def _take(self, working_dir: str, reason: str) -> bool:
        shadow = _shadow_repo_path(working_dir)
        shadow.mkdir(parents=True, exist_ok=True)
        # Init if empty
        if not (shadow / "HEAD").exists():
            _run_git(["init"], shadow, working_dir)
            _run_git(["checkout", "--orphan", "main"], shadow, working_dir)
            _run_git(["config", "user.email", "qclaw@checkpoint"], shadow, working_dir)
            _run_git(["config", "user.name", "qclaw"], shadow, working_dir)
            # Write HERMES_WORKDIR marker
            marker = shadow / "HERMES_WORKDIR"
            marker.write_text(str(_normalize_path(working_dir)))
            _run_git(["add", "HERMES_WORKDIR"], shadow, working_dir)
            _run_git(["commit", "-m", "init"], shadow, working_dir)
        # Add all changes
        ok, _, _ = _run_git(["add", "-A"], shadow, working_dir, timeout=_GIT_TIMEOUT * 2)
        if not ok:
            return False
        # Check for changes
        ok, out, _ = _run_git(["diff", "--cached", "--quiet"], shadow, working_dir)
        if ok:
            return False  # no changes
        # Commit
        msg = reason if reason else "auto checkpoint"
        ok, _, _ = _run_git(["commit", "-m", msg], shadow, working_dir)
        return ok

    def list_checkpoints(self, working_dir: str) -> List[Dict]:
        abs_dir = str(_normalize_path(working_dir))
        shadow = _shadow_repo_path(abs_dir)
        if not (shadow / "HEAD").exists():
            return []
        ok, stdout, _ = _run_git(
            ["log", "--format=%H|%h|%aI|%s", "-n", str(self.max_snapshots)],
            shadow, abs_dir,
        )
        if not ok or not stdout:
            return []
        results = []
        for line in stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                entry = dict(zip(["hash", "short_hash", "timestamp", "reason"], parts))
                entry.update(files_changed=0, insertions=0, deletions=0)
                stat_ok, stat_out, _ = _run_git(
                    ["diff", "--shortstat", f"{parts[0]}~1", parts[0]],
                    shadow, abs_dir, allowed_returncodes={128, 129},
                )
                if stat_ok and stat_out:
                    m = re.search(r"(\d+) file", stat_out)
                    if m: entry["files_changed"] = int(m.group(1))
                    m = re.search(r"(\d+) insertion", stat_out)
                    if m: entry["insertions"] = int(m.group(1))
                    m = re.search(r"(\d+) deletion", stat_out)
                    if m: entry["deletions"] = int(m.group(1))
                results.append(entry)
        return results

    def diff(self, working_dir: str, commit_hash: str) -> Dict:
        err = _validate_hash(commit_hash)
        if err:
            return {"success": False, "error": err}
        abs_dir = str(_normalize_path(working_dir))
        shadow = _shadow_repo_path(abs_dir)
        if not (shadow / "HEAD").exists():
            return {"success": False, "error": "No checkpoints"}
        ok, _, err2 = _run_git(["cat-file", "-t", commit_hash], shadow, abs_dir)
        if not ok:
            return {"success": False, "error": f"Hash not found: {commit_hash}"}
        _run_git(["add", "-A"], shadow, abs_dir, timeout=_GIT_TIMEOUT * 2)
        ok_stat, stat_out, _ = _run_git(["diff", "--stat", commit_hash, "--cached"], shadow, abs_dir)
        ok_diff, diff_out, _ = _run_git(["diff", commit_hash, "--cached"], shadow, abs_dir)
        _run_git(["reset", "HEAD", "--quiet"], shadow, abs_dir)
        if not ok_stat and not ok_diff:
            return {"success": False, "error": "Could not generate diff"}
        return {"success": True, "stat": stat_out if ok_stat else "", "diff": diff_out if ok_diff else ""}

    def restore(self, working_dir: str, commit_hash: str, file_path: str = None) -> Dict:
        err = _validate_hash(commit_hash)
        if err:
            return {"success": False, "error": err}
        abs_dir = str(_normalize_path(working_dir))
        if file_path:
            err = _validate_file_path(file_path, abs_dir)
            if err:
                return {"success": False, "error": err}
        shadow = _shadow_repo_path(abs_dir)
        if not (shadow / "HEAD").exists():
            return {"success": False, "error": "No checkpoints"}
        args = ["checkout", commit_hash, "--"]
        if file_path:
            args.append(file_path)
        else:
            args.append(".")
        ok, out, err2 = _run_git(args, shadow, abs_dir)
        if not ok:
            return {"success": False, "error": err2 or "checkout failed"}
        return {"success": True, "restored": file_path or "all files", "hash": commit_hash}


if __name__ == "__main__":
    import tempfile
    cm = CheckpointManager(enabled=True)
    with tempfile.TemporaryDirectory() as td:
        test_file = Path(td) / "test.txt"
        test_file.write_text("hello")
        cm.new_turn()
        ok = cm.ensure_checkpoint(td, "test checkpoint")
        print(f"Checkpoint taken: {ok}")
        cps = cm.list_checkpoints(td)
        print(f"Checkpoints: {len(cps)}")
        if cps:
            print(f"  Latest: {cps[0]['short_hash']} - {cps[0]['reason']}")
