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