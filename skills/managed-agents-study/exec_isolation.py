# -*- coding: utf-8 -*-
"""
exec_isolation.py — Sandbox 凭证隔离（Anthropic Managed Agents 落地）

对应 CMA 的 Sandbox 安全隔离设计：
- 凭证在 Vault，不在 Sandbox
- Sandbox 内代码对凭证无感知
- 执行时通过注入方式提供（如 Git 远程仓库的本地配置）
- Agent 代码运行时对凭证无感知

核心设计：
- CredentialVault：凭证存储（不在 Sandbox 内）
- inject_credentials()：执行前注入凭证到环境
- strip_credentials()：执行后清除环境中的凭证
- execute_isolated()：带隔离的命令执行

与 CMA 对照：
  CMA: Vault → Sandbox 注入 → Agent 无感知 → 执行后清除
  qclaw: CredentialVault → inject → subprocess → strip
"""

from __future__ import annotations

import os
import re
import copy
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

log = logging.getLogger("qclaw.exec_isolation")

# ─── 凭证模式识别 ─────────────────────────────────────────

# 常见凭证环境变量模式
CREDENTIAL_PATTERNS = [
    r".*_TOKEN$",          # GITHUB_TOKEN, API_TOKEN, etc.
    r".*_KEY$",            # API_KEY, SECRET_KEY, etc.
    r".*_SECRET$",         # CLIENT_SECRET, etc.
    r".*_PASSWORD$",       # DB_PASSWORD, etc.
    r".*_CREDENTIAL$",     # AWS_CREDENTIAL, etc.
    r"AUTH_.*",            # AUTH_TOKEN, etc.
    r"ANTHROPIC_API_KEY",
    r"OPENAI_API_KEY",
    r"DATABASE_URL",       # 可能含密码
]

# 白名单：即使匹配模式也不剥离的环境变量
SAFE_WHITELIST = {
    "PATH",
    "HOME",
    "USER",
    "TEMP",
    "TMP",
    "COMPUTERNAME",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "PYTHONPATH",
    "NODE_PATH",
}


# ─── 凭证 Vault ──────────────────────────────────────────

@dataclass
class CredentialEntry:
    """单个凭证条目"""
    name: str = ""             # 环境变量名
    value: str = ""            # 凭证值
    source: str = ""           # 来源描述（"config"/"env"/"user_input"）
    inject_as: str = ""        # 注入时的变量名（默认=name）
    visible_to: List[str] = field(default_factory=list)  # 允许访问的 sandbox_id 列表


class CredentialVault:
    """
    凭证 Vault（对应 CMA 的 Vault 机制）
    
    核心原则：
    1. 凭证永远不存储在 Sandbox 内
    2. 执行时通过 inject_credentials() 临时注入
    3. 执行后通过 strip_credentials() 清除
    4. Agent 代码对凭证来源无感知
    """

    def __init__(self):
        self._vault: Dict[str, CredentialEntry] = {}
        self._injected: Dict[str, List[str]] = {}  # sandbox_id → [var_names]

    def store(self, name: str, value: str, source: str = "env",
              inject_as: str = "", visible_to: List[str] = None) -> None:
        """存储凭证到 Vault"""
        self._vault[name] = CredentialEntry(
            name=name,
            value=value,
            source=source,
            inject_as=inject_as or name,
            visible_to=visible_to or [],
        )

    def retrieve(self, name: str) -> Optional[str]:
        """从 Vault 获取凭证值"""
        entry = self._vault.get(name)
        return entry.value if entry else None

    def list_entries(self) -> List[str]:
        """列出所有存储的凭证名"""
        return list(self._vault.keys())

    def load_from_env(self) -> int:
        """
        从当前环境变量加载凭证到 Vault
        
        扫描匹配 CREDENTIAL_PATTERNS 的环境变量，
        将它们存储到 Vault 并从当前环境中移除。
        """
        count = 0
        env_copy = dict(os.environ)
        for key, value in env_copy.items():
            for pattern in CREDENTIAL_PATTERNS:
                if re.match(pattern, key):
                    self.store(key, value, source="env")
                    count += 1
                    break
        log.info(f"Loaded {count} credentials from environment into Vault")
        return count

    def inject_credentials(self, sandbox_id: str,
                           env_dict: Dict[str, str] = None) -> Dict[str, str]:
        """
        为指定 Sandbox 注入凭证
        
        Args:
            sandbox_id: Sandbox 标识符
            env_dict: 基础环境变量字典（不含凭证）
        
        Returns:
            注入凭证后的环境变量字典
        """
        env = dict(env_dict or os.environ)

        for name, entry in self._vault.items():
            # 检查可见性
            if entry.visible_to and sandbox_id not in entry.visible_to:
                continue
            inject_name = entry.inject_as
            env[inject_name] = entry.value
            # 记录注入
            if sandbox_id not in self._injected:
                self._injected[sandbox_id] = []
            self._injected[sandbox_id].append(inject_name)

        log.info(f"Injected {len(self._injected.get(sandbox_id, []))} credentials into sandbox {sandbox_id}")
        return env

    def strip_credentials(self, sandbox_id: str,
                          env_dict: Dict[str, str]) -> Dict[str, str]:
        """
        执行后清除 Sandbox 中的凭证
        
        Returns:
            清除凭证后的环境变量字典
        """
        injected = self._injected.pop(sandbox_id, [])
        env = dict(env_dict)
        for var_name in injected:
            env.pop(var_name, None)
        log.info(f"Stripped {len(injected)} credentials from sandbox {sandbox_id}")
        return env


