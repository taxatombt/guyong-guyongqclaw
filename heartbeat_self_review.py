"""
heartbeat_self_review.py — 心跳自检：检查是否需要复盘
每天心跳时检查：如果今天有新工作但还没复盘，输出 REMIND_SELF_REVIEW

逻辑：
1. 检查最近24小时的 reviews.jsonl
2. 如果有超过2条新 review → 今天有工作
3. 检查 memory/heartbeat-state.json 是否已记录今天提醒过
4. 未提醒 + 有工作 → 输出 REMIND_SELF_REVIEW
"""

import json
import time
from pathlib import Path

WORKSPACE = Path(__file__).parent
REVIEWS   = WORKSPACE / ".self_review_reviews.jsonl"
STATE_FILE = WORKSPACE / "memory" / "heartbeat-state.json"

ONE_DAY_SECONDS = 24 * 60 * 60
WORK_THRESHOLD  = 2  # 超过2条新review → 今天有工作


def get_today():
    return time.strftime("%Y-%m-%d")


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"last_reminded": None, "last_check": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)




# v2: Phase detection for strategic compaction
PHASE_TRANSITIONS = {
    ('research','plan'): 'YES - Research context is bulky, plan is the distilled output',
    ('plan','implement'): 'YES - Plan is in TodoWrite, free up context for code',
    ('plan','debug'): 'YES - Clear exploration context before debugging',
    ('debug','implement'): 'YES - Clear dead-end reasoning before next approach',
    ('debug','plan'): 'YES - Debug traces pollute context for unrelated work',
    ('implement','test'): 'MAYBE - Keep if tests reference recent code',
    ('test','implement'): 'NO - Lose variable names, file paths',
    ('implement','debug'): 'NO - Mid-implementation, losing state is costly',
}

TOOL_CALL_THRESHOLD = 50
TOOL_CALL_REMINDER = 25

def detect_phase(task_context):
    task = task_context.lower()
    phases = {'research':0,'search':0,'investigate':0,'plan':0,'design':0,'implement':0,'code':0,'write':0,'test':0,'debug':0,'fix':0,'review':0,'deploy':0}
    for kw,phase in [('research','research'),('search','research'),('investigate','research'),('调研','research'),
                      ('plan','plan'),('design','plan'),('规划','plan'),('策划','plan'),
                      ('implement','implement'),('code','implement'),('write','implement'),('执行','implement'),
                      ('test','test'),('testing','test'),
                      ('debug','debug'),('fix','debug'),('调试','debug')]:
        phases[phase] += task.count(kw)
    return max(phases, key=phases.get)

def count_today_reviews():
    """统计今天的新review数"""
    if not REVIEWS.exists():
        return 0

    today = get_today()
    count = 0

    with open(REVIEWS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                if ts.startswith(today):
                    count += 1
            except json.JSONDecodeError:
                continue

    return count


def check_and_remind() -> str:
    """
    主逻辑：
    - 有工作（>=2条新review）→ 检查是否提醒过
    - 没提醒过 → 输出REMIND_SELF_REVIEW + 更新状态
    - 其他情况 → 无输出
    """
    state = load_state()
    today = get_today()

    # 统计今天新review
    count = count_today_reviews()

    if count < WORK_THRESHOLD:
        # 今天没什么工作，不用提醒
        state["last_check"] = f"{today} 00条"
        save_state(state)
        return ""  # 无输出

    # 有工作，检查是否已提醒
    last_reminded = state.get("last_reminded", "")

    if last_reminded == today:
        # 今天已经提醒过了，跳过
        state["last_check"] = f"{today} {count}条(已提醒)"
        save_state(state)
        return ""  # 无输出

    # 未提醒 → 输出提醒 + 更新状态
    state["last_reminded"] = today
    state["last_check"] = f"{today} {count}条(已提醒)"
    save_state(state)

    return (
        f"REMIND_SELF_REVIEW: "
        f"今天有 {count} 条新工作记录（>= {WORK_THRESHOLD}），"
        f"上次复盘提醒为 {last_reminded or '从未'}。"
        f"建议在 HEARTBEAT.md 第5项轮转时进行复盘回顾。"
    )


def main():
    result = check_and_remind()
    if result:
        print(result)
    else:
        print("OK — 无需提醒")


if __name__ == "__main__":
    main()
