#!/usr/bin/env python3
"""
security_hook.py — 顾庸t 安全审计 Hook
来源：Claude Code plugins/security-guidance/security_reminder_hook.py
日期：2026-04-05

功能：
- PreToolUse 钩子，检查 Edit/Write/MultiEdit 中的 10 种危险模式
- session-specific state 避免重复警告
- 30 天自动清理旧状态
- Exit code 2 = block，Exit code 0 = allow

Exit Code：
  0 = ALLOW（无危险模式或已警告过）
  2 = DENY（发现危险模式，阻止执行）

用法：
  python3 security_hook.py --check-file /path/to/file --content "code content"
  python3 security_hook.py --stdin < input.json
  # 作为 PreToolUse hook 调用（OpenClaw hook 集成时使用）
"""

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ===== 安全模式定义 =====

SECURITY_PATTERNS = [
    {
        "ruleName": "github_actions_workflow",
        "path_check": lambda path: ".github/workflows/" in path and path.endswith((".yml", ".yaml")),
        "reminder": """⚠️ Security Warning: GitHub Actions workflow file detected.

Command Injection 风险：
UNSAFE: run: echo "${{ github.event.issue.title }}"
SAFE:   env: TITLE: ${{ github.event.issue.title }}\n      run: echo "$TITLE"

其他危险输入：
- github.event.issue.body
- github.event.pull_request.title
- github.event.commits.*.message
- github.event.head_commit.author.email""",
    },
    {
        "ruleName": "child_process_exec",
        "substrings": ["child_process.exec", "exec(", "execSync("],
        "reminder": """⚠️ Security Warning: child_process.exec() 可导致命令注入漏洞。

安全替代方案：
  from subprocess import call\n  call(['command', arg1, arg2])

exec() 只在以下情况使用：
- 输入保证安全（绝对信任来源）
- 需要 shell 特性（且无替代方案）""",
    },
    {
        "ruleName": "new_function_injection",
        "substrings": ["new Function("],
        "reminder": "⚠️ Security Warning: new Function() 可导致代码注入。仅在确实需要动态执行代码时使用，确保输入完全受控。",
    },
    {
        "ruleName": "eval_injection",
        "substrings": ["eval("],
        "reminder": "⚠️ Security Warning: eval() 执行任意代码，是严重安全风险。优先使用 JSON.parse() 等安全替代方案。",
    },
    {
        "ruleName": "react_dangerously_set_html",
        "substrings": ["dangerouslySetInnerHTML"],
        "reminder": "⚠️ Security Warning: dangerouslySetInnerHTML 可导致 XSS。使用 DOMPurify 等库消毒内容，或使用 textContent。",
    },
    {
        "ruleName": "document_write_xss",
        "substrings": ["document.write"],
        "reminder": "⚠️ Security Warning: document.write() 可被 XSS 利用，且有性能问题。使用 createElement() + appendChild() 替代。",
    },
    {
        "ruleName": "innerHTML_xss",
        "substrings": [".innerHTML =", ".innerHTML="],
        "reminder": "⚠️ Security Warning: innerHTML 设置不可信内容可导致 XSS。使用 textContent 处理纯文本，或使用 DOMPurify 处理 HTML。",
    },
    {
        "ruleName": "pickle_deserialization",
        "substrings": ["pickle"],
        "reminder": "⚠️ Security Warning: pickle 反序列化不可信数据可导致任意代码执行。优先使用 JSON。",
    },
    {
        "ruleName": "os_system_injection",
        "substrings": ["os.system", "from os import system"],
        "reminder": "⚠️ Security Warning: os.system() 使用静态参数，永远不要用用户可控输入。",
    },
    {
        "ruleName": "sql_injection_raw",
        "substrings": ["execute(", ".execute("],
        "reminder": "⚠️ Security Warning: 原始 SQL 拼接容易引发 SQL 注入。使用参数化查询：cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
    },
]


# ===== 状态管理 =====

def get_state_dir() -> Path:
    """获取状态文件目录"""
    state_dir = Path.home() / ".claude"
    try:
        state_dir.mkdir(exist_ok=True)
    except Exception:
        state_dir = Path("/tmp/.claude")
        state_dir.mkdir(exist_ok=True)
    return state_dir


def get_state_file(session_id: str) -> Path:
    return get_state_dir() / f"security_warnings_{session_id}.json"


