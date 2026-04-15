"""
self_review.py — 顾庸的自我复盘系统
在 evolver.py 的经验积累之上，增加"任务后复盘"环节

核心思路（来自 self-improving skill + 顾庸x）：
不是等失败才学，而是每次重要任务后主动检查：
- 有没有漏用的工具？
- 有没有重复犯的错？
- 这次学到了什么新教训？
"""

import json
import time
from pathlib import Path

BASE = Path(__file__).parent

CORRECTIONS = BASE / ".self_review_corrections.json"
LESSONS     = BASE / ".self_review_lessons.json"
REVIEWS     = BASE / ".self_review_reviews.jsonl"

# ─── 工具清单（启发式检测用）──────────────────────────────

WORKSPACE_TOOLS = [
    "exec", "read", "write", "edit",
    "web_fetch", "web_search", "browser",
    "message", "sessions_send", "tts",
    "pdf", "docx", "xlsx", "pptx",
    "memory_search", "memory_get",
    "skillhub_install", "clawhub",
    "git", "file_search", "glob",
]

# ─── 数据层 ───────────────────────────────────────────────

def load_corrections():
    if CORRECTIONS.exists():
        with open(CORRECTIONS, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_corrections(data):
    with open(CORRECTIONS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_lessons():
    if LESSONS.exists():
        with open(LESSONS, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_lessons(data):
    with open(LESSONS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_reviews():
    reviews = []
    if REVIEWS.exists():
        with open(REVIEWS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    reviews.append(json.loads(line))
    return reviews

def append_review(review):
    """写入 review 到 JSONL 文件（evolver auto-trigger 在 run_review 中处理）"""
    try:
        with open(REVIEWS, "a", encoding="utf-8") as f:
            f.write(json.dumps(review, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ─── 核心功能 ─────────────────────────────────────────────

def detect_tool_leaks(task: str, used_tools: list, current_task: str) -> list:
    """
    启发式漏用检测：
    - 任务中可能需要的工具 vs 实际用到的工具
    - 排除当前任务本身（避免"搜东西"触发搜索建议）
    """
    leaks = []
    task_lower = task.lower()

    # 任务类型 → 可能需要的工具
    needs_map = {
        "search": ["web_search", "web_fetch", "exec"],
        "搜": ["web_search", "web_fetch", "exec"],
        "install": ["exec", "clawhub", "skillhub_install"],
        "装": ["exec", "clawhub", "skillhub_install"],
        "写文件": ["write", "edit"],
        "write": ["write", "edit"],
        "读文件": ["read", "file_search"],
        "read": ["read", "file_search"],
        "git": ["git", "exec"],
        "commit": ["git", "exec"],
        "pdf": ["pdf"],
        "docx": ["docx"],
        "xlsx": ["xlsx"],
        "pptx": ["pptx"],
        "邮件": ["message", "email", "exec"],
        "email": ["message", "email", "exec"],
        "搜索": ["web_search", "web_fetch"],
        "网页": ["web_fetch", "browser"],
        "浏览器": ["browser"],
        "复制": ["exec"],
    }

    for keyword, expected in needs_map.items():
        if keyword in task_lower:
            for tool in expected:
                if tool not in used_tools and tool in WORKSPACE_TOOLS:
                    # 排除当前任务本身
                    if tool.lower() not in current_task.lower():
                        leaks.append(tool)

    return list(set(leaks))  # 去重


def detect_repeat_patterns(lessons: list, task: str, method: str) -> dict:
    """
    追踪重复模式：同类错误3次+ → [PATTERN×N]
    """
    task_lower = task.lower()

    # 找同类任务
    same_tasks = [l for l in lessons if l.get("task", "").lower() == task_lower]

    if len(same_tasks) >= 3:
        errors = [l for l in same_tasks if not l.get("success", True)]
        if len(errors) >= 3:
            return {
                "tag": f"[PATTERN×{len(same_tasks)}]",
                "message": f"同类任务 '{task}' 已失败 {len(errors)} 次，建议主动排查根本原因",
            }

    return None


def generate_lessons(task: str, method: str, success: bool,
                     tool_leaks: list, error: str = None) -> str:
    """
    自动从漏用/错误生成可执行教训
    """
    lines = []

    if tool_leaks:
        lines.append(f"任务中可能用到但未使用的工具: {', '.join(tool_leaks)}")

    if error:
        # 提取错误关键词
        if "timeout" in error.lower():
            lines.append("超时错误 → 考虑加长 timeout 或分段执行")
        if "rate limit" in error.lower():
            lines.append("限速错误 → 换国内镜像或加延迟")
        if "not found" in error.lower():
            lines.append("找不到 → 先检查路径或文件名")
        if "permission" in error.lower():
            lines.append("权限错误 → 检查 exec 权限或文件权限")
        if "network" in error.lower() or "connection" in error.lower():
            lines.append("网络错误 → 考虑代理或国内替代方案")

    if not lines:
        if success:
            lines.append(f"'{method}' 方法对 '{task}' 有效，记录备用")
        else:
            lines.append(f"'{method}' 方法对 '{task}' 无效，需要找替代方案")

    return " | ".join(lines) if lines else None


def run_review(task: str, method: str, success: bool,
               used_tools: list, error: str = None, notes: str = None) -> dict:
    """
    主入口：运行一次复盘
    """
    lessons = load_lessons()
    corrections = load_corrections()

    # 1. 漏用检测
    tool_leaks = detect_tool_leaks(task, used_tools, task)

    # 2. 重复模式检测
    pattern = detect_repeat_patterns(lessons, task, method)

    # 3. 生成教训
    lesson_text = generate_lessons(task, method, success, tool_leaks, error)

    # 4. 记录到 corrections
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
        "task": task,
        "method": method,
        "success": success,
        "error": error,
        "used_tools": used_tools,
        "tool_leaks": tool_leaks,
        "pattern": pattern.get("tag") if pattern else None,
        "lesson": lesson_text,
        "notes": notes,
    }

    corrections.append(entry)
    save_corrections(corrections[-50:])  # 保留最近50条

    # 5. 教训入库
    if lesson_text:
        lesson_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            "task": task,
            "lesson": lesson_text,
            "source": "auto_review",
        }
        # 避免重复
        existing = [l["lesson"] for l in lessons]
        if lesson_text not in existing:
            lessons.append(lesson_entry)
            save_lessons(lessons)

    # 6. 写入 reviews.jsonl
    review = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
        "task": task,
        "method": method,
        "success": success,
        "tool_leaks": tool_leaks,
        "pattern_tag": pattern.get("tag") if pattern else None,
    }
    append_review(review)

    return {
        "success": success,
        "tool_leaks": tool_leaks,
        "pattern": pattern,
        "lesson": lesson_text,
        "corrections_count": len(corrections),
        "lessons_count": len(lessons),
    }



# v2.2: ToolObserver integration
def observe_tool(tool, action, target, outcome='success', error='', task_context=''):
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from evolver import observe as do_observe
        do_observe(tool, action, target, outcome, error, task_context=task_context)
    except:
        pass

def print_report(result: dict, task: str, method: str, error: str = None):
    """格式化输出复盘报告（Windows GBK兼容）"""
    ok = "[OK]" if result["success"] else "[FAIL]"
    warn = "[WARN]" if result["tool_leaks"] else ""
    pat = "[PATTERN]" if result["pattern"] else ""

    lines = [
        "",
        "=" * 50,
        f"[REVIEW] {task}",
        f"Method: {method}",
        f"Result: {ok}",
    ]
    if error:
        lines.append(f"Error: {error}")
    lines.append("-" * 50)

    if result["tool_leaks"]:
        lines.append(f"[!] Tool leaks: {', '.join(result['tool_leaks'])}")

    if result["pattern"]:
        p = result["pattern"]
        lines.append(f"[~] {p['tag']} — {p['message']}")

    if result["lesson"]:
        lines.append(f"[+] Lesson: {result['lesson']}")

    lines.extend([
        "",
        f"Stats: corrections={result['corrections_count']}, lessons={result['lessons_count']}",
        "=" * 50,
    ])

    for line in lines:
        print(line)


# ─── CLI ─────────────────────────────────────────────────

def main():
    import sys

    if len(sys.argv) < 3:
        print("用法: self_review.py <task> <method> <success:yes|no> [used_tools] [error]")
        print("示例: self_review.py '搜索GitHub' 'GitHub API' yes 'web_fetch,exec'")
        return

    task   = sys.argv[1]
    method = sys.argv[2]
    success = "yes" in sys.argv[3].lower()

    used_tools = []
    if len(sys.argv) > 4:
        used_tools = [t.strip() for t in sys.argv[4].split(",")]

    error = sys.argv[5] if len(sys.argv) > 5 else None

    result = run_review(task, method, success, used_tools, error)
    print_report(result, task, method, error)


if __name__ == "__main__":
    main()
