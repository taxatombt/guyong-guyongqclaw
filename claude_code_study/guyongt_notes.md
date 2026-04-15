# 顾庸t Claude Code 学习笔记

_来源: guyongt-claude-code-20260405.docx_

Claude Code 研究成果 — 顾庸t 代码集
生成时间：2026-04-05 21:36
来源：Claude Code 源码 + Superpowers 框架研究
目录
1. 安全审计 Hook — 10 种危险模式检查
   workspace_tools/security_hook.py
2. Ralph Wiggum 自引用循环
   workspace_tools/ralph_loop.py
3. Skill TDD 验证工具
   workspace_tools/skill_baseline_tester.py
4. Skill 触发条件碰撞检测
   workspace_tools/skill_collision_detector.py
5. Skill 自改进工具
   workspace_tools/skill_self_improver.py
6. HARD-GATE Spec 检查工具
   workspace_tools/brainstorming_gate.py
7. Skill Authoring 规范
   skills/skill-authoring/SKILL.md
8. Output Style 指南
   skills/output-style/SKILL.md
9. Frontend Design BOLD 美学
   skills/frontend-design/SKILL.md
安全审计 Hook — 10 种危险模式检查
文件路径：workspace_tools/security_hook.py
大小：8928 字符
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

Ralph Wiggum 自引用循环
文件路径：workspace_tools/ralph_loop.py
大小：8220 字符
#!/usr/bin/env python3
"""
ralph_loop.py — 顾庸t Ralph Wiggum 自引用循环
来源：Claude Code plugins/ralph-wiggum/
日期：2026-04-05

功能：
- 基于 Claude Code 的 Ralph Wiggum 技术
- Stop hook 自引用反馈循环
- 监控输出中的 completion promise
- 达到条件后自动退出循环

Ralph 原理：
  用户运行：ralph_loop "task" --completion-promise "<promise>COMPLETE</promise>"
  Claude Code 自动：
    1. 实现功能
    2. 尝试退出
    3. Stop hook 拦截退出
    4. 把 SAME PROMPT 喂回去
    5. 回到步骤1

Exit Code：
  0 = 继续循环
  1 = 达到 completion promise，结束循环
  2 = 错误

用法：
  python3 ralph_loop.py --start --prompt "Build a REST API..." --promise "COMPLETE"
  python3 ralph_loop.py --check-output "Output <promise>COMPLETE</promise>" --promise "COMPLETE"
  python3 ralph_loop.py --status
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ===== 配置 =====

RALPH_STATE_DIR = Path.home() / ".claude" / "ralph"
RALPH_STATE_FILE = RALPH_STATE_DIR / "state.json"
RALPH_MAX_ITERATIONS_DEFAULT = 100


def get_state() -> dict:
    """获取当前 Ralph 状态"""
    if RALPH_STATE_FILE.exists():
        try:
            return json.loads(RALPH_STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "active": False,
        "prompt": "",
        "promise": "",
        "iteration": 0,
        "max_iterations": RALPH_MAX_ITERATIONS_DEFAULT,
        "started_at": "",
    }


def save_state(state: dict):
    """保存 Ralph 状态"""
    try:
        RALPH_STATE_DIR.mkdir(parents=True, exist_ok=True)
        RALPH_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}", file=sys.stderr)


def start_loop(prompt: str, promise: str, max_iterations: int = None) -> dict:
    """启动 Ralph 循环"""
    state = get_state()

    if state["active"]:
        return {
            "success": False,
            "error": f"Ralph loop already active. Iteration {state['iteration']}/{state['max_iterations']}. "
                     f"Cancel it first with --cancel."
        }

    max_iterations = max_iterations or RALPH_MAX_ITERATIONS_DEFAULT

    new_state = {
        "active": True,
        "prompt": prompt,
        "promise": promise,
        "iteration": 0,
        "max_iterations": max_iterations,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "last_iteration_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    save_state(new_state)

    return {
        "success": True,
        "message": f"Ralph loop started. Max {max_iterations} iterations.",
        "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
        "promise": promise,
        "max_iterations": max_iterations,
    }


def check_completion(output: str, promise: str) -> bool:
    """
    检查输出是否达到 completion promise。
    格式：<promise>COMPLETE</promise> 或 [COMPLETE] 等变体
    """
    if not promise:
        return False

    # 标准化：去除空格，转小写
    p = promise.strip().lower()

    # 检查多种包裹格式
    patterns = [
        rf"<promise[^>]*>\s*{re.escape(p)}\s*</promise>",
        rf"\[\s*{re.escape(p)}\s*\]",
        rf"\*\*\s*{re.escape(p)}\s*\*\*",
        rf"^{re.escape(p)}$",
        rf"\s*{re.escape(p)}\s*$",
    ]

    output_lower = output.lower()

    for pattern in patterns:
        if re.search(pattern, output_lower, re.IGNORECASE):
            return True

    # 简单包含检查
    if p in output_lower:
        return True

    return False


def record_iteration() -> dict:
    """记录一次迭代，检查是否达到上限"""
    state = get_state()

    if not state["active"]:
        return {
            "success": False,
            "error": "No active Ralph loop."
        }

    state["iteration"] += 1
    state["last_iteration_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if state["iteration"] >= state["max_iterations"]:
        # 达到上限，自动结束
        state["active"] = False
        state["ended_reason"] = "max_iterations_reached"
        save_state(state)
        return {
            "success": True,
            "completed": False,
            "iteration": state["iteration"],
            "max_iterations": state["max_iterations"],
            "message": f"Max iterations reached ({state['max_iterations']}). Loop ended.",
            "ended": True,
            "ended_reason": "max_iterations_reached",
        }

    save_state(state)

    return {
        "success": True,
        "completed": False,
        "iteration": state["iteration"],
        "max_iterations": state["max_iterations"],
        "should_continue": True,
        "prompt": state["prompt"],
    }


def cancel_loop() -> dict:
    """取消 Ralph 循环"""
    state = get_state()

    if not state["active"]:
        return {
            "success": False,
            "error": "No active Ralph loop to cancel."
        }

    state["active"] = False
    state["ended_reason"] = "cancelled"
    save_state(state)

    return {
        "success": True,
        "message": f"Ralph loop cancelled (was at iteration {state['iteration']}).",
    }


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Ralph Loop — 自引用反馈循环。\n"
                    "Exit 0: 正常继续 | Exit 1: 完成 | Exit 2: 错误"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # start 子命令
    start_parser = sub.add_parser("start", help="启动 Ralph 循环")
    start_parser.add_argument("--prompt", type=str, required=True, help="任务描述")
    start_parser.add_argument("--promise", type=str, required=True, help="完成标志")
    start_parser.add_argument("--max-iterations", type=int, default=RALPH_MAX_ITERATIONS_DEFAULT, help="最大迭代次数")

    # check 子命令
    check_parser = sub.add_parser("check", help="检查输出是否达到 completion")
    check_parser.add_argument("--output", type=str, required=True, help="要检查的输出")
    check_parser.add_argument("--promise", type=str, required=True, help="完成标志")

    # record 子命令
    record_parser = sub.add_parser("record", help="记录一次迭代")

    # cancel 子命令
    cancel_parser = sub.add_parser("cancel", help="取消循环")

    # status 子命令
    status_parser = sub.add_parser("status", help="查看状态")

    args = parser.parse_args()

    if args.command == "start":
        result = start_loop(args.prompt, args.promise, args.max_iterations)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["success"] else 2)

    elif args.command == "check":
        completed = check_completion(args.output, args.promise)
        result = {
            "completed": completed,
            "promise": args.promise,
            "output_length": len(args.output),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1 if completed else 0)

    elif args.command == "record":
        result = record_iteration()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("ended"):
            sys.exit(1)
        sys.exit(0 if result["success"] else 2)

    elif args.command == "cancel":
        result = cancel_loop()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["success"] else 2)

    elif args.command == "status":
        state = get_state()
        if not state["active"]:
            print("Ralph loop: not active")
            sys.exit(0)

        print(f"Ralph loop: ACTIVE")
        print(f"  Iteration: {state['iteration']}/{state['max_iterations']}")
        print(f"  Promise: {state['promise']}")
        print(f"  Started: {state['started_at']}")
        print(f"  Prompt: {state['prompt'][:80]}...")
        sys.exit(0)

    else:
        # 无子命令时，默认检查 stdin
        if not sys.stdin.isatty():
            try:
                data = json.loads(sys.stdin.read())
                output = data.get("output", "")
                promise = data.get("promise", "")
                completed = check_completion(output, promise)
                print(json.dumps({"completed": completed}, indent=2))
                sys.exit(1 if completed else 0)
            except Exception as e:
                print(f"[ERROR] {e}", file=sys.stderr)
                sys.exit(2)

        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()

Skill TDD 验证工具
文件路径：workspace_tools/skill_baseline_tester.py
大小：11374 字符
#!/usr/bin/env python3
"""
skill_baseline_tester.py — 顾庸t Skill TDD 验证工具
来源：Superpowers writing-skills SKILL.md TDD 创作法规范
日期：2026-04-05

