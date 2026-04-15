# -*- coding: utf-8 -*-
"""
qclaw_insights.py — qclaw 用量洞察报告生成器

参考：Hermes agent/insights.py（33KB）
来源：evolver_db.json + evolver_observations.jsonl

功能：
- 从 evolver_db 生成规则使用统计
- 从 observations 生成工具调用模式
- 输出终端友好的可视化报告
"""

import json
import pathlib
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

WORKSPACE = pathlib.Path(__file__).parent
DB_PATH = WORKSPACE / ".evolver_db.json"
OBS_PATH = WORKSPACE / ".evolver_observations.jsonl"
INSTINCTS_DIR = WORKSPACE / ".evolver_instincts"

# ─── 数据模型 ──────────────────────────────────────────────

@dataclass
class InsightStats:
    total_rules: int
    active_rules: int
    total_records: int
    avg_confidence: float
    top_methods: list[dict]
    method_breakdown: dict[str, dict]
    recent_activity: list[dict]
    instinct_count: int
    observation_count: int


# ─── 读取数据 ──────────────────────────────────────────────

def load_evolver_db() -> dict:
    if not DB_PATH.exists():
        return {"rules": []}
    return json.loads(DB_PATH.read_text(encoding="utf-8", errors="ignore"))


def load_observations() -> list[dict]:
    if not OBS_PATH.exists():
        return []
    records = []
    for line in OBS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def load_instincts() -> list[pathlib.Path]:
    if not INSTINCTS_DIR.exists():
        return []
    return list(INSTINCTS_DIR.glob("*.yaml")) + list(INSTINCTS_DIR.glob("*.yml"))


# ─── 分析引擎 ──────────────────────────────────────────────

def compute_confidence(rule: dict) -> float:
    """Hermes 置信度公式：success_rate × (0.7 + 0.2×样本权重 + 0.1×优先级)"""
    success = rule.get("success_count", 0)
    total = rule.get("total_count", 0)
    priority = rule.get("priority", 0)
    if total == 0:
        return 0.0
    rate = success / total
    sample_weight = min(1.0, total / 10.0)  # 每10条样本 = 100% 样本权重
    return rate * (0.7 + 0.2 * sample_weight + 0.1 * priority)


def build_insights() -> InsightStats:
    db = load_evolver_db()
    rules = db.get("rules", [])
    observations = load_observations()
    instincts = load_instincts()

    # Method breakdown
    methods: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "success": 0, "failures": 0, "confidence": 0.0, "rules": []
    })
    for r in rules:
        m = r.get("method", "unknown")
        methods[m]["total"] += r.get("total_count", 0)
        methods[m]["success"] += r.get("success_count", 0)
        methods[m]["failures"] += r.get("total_count", 0) - r.get("success_count", 0)
        methods[m]["confidence"] = max(methods[m]["confidence"], compute_confidence(r))
        methods[m]["rules"].append(r.get("id", ""))

    # Top methods by confidence
    top_methods = sorted(
        [{"method": m, **v} for m, v in methods.items()],
        key=lambda x: (x["confidence"], x["total"]),
        reverse=True,
    )[:10]

    # Recent activity (last 7 days)
    now = datetime.now()
    recent = []
    for r in rules:
        ls = r.get("last_success", "")
        if ls:
            try:
                dt = datetime.strptime(ls, "%Y-%m-%d %H:%M")
                if (now - dt) < timedelta(days=7):
                    recent.append({
                        "task": r.get("task", ""),
                        "method": r.get("method", ""),
                        "confidence": round(compute_confidence(r), 3),
                        "success_rate": round(r.get("success_count", 0) / max(1, r.get("total_count", 1)), 2),
                        "last_success": ls,
                    })
            except ValueError:
                pass

    avg_conf = sum(compute_confidence(r) for r in rules) / max(1, len(rules))

    return InsightStats(
        total_rules=len(rules),
        active_rules=sum(1 for r in rules if r.get("is_active", True)),
        total_records=sum(r.get("total_count", 0) for r in rules),
        avg_confidence=round(avg_conf, 3),
        top_methods=top_methods,
        method_breakdown=dict(methods),
        recent_activity=recent,
        instinct_count=len(instincts),
        observation_count=len(observations),
    )


# ─── 终端格式化 ─────────────────────────────────────────────

