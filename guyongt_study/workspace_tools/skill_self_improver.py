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