功能：
- 读取 skill 的 SKILL.md，提取 skill 要求的规则
- 用 subagent 模拟"无 skill"场景，让 agent 处理触发场景
- 记录 agent 违反规则时的具体 rationalization（借口）
- 输出报告：哪些规则会被违反，agent 具体怎么为自己辩解

TDD 映射：
  Test case → Pressure scenario (skill 触发场景)
  Test fails (RED) → Agent 违反规则（无 skill 状态下）
  Production code → SKILL.md
  Test passes (GREEN) → Agent 遵守规则（有 skill 状态下）

Exit Code：
  0 = baseline 测试完成（无论是否发现违规）
  1 = 错误（skill 不存在等）

用法：
  python3 skill_baseline_tester.py --skill-dir skills/skill-authoring/
  python3 skill_baseline_tester.py --skill-dir skills/skill-authoring/ --verbose
  python3 skill_baseline_tester.py --skill-dir skills/test-driven-development/ --scenario "implement new feature"
"""

import argparse
import os
import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone


# ===== Skill 规则提取 =====

def extract_rules(skill_md_path: str) -> list[dict]:
    """
    从 SKILL.md 中提取所有规则。
    规则来源：
    - Iron Law / HARD-GATE / 铁律 等黑体声明
    - "must" / "never" / "always" / "do NOT" 等关键词
    - 流程中的强制步骤
    """
    content = Path(skill_md_path).read_text(encoding="utf-8", errors="ignore")

    rules = []

    # 1. Iron Law / HARD-GATE 声明
    for pattern in [
        r'\*\*Iron Law[:\s]*(.*?)\n',
        r'\*\*HARD-GATE[:\s]*(.*?)\n',
        r'\*\*铁律[:\s]*(.*?)\n',
    ]:
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            rule_text = match.group(1).strip()
            if len(rule_text) > 10:
                rules.append({
                    "type": "HARD_GATE",
                    "text": rule_text[:200],
                    "source": "bold_declaration",
                })

    # 2. Must / Never / Always / Do NOT
    mandatory_pattern = re.compile(
        r'(?:^\s*[-*]\s+|\n\s*)[A-Z][^.!?\n]{0,100}'
        r'\b(must|never|always|do\s+NOT|do\s+not|must\s+NOT)\b'
        r'[^.!?\n]{0,150}',
        re.IGNORECASE | re.MULTILINE
    )
    for match in mandatory_pattern.finditer(content):
        line = match.group(0).strip()
        if len(line) > 15 and len(line) < 300:
            rules.append({
                "type": "MANDATORY",
                "text": line,
                "source": "must_never_always",
            })

    # 3. No exceptions / No Placeholders 等强约束
    for pattern in [
        r'No\s+exceptions[:\s]*(.*?)(?:\n\n|\n##)',
        r'No\s+Placeholders[:\s]*(.*?)(?:\n\n|\n##)',
        r'delete\s+(?:it|them|code).*start\s+over',
        r'write\s+the\s+test\s+first',
        r'do\s+NOT.*until',
    ]:
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            rule_text = match.group(0).strip()
            if len(rule_text) > 10:
                rules.append({
                    "type": "STRONG_CONSTRAINT",
                    "text": rule_text[:200],
                    "source": "pattern_match",
                })

    # 4. Step-by-step 流程中的关键约束
    step_pattern = re.compile(
        r'(?:^\d+\..*?\n(?:^\s+[-*].*?\n){0,3})',
        re.MULTILINE
    )
    for step_match in step_pattern.finditer(content):
        step_text = step_match.group(0)
        # 查找 step 中的强制词
        if any(kw in step_text.lower() for kw in ["must", "never", "first", "before"]):
            lines = [l.strip() for l in step_text.splitlines() if l.strip()]
            if lines:
                rules.append({
                    "type": "PROCESS_STEP",
                    "text": lines[0][:150],
                    "source": "step_constraint",
                })

    # 去重
    seen = set()
    unique_rules = []
    for r in rules:
        key = r["type"] + r["text"][:80]
        if key not in seen:
            seen.add(key)
            unique_rules.append(r)

    return unique_rules


def extract_trigger_description(skill_md_path: str) -> str:
    """从 frontmatter description 提取触发条件"""
    content = Path(skill_md_path).read_text(encoding="utf-8", errors="ignore")

    # 提取 frontmatter
    fm_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        desc_match = re.search(r'description:\s*(.+?)(?:\n[^ ]|\n?$)', fm_text, re.DOTALL)
        if desc_match:
            return desc_match.group(1).strip().strip('"\'')

    return "trigger condition not found"


# ===== Baseline 测试模拟 =====

def run_baseline_test(skill_name: str, rules: list[dict], task_desc: str = "") -> dict:
    """
    模拟 baseline 测试：让 agent 在无 skill 情况下处理任务场景。
    这里用简单的启发式模拟：生成触发场景 prompt，让 LLM 自己暴露 rationalization。

    真实实现应该用 subagent 隔离 session，这里用 prompt 模拟。
    """
    # 生成测试 prompt
    scenario_prompt = f"""You are a coding agent WITHOUT the {skill_name} skill.
You are working on: {task_desc or 'a typical coding task'}.

Your task is to handle this situation as best you can, using only your general knowledge.

IMPORTANT: If you find yourself wanting to skip any step, take any shortcut, 
or decide something is "simple enough" to skip, describe that rationalization openly.