# ─── 凭证检测 ─────────────────────────────────────────────

def detect_credentials_in_output(output: str) -> List[str]:
    """
    检测输出中是否泄露了凭证
    
    Returns: 泄露的凭证名列表
    """
    leaked = []
    # 检查常见凭证格式
    patterns = [
        r'(?:token|key|secret|password)\s*[=:]\s*["\']?\w{16,}',
        r'sk-[a-zA-Z0-9]{20,}',      # OpenAI API key
        r'ghp_[a-zA-Z0-9]{30,}',     # GitHub PAT
        r'AKIA[0-9A-Z]{16}',         # AWS Access Key
    ]
    for pat in patterns:
        if re.search(pat, output, re.IGNORECASE):
            leaked.append(f"pattern:{pat[:30]}")
    return leaked


def sanitize_output(output: str) -> str:
    """
    清理输出中的凭证信息
    
    将匹配凭证模式的字符串替换为 ***。
    """
    sanitized = output
    patterns_replace = [
        (r'(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]+', r'\1***'),
        (r'(ghp_[a-zA-Z0-9]{4})[a-zA-Z0-9]+', r'\1***'),
        (r'(AKIA[0-9A-Z]{4})[0-9A-Z]+', r'\1***'),
        (r'((?:token|key|secret|password)\s*[=:]\s*["\']?)\w{16,}', r'\1***'),
    ]
    for pat, repl in patterns_replace:
        sanitized = re.sub(pat, repl, sanitized, flags=re.IGNORECASE)
    return sanitized


# ─── 隔离执行 ─────────────────────────────────────────────

@dataclass
class IsolatedResult:
    """隔离执行的结果"""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    credentials_leaked: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def execute_isolated(command: str, sandbox_id: str = "default",
                     timeout: int = 60,
                     vault: CredentialVault = None,
                     cwd: str = None) -> IsolatedResult:
    """
    带凭证隔离的命令执行
    
    流程：
    1. 从 Vault 注入凭证到临时环境
    2. 执行命令
    3. 清除环境中的凭证
    4. 检测输出是否泄露凭证
    5. 清理泄露后返回结果
    """
    import time
    start = time.time()
    
    _vault = vault or CredentialVault()
    
    # 1. 注入凭证
    env = _vault.inject_credentials(sandbox_id)
    
    try:
        # 2. 执行命令
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode
        
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = f"Command timed out after {timeout}s"
        exit_code = -1
    except Exception as e:
        stdout = ""
        stderr = str(e)
        exit_code = -1
    finally:
        # 3. 清除凭证
        _vault.strip_credentials(sandbox_id, env)
    
    # 4. 检测泄露
    leaked = detect_credentials_in_output(stdout + stderr)
    
    # 5. 清理泄露
    if leaked:
        log.warning(f"Credentials leaked in output: {leaked}")
        stdout = sanitize_output(stdout)
        stderr = sanitize_output(stderr)
    
    return IsolatedResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        credentials_leaked=leaked,
        duration_seconds=time.time() - start,
    )


# ─── 便捷函数 ─────────────────────────────────────────────

_vault: Optional[CredentialVault] = None

def get_vault() -> CredentialVault:
    """获取全局 CredentialVault 实例"""
    global _vault
    if _vault is None:
        _vault = CredentialVault()
    return _vault
