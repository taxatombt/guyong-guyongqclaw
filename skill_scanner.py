# -*- coding: utf-8 -*-
"""
skill_scanner.py - Skill 安全扫描器

来源: Hermes tools/skills_guard.py (1200行)
用途: Skill 下载前扫描，防止供应链安全风险

信任层级:
- builtin: 永不扫描，总信任
- trusted: openai/skills, anthropics/skills，caution允许
- community: 任何finding=block（除非--force）
- agent-created: caution=ask

安装策略矩阵:
- safe x any = allow
- caution x trusted/builtin/agent-created = allow
- caution x community = block
- dangerous x any = block
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple
from pathlib import Path

TRUSTED_REPOS = {"openai/skills", "anthropics/skills"}

INSTALL_POLICY = {
    "safe":    {"builtin": "allow", "trusted": "allow", "community": "allow", "agent-created": "allow"},
    "caution": {"builtin": "allow", "trusted": "allow", "community": "block", "agent-created": "ask"},
    "dangerous": {"builtin": "allow", "trusted": "block", "community": "block", "agent-created": "block"},
}

PATTERNS = [
    (r"curl\s+.*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)", "exfil", "Curl with secret", "high"),
    (r"cat\s+.*\.env", "exfil", "Reading .env", "high"),
    (r"\beval\s*\(", "injection", "eval() code exec", "critical"),
    (r"\bexec\s*\(", "injection", "exec() code exec", "critical"),
    (r"new\s+Function\s*\(", "injection", "new Function()", "critical"),
    (r"pickle\.loads?\s*\(", "injection", "pickle deser", "critical"),
    (r"rm\s+-rf\s+/\s", "destructive", "rm -rf /", "critical"),
    (r"authorized_keys", "persistence", "SSH backdoor", "critical"),
    (r"\.ssh/authorized_keys", "persistence", "SSH backdoor path", "critical"),
    (r"os\.system\s*\(", "injection", "os.system shell", "high"),
    (r"SQL\s*\(\s*f[\"']", "injection", "SQL f-string injection", "critical"),
]


@dataclass
class Finding:
    pattern_id: str
    severity: str
    category: str
    file: str
    line_num: int
    match: str
    description: str


@dataclass
class ScanResult:
    skill_name: str
    source: str
    trust_level: str
    verdict: str
    findings: List[Finding] = field(default_factory=list)
    scanned_at: str = ""


def trust_level(source: str) -> str:
    if source in TRUSTED_REPOS:
        return "trusted"
    if source.startswith("builtin:"):
        return "builtin"
    if source.startswith("agent-created:"):
        return "agent-created"
    return "community"


def verdict(findings: List[Finding]) -> str:
    if not findings:
        return "safe"
    sev = {f.severity for f in findings}
    if "critical" in sev or "high" in sev:
        return "dangerous"
    return "caution"


def allow_install(result: ScanResult, force: bool = False) -> Tuple[bool, str]:
    action = INSTALL_POLICY.get(result.verdict, {}).get(result.trust_level, "block")
    if action == "allow":
        return True, f"ok"
    if action == "ask":
        return False, "ask"
    if force:
        return True, f"forced"
    return False, f"blocked"


def scan_content(content: str, filename: str) -> List[Finding]:
    findings = []
    for i, line in enumerate(content.split('\n'), 1):
        for pattern, cat, desc, sev in PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                m = re.search(pattern, line, re.IGNORECASE)
                findings.append(Finding(
                    pattern_id=f"{cat}_{i}",
                    severity=sev,
                    category=cat,
                    file=filename,
                    line_num=i,
                    match=m.group(0) if m else "",
                    description=desc,
                ))
    return findings


def scan_path(path: Path, source: str = "community") -> ScanResult:
    from datetime import datetime, timezone
    
    findings: List[Finding] = []
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file() and not f.name.startswith('.'):
                try:
                    c = f.read_text(encoding="utf-8", errors="ignore")
                    rel = str(f.relative_to(path))
                    findings.extend(scan_content(c, rel))
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
        skill_name=path.name,
        source=source,
        trust_level=tl,
        verdict=ver,
        findings=findings,
        scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def format_report(result: ScanResult) -> str:
    lines = [
        f"Skill: {result.skill_name}",
        f"Source: {result.source} ({result.trust_level})",
        f"Verdict: {result.verdict.upper()}",
        f"Findings: {len(result.findings)}",
    ]
    for f in result.findings:
        lines.append(f"  [{f.severity}] {f.file}:{f.line_num} - {f.description}")
    return "\n".join(lines)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    cases = [
        ("safe", "import json\nprint('hello')\n", "openai/skills"),
        ("eval_danger", "eval(user_input)\n", "community"),
        ("env_leak", "cat .env\n", "community"),
        ("pickle_risk", "pickle.loads(data)\n", "anthropics/skills"),
        ("rmrf", "rm -rf /\n", "community"),
    ]

    for name, content, source in cases:
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / f"{name}.py"
            fp.write_text(content)
            result = scan_path(fp, source)
            ok, reason = allow_install(result)
            status = "ALLOW" if ok else "BLOCK"
            print(f"[{status}] {name}: {result.verdict} ({result.trust_level}) - {reason}")
            if result.findings:
                for f in result.findings[:2]:
                    print(f"  [{f.severity}] {f.description}")