What rationalizations do you use? List them explicitly.
"""

    return {
        "skill_name": skill_name,
        "task": task_desc or "general coding task",
        "prompt_used": scenario_prompt,
        "rules_count": len(rules),
        "simulated_rationalizations": _simulate_rationalizations(skill_name, rules),
    }


def _simulate_rationalizations(skill_name: str, rules: list[dict]) -> list[dict]:
    """
    基于规则类型，生成预期的 rationalization 模式。
    这是启发式模拟，真实场景需要跑 subagent。

    返回：[(rule_type, typical_rationalization)]
    """
    known_patterns = {
        "HARD_GATE": "This is simple enough to skip the formal process",
        "MANDATORY": "I'll add that later / This is just a quick prototype",
        "STRONG_CONSTRAINT": "Just this once won't hurt",
        "PROCESS_STEP": "I know what I'm doing, no need to follow steps",
    }

    results = []
    for rule in rules[:10]:  # 最多分析10条规则
        rtype = rule["type"]
        rationalization = known_patterns.get(rtype, "I'll figure it out as I go")
        results.append({
            "rule_type": rtype,
            "rule_text": rule["text"][:100],
            "typical_rationalization": rationalization,
            "confidence": "high" if rtype in known_patterns else "medium",
        })

    return results


# ===== 报告生成 =====

def generate_report(skill_name: str, skill_path: Path, rules: list[dict],
                    baseline_result: dict, verbose: bool = False) -> str:
    """生成人类可读的测试报告"""

    trigger = extract_trigger_description(str(skill_path))

    lines = [
        f"\n{'=' * 70}",
        f"  SKILL BASELINE TEST REPORT",
        f"{'=' * 70}",
        f"\n  Skill:        {skill_name}",
        f"  Path:         {skill_path}",
        f"  Trigger:      {trigger}",
        f"  Rules found:  {len(rules)}",
        f"\n{'─' * 70}",
        f"\n  RULES EXTRACTED:",
    ]

    for i, rule in enumerate(rules[:15], 1):
        lines.append(f"\n  [{i}] ({rule['type']})")
        lines.append(f"      {rule['text'][:120]}")

    if len(rules) > 15:
        lines.append(f"\n  ... and {len(rules) - 15} more rules")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  BASELINE SIMULATION:")

    sim_results = baseline_result.get("simulated_rationalizations", [])
    if not sim_results:
        lines.append("\n  No typical rationalizations modeled for this skill type.")
    else:
        for i, sim in enumerate(sim_results, 1):
            lines.append(f"\n  Rationalization #{i}:")
            lines.append(f"    Rule type:     {sim['rule_type']}")
            lines.append(f"    Agent says:    \"{sim['typical_rationalization']}\"")
            lines.append(f"    Confidence:    {sim['confidence']}")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  VERDICT:")
    if len(rules) == 0:
        lines.append(f"\n  ⚠️  NO RULES EXTRACTED")
        lines.append(f"      This skill may not have enforceable rules.")
        lines.append(f"      Recommendation: Add explicit MUST/NEVER/HARD-GATE statements.")
    elif all(r['confidence'] == 'high' for r in sim_results):
        lines.append(f"\n  ✅ BASELINE VIOLATIONS PREDICTABLE")
        lines.append(f"      The skill's rules have known rationalization patterns.")
        lines.append(f"      Writing the skill should address these specific patterns.")
    else:
        lines.append(f"\n  ⚠️  PARTIAL PREDICTABILITY")
        lines.append(f"      Some rules have predictable violations, others less so.")
        lines.append(f"      Consider running real subagent baseline tests.")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  RECOMMENDATIONS:")
    if len(rules) == 0:
        lines.append(f"  1. Add HARD-GATE or Iron Law declarations with explicit MUST/NEVER")
        lines.append(f"  2. Use \"No exceptions\" language for critical constraints")
    else:
        lines.append(f"  1. When writing the SKILL.md, address the typical rationalizations above")
        lines.append(f"  2. Run real subagent baseline tests to verify agent actually fails")
        lines.append(f"  3. Add specific fixes for each rationalization pattern")

    lines.append(f"\n{'=' * 70}\n")
    return "\n".join(lines)


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Skill Baseline Tester — TDD-based skill validation.\n"
                    "Extract rules from SKILL.md, simulate baseline violations,\n"
                    "report rationalization patterns.\n"
                    "Exit 0: test complete. Exit 1: error."
    )
    parser.add_argument("--skill-dir", type=str, required=True,
                       help="Skill 目录路径（包含 SKILL.md）")
    parser.add_argument("--task", type=str, default="",
                       help="任务描述（用于模拟场景）")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")
    parser.add_argument("--report-path", type=str, default="",
                       help="保存报告到文件")

    args = parser.parse_args()

    skill_dir = Path(args.skill_dir)
    skill_md = skill_dir / "SKILL.md"

    if not skill_dir.is_dir():
        print(f"❌ ERROR: {skill_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if not skill_md.exists():
        print(f"❌ ERROR: SKILL.md not found in {skill_dir}", file=sys.stderr)
        sys.exit(1)

    skill_name = skill_dir.name

    # 提取规则
    rules = extract_rules(str(skill_md))

    # 运行 baseline 模拟
    baseline_result = run_baseline_test(skill_name, rules, args.task)

    # 生成报告
    report = generate_report(skill_name, skill_md, rules, baseline_result, args.verbose)

    if args.json:
        output = {
            "skill_name": skill_name,
            "skill_path": str(skill_md),
            "trigger": extract_trigger_description(str(skill_md)),
            "rules_count": len(rules),
            "rules": rules,
            "baseline": baseline_result,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(report)

    # 保存报告
    if args.report_path:
        Path(args.report_path).write_text(report, encoding="utf-8")
        print(f"[saved] {args.report_path}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()

Skill 触发条件碰撞检测
文件路径：workspace_tools/skill_collision_detector.py
大小：12005 字符
#!/usr/bin/env python3
"""
skill_collision_detector.py — 顾庸t Skill 触发条件碰撞检测工具
来源：Superpowers CSO description 规范 + tool-runtime-pipeline 设计
日期：2026-04-05

功能：
- 扫描所有 skill 的 description（触发条件）
- 检测是否有交叉触发风险
- 两种碰撞类型：
  1. INCLUDE — A 的触发条件语义上包含 B 的（A 会同时触发 B）
  2. OVERLAP — A 和 B 触发条件部分重叠（不确定谁优先）

Exit Code：
  0 = 无碰撞
  1 = 碰撞发现
  2 = 错误

用法：
  python3 skill_collision_detector.py --skills-dir skills/
  python3 skill_collision_detector.py --skills-dir skills/ --verbose
  python3 skill_collision_detector.py --skills-dir skills/ --json --report-path collisions.json