def cleanup_old_state_files():
    """清理 30 天前的状态文件（10% 概率触发）"""
    if random.random() > 0.1:
        return

    state_dir = get_state_dir()
    if not state_dir.exists():
        return

    try:
        thirty_days_ago = datetime.now().timestamp() - (30 * 24 * 60 * 60)
        for filename in os.listdir(state_dir):
            if filename.startswith("security_warnings_") and filename.endswith(".json"):
                file_path = state_dir / filename
                try:
                    if file_path.stat().st_mtime < thirty_days_ago:
                        file_path.unlink()
                except OSError:
                    pass
    except Exception:
        pass


def load_state(session_id: str) -> set:
    """加载当前 session 的已警告集合"""
    state_file = get_state_file(session_id)
    if state_file.exists():
        try:
            return set(json.loads(state_file.read_text()))
        except Exception:
            return set()
    return set()


def save_state(session_id: str, warnings: set):
    """保存已警告集合"""
    state_file = get_state_file(session_id)
    try:
        get_state_file(session_id).write_text(json.dumps(list(warnings)))
    except Exception:
        pass


# ===== 危险模式检测 =====

def check_patterns(file_path: str, content: str) -> tuple[Optional[str], Optional[str]]:
    """
    检查内容是否匹配危险模式。
    Returns: (ruleName, reminder) 或 (None, None)
    """
    normalized_path = file_path.lstrip("/")

    for pattern in SECURITY_PATTERNS:
        # 路径检查
        if "path_check" in pattern and pattern["path_check"](normalized_path):
            return pattern["ruleName"], pattern["reminder"]

        # 内容检查
        if "substrings" in pattern and content:
            for substring in pattern["substrings"]:
                if substring in content:
                    return pattern["ruleName"], pattern["reminder"]

    return None, None


def extract_tool_content(tool_name: str, tool_input: dict) -> str:
    """从工具输入中提取要检查的内容"""
    if tool_name == "Write":
        return tool_input.get("content", "")
    elif tool_name == "Edit":
        return tool_input.get("new_string", "")
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        return " ".join(e.get("new_string", "") for e in edits)
    return ""


# ===== 主逻辑 =====

def run_check(file_path: str, content: str, session_id: str = "default") -> dict:
    """
    执行安全检查。
    Returns: {
        "allowed": bool,
        "rule_name": str or None,
        "reminder": str or None,
        "warning_key": str or None,
        "is_new_warning": bool
    }
    """
    rule_name, reminder = check_patterns(file_path, content)

    if not rule_name or not reminder:
        return {
            "allowed": True,
            "rule_name": None,
            "reminder": None,
            "warning_key": None,
            "is_new_warning": False,
        }

    warning_key = f"{file_path}-{rule_name}"
    warnings = load_state(session_id)

    is_new = warning_key not in warnings

    if is_new:
        warnings.add(warning_key)
        save_state(session_id, warnings)

    return {
        "allowed": is_new,  # 已警告过则允许（不重复阻止）
        "rule_name": rule_name,
        "reminder": reminder,
        "warning_key": warning_key,
        "is_new_warning": is_new,
    }


# ===== CLI =====

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Security Hook — 检查代码中的安全危险模式。\n"
                    "Exit 0: ALLOW | Exit 2: DENY (new warning)"
    )
    parser.add_argument("--check-file", type=str, help="文件路径")
    parser.add_argument("--content", type=str, default="", help="要检查的代码内容")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取 JSON 输入")
    parser.add_argument("--session-id", type=str, default="default", help="session ID")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--allow", action="store_true", help="强制允许（不阻止）")

    args = parser.parse_args()

    # 清理旧状态
    cleanup_old_state_files()

    # 从 stdin 读取
    if args.stdin:
        try:
            raw = sys.stdin.read()
            input_data = json.loads(raw)
            file_path = input_data.get("file_path", "")
            content = input_data.get("content", "")
            session_id = input_data.get("session_id", args.session_id)
        except json.JSONDecodeError:
            if args.json:
                print(json.dumps({"error": "Invalid JSON input"}))
            sys.exit(0)
    else:
        file_path = args.check_file or ""
        content = args.content
        session_id = args.session_id

    result = run_check(file_path, content, session_id)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    if result["allowed"] or args.allow:
        if args.verbose:
            print(f"✅ No security issues detected: {file_path or 'content'}")
        sys.exit(0)
    else:
        print(f"\n🚫 BLOCKED: {result['rule_name']}")
        print(result["reminder"])
        if result["is_new_warning"]:
            print(f"\n(Only shown once per session. Warning key: {result['warning_key']})")
        sys.exit(2)


if __name__ == "__main__":
    main()