def format_confidence_bar(conf: float, width: int = 10) -> str:
    """置信度可视化条"""
    filled = int(conf * width)
    empty = width - filled
    return "[" + "=" * filled + "-" * empty + "]" + f" {conf:.1%}"


def format_confidence_color(conf: float) -> str:
    if conf >= 0.8:
        return f"\033[92m"  # 绿
    elif conf >= 0.5:
        return f"\033[93m"  # 黄
    else:
        return f"\033[91m"  # 红


def ANSI_RESET():
    return "\033[0m"


def print_insights_report(stats: InsightStats):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print()
    print(f"╔{'═' * 58}╗")
    print(f"║  🧠 qclaw Insights Report  ({now}){' ' * (12 - len(now))}║")
    print(f"╠{'═' * 58}╣")

    # 概览
    print(f"║  📊 Overview{' ' * 44}║")
    print(f"║    Rules:       {stats.total_rules:>6}  (active: {stats.active_rules}){' ' * 22}║")
    print(f"║    Records:     {stats.total_records:>6}  total executions{' ' * 26}║")
    print(f"║    Avg Conf:     {format_confidence_bar(stats.avg_confidence, 8)}{' ' * 19}║")
    print(f"║    Instincts:   {stats.instinct_count:>6}  YAML atomic behaviors{' ' * 24}║")
    print(f"║    Observations: {stats.observation_count:>5}  tool call logs{' ' * 26}║")
    print(f"╠{'═' * 58}╣")

    # Top methods
    print(f"║  🏆 Top Methods by Confidence{' ' * 32}║")
    if stats.top_methods:
        print(f"║  {'Method':<20} {'Conf':<8} {'Success':<10} {'Total':<8} {'Rate':<8}║")
        print(f"║  {'-'*20} {'-'*8} {'-'*10} {'-'*8} {'-'*8}║")
        for m in stats.top_methods[:8]:
            conf = m["confidence"]
            rate = m["success"] / max(1, m["total"])
            color = format_confidence_color(conf)
            reset = ANSI_RESET()
            name = m["method"][:20]
            print(f"║  {color}{name:<20}{reset} {format_confidence_bar(conf,5):<12} {m['success']:>5}/{m['total']:<4} {rate:>7.0%}  ║")
    else:
        print(f"║  (no data yet){' ' * 44}║")
    print(f"╠{'═' * 58}╣")

    # Recent activity
    print(f"║  📅 Recent Activity (7 days){' ' * 33}║")
    if stats.recent_activity:
        for a in stats.recent_activity[:5]:
            task = a["task"][:20] or "(unnamed)"
            conf_str = format_confidence_color(a["confidence"]) + f"{a['confidence']:.0%}" + ANSI_RESET()
            print(f"║    [{conf_str}] {task:<22} {a['method']:<12} {a['last_success']:<8}║")
    else:
        print(f"║  (no recent activity){' ' * 39}║")
    print(f"╠{'═' * 58}╣")

    # Method breakdown table
    if stats.method_breakdown:
        print(f"║  📋 Method Breakdown{' ' * 41}║")
        for m, v in sorted(stats.method_breakdown.items(), key=lambda x: -x[1]["total"])[:5]:
            rate = v["success"] / max(1, v["total"])
            conf = format_confidence_color(v["confidence"])
            reset = ANSI_RESET()
            print(f"║    {conf}{m:<22}{reset} {v['total']:>4} exec  {rate:>5.0%} success  conf {v['confidence']:.0%}║")
    print(f"╚{'═' * 58}╝")
    print()


# ─── 快速单行摘要（供 heartbeat 使用）───

def get_quick_summary() -> str:
    try:
        stats = build_insights()
        if stats.total_rules == 0:
            return "No evolver data yet"
        top = stats.top_methods[0] if stats.top_methods else None
        if top:
            return f"Rules={stats.total_rules} exec={stats.total_records} top={top['method']}({top['confidence']:.0%})"
        return f"Rules={stats.total_rules} exec={stats.total_records} conf={stats.avg_confidence:.0%}"
    except Exception as e:
        return f"insights error: {e}"


# ─── 主入口 ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="qclaw Insights Report")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quick", action="store_true", help="One-line summary")
    args = parser.parse_args()

    if args.quick:
        print(get_quick_summary())
        return

    stats = build_insights()
    if args.json:
        print(json.dumps(asdict(stats), ensure_ascii=False, indent=2))
    else:
        print_insights_report(stats)


if __name__ == "__main__":
    main()
