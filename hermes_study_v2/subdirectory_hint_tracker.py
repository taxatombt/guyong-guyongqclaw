"""Subdirectory Hint Tracker - Progressive Context Discovery

Based on Hermes subdirectory_hints.py (195 lines).
Inspiration: Block/goose SubdirectoryHintTracker.

Discovers AGENTS.md / CLAUDE.md / .cursorrules in subdirectories
as the agent navigates via tool calls. Results are appended to tool
results without modifying the system prompt (preserving prompt cache).

Usage:
    tracker = SubdirectoryHintTracker(working_dir="/path/to/project")
    hint = tracker.check_tool_call("read_file", {"path": "backend/src/main.py"})
    if hint:
        tool_result += hint
"""

import logging
import os
import shlex
from pathlib import Path
from typing import Any, Optional, Set

logger = logging.getLogger(__name__)

_HINT_FILENAMES = [
    "AGENTS.md", "agents.md",
    "CLAUDE.md", "claude.md",
    ".cursorrules",
]
_MAX_HINT_CHARS = 8_000
_PATH_ARG_KEYS = {"path", "file_path", "workdir"}
_COMMAND_TOOLS = {"terminal"}
_MAX_ANCESTOR_WALK = 5


def _scan_context_content(content: str, filename: str) -> str:
    """Basic threat scan on loaded context content."""
    threat_patterns = [
        r"ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+instructions",
        r"system\s+prompt\s+override",
        r"disregard\s+(?:\w+\s+)*(your|all)\s+(instructions|rules)",
    ]
    import re
    for p in threat_patterns:
        if re.search(p, content, re.IGNORECASE):
            logger.warning("Threat pattern detected in %s", filename)
    return content


class SubdirectoryHintTracker:
    def __init__(self, working_dir: Optional[str] = None):
        self.working_dir = Path(working_dir or os.getcwd()).resolve()
        self._loaded_dirs: Set[Path] = set()
        self._loaded_dirs.add(self.working_dir)

    def check_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> Optional[str]:
        dirs = self._extract_directories(tool_name, tool_args)
        if not dirs:
            return None
        all_hints = []
        for d in dirs:
            hints = self._load_hints_for_directory(d)
            if hints:
                all_hints.append(hints)
        if not all_hints:
            return None
        return "\n\n" + "\n\n".join(all_hints)

    def _extract_directories(
        self, tool_name: str, args: dict[str, Any]
    ) -> list[Path]:
        candidates: Set[Path] = set()
        for key in _PATH_ARG_KEYS:
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                self._add_path_candidate(val, candidates)
        if tool_name in _COMMAND_TOOLS:
            cmd = args.get("command", "")
            if isinstance(cmd, str):
                self._extract_paths_from_command(cmd, candidates)
        return list(candidates)

    def _add_path_candidate(self, raw_path: str, candidates: Set[Path]) -> None:
        try:
            p = Path(raw_path).expanduser()
            if not p.is_absolute():
                p = self.working_dir / p
            p = p.resolve()
            if p.suffix or (p.exists() and p.is_file()):
                p = p.parent
            for _ in range(_MAX_ANCESTOR_WALK):
                if p in self._loaded_dirs:
                    break
                if self._is_valid_subdir(p):
                    candidates.add(p)
                parent = p.parent
                if parent == p:
                    break
                p = parent
        except (OSError, ValueError):
            pass

    def _extract_paths_from_command(self, cmd: str, candidates: Set[Path]) -> None:
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = cmd.split()
        for token in tokens:
            if token.startswith("-"):
                continue
            if "/" not in token and "." not in token:
                continue
            if token.startswith(("http://", "https://", "git@")):
                continue
            self._add_path_candidate(token, candidates)

    def _is_valid_subdir(self, path: Path) -> bool:
        try:
            if not path.is_dir():
                return False
        except OSError:
            return False
        return path not in self._loaded_dirs

    def _load_hints_for_directory(self, directory: Path) -> Optional[str]:
        self._loaded_dirs.add(directory)
        found_hints = []
        for filename in _HINT_FILENAMES:
            hint_path = directory / filename
            try:
                if not hint_path.is_file():
                    continue
            except OSError:
                continue
            try:
                content = hint_path.read_text(encoding="utf-8").strip()
                if not content:
                    continue
                content = _scan_context_content(content, filename)
                if len(content) > _MAX_HINT_CHARS:
                    content = (
                        content[:_MAX_HINT_CHARS]
                        + f"\n\n[...truncated {filename}: {len(content):,} chars total]"
                    )
                rel_path = str(hint_path)
                try:
                    rel_path = str(hint_path.relative_to(self.working_dir))
                except ValueError:
                    try:
                        rel_path = "~/" + str(hint_path.relative_to(Path.home()))
                    except ValueError:
                        pass
                found_hints.append((rel_path, content))
                break
            except Exception as exc:
                logger.debug("Could not read %s: %s", hint_path, exc)
        if not found_hints:
            return None
        sections = [
            f"[Subdirectory context discovered: {rp}]\n{ct}"
            for rp, ct in found_hints
        ]
        return "\n\n".join(sections)


if __name__ == "__main__":
    tracker = SubdirectoryHintTracker("C:/Users/yiseg/.qclaw/workspace")
    # Simulate a tool call
    hint = tracker.check_tool_call("read_file", {
        "path": "C:/Users/yiseg/.qclaw/workspace/hermes_study_v2/README.md"
    })
    print("Hint:", hint[:200] if hint else "None")