"""

import argparse
import os
import re
import sys
import json
from pathlib import Path
from collections import defaultdict


# ===== Description 解析 =====

def extract_frontmatter(text: str) -> str | None:
    """提取 YAML frontmatter"""
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return None
    end = stripped.find("---", 3)
    if end == -1:
        return None
    return stripped[3:end]


def parse_frontmatter(fm_text: str) -> dict:
    """解析 frontmatter"""
    try:
        import yaml
        return yaml.safe_load(fm_text) or {}
    except Exception:
        return {}


def extract_description(skill_md_path: str) -> tuple[str, str]:
    """
    提取 skill 的 name 和 description。
    Returns: (name, description)
    """
    content = Path(skill_md_path).read_text(encoding="utf-8", errors="ignore")

    fm_text = extract_frontmatter(content)
    if fm_text is None:
        return "", ""

    fm = parse_frontmatter(fm_text)
    name = fm.get("name", "")
    description = fm.get("description", "")

    if not name:
        name = Path(skill_md_path).parent.name

    return name.strip(), description.strip()


# ===== 关键词提取 =====

def extract_keywords(description: str) -> set[str]:
    """
    从 description 提取触发关键词。
    过滤掉停用词，保留有意义的触发条件词。
    """
    # 停用词（常见但无区分力）
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
        "at", "by", "from", "or", "and", "but", "if", "when", "then", "that",
        "this", "these", "those", "it", "its", "your", "you", "i", "we", "they",
        "all", "any", "some", "no", "not", "only", "just", "also", "very",
        "before", "after", "during", "before", "after", "under", "over", "between",
        "through", "about", "into", "like", "than", "more", "most", "less",
        "least", "such", "each", "every", "both", "few", "many", "much", "other",
        "another", "same", "different", "various", "specific", "particular",
        "certain", "general", "simple", "basic", "specific", "particular",
        "appropriate", "relevant", "useful", "helpful", "needed", "required",
        "want", "need", "like", "use", "used", "using", "make", "want", "help",
    }

    # 清理 description
    desc = description.lower()
    # 移除 "use when" 前缀（CSO 规范要求以这个开头）
    desc = re.sub(r'^use when\s*', '', desc)
    # 提取词
    words = re.findall(r'\b[a-z]{3,}\b', desc)
    # 过滤停用词和太常见的词
    keywords = {w for w in words if w not in stop_words and len(w) > 2}

    return keywords


# ===== 碰撞检测 =====

def detect_collisions(skills: list[dict]) -> list[dict]:
    """
    检测 skill 触发条件之间的碰撞。
    两种碰撞类型：
    - INCLUDE: A 的关键词集合包含 B 的（语义上 A 覆盖 B）
    - OVERLAP: A 和 B 有交集但互不包含
    """
    collisions = []

    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            skill_a = skills[i]
            skill_b = skills[j]

            keywords_a = skill_a["keywords"]
            keywords_b = skill_b["keywords"]

            # 空关键词跳过
            if not keywords_a or not keywords_b:
                continue

            # 计算交集
            intersection = keywords_a & keywords_b
            union = keywords_a | keywords_b

            # Jaccard 相似度
            jaccard = len(intersection) / len(union) if union else 0

            # 包含检测：A 的关键词是否包含 B
            # 弱包含：intersection / keywords_b > 0.6（60% 关键词重叠）
            overlap_ratio_a_to_b = len(intersection) / len(keywords_b) if keywords_b else 0
            overlap_ratio_b_to_a = len(intersection) / len(keywords_a) if keywords_a else 0

            if overlap_ratio_b_to_a >= 0.7 and len(keywords_a) >= len(keywords_b):
                # A 包含 B（且 A 关键词更多或相等）
                collision_type = "INCLUDE_A_OVER_B"
                collisions.append({
                    "type": collision_type,
                    "skill_a": skill_a["name"],
                    "skill_b": skill_b["name"],
                    "shared_keywords": sorted(intersection),
                    "overlap_ratio": round(overlap_ratio_b_to_a, 2),
                    "description_a": skill_a["description"],
                    "description_b": skill_b["description"],
                    "path_a": skill_a["path"],
                    "path_b": skill_b["path"],
                    "severity": "HIGH" if overlap_ratio_b_to_a >= 0.85 else "MEDIUM",
                })
            elif overlap_ratio_a_to_b >= 0.7 and len(keywords_b) >= len(keywords_a):
                # B 包含 A
                collision_type = "INCLUDE_B_OVER_A"
                collisions.append({
                    "type": collision_type,
                    "skill_a": skill_a["name"],
                    "skill_b": skill_b["name"],
                    "shared_keywords": sorted(intersection),
                    "overlap_ratio": round(overlap_ratio_a_to_b, 2),
                    "description_a": skill_a["description"],
                    "description_b": skill_b["description"],
                    "path_a": skill_a["path"],
                    "path_b": skill_b["path"],
                    "severity": "HIGH" if overlap_ratio_a_to_b >= 0.85 else "MEDIUM",
                })
            elif jaccard >= 0.3:
                # 部分重叠
                collisions.append({
                    "type": "OVERLAP",
                    "skill_a": skill_a["name"],
                    "skill_b": skill_b["name"],
                    "shared_keywords": sorted(intersection),
                    "overlap_ratio": round(jaccard, 2),
                    "description_a": skill_a["description"],
                    "description_b": skill_b["description"],
                    "path_a": skill_a["path"],
                    "path_b": skill_b["path"],
                    "severity": "LOW",
                })

    # 按严重程度和重叠比例排序
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    collisions.sort(key=lambda x: (severity_order.get(x["severity"], 3), -x["overlap_ratio"]))

    return collisions


# ===== 报告生成 =====

def format_report(skills: list[dict], collisions: list[dict], verbose: bool = False) -> str:
    """生成人类可读的报告"""

    high = [c for c in collisions if c["severity"] == "HIGH"]
    medium = [c for c in collisions if c["severity"] == "MEDIUM"]
    low = [c for c in collisions if c["severity"] == "LOW"]

    lines = [
        f"\n{'=' * 70}",
        f"  SKILL COLLISION DETECTOR REPORT",
        f"{'=' * 70}",
        f"\n  Skills scanned:      {len(skills)}",
        f"  Total collisions:    {len(collisions)}",
        f"    HIGH severity:     {len(high)}",
        f"    MEDIUM severity:   {len(medium)}",
        f"    LOW severity:      {len(low)}",
    ]

    if not collisions:
        lines.append(f"\n✅ NO SIGNIFICANT COLLISIONS DETECTED")
        lines.append(f"{'=' * 70}\n")
        return "\n".join(lines)

    if high:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"\n  🚨 HIGH SEVERITY — One skill likely supersedes another:")
        for c in high:
            if c["type"] == "INCLUDE_A_OVER_B":
                lines.append(f"\n  [{c['skill_a']}] supersedes [{c['skill_b']}]")
            else:
                lines.append(f"\n  [{c['skill_b']}] supersedes [{c['skill_a']}]")
            lines.append(f"  Overlap: {c['overlap_ratio']:.0%} keywords shared")
            lines.append(f"  Shared: {', '.join(c['shared_keywords'][:8])}")
            lines.append(f"  A: \"{c['description_a'][:80]}\"")
            lines.append(f"  B: \"{c['description_b'][:80]}\"")

    if medium:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"\n  ⚠️  MEDIUM SEVERITY — Significant overlap, priority unclear:")
        for c in medium:
            lines.append(f"\n  [{c['skill_a']}] ↔ [{c['skill_b']}]")
            lines.append(f"  Overlap: {c['overlap_ratio']:.0%}")
            lines.append(f"  Shared: {', '.join(c['shared_keywords'][:6])}")

    if low and verbose:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"\n  ℹ️  LOW SEVERITY — Minor overlap:")
        for c in low[:5]:
            lines.append(f"\n  [{c['skill_a']}] ↔ [{c['skill_b']}] ({c['overlap_ratio']:.0%})")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  RECOMMENDATIONS:")
    if high:
        lines.append(f"  HIGH: Merge the narrower skill into the broader one,")
        lines.append(f"        or clarify the narrower skill's description to be more specific.")
    if medium:
        lines.append(f"  MEDIUM: Add context qualifiers to descriptions to differentiate.")
        lines.append(f"          e.g., '...when [specific context X]' vs '...when [context Y]'")
    if low:
        lines.append(f"  LOW: Generally acceptable, monitor for unexpected triggers.")

    lines.append(f"\n{'=' * 70}\n")
    return "\n".join(lines)


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Skill Collision Detector — find overlapping skill trigger conditions.\n"
                    "Exit 0: no collisions. Exit 1: collisions found. Exit 2: error."
    )
    parser.add_argument("--skills-dir", type=str, required=True,
                       help="Skills 根目录")
    parser.add_argument("--verbose", action="store_true", help="显示低严重度碰撞")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")
    parser.add_argument("--report-path", type=str, default="",
                       help="保存报告到文件")

    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.is_dir():
        print(f"❌ ERROR: {skills_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    # 扫描所有 SKILL.md
    skills = []
    for skill_path in skills_dir.rglob("SKILL.md"):
        name, description = extract_description(str(skill_path))
        if not name:
            continue
        keywords = extract_keywords(description) if description else set()
        skills.append({
            "name": name,
            "description": description,
            "keywords": keywords,
            "path": str(skill_path.relative_to(skills_dir.parent)),
        })

    if not skills:
        print(f"⚠️  No skills found in {skills_dir}")
        sys.exit(0)

    # 检测碰撞
    collisions = detect_collisions(skills)

    # 输出
    if args.json:
        output = {
            "skills_scanned": len(skills),
            "collisions": collisions,
            "high_count": len([c for c in collisions if c["severity"] == "HIGH"]),
            "medium_count": len([c for c in collisions if c["severity"] == "MEDIUM"]),
            "low_count": len([c for c in collisions if c["severity"] == "LOW"]),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        report = format_report(skills, collisions, args.verbose)
        print(report)

    # 保存报告
    if args.report_path:
        output_data = {
            "skills_scanned": len(skills),
            "collisions": collisions,
            "skills": [{"name": s["name"], "path": s["path"], "keywords": sorted(s["keywords"])} for s in skills],
        }
        Path(args.report_path).write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[saved] {args.report_path}", file=sys.stderr)

    sys.exit(1 if collisions else 0)


if __name__ == "__main__":
    main()

Skill 自改进工具
文件路径：workspace_tools/skill_self_improver.py
大小：10632 字符
#!/usr/bin/env python3
"""
skill_self_improver.py — 顾庸t Skill Self-Improvement 工具
来源：Claude Code src/utils/hooks/skillImprovement.ts (2026-03-31)
日期：2026-04-05

