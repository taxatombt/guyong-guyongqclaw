# -*- coding: utf-8 -*-
"""
security_hook.py — 10大漏洞检测安全Hook

来源: 顾庸t workspace_tools/security_hook.py
用途: PreToolUse 检测，扫描代码写入中的安全漏洞

不修改任何现有系统代码，纯新建模块。
"""

import re
from typing import List, Tuple, Optional

# ===== 10大安全模式（参考顾庸t Security Hook）=====

SECURITY_PATTERNS = [
    {
        "ruleName": "github_actions_workflow",
        "path_check": lambda path: ".github/workflows/" in path and path.endswith((".yml", ".yaml")),
        "substrings": None,
        "reminder": (
            "Security Warning: GitHub Actions workflow file detected.\n"
            "Command Injection risk:\n"
            "  UNSAFE: run: echo \"${{ github.event.issue.title }}\"\n"
            "  SAFE:   env: TITLE: ${{ github.event.issue.title }}\n"
            "              run: echo \"$TITLE\"\n"
            "Dangerous context vars:\n"
            "  - github.event.issue.body\n"
            "  - github.event.pull_request.title\n"
            "  - github.event.commits.*.message\n"
            "  - github.event.head_commit.author.email"
        ),
    },
    {
        "ruleName": "child_process_exec",
        "path_check": None,
        "substrings": ["child_process.exec", "exec(", "execSync("],
        "reminder": (
            "Security Warning: child_process.exec() allows shell injection.\n"
            "Use spawn/execFile instead:\n"
            "  from subprocess import call\n"
            "  call(['command', arg1, arg2])\n"
            "exec() merges args into shell string, attacker can inject commands."
        ),
    },
    {
        "ruleName": "new_function_injection",
        "path_check": None,
        "substrings": ["new Function("],
        "reminder": (
            "Security Warning: new Function() creates functions from strings, "
            "equivalent to eval(). Use proper function definitions instead."
        ),
    },
    {
        "ruleName": "eval_injection",
        "path_check": None,
        "substrings": ["eval("],
        "reminder": (
            "Security Warning: eval() executes arbitrary code. "
            "Use JSON.parse() for data, Function constructors for logic."
        ),
    },
    {
        "ruleName": "react_dangerously_set_html",
        "path_check": None,
        "substrings": ["dangerouslySetInnerHTML"],
        "reminder": (
            "Security Warning: dangerouslySetInnerHTML enables XSS. "
            "Use DOMPurify to sanitize, or textContent for plain text."
        ),
    },
    {
        "ruleName": "document_write_xss",
        "path_check": None,
        "substrings": ["document.write"],
        "reminder": (
            "Security Warning: document.write() enables XSS. "
            "Use createElement() + appendChild() instead."
        ),
    },
    {
        "ruleName": "innerHTML_xss",
        "path_check": None,
        "substrings": [".innerHTML =", ".innerHTML="],
        "reminder": (
            "Security Warning: innerHTML enables XSS. "
            "Use textContent for plain text, DOMPurify for HTML."
        ),
    },
    {
        "ruleName": "pickle_deserialization",
        "path_check": None,
        "substrings": ["pickle"],
        "reminder": (
            "Security Warning: pickle deserialization executes arbitrary code. "
            "Use JSON or msgpack for data serialization."
        ),
    },
    {
        "ruleName": "os_system_injection",
        "path_check": None,
        "substrings": ["os.system", "from os import system"],
        "reminder": (
            "Security Warning: os.system() allows shell injection. "
            "Use subprocess.run() with list args instead."
        ),
    },
    {
        "ruleName": "sql_injection_raw",
        "path_check": None,
        "substrings": ["execute(", ".execute("],
        "reminder": (
            "Security Warning: Raw SQL execution enables SQL injection. "
            "Use parameterized queries:\n"
            "  cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"
        ),
    },
]


def check_security(file_path: str, content: str) -> List[Tuple[str, str]]:
    """
    检查文件内容中的安全漏洞
    
    Args:
        file_path: 文件路径
        content: 文件内容
    
    Returns:
        List of (ruleName, reminder) tuples for matched patterns
    """
    warnings = []
    normalized_path = file_path.lstrip("/")
    
    for pattern in SECURITY_PATTERNS:
        matched = False
        
        # 路径检查
        if pattern.get("path_check") and pattern["path_check"](normalized_path):
            matched = True
        
        # 子串检查
        if pattern.get("substrings") and content:
            for substring in pattern["substrings"]:
                if substring in content:
                    matched = True
                    break
        
        if matched:
            warnings.append((pattern["ruleName"], pattern["reminder"]))
    
    return warnings


def extract_tool_content(tool_name: str, tool_input: dict) -> str:
    """
    从工具输入中提取待检查的内容
    
    参考顾庸t extract_tool_content()
    """
    if tool_name == "Write":
        return tool_input.get("content", "")
    elif tool_name == "Edit":
        return tool_input.get("new_string", "")
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        return " ".join(e.get("new_string", "") for e in edits)
    return ""


def run_security_check(file_path: str, content: str) -> dict:
    """
    完整安全检查
    
    Returns:
        {
            "allowed": bool,
            "warnings": List[Tuple[str, str]],
            "summary": str
        }
    """
    warnings = check_security(file_path, content)
    
    if not warnings:
        return {
            "allowed": True,
            "warnings": [],
            "summary": "No security issues detected"
        }
    
    parts = [f"Found {len(warnings)} security warning(s):"]
    for rule_name, reminder in warnings:
        parts.append(f"\n[{rule_name}]")
        parts.append(reminder)
    
    return {
        "allowed": True,  # Warn, don't block (参考顾庸t: exit 0 = allow with warning)
        "warnings": warnings,
        "summary": "\n".join(parts)
    }


if __name__ == "__main__":
    # 测试
    tests = [
        ("app.py", "eval(user_input)"),
        (".github/workflows/ci.yml", "run: echo ${{ github.event.issue.title }}"),
        ("server.js", "child_process.exec(cmd)"),
        ("safe.py", "import json\ndata = json.loads(input)"),
    ]
    
    for path, content in tests:
        result = run_security_check(path, content)
        status = "ALLOW" if result["allowed"] else "BLOCK"
        print(f"\n[{status}] {path}")
        if result["warnings"]:
            for name, _ in result["warnings"]:
                print(f"  Warning: {name}")
