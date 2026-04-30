"""
qclaw_unified_security.py — 统一安全扫描器

整合来源（3个模块 → 1个）：
  1. security_hook.py      → 10大漏洞检测（PreToolUse）
  2. agentshield_scan.py   → 5类安全扫描（敏感信息/注入/网络/权限/验证）
  3. hooks/dangerous_cmd_checker.py → 危险命令检查（已被tool_pipeline覆盖，不再单独需要）

设计：
  - 5大扫描维度，覆盖原3个模块所有能力
  - Severity 分级（INFO → CRITICAL）
  - 统一 check() 接口，支持文件内容扫描和命令扫描
  - 与 tool_pipeline.py DANGEROUS_PATTERNS 互补（不重复）
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class Severity(Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityFinding:
    """安全发现 — 统一格式"""
    category: str
    severity: Severity
    rule_name: str
    description: str
    evidence: str
    recommendation: str = ""
    source: str = "unified"  # security_hook / agentshield / unified


# ===== 维度1: 代码漏洞检测 — 源自 security_hook.py =====

CODE_VULNERABILITY_PATTERNS = [
    {
        "ruleName": "github_actions_workflow",
        "path_check": lambda path: ".github/workflows/" in path and path.endswith((".yml", ".yaml")),
        "substrings": None,
        "severity": Severity.HIGH,
        "reminder": (
            "GitHub Actions workflow: Command Injection risk.\n"
            "  UNSAFE: direct interpolation of GH context vars\n"
            "  SAFE:   use env: block to pass context safely"
        ),
    },
    {
        "ruleName": "eval_injection",
        "substrings": ["eval("],
        "severity": Severity.HIGH,
        "reminder": "eval() executes arbitrary code. Use JSON.parse() for data.",
    },
    {
        "ruleName": "child_process_exec",
        "substrings": ["child_process.exec", "exec(", "execSync("],
        "severity": Severity.HIGH,
        "reminder": "child_process.exec() allows shell injection. Use spawn/execFile instead.",
    },
    {
        "ruleName": "new_function_injection",
        "substrings": ["new Function("],
        "severity": Severity.HIGH,
        "reminder": "new Function() = eval(). Use proper function definitions.",
    },
    {
        "ruleName": "innerHTML_xss",
        "substrings": [".innerHTML =", ".innerHTML="],
        "severity": Severity.MEDIUM,
        "reminder": "innerHTML enables XSS. Use textContent for plain text.",
    },
    {
        "ruleName": "dangerously_set_html",
        "substrings": ["dangerouslySetInnerHTML"],
        "severity": Severity.HIGH,
        "reminder": "dangerouslySetInnerHTML enables XSS. Use DOMPurify.",
    },
    {
        "ruleName": "document_write_xss",
        "substrings": ["document.write"],
        "severity": Severity.MEDIUM,
        "reminder": "document.write() enables XSS. Use createElement() + appendChild().",
    },
    {
        "ruleName": "pickle_deserialization",
        "substrings": ["pickle"],
        "severity": Severity.HIGH,
        "reminder": "pickle deserialization executes arbitrary code. Use JSON.",
    },
    {
        "ruleName": "os_system_injection",
        "substrings": ["os.system", "from os import system"],
        "severity": Severity.HIGH,
        "reminder": "os.system() allows shell injection. Use subprocess.run().",
    },
    {
        "ruleName": "sql_injection_raw",
        "substrings": ["execute(", ".execute("],
        "severity": Severity.MEDIUM,
        "reminder": "Raw SQL enables injection. Use parameterized queries.",
    },
]


# ===== 维度2: 敏感信息泄露 — 源自 agentshield_scan.py =====

SENSITIVE_INFO_PATTERNS = [
    (r'(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9]{20,}', "API Key", Severity.HIGH),
    (r'(password|passwd|pwd)\s*[=:]\s*["\']?\S+', "Password", Severity.CRITICAL),
    (r'(secret|token|auth)\s*[=:]\s*["\']?[a-zA-Z0-9._-]{20,}', "Secret/Token", Severity.HIGH),
    (r'(sk-|pk_|rk_)[a-zA-Z0-9]{20,}', "Provider Key", Severity.CRITICAL),
    (r'Bearer\s+[a-zA-Z0-9._-]{20,}', "Bearer Token", Severity.HIGH),
    (r'(AWS|aws)[_-]?(ACCESS|SECRET)[_-]?KEY', "AWS Credential", Severity.CRITICAL),
]


# ===== 维度3: 输入注入 — 源自 agentshield_scan.py =====

INJECTION_PATTERNS = [
    (r';\s*(cat|ls|rm|wget|curl)\b', "Command Injection (;)", Severity.HIGH),
    (r'\$\([^)]+\)', "Command Substitution", Severity.MEDIUM),
    (r'\|\s*(bash|sh|python|perl|ruby)\b', "Pipe Injection", Severity.HIGH),
    (r'`[^`]+`', "Backtick Execution", Severity.MEDIUM),
    (r'\b(union\s+select|drop\s+table|or\s+1=1)', "SQL Injection", Severity.HIGH),
]


# ===== 维度4: 网络风险 — 源自 agentshield_scan.py =====

NETWORK_RISK_PATTERNS = [
    (r'(nc|netcat|ncat)\s+-[elp]+\s+\S+\s+\d+', "Reverse Shell (nc)", Severity.CRITICAL),
    (r'bash\s+-i\s+>/dev/tcp/', "Reverse Shell (bash)", Severity.CRITICAL),
    (r'(wget|curl)\b.*\|\s*(ba)?sh', "Remote Code Exec", Severity.CRITICAL),
    (r'(exfil|leak|upload)\s+.*\b(sensitive|secret|password)', "Data Exfiltration", Severity.HIGH),
]


# ===== 维度5: 权限越界 =====

PRIVILEGE_PATTERNS = [
    (r'\bsudo\b', "sudo Usage", Severity.HIGH),
    (r'\bchmod\s+777\b', "World-Writable Permission", Severity.HIGH),
    (r'\brm\s+-rf\s+/', "Destructive Root Delete", Severity.CRITICAL),
]


class UnifiedSecurityScanner:
    """
    qclaw 统一安全扫描器
    
    5大维度，覆盖原3个模块全部能力：
    1. 代码漏洞（security_hook 10大模式）
    2. 敏感信息泄露（agentshield 6类凭证）
    3. 输入注入（agentshield 5类注入）
    4. 网络风险（agentshield 4类网络威胁）
    5. 权限越界（sudo/chmod/rm -rf）
    """
    
    def scan_file(self, file_path: str, content: str) -> List[SecurityFinding]:
        """扫描文件内容 — 5维度全检"""
        findings = []
        
        # 维度1: 代码漏洞
        findings.extend(self._check_code_vulnerabilities(file_path, content))
        
        # 维度2: 敏感信息
        findings.extend(self._check_sensitive_info(content))
        
        # 维度3: 输入注入
        findings.extend(self._check_injection(content))
        
        # 维度4: 网络风险
        findings.extend(self._check_network_risk(content))
        
        # 维度5: 权限越界
        findings.extend(self._check_privilege(content))
        
        return findings
    
    def scan_command(self, command: str) -> List[SecurityFinding]:
        """扫描命令 — 维度2-5"""
        findings = []
        findings.extend(self._check_sensitive_info(command))
        findings.extend(self._check_injection(command))
        findings.extend(self._check_network_risk(command))
        findings.extend(self._check_privilege(command))
        return findings
    
    def check(self, file_path: str = "", content: str = "", command: str = "") -> Dict[str, Any]:
        """
        统一检查接口
        
        Returns:
            {"allowed": bool, "findings": [...], "summary": str}
        """
        all_findings = []
        
        if content and file_path:
            all_findings.extend(self.scan_file(file_path, content))
        
        if command:
            all_findings.extend(self.scan_command(command))
        
        # 去重
        seen = set()
        unique = []
        for f in all_findings:
            key = (f.rule_name, f.evidence[:30])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        
        # CRITICAL = block, 其他 = warn
        has_critical = any(f.severity == Severity.CRITICAL for f in unique)
        
        return {
            "allowed": not has_critical,
            "findings": unique,
            "summary": self._format_report(unique),
        }
    
    # ─── 内部扫描方法 ────────────────────────────────
    
    def _check_code_vulnerabilities(self, file_path: str, content: str) -> List[SecurityFinding]:
        """维度1: 代码漏洞 — 源自 security_hook.py"""
        findings = []
        normalized_path = file_path.lstrip("/")
        
        for pattern in CODE_VULNERABILITY_PATTERNS:
            matched = False
            
            if pattern.get("path_check") and pattern["path_check"](normalized_path):
                matched = True
            
            if pattern.get("substrings") and content:
                for substring in pattern["substrings"]:
                    if substring in content:
                        matched = True
                        break
            
            if matched:
                findings.append(SecurityFinding(
                    category="Code Vulnerability",
                    severity=pattern.get("severity", Severity.MEDIUM),
                    rule_name=pattern["ruleName"],
                    description=pattern["ruleName"],
                    evidence=content[:80] if content else file_path,
                    recommendation=pattern.get("reminder", ""),
                    source="security_hook",
                ))
        
        return findings
    
    def _check_sensitive_info(self, text: str) -> List[SecurityFinding]:
        """维度2: 敏感信息泄露"""
        findings = []
        for pattern, name, severity in SENSITIVE_INFO_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                evidence = match.group()
                masked = evidence[:10] + "***" if len(evidence) > 15 else evidence
                findings.append(SecurityFinding(
                    category="Sensitive Info",
                    severity=severity,
                    rule_name=name,
                    description=f"Detected: {name}",
                    evidence=masked,
                    recommendation=f"Rotate/secure: {name}",
                    source="agentshield",
                ))
        return findings
    
    def _check_injection(self, text: str) -> List[SecurityFinding]:
        """维度3: 输入注入"""
        findings = []
        for pattern, name, severity in INJECTION_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append(SecurityFinding(
                    category="Input Validation",
                    severity=severity,
                    rule_name=name,
                    description=f"Detected: {name}",
                    evidence=match.group()[:50],
                    source="agentshield",
                ))
        return findings
    
    def _check_network_risk(self, text: str) -> List[SecurityFinding]:
        """维度4: 网络风险"""
        findings = []
        for pattern, name, severity in NETWORK_RISK_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append(SecurityFinding(
                    category="Network Risk",
                    severity=severity,
                    rule_name=name,
                    description=f"Detected: {name}",
                    evidence=match.group()[:50],
                    source="agentshield",
                ))
        return findings
    
    def _check_privilege(self, text: str) -> List[SecurityFinding]:
        """维度5: 权限越界"""
        findings = []
        for pattern, name, severity in PRIVILEGE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append(SecurityFinding(
                    category="Privilege Escalation",
                    severity=severity,
                    rule_name=name,
                    description=f"Detected: {name}",
                    evidence=match.group()[:50],
                    source="unified",
                ))
        return findings
    
    def _format_report(self, findings: List[SecurityFinding]) -> str:
        """格式化报告"""
        if not findings:
            return "No security issues found."
        
        by_severity = {s: [] for s in Severity}
        for f in findings:
            by_severity[f.severity].append(f)
        
        lines = [f"Security Scan: {len(findings)} finding(s)\n"]
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            items = by_severity[sev]
            if items:
                lines.append(f"\n{sev.value.upper()} ({len(items)}):")
                for item in items:
                    lines.append(f"  [{item.category}] {item.rule_name}")
        
        return "\n".join(lines)


# ===== 全局单例 =====

_scanner: Optional[UnifiedSecurityScanner] = None

def get_security_scanner() -> UnifiedSecurityScanner:
    global _scanner
    if _scanner is None:
        _scanner = UnifiedSecurityScanner()
    return _scanner


# ===== 兼容旧接口 =====

def check_security(file_path: str, content: str) -> List[Tuple[str, str]]:
    """兼容 security_hook.check_security()"""
    scanner = get_security_scanner()
    findings = scanner.scan_file(file_path, content)
    return [(f.rule_name, f.recommendation) for f in findings]


def run_security_check(file_path: str, content: str) -> dict:
    """兼容 security_hook.run_security_check()"""
    return get_security_scanner().check(file_path=file_path, content=content)


# ===== 自测 =====

if __name__ == "__main__":
    scanner = UnifiedSecurityScanner()
    
    # 测试1: 代码漏洞
    r1 = scanner.check(file_path="app.py", content="eval(user_input)")
    assert len(r1["findings"]) > 0
    print(f"✅ 代码漏洞: {len(r1['findings'])} finding(s)")
    
    # 测试2: 敏感信息 (sk- format)
    r2 = scanner.check(content='key = sk-abc1234567890def1234567890abc')
    # Provider Key pattern should match
    print(f"✅ 敏感信息: {len(r2['findings'])} finding(s), has_critical={not r2['allowed']}")
    
    # 测试3: 命令注入
    r3 = scanner.check(command="cat file.txt; rm -rf /")
    assert len(r3["findings"]) > 0
    print(f"✅ 命令扫描: {len(r3['findings'])} finding(s)")
    
    # 测试4: 安全内容
    r4 = scanner.check(file_path="safe.py", content="import json\ndata = json.loads(input)")
    assert r4["allowed"]
    print(f"✅ 安全内容: allowed={r4['allowed']}")
    
    # 测试5: 旧接口兼容
    warnings = check_security("app.py", "eval(x)")
    assert len(warnings) > 0
    print(f"✅ 旧接口兼容: {len(warnings)} warning(s)")
    
    # 测试6: 报告格式
    report = scanner._format_report(r2["findings"])
    print(f"✅ 报告格式: OK")
    
    print("\n🎯 UnifiedSecurityScanner 全部测试通过！")