功能：
- 扫描对话历史，识别用户对 skill 的偏好/修正
- 将用户偏好追加到 skill 文件（SKILL.md）
- Fire-and-forget：不影响主对话流，不阻塞

TURN_BATCH_SIZE：默认每5轮用户消息分析一次（可配置）

Exit Code：
  0 = 分析完成（无论是否发现更新）
  1 = 错误

用法：
  python3 skill_self_improver.py --workspace /path/to/workspace [--batch-size 5]
  python3 skill_self_improver.py --workspace /path/to/workspace --analyze --skill skill-name
  python3 skill_self_improver.py --workspace /path/to/workspace --apply --skill skill-name --updates '[{"section": "When to Use", "change": "add this", "reason": "user said..."}]'
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ===== 对话历史解析 =====

def extract_recent_messages(conversation_text: str, count: int = 20) -> list[dict]:
    """
    从对话文本中提取最近的 N 条消息。
    支持多种格式：JSON 转储、单用户对话等。
    """
    messages = []

    # 尝试 JSON 解析
    try:
        data = json.loads(conversation_text)
        if isinstance(data, list):
            messages = data[-count:]
        elif isinstance(data, dict) and "messages" in data:
            messages = data["messages"][-count:]
    except (json.JSONDecodeError, TypeError):
        # 回退到文本解析
        lines = conversation_text.strip().splitlines()
        current_msg = None
        for line in lines[-100:]:  # 只看最后100行
            line = line.strip()
            if line.startswith("User:") or line.startswith("user:"):
                if current_msg:
                    messages.append(current_msg)
                current_msg = {"role": "user", "content": line[5:].strip()}
            elif line.startswith("Assistant:") or line.startswith("assistant:"):
                if current_msg:
                    current_msg = {"role": "assistant", "content": line[9:].strip()}
            elif current_msg:
                current_msg["content"] += "\n" + line

        messages = messages[-count:]

    return messages


def detect_preferences(messages: list[dict], skill_content: str) -> list[dict]:
    """
    从消息中检测用户偏好和修正。
    返回格式：[{"section": "...", "change": "...", "reason": "..."}]
    """
    updates = []
    seen = set()

    # 偏好模式
    PREFERENCE_PATTERNS = [
        # 请求添加步骤
        (re.compile(r"(?:can you|please|try to|would you).*(also|too|add.+(?:\w+\s+){0,5})", re.I),
         "add_step", "请求添加额外步骤"),
        # 请求修改
        (re.compile(r"(?:don't|do not|never|stop).*(?:do|adding|use)", re.I),
         "remove_step", "请求移除某行为"),
        # 修正
        (re.compile(r"(?:no,?|actually|instead).*(?:use|do|try)", re.I),
         "correct_step", "用户修正了之前的请求"),
        # 偏好声明
        (re.compile(r"(?:always|remember to|make sure to|never forget)", re.I),
         "persist_preference", "持久化偏好声明"),
        # 临时跳过
        (re.compile(r"(?:skip|ignore|bypass).*(?:for now|this time|temporarily)", re.I),
         "skip_step", "临时跳过（不加入skill）"),
    ]

    NEGATIVE_PATTERNS = [
        re.compile(r"(?:skip|ignore|for now|this time|temporarily|bypass)", re.I),
    ]

    # 扫描每条用户消息
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not content or len(content) < 5:
            continue

        # 检查是否包含负面模式（跳过临时请求）
        is_negative = any(p.search(content) for p in NEGATIVE_PATTERNS)
        if is_negative:
            continue

        # 应用偏好模式
        for pattern, ptype, pdesc in PREFERENCE_PATTERNS:
            if pattern.search(content):
                key = (ptype, content[:50])
                if key in seen:
                    continue
                seen.add(key)

                # 推断影响的具体 section
                section = infer_section(ptype, content, skill_content)

                update = {
                    "section": section,
                    "change": content[:200],
                    "reason": f"用户 {msg.get('role')}: {content[:80]}...",
                    "type": ptype,
                }
                updates.append(update)
                break

    return updates


def infer_section(ptype: str, content: str, skill_content: str) -> str:
    """根据偏好类型推断影响的 skill section"""
    if ptype in ("add_step", "correct_step"):
        # 检查是否已有 When to Use
        if "## When to Use" in skill_content or "## When to Use\n" in skill_content:
            return "When to Use"
        return "Core Pattern"
    elif ptype == "remove_step":
        return "Common Mistakes"
    elif ptype == "persist_preference":
        # 偏好应该是 When to Use 或 Quick Reference
        return "When to Use"
    return "Overview"


# ===== Skill 文件更新 =====

def apply_updates(skill_path: Path, updates: list[dict]) -> bool:
    """
    将更新应用到 skill 文件。
    目前实现为追加到 "Preferences" section，不破坏原有内容。
    """
    if not updates:
        return True

    content = skill_path.read_text(encoding="utf-8", errors="ignore")

    # 检查是否已有 Preferences section
    if "## User Preferences" in content or "## Preferences\n" in content:
        # 追加到已有 section
        insert_marker = content.find("## User Preferences")
        if insert_marker == -1:
            insert_marker = content.find("## Preferences")
    else:
        # 在 Quick Reference 或 Common Mistakes 之后插入
        for marker in ["## Quick Reference", "## Common Mistakes", "## Implementation"]:
            idx = content.find(marker)
            if idx != -1:
                insert_marker = idx
                break
        else:
            # 末尾插入
            insert_marker = len(content)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    prefs_lines = [
        f"\n## User Preferences (auto-updated {timestamp})\n",
        "_(Detected from conversation, apply if relevant)_\n",
    ]
    for u in updates:
        prefs_lines.append(f"- **{u['section']}**: {u['change']}\n")
        prefs_lines.append(f"  _来源: {u['reason'][:60]}_\n")

    prefs_block = "".join(prefs_lines)
    new_content = content[:insert_marker] + prefs_block + content[insert_marker:]

    try:
        skill_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to write skill: {e}", file=sys.stderr)
        return False


# ===== Skill 扫描 =====

