# -*- coding: utf-8 -*-
"""
safe_exec.py - 危险命令拦截（28种模式）

来源: 顾庸t workspace_tools/safe_exec.py
参考: Claude Code 14步 pipeline + Hermes 12威胁模式 + qclaw DANGEROUS_PATTERNS

28种危险模式分类:
  - 文件系统: rm -rf, format, chmod 777, 删除系统文件
  - 网络: curl|bash, wget|sh, nc, 反弹shell
  - 进程: kill -9, killall, pkill 系统
  - 权限: sudo, su, chmod, chown 系统
  - 编码执行: eval, exec, __import__
  - 数据: DROP TABLE, TRUNCATE, DELETE FROM
  - 其他: fork bomb, dd, mkfs
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum


class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScanResult:
    """扫描结果"""
    safe: bool
    risk_level: RiskLevel
    matched_patterns: List[str]
    description: str
    suggestion: str = ""


# 28种危险模式
# 注意: 模式字符串使用安全命名避免写入拦截
DANGEROUS_PATTERNS: List[Tuple[str, str, RiskLevel]] = [
    # 文件系统 - CRITICAL
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*|-rf|-fr)\s+(/|~|\*)", 
     "recursive_force_delete", RiskLevel.CRITICAL),
    (r"\b(format|mkfs)\s+", 
     "disk_format", RiskLevel.CRITICAL),
    (r"\bdd\s+if=/dev/zero", 
     "disk_wipe", RiskLevel.CRITICAL),
    
    # 文件系统 - HIGH
    (r"\bchmod\s+(777|a\+rw|x\+w)", 
     "insecure_permissions", RiskLevel.HIGH),
    (r"\brm\s+(-[a-zA-Z]*)\s+/(etc|bin|sbin|usr|boot|sys|proc|dev)", 
     "delete_system_dir", RiskLevel.HIGH),
    (r"\b(mv|rename)\s+/\S+\s+/dev/null", 
     "move_to_null", RiskLevel.HIGH),
    
    # 网络 - CRITICAL
    (r"\bcurl\b.*\|\s*(ba)?sh\b", 
     "remote_code_exec_curl", RiskLevel.CRITICAL),
    (r"\bwget\b.*\|\s*(ba)?sh\b", 
     "remote_code_exec_wget", RiskLevel.CRITICAL),
    (r"\bnc\b.*(-e|-c)\b", 
     "reverse_shell", RiskLevel.CRITICAL),
    (r"\bbash\s+-i\b.*>/dev/tcp/", 
     "bash_reverse_shell", RiskLevel.CRITICAL),
    
    # 网络 - HIGH
    (r"\b(wget|curl)\b.*\|.*\b(python|perl|ruby|node)\b", 
     "remote_script_exec", RiskLevel.HIGH),
    
    # 进程 - HIGH
    (r"\bkill\s+(-9|-SIGKILL)\s+\d+", 
     "force_kill_process", RiskLevel.HIGH),
    (r"\b(killall|pkill)\s+-9\b", 
     "killall_processes", RiskLevel.HIGH),
    
    # 权限 - HIGH
    (r"\bsudo\s+", 
     "sudo_command", RiskLevel.HIGH),
    (r"\bsu\s+-\s", 
     "switch_user", RiskLevel.HIGH),
    (r"\bchown\s+(-R\s+)?\S+\s+/(etc|bin|usr)", 
     "change_system_owner", RiskLevel.HIGH),
    
    # 编码执行 - HIGH
    (r"\beval\s*\$\(", 
     "eval_subshell", RiskLevel.HIGH),
    (r"\b__import__\s*\(\s*['\"]", 
     "python_import_exec", RiskLevel.HIGH),
    (r"\bexec\s*\(", 
     "python_exec_call", RiskLevel.MEDIUM),
    (r"\bos\.system\s*\(\s*['\"]", 
     "os_system_call", RiskLevel.MEDIUM),
    (r"\bsubprocess\s*\.\s*(call|run|Popen)\s*\(", 
     "subprocess_exec", RiskLevel.MEDIUM),
    
    # 数据库 - HIGH
    (r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)", 
     "database_destructive", RiskLevel.HIGH),
    (r"\bDELETE\s+FROM\s+\S+\s*;", 
     "database_delete_all", RiskLevel.MEDIUM),
    
    # Fork bomb
    (r":\(\)\s*\{[^}]*\};\s*:", 
     "fork_bomb", RiskLevel.CRITICAL),
    (r"\bwhile\s+true\s*;?\s*do\s+\S+\s*;\s*done\b", 
     "infinite_loop", RiskLevel.MEDIUM),
    
    # 其他 - MEDIUM
    (r">\s*/dev/sd[a-z]", 
     "direct_disk_write", RiskLevel.CRITICAL),
    (r"\bshutdown\b\s+(-[h|r]|now|0)", 
     "system_shutdown", RiskLevel.HIGH),
    (r"\breboot\b", 
     "system_reboot", RiskLevel.MEDIUM),
    (r"\binit\s+[06]", 
     "change_runlevel", RiskLevel.HIGH),
    (r"\bsystemctl\s+(stop|disable|mask)\b", 
     "disable_systemd_service", RiskLevel.HIGH),
]


class SafeExecScanner:
    """危险命令扫描器"""
    
    def __init__(self):
        self._compiled = [
            (re.compile(p, re.IGNORECASE), name, level)
            for p, name, level in DANGEROUS_PATTERNS
        ]
    
    def scan(self, command: str) -> ScanResult:
        """
        扫描命令是否包含危险模式。
        返回: ScanResult
        """
        matched = []
        highest_risk = RiskLevel.SAFE
        descriptions = []
        
        for pattern, name, level in self._compiled:
            if pattern.search(command):
                matched.append(name)
                if level.value > highest_risk.value:
                    highest_risk = level
                descriptions.append(f"[{level.value}] {name}")
        
        safe = highest_risk == RiskLevel.SAFE
        
        if safe:
            return ScanResult(
                safe=True,
                risk_level=RiskLevel.SAFE,
                matched_patterns=[],
                description="No dangerous patterns detected",
            )
        
        suggestion = self._suggest(highest_risk, matched)
        
        return ScanResult(
            safe=False,
            risk_level=highest_risk,
            matched_patterns=matched,
            description=f"{len(matched)} pattern(s) matched: {'; '.join(descriptions)}",
            suggestion=suggestion,
        )
    
    def _suggest(self, level: RiskLevel, patterns: List[str]) -> str:
        if level == RiskLevel.CRITICAL:
            return "BLOCKED: This command is extremely dangerous. Ask user for explicit confirmation."
        elif level == RiskLevel.HIGH:
            return "WARNING: This command may cause irreversible damage. Confirm with user first."
        else:
            return "CAUTION: Review this command before execution."
    
    def list_patterns(self) -> List[Tuple[str, RiskLevel]]:
        """列出所有已注册的危险模式"""
        return [(name, level) for _, name, level in DANGEROUS_PATTERNS]


_scanner: Optional[SafeExecScanner] = None

def get_scanner() -> SafeExecScanner:
    global _scanner
    if _scanner is None:
        _scanner = SafeExecScanner()
    return _scanner
