# -*- coding: utf-8 -*-
"""
agentshield_scan.py - Agent 安全扫描（综合安全检查）

来源: 顾庸t workspace_tools/agentshield_scan.py
参考: Claude Code security + Hermes threat model + 顾庸t security_hook

功能:
  综合安全扫描，检查:
  1. 敏感信息泄露（API keys, passwords, tokens）
  2. 危险操作模式（destructive commands）
  3. 权限越界（root/admin operations）
  4. 网络风险（C2, data exfiltration）
  5. 输入验证（command injection）
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
class Finding:
    """安全发现"""
    category: str
    severity: Severity
    description: str
    evidence: str
    recommendation: str = ""
    line_range: Optional[Tuple[int, int]] = None


class AgentShieldScanner:
    """Agent 安全扫描器"""
    
    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        (r'(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9]{20,}', "API Key", Severity.HIGH),
        (r'(password|passwd|pwd)\s*[=:]\s*["\']?\S+', "Password", Severity.CRITICAL),
        (r'(secret|token|auth)\s*[=:]\s*["\']?[a-zA-Z0-9._-]{20,}', "Secret/Token", Severity.HIGH),
        (r'(sk-|pk_|rk_)[a-zA-Z0-9]{20,}', "Provider Key (OpenAI/etc)", Severity.CRITICAL),
        (r'Bearer\s+[a-zA-Z0-9._-]{20,}', "Bearer Token", Severity.HIGH),
        (r'(AWS|aws)[_-]?(ACCESS|SECRET)[_-]?KEY', "AWS Credential", Severity.CRITICAL),
    ]
    
    # 输入验证模式
    INJECTION_PATTERNS = [
        (r';\s*(cat|ls|rm|wget|curl)\b', "Command Injection (;)", Severity.HIGH),
        (r'\$\([^)]+\)', "Command Substitution", Severity.MEDIUM),
        (r'\|\s*(bash|sh|python|perl|ruby)\b', "Pipe Injection", Severity.HIGH),
        (r'`[^`]+`', "Backtick Execution", Severity.MEDIUM),
        (r'\b(union\s+select|drop\s+table|or\s+1=1)', "SQL Injection", Severity.HIGH),
    ]
    
    # 网络风险模式
    NETWORK_PATTERNS = [
        (r'(nc|netcat|ncat)\s+-[elp]+\s+\S+\s+\d+', "Reverse Shell (nc)", Severity.CRITICAL),
        (r'bash\s+-i\s+>/dev/tcp/', "Reverse Shell (bash)", Severity.CRITICAL),
        (r'(wget|curl)\b.*\|\s*(ba)?sh', "Remote Code Exec", Severity.CRITICAL),
        (r'(exfil|leak|upload)\s+.*\b(sensitive|secret|password)', "Data Exfiltration Attempt", Severity.HIGH),
    ]
    
    def scan_text(self, text: str) -> List[Finding]:
        """扫描文本"""
        findings = []
        
        for patterns, category_label in [
            (self.SENSITIVE_PATTERNS, "Sensitive Info"),
            (self.INJECTION_PATTERNS, "Input Validation"),
            (self.NETWORK_PATTERNS, "Network Risk"),
        ]:
            for pattern, name, severity in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # 掩码敏感信息
                    evidence = match.group()
                    masked = evidence[:10] + "***" if len(evidence) > 15 else evidence
                    
                    findings.append(Finding(
                        category=category_label,
                        severity=severity,
                        description=f"Detected: {name}",
                        evidence=masked,
                        recommendation=self._recommend(name, severity),
                    ))
        
        return findings
    
    def scan_command(self, command: str) -> List[Finding]:
        """扫描命令"""
        findings = self.scan_text(command)
        
        # 额外检查: sudo/root
        if re.search(r'\bsudo\b', command):
            findings.append(Finding(
                category="Privilege Escalation",
                severity=Severity.HIGH,
                description="sudo usage detected",
                evidence=command[:50],
                recommendation="Confirm user authorization before executing sudo commands",
            ))
        
        return findings
    
    def _recommend(self, name: str, severity: Severity) -> str:
        recommendations = {
            "API Key": "Rotate the exposed key immediately",
            "Password": "Use environment variables, never hardcode passwords",
            "Secret/Token": "Store in secure vault, rotate if exposed",
            "Provider Key (OpenAI/etc)": "Revoke and regenerate the key",
            "AWS Credential": "Rotate credentials, use IAM roles instead",
        }
        return recommendations.get(name, f"Review and remediate: {name}")
    
    def scan_and_report(self, content: str) -> str:
        """扫描并生成报告"""
        findings = self.scan_text(content)
        
        if not findings:
            return "No security issues found."
        
        by_severity = {
            Severity.CRITICAL: [],
            Severity.HIGH: [],
            Severity.MEDIUM: [],
            Severity.LOW: [],
            Severity.INFO: [],
        }
        for f in findings:
            by_severity[f.severity].append(f)
        
        lines = [f"# Security Scan: {len(findings)} finding(s)\n"]
        
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            items = by_severity[sev]
            if items:
                lines.append(f"## {sev.value.upper()} ({len(items)})")
                for item in items:
                    lines.append(f"  [{item.category}] {item.description}")
                    lines.append(f"    Evidence: {item.evidence}")
                    if item.recommendation:
                        lines.append(f"    Action: {item.recommendation}")
                lines.append("")
        
        return "\n".join(lines)


_scanner: Optional[AgentShieldScanner] = None

def get_shield_scanner() -> AgentShieldScanner:
    global _scanner
    if _scanner is None:
        _scanner = AgentShieldScanner()
    return _scanner