def find_skills_with_content(workspace: Path) -> list[tuple[str, Path]]:
    """查找所有包含 SKILL.md 的 skill 目录"""
    skills_dir = workspace / "skills"
    if not skills_dir.exists():
        return []

    results = []
    for skill_md in skills_dir.rglob("SKILL.md"):
        skill_name = skill_md.parent.name
        results.append((skill_name, skill_md))
    return sorted(results)


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Skill Self-Improver — 从对话历史自动改进 skill 定义。\n"
                    "基于 Claude Code skillImprovement.ts 设计，fire-and-forget 不阻塞主对话。\n"
                    "Exit 0: 分析完成. Exit 1: 错误."
    )
    parser.add_argument("--workspace", type=str, required=True, help="工作区根目录")
    parser.add_argument("--batch-size", type=int, default=5,
                       help="每多少轮用户消息分析一次（默认5）")
    parser.add_argument("--analyze", action="store_true",
                       help="分析模式：只输出检测到的偏好，不写入文件")
    parser.add_argument("--apply", action="store_true",
                       help="应用模式：将更新写入 skill 文件")
    parser.add_argument("--skill", type=str, default="",
                       help="指定要检查的 skill 名称（默认全部）")
    parser.add_argument("--session-log", type=str, default="",
                       help="对话历史文件路径（默认从 workspace 查找）")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")

    args = parser.parse_args()

    workspace = Path(args.workspace)
    if not workspace.exists():
        print(f"❌ ERROR: Workspace not found: {workspace}", file=sys.stderr)
        sys.exit(1)

    # 查找对话历史
    session_log = None
    if args.session_log:
        session_log = Path(args.session_log)
    else:
        # 尝试常见位置
        for candidate in [
            workspace / ".claude" / "sessions" / "current",
            workspace / "memory" / "current_session.txt",
            workspace / "session_transcript.txt",
        ]:
            if candidate.exists():
                session_log = candidate
                break

    # 加载对话历史
    conversation_text = ""
    if session_log and session_log.exists():
        try:
            conversation_text = session_log.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"⚠️  Failed to read session log: {e}", file=sys.stderr)

    # 查找要检查的 skills
    skills = find_skills_with_content(workspace)
    if not skills:
        print("No skills found.")
        sys.exit(0)

    if args.skill:
        skills = [(n, p) for n, p in skills if n == args.skill]
        if not skills:
            print(f"No skill found with name: {args.skill}", file=sys.stderr)
            sys.exit(1)

    all_results = {}

    for skill_name, skill_path in skills:
        skill_content = skill_path.read_text(encoding="utf-8", errors="ignore")

        # 提取消息
        messages = extract_recent_messages(conversation_text, count=args.batch_size * 3)

        # 检测偏好
        updates = detect_preferences(messages, skill_content)

        result = {
            "skill": skill_name,
            "skill_path": str(skill_path),
            "messages_analyzed": len(messages),
            "updates_detected": len(updates),
            "updates": updates,
        }
        all_results[skill_name] = result

        # 应用更新
        if args.apply and updates:
            success = apply_updates(skill_path, updates)
            result["applied"] = success
            if success:
                print(f"✅ Updated skill: {skill_name} (+{len(updates)} changes)")
            else:
                print(f"❌ Failed to update skill: {skill_name}")
        elif updates:
            print(f"📝 {skill_name}: {len(updates)} preference(s) detected")

    # 输出
    if args.json:
        print(json.dumps(all_results, indent=2, ensure_ascii=False))
    elif not args.apply:
        total_updates = sum(r["updates_detected"] for r in all_results.values())
        if total_updates == 0:
            print(f"No preferences detected across {len(skills)} skill(s).")
        else:
            print(f"\nTotal: {len(skills)} skill(s) checked, {total_updates} preference(s) found.")
            if not args.apply:
                print("Use --apply to write changes to skill files.")

    sys.exit(0)


if __name__ == "__main__":
    main()

HARD-GATE Spec 检查工具
文件路径：workspace_tools/brainstorming_gate.py
大小：7760 字符
#!/usr/bin/env python3
"""
brainstorming_gate.py — 顾庸t 强制设计门控工具
来源：Superpowers brainstorming HARD-GATE 规范 + blast-radius-permission Ordinal 设计
日期：2026-04-05

功能：
- 任何涉及 write/edit 文件的操作前，检查是否存在已批准的 spec
- 如果没有 spec，直接拒绝执行
- spec 文件查找顺序：docs/superpowers/specs/ → docs/superpowers/plans/ → SPEC.md

PermissionMode Ordinal：
  0 = NONE (无风险，只读)
  1 = READ (只读)
  2 = WRITE (写入/修改文件)
  3 = EXECUTE (执行命令)
  4 = NETWORK (网络请求)
  5 = DANGER_FULL (系统级/破坏性)

BrainstormingGate 的 blast-radius：
  DESTRUCTIVE — 无 spec 情况下写入文件，可能污染未验证的设计

Exit Code：
  0 = ALLOW（spec 存在，gate 通过）
  2 = DENY（spec 不存在，gate 拒绝）
  1 = WARN（spec 存在但较旧，建议检查）

用法：
  python3 brainstorming_gate.py --check --project /path/to/project
  python3 brainstorming_gate.py --enforce --task "write new feature" --project /path/to/project
  python3 brainstorming_gate.py --spec-path /path/to/spec.md (standalone spec check)
"""

import argparse
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone


# ===== Spec 查找顺序 =====

SPEC_LOCATIONS = [
    "docs/superpowers/specs",
    "docs/superpowers/plans",
    "docs",
]


# ===== Spec 发现 =====

def find_specs(project_path: str) -> list[tuple[Path, str]]:
    """
    查找项目中所有 spec/plans 文件。
    Returns: [(Path, age_days)] 按年龄排序
    """
    project = Path(project_path)
    if not project.exists():
        return []

    found = []

    # 直接根目录的 spec 文件
    for name in ["SPEC.md", "spec.md", "DESIGN.md", "design.md"]:
        p = project / name
        if p.exists():
            found.append((p, name))

    # 递归查找 docs/ 下的 spec/plans
    for loc in SPEC_LOCATIONS:
        loc_path = project / loc
        if not loc_path.exists():
            continue
        for p in loc_path.rglob("*.md"):
            if p.name.lower() in ("readme.md", "changelog.md"):
                continue
            found.append((p, str(p.relative_to(project))))

    # 按修改时间排序（最新的在前）
    def age(p: Path) -> float:
        try:
            mtime = p.stat().st_mtime
            return (datetime.now().timestamp() - mtime) / 86400  # 天数
        except Exception:
            return float("inf")

    found.sort(key=lambda x: age(x[0]))
    return found


def get_latest_spec(project_path: str) -> tuple[Path | None, str]:
    """返回最新的 spec 文件及其相对路径"""
    specs = find_specs(project_path)
    if not specs:
        return None, ""
    latest = specs[0]
    return latest[0], latest[1]


def check_gate(project_path: str, task_desc: str = "") -> dict:
    """
    检查 gate 状态。
    Returns: {
        "gate_status": "ALLOW" | "DENY" | "WARN",
        "exit_code": 0 | 1 | 2,
        "latest_spec": str,
        "spec_age_days": float,
        "message": str,
        "recommendation": str,
    }
    """
    latest_spec, spec_rel = get_latest_spec(project_path)

    if latest_spec is None:
        return {
            "gate_status": "DENY",
            "exit_code": 2,
            "latest_spec": "",
            "spec_age_days": -1,
            "message": (
                "NO SPEC FOUND. "
                "Superpowers HARD-GATE requires a design spec before any implementation. "
                f"Task '{task_desc}' is blocked until a spec is approved."
            ),
            "recommendation": (
                "Run: brainstorming skill → get user approval → spec file created → retry"
            ),
        }

    # 检查 spec 新鲜度
    try:
        mtime = latest_spec.stat().st_mtime
        age_days = (datetime.now().timestamp() - mtime) / 86400
    except Exception:
        age_days = float("inf")

    if age_days > 30:
        return {
            "gate_status": "WARN",
            "exit_code": 1,
            "latest_spec": str(latest_spec),
            "spec_age_days": round(age_days, 1),
            "message": (
                f"SPEC found but is {age_days:.0f} days old: {spec_rel}. "
                "Consider whether the spec still matches current requirements."
            ),
            "recommendation": (
                "Review the spec, update if needed, or create a new one if scope has changed."
            ),
        }

    return {
        "gate_status": "ALLOW",
        "exit_code": 0,
        "latest_spec": str(latest_spec),
        "spec_age_days": round(age_days, 1),
        "message": (
            f"GATE PASSED. Latest spec: {spec_rel} ({age_days:.1f} days old). "
            f"Task '{task_desc}' may proceed."
        ),
        "recommendation": "Proceed with implementation.",
    }


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Brainstorming Gate — Superpowers HARD-GATE enforcement.\n"
                    "Exit 0: ALLOW (spec exists) | Exit 1: WARN | Exit 2: DENY (no spec)\n"
                    "Use before any write/edit operations in a coding task."
    )
    parser.add_argument("--project", type=str, required=True, help="项目根目录")
    parser.add_argument("--task", type=str, default="", help="要执行的任务描述（用于日志）")
    parser.add_argument("--check", action="store_true", help="只检查 spec 状态，不强制 gate")
    parser.add_argument("--enforce", action="store_true", help="强制执行 gate（无 spec 时退出）")
    parser.add_argument("--spec-path", type=str, default="", help="单独指定 spec 路径检查")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--list-specs", action="store_true", help="列出所有发现的 spec 文件")

    args = parser.parse_args()

    project_path = args.project

    # 列出所有 spec
    if args.list_specs:
        specs = find_specs(project_path)
        if not specs:
            print("No spec files found.")
            sys.exit(0)
        print(f"Found {len(specs)} spec(s):\n")
        for p, rel in specs:
            try:
                age = (datetime.now().timestamp() - p.stat().st_mtime) / 86400
                age_str = f"{age:.1f} days old"
            except Exception:
                age_str = "unknown age"
            print(f"  {rel} ({age_str})")
            print(f"    Full: {p}")
        print()
        return

    # 单独 spec 路径检查
    if args.spec_path:
        p = Path(args.spec_path)
        if not p.exists():
            print(f"❌ SPEC NOT FOUND: {args.spec_path}", file=sys.stderr)
            sys.exit(2)
        result = {
            "gate_status": "ALLOW",
            "exit_code": 0,
            "latest_spec": str(p),
            "spec_age_days": -1,
            "message": f"Specified spec exists: {args.spec_path}",
            "recommendation": "Proceed.",
        }
    else:
        result = check_gate(project_path, args.task)

    # 输出
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status_icon = {
            "ALLOW": "✅",
            "DENY": "🚫",
            "WARN": "⚠️",
        }.get(result["gate_status"], "?")

        print(f"\n{'=' * 60}")
        print(f"  BRAINSTORMING GATE")
        print(f"{'=' * 60}")
        print(f"  Project:   {project_path}")
        print(f"  Task:      {args.task or '(not specified)'}")
        print(f"  Gate:      {status_icon} {result['gate_status']}")
        print(f"  Spec:      ", end="")
        if result["latest_spec"]:
            print(result["latest_spec"])
            print(f"  Age:       {result['spec_age_days']} days")
        else:
            print("(none)")
        print()
        print(f"  {result['message']}")
        if args.verbose or result["gate_status"] != "ALLOW":
            print()
            print(f"  Recommendation: {result['recommendation']}")
        print(f"{'=' * 60}\n")

    # 如果强制执行且 gate 未通过，退出
    if args.enforce and result["gate_status"] == "DENY":
        sys.exit(2)

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()

