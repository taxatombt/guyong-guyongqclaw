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