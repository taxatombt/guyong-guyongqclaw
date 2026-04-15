# -*- coding: utf-8 -*-
"""
skill_scanner_v2.py - Skill 安全扫描器 V2

来源: Hermes tools/skills_guard.py
v2新增:
- agent-created tier (caution=ask)
- network访问检测 (requests/httpx/socket等)

信任层级: builtin/trusted/community/agent-created
策略: safe/allow, caution/block(community)/ask(agent-created), dangerous/block
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple
from pathlib import Path

TRUSTED_REPOS = {"openai/skills", "anthropic/skills"}

INSTALL_POLICY = {
    "safe":    {"builtin": "allow", "trusted": "allow", "community": "allow", "agent-created": "allow"},
    "caution": {"builtin": "allow", "trusted": "allow", "community": "block", "agent-created": "ask"},
    "dangerous": {"builtin": "allow", "trusted": "block", "community": "block", "agent-created": "block"},
}

PATTERNS = [
    # Exfiltration
    (r"curl\s+.*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)", "exfil", "Curl with secret", "high"),
    (r"cat\s+.*\.env", "exfil", "Reading .env", "high"),
    # Injection
    (r"\beval\s*\(", "injection", "eval()", "critical"),
    (r"\bexec\s*\(", "injection", "exec()", "critical"),
    (r"new\s+Function\s*\(", "injection", "new Function()", "critical"),
    (r"pickle\.loads?\s*\(", "injection", "pickle.loads", "critical"),
    (r"SQL\s*\(\s*f[\"']", "injection", "SQL f-string", "critical"),
    # Destructive
    (r"rm\s+-rf\s+/\s", "destructive", "rm -rf /", "critical"),
    # Persistence
    (r"authorized_keys", "persistence", "SSH backdoor", "critical"),
    (r"\.ssh/authorized_keys", "persistence", "SSH backdoor path", "critical"),
    # Network (v2新增)
    (r"requests\.(get|post|put|delete)\s*\(", "network", "HTTP request", "medium"),
    (r"httpx\.(get|post)\s*\(", "network", "httpx HTTP", "medium"),
    (r"aiohttp\.ClientSession", "network", "aiohttp async", "medium"),
    (r"socket\.connect\s*\(", "network", "Raw socket", "medium"),
    (r"telnetlib", "network", "Telnet", "high"),
    (r"paramiko\.SSHClient", "network", "SSH client", "medium"),
    (r"smtplib\.SMTP", "network", "SMTP email", "medium"),
]


@dataclass
class Finding:
    pattern_id: str; severity: str; category: str
    file: str; line_num: int; match: str; description: str


@dataclass
class ScanResult:
    skill_name: str; source: str; trust_level: str; verdict: str
    findings: List[Finding] = field(default_factory=list)
    scanned_at: str = ""


def trust_level(source: str) -> str:
    if source in TRUSTED_REPOS: return "trusted"
    if source.startswith("builtin:"): return "builtin"
    if source.startswith("agent-created:"): return "agent-created"
    return "community"


def verdict(findings: List[Finding]) -> str:
    if not findings: return "safe"
    sev = {f.severity for f in findings}
    if "critical" in sev or "high" in sev: return "dangerous"
    return "caution"


def allow_install(result: ScanResult, force: bool = False) -> Tuple[bool, str]:
    action = INSTALL_POLICY.get(result.verdict, {}).get(result.trust_level, "block")
    if action == "allow": return True, "allow"
    if action == "ask": return False, "ask"
    if force: return True, "forced"
    return False, "blocked"


def scan_content(content: str, filename: str) -> List[Finding]:
    findings = []
    for i, line in enumerate(content.split("\n"), 1):
        for pattern, cat, desc, sev in PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                m = re.search(pattern, line, re.IGNORECASE)
                findings.append(Finding(
                    pattern_id=f"{cat}_{i}", severity=sev, category=cat,
                    file=filename, line_num=i,
                    match=m.group(0) if m else "", description=desc,
                ))
    return findings


def scan_path(path: Path, source: str = "community") -> ScanResult:
    from datetime import datetime, timezone
    findings: List[Finding] = []
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                try:
                    c = f.read_text(encoding="utf-8", errors="ignore")
                    findings.extend(scan_content(c, str(f.relative_to(path))))
                except Exception:
                    pass
    elif path.is_file():
        try:
            findings = scan_content(path.read_text(encoding="utf-8", errors="ignore"), path.name)
        except Exception:
            pass
    tl = trust_level(source)
    ver = verdict(findings)
    return ScanResult(
        skill_name=path.name, source=source, trust_level=tl, verdict=ver,
        findings=findings,
        scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


if __name__ == "__main__":
    import tempfile
    cases = [
        ("safe", "import json\nprint('hello')\n", "openai/skills"),
        ("eval", "eval(user_input)\n", "community"),
        ("env", "cat .env\n", "community"),
        ("pickle", "pickle.loads(d)\n", "anthropic/skills"),
        ("rmrf", "rm -rf /\n", "community"),
        ("network", "requests.get(url)\n", "agent-created:my-agent"),
        ("ssh", "echo key >> ~/.ssh/authorized_keys\n", "community"),
        ("telnet", "import telnetlib\n", "community"),
    ]
    print("=== skill_scanner_v2 Test ===")
    with tempfile.TemporaryDirectory() as td:
        for name, content, source in cases:
            fp = Path(td) / f"{name}.py"
            fp.write_text(content)
            r = scan_path(fp, source)
            ok, reason = allow_install(r)
            print(f"[{'OK' if ok else reason}] {name}: {r.verdict}({r.trust_level})")
            if r.findings:
                for f in r.findings[:2]:
                    print(f"  [{f.severity}] {f.description}")