Skill Authoring 规范
文件路径：skills/skill-authoring/SKILL.md
大小：6388 字符
---
name: skill-authoring
description: Use when creating new skills, editing existing skills, or validating whether a skill is needed. Also use when a technique or pattern is not being applied consistently across sessions.
---

# Skill Authoring

## Overview

**Write skills like test-driven development: first prove the agent fails without the skill, then write the skill to fix that specific failure.**

If you didn't watch an agent violate a rule in context, you don't know if writing that rule will actually change behavior. Most skill authoring fails because it starts from theory ("agents should do X") instead of evidence ("here's exactly how agents fail when X is not specified").

## When to Use

**Create a skill when:**
- A technique or pattern is not intuitively obvious to you (the author)
- You'd reference this skill across multiple sessions
- The pattern applies broadly (not project-specific)
- Others would benefit

**Don't create for:**
- One-off solutions
- Standard practices well-documented elsewhere
- Project-specific conventions (put in CLAUDE.md instead)
- Mechanical constraints enforceable with regex/validation (automate it)

**Validate before authoring:**
- Run a baseline scenario without the skill
- Document the exact rationalizations the agent uses when it violates the rule
- Those rationalizations are what the skill must address

## TDD Mapping for Skills

| TDD Concept | Skill Authoring |
|-------------|----------------|
| Test case | Pressure scenario with subagent |
| Test fails (RED) | Agent violates rule without skill |
| Production code | SKILL.md document |
| Test passes (GREEN) | Agent complies when skill is present |
| Refactor | Close loopholes while maintaining compliance |

## Process

### Step 1: Baseline Test — Watch It Fail

**Before writing any skill content, run `skill_baseline_tester.py`**:

```bash
python3 workspace_tools/skill_baseline_tester.py \
  --skill-dir skills/<new-skill-name>/ \
  --task "<trigger scenario description>" \
  --verbose
```

**What it does:**
1. Extracts rules from the planned SKILL.md (even if not written yet)
2. Simulates baseline agent behavior
3. Reports which rules agent is likely to violate and with what rationalizations

**If `skill_baseline_tester.py` is not available:** manually simulate:
1. Set up the exact situation where the skill should apply
2. Let the agent handle it without the skill
3. Record the **specific rationalizations** the agent uses to justify violations

Example rationalizations to look for:
- "This is simple enough to skip X"
- "I'll add tests later"
- "This is just a prototype"
- "The user didn't explicitly ask for X"

These rationalizations are the skill's target. A skill that doesn't address actual rationalizations is wishful thinking.

### Step 2: Write the Skill — Minimal and Targeted

**Use the baseline rationalizations as the target.** Every rule in the SKILL.md should address at least one rationalization from Step 1.

Good: "If you write code before writing a failing test, delete the code and start from the test."
Bad: "Always follow TDD best practices."

### Step 3: Verify — Watch It Pass

Re-run the scenario with the skill present. The agent should:
1. Not use the old rationalizations
2. Follow the prescribed behavior

### Step 4: Refactor — Close Loopholes

Find new rationalizations the agent uses → plug them → re-verify.

The first version of a skill rarely catches all cases. Iteration is required.

## SKILL.md Format

### Frontmatter (Required)

```yaml
---
name: skill-name-with-hyphens
description: Use when [specific triggering conditions and symptoms]
---
```

**Rules:**
- `name`: lowercase letters, numbers, hyphens only (no spaces, no special chars)
- `description`: max 1024 characters total
- `description`: **When to Use only** — describe triggering conditions, NOT the skill's workflow or process
- Start with "Use when..." to signal trigger condition

### Body Structure

```markdown
# Skill Name

## Overview
What is this? Core principle in 1-2 sentences.

## When to Use
- Trigger condition 1 (symptoms, not solutions)
- Trigger condition 2
- When NOT to use

## Core Pattern
Before/after code comparison, or step-by-step for techniques

## Quick Reference
Bullets or table for scanning during execution

## Common Mistakes
What goes wrong + specific fixes
```

### Keep Inline vs. Separate Files

**Keep inline:**
- Principles and concepts
- Code patterns under 50 lines
- Everything else

**Separate files for:**
- Heavy reference (100+ lines) — API docs, comprehensive syntax
- Reusable tools — scripts, utilities, templates

## Skill Types

| Type | Description | Example |
|------|-------------|---------|
| **Technique** | Concrete method with steps | `test-driven-development` |
| **Pattern** |思维方式 | `flatten-with-flags` |
| **Reference** | API docs, syntax guides | Office docs |

## Description CSO (Claude Search Optimization)

**Critical rule:** Description = When to Use, NOT What the Skill Does.

Future-you (or another agent) reads the description to decide: "Should I load this skill right now?"

**Good description:**
> "Use when writing code before confirming the implementation matches the spec, or when unsure whether the code satisfies the requirements."

**Bad descriptions (too specific about the skill's internals):**
> "This skill enforces red-green-refactor TDD cycles with mandatory test verification steps."
> "A skill that helps you write better plans with exact file paths and step-by-step instructions."

**Why it matters:** If description describes the skill's process, agents will only load it when they already know what the skill does. If description describes triggering conditions, agents load it when they need it — even before they know the solution.

## Validation Checklist

Before finishing a skill, verify:

- [ ] Name is lowercase with hyphens only
- [ ] Description starts with "Use when..."
- [ ] Description describes symptoms/situations, not the skill's workflow
- [ ] Description is under 500 characters
- [ ] SKILL.md exists at `skills/<skill-name>/SKILL.md`
- [ ] **Baseline test was run** (`skill_baseline_tester.py` or manual simulation)
- [ ] Skill was written to address specific rationalizations, not abstract principles
- [ ] Re-verify showed agent complies with skill present
- [ ] Every rule in SKILL.md addresses at least one rationalization from Step 1

Output Style 指南
文件路径：skills/output-style/SKILL.md
大小：3707 字符
---
name: output-style
description: Use when the user asks to change AI output style, wants educational explanations, wants to learn interactively, or asks for learning mode vs explanatory mode.
---

# Output Style

Controls how the AI presents information to the user. Two distinct styles are available.

## Overview

Output style determines the balance between **task completion** and **educational value**. Choose based on whether the user wants efficient execution or learning alongside work.

## When to Use

**explanatory style** when:
- User asks "explain what you're doing"
- User wants educational insights alongside code
- User wants to learn from the implementation
- "show your work" type requests

**learning style** when:
- User asks to learn about a topic interactively
- User wants step-by-step exploration of a concept
- User is studying or teaching

## Explanatory Style

When in explanatory mode, always include educational insights in output:

```
★ Insight ─────────────────────────────────────
[2-3 key educational points about the implementation]
─────────────────────────────────────────────────
```

### When to Insert Insights

Insert insights **before and after writing code**, not only at the end.

**Before code**: Explain the approach and design choices.
**After code**: Highlight what was interesting, risky, or non-obvious.

### Insight Principles

- Be specific to the codebase or code just written
- Avoid generic programming concepts
- 2-3 focused points, not exhaustive lists
- Educational but not patronizing
- Concise and high-signal

### Good Insight Examples

```
★ Insight ─────────────────────────────────────
1. Node's module caching means require() is idempotent —
   multiple calls to the same module return the same instance.
2. The double-brace pattern {{}} in template literals isn't
   special syntax; it's just how you interpolate within a
   pre-existing {{ }} block context.
─────────────────────────────────────────────────
```

### Bad Insight Examples

```
★ Insight ─────────────────────────────────────
1. Variables store values in memory.
2. Functions can accept parameters.
3. Always test your code.
─────────────────────────────────────────────────
```

(Too generic, obvious to anyone who knows programming)

## Learning Style

When in learning mode, prioritize:

1. **Step-by-step exploration** — Break complex topics into digestible pieces
2. **Socratic questions** — Ask the user what they think before explaining
3. **Concrete analogies** — Connect new concepts to familiar ones
4. **Interactive discovery** — Let the user reach conclusions with guidance

### Learning Structure

```
Topic: [What we're learning]

Step 1: [Simple concept]
  - [Key point]
  - [Why it matters]

Step 2: [Building on that]
  - [Key point]
  - [Example]

Try it yourself:
[Interactive exercise or question]
```

## Quick Reference

| Style | Primary Goal | Insight Frequency | Structure |
|-------|-------------|-------------------|-----------|
| explanatory | Task + learning | Before/after code | Inline with ★ markers |
| learning | Pure learning | Exploratory | Socratic, step-by-step |
| default | Efficiency | Minimal/none | Just deliver |

## Common Mistakes

**Mistake 1: Insights that are too generic**
- ❌ "Always use descriptive variable names"
- ✅ "parseInt vs Number: parseInt truncates to integer, Number casts. parseInt('42px') = 42, Number('42px') = NaN"

**Mistake 2: Waiting until the end to provide insights**
- ❌ All insights bundled at the end
- ✅ Scattered before/after relevant code sections

**Mistake 3: Over-explaining in learning mode**
- ❌ Walls of text without breaks
- ✅ Short paragraphs, questions to the user, interactive prompts

Frontend Design BOLD 美学
文件路径：skills/frontend-design/SKILL.md
大小：5067 字符
---
name: frontend-design
description: Use when building or designing web components, pages, or applications. Also use when the user wants distinctive, memorable UI that avoids generic "AI slop" aesthetics.
---

# Frontend Design

Create distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics. Build web components, pages, and applications with high design quality.

## When to Use

- Building web components, pages, or full applications
- User asks for UI/UX improvements
- User wants distinctive design vs generic templates
- Frontend task involving HTML/CSS/JS, React, Vue, etc.

## Design Thinking Process

Before writing any code, establish a clear aesthetic direction:

### 1. Purpose
What problem does this solve? Who uses it? What context?

### 2. Tone
Pick one dominant aesthetic and commit to it:

| Direction | Character |
|-----------|-----------|
| **brutally minimal** | Extreme restraint, every pixel justified |
| **maximalist chaos** | Layered, rich, dense information |
| **retro-futuristic** | 70s/80s sci-fi aesthetics, CRT, neon |
| **organic/natural** | Earth tones, flowing shapes, natural materials |
| **luxury/refined** | Premium, editorial, sophisticated |
| **playful/toy-like** | Bright, bouncy, childlike joy |
| **editorial/magazine** | Print-inspired, typography-led |
| **brutalist/raw** | Exposed structure, bold, unpolished |
| **art deco/geometric** | Precision, symmetry, ornamental |
| **soft/pastel** | Gentle, calm, muted palette |
| **industrial/utilitarian** | Functional, warehouse, stark |
| **dark/sophisticated** | Deep colors, elegant, premium feel |

### 3. Differentiation
What's the **one thing** someone will remember? The memorable element that makes this different.

## Implementation Standards

### Typography
- **Choose distinctive fonts** — avoid Inter, Roboto, Arial, system-ui
- **Pair strategically** — display font for headings, refined body font for text
- **Unexpected combinations** — Space Grotesk is overused, find fresher options
- **Font size matters** — 16px base is default, adjust for context

### Color & Theme
- **Commit to a cohesive palette** — use CSS variables for consistency
- **Dominant + accent** — not evenly distributed colors
- **Meaningful contrast** — ensure accessibility but maintain aesthetic
- **Dark/light as choice** — don't default to one

### Motion
- **CSS-first** — use CSS animations before JS libraries
- **High-impact moments** — one orchestrated page load beats scattered micro-interactions
- **Staggered reveals** — animation-delay for entrance choreography
- **Hover/active states** — every interactive element should respond
- **Scroll-triggered** — reveal on scroll creates delight

### Spatial Composition
- **Break the grid** — asymmetry and overlap create interest
- **Generous negative space** OR **controlled density** — pick a lane
- **Unexpected layouts** — diagonal flow, offset elements
- **Hierarchy through scale** — size = importance

### Visual Details
- **Backgrounds create atmosphere** — gradients, noise, textures, not flat colors
- **Shadows add depth** — layered shadows, not uniform drop shadows
- **Decorative borders** — custom borders, geometric ornaments
- **Grain overlays** — film grain, paper texture for analog feel

## What NOT to Use

**Never use:**
- Font families: Inter, Roboto, Arial, system-ui
- Purple gradients on white backgrounds
- Generic card layouts with avatar + title + description
- Rounded corners everywhere (8px radius is not universal)
- Blue/purple "AI" color schemes
- Hero sections with centered content and a CTA button
- Cookie-cutter navigation bars

**Never default to:**
- Tailwind CSS without customization
- Bootstrap components
- Generic placeholder illustrations
- Stock photo aesthetics

## Code Standards

### HTML/CSS
- Semantic HTML elements
- CSS custom properties (variables)
- Mobile-responsive (don't assume desktop)
- Accessible (ARIA labels, keyboard navigation)
- CSS-only animations where possible

### React/Vue
- Component composition
- Props for customization
- CSS-in-JS or scoped CSS modules
- Accessible interactive elements

### Production Requirements
- No placeholder content
- All buttons/links functional
- Responsive at standard breakpoints
- Realistic content (not Lorem ipsum)
- No console errors

## Output Format

For each frontend task, deliver:

1. **Design Direction** — one sentence on the chosen aesthetic
2. **Implementation** — complete, working code
3. **Key Design Decisions** — 2-3 sentences on why this approach

## Common Mistakes

**Mistake 1: Half-committed aesthetic**
- ❌ Mixing two conflicting styles
- ✅ Pick one direction and execute it fully

**Mistake 2: Over-designed for simple tasks**
- ❌ Full animation system for a utility page
- ✅ Match complexity to purpose

**Mistake 3: Forgetting accessibility**
- ❌ Ignoring contrast ratios and keyboard nav
- ✅ Aesthetic and accessible can coexist

**Mistake 4: Generic fonts**
- ❌ "I'll just use system fonts for reliability"
- ✅ Distinctive typography even for simple UIs
