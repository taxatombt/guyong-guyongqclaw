# -*- coding: utf-8 -*-
"""
qclaw_eval.py — qclaw 版评估驱动开发（EDD）框架

参考：ECC eval-harness（MIT License）
来源：evolver.py EvalTracker + ECC eval-harness 概念
适配：qclaw evolver.py v2.3

概念：
- EDD = Eval-Driven Development：在动手前先定义"成功标准"
- pass@k = k次尝试中至少一次成功
- pass^k = 连续k次全部成功

使用流程：
1. 定义评估（yaml/json）
2. 执行评估
3. 追踪 pass@k 指标
4. 报告趋势
"""
import json
import time
import subprocess
import re
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Literal

WORKSPACE = Path(__file__).parent
EVALS_DIR = WORKSPACE / ".evals"
BASELINE_FILE = EVALS_DIR / "baseline.json"
HISTORY_DIR = EVALS_DIR / "history"


@dataclass
class Eval:
    """一次评估定义"""
    name: str
    description: str
    type: str  # "capability" | "regression"
    grader: str  # "code" | "model" | "human"
    command: str = ""  # 代码级评估命令
    prompt: str = ""  # 模型级评估提示
    criteria: list = None  # 成功标准列表
    expected: str = ""  # 期望输出
    tags: list = None

    def __post_init__(self):
        if self.criteria is None:
            self.criteria = []
        if self.tags is None:
            self.tags = []


def _load_evals() -> list[dict]:
    """从 .evals/ 目录加载所有评估定义"""
    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    evals = []
    for f in EVALS_DIR.glob("*.json"):
        try:
            evals.extend(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    for f in EVALS_DIR.glob("*.yaml"):
        try:
            import yaml
            evals.extend(yaml.safe_load(f.read_text(encoding="utf-8")) or [])
        except ImportError:
            # 无 yaml 库，降级
            pass
    return evals


def _save_eval_history(name: str, run: dict):
    """保存评估历史"""
    hist_file = HISTORY_DIR / f"{name}.jsonl"
    with open(hist_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")


def _load_history(name: str, limit: int = 50) -> list[dict]:
    """加载评估历史"""
    hist_file = HISTORY_DIR / f"{name}.jsonl"
    if not hist_file.exists():
        return []
    runs = []
    with open(hist_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                runs.append(json.loads(line.strip()))
            except Exception:
                pass
    return runs[-limit:]


# ═══════════════════════════════════════════════════════
# 评估执行器
# ═══════════════════════════════════════════════════════

def run_code_grader(command: str) -> tuple[bool, str]:
    """执行代码级评估（bash 命令）"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # exit code 0 = 成功
        passed = result.returncode == 0
        output = result.stdout.strip()[:200]
        return passed, output or result.stderr.strip()[:200]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (>60s)"
    except Exception as e:
        return False, str(e)[:100]


def run_grader(eval_def: dict) -> tuple[bool, str, float]:
    """
    执行评估。
    返回：(passed, output, duration_ms)
    """
    start = time.time()
    grader = eval_def.get("grader", "code")
    name = eval_def.get("name", "unknown")

    if grader == "code":
        command = eval_def.get("command", "")
        if not command:
            return False, "No command specified", 0
        passed, output = run_code_grader(command)
        return passed, output, (time.time() - start) * 1000

    elif grader == "model":
        # 模型级评估：使用当前模型评估输出
        # 需要 output 字段或 expected 字段
        expected = eval_def.get("expected", "")
        criteria = eval_def.get("criteria", [])

        # 这里用启发式：检查 expected 是否在 criteria 中
        if criteria and expected:
            # 检查 criteria 中的每个条件
            passed_count = sum(1 for c in criteria if c.lower() in expected.lower())
            passed = passed_count >= len(criteria) * 0.6  # 60% 标准
            return passed, f"{passed_count}/{len(criteria)} criteria met", (time.time() - start) * 1000

        return False, "Model grader requires criteria/expected", 0

    elif grader == "human":
        # 人工评估：标记为需要人工审核
        return False, "HUMAN_REVIEW_REQUIRED", (time.time() - start) * 1000

    return False, f"Unknown grader type: {grader}", 0


# ═══════════════════════════════════════════════════════
# pass@k 计算
# ═══════════════════════════════════════════════════════

def compute_pass_at_k(n_attempts: int, k: int, n_successes: int) -> float:
    """
    计算 pass@k。

    pass@k = 1 - C(n-k, k) / C(n, k)
             = 1 - (n-k)!(n-k)! / n! / (n-2k)!...（简化版）

    蒙特卡洛估计：
    pass@k ≈ 1 - (1 - s/n)^k
    其中 s = 成功次数，n = 总次数
    """
    if n_attempts == 0:
        return 0.0
    if n_successes == 0:
        return 0.0
    if n_attempts < k:
        # 不够数据，保守估计
        return float(n_successes) / n_attempts

    # 近似：s/n 作为单次成功率
    success_rate = n_successes / n_attempts
    return 1.0 - (1.0 - success_rate) ** k


# ═══════════════════════════════════════════════════════
# 主评估流程
# ═══════════════════════════════════════════════════════

def define_eval(name: str, description: str, type: str = "capability",
                grader: str = "code", command: str = "", criteria: list = None,
                expected: str = "", tags: list = None) -> str:
    """
    定义新评估，写入 .evals/<name>.json
    返回：评估文件路径
    """
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    eval_data = {
        "name": name,
        "description": description,
        "type": type,  # "capability" | "regression"
        "grader": grader,  # "code" | "model" | "human"
        "command": command,
        "criteria": criteria or [],
        "expected": expected,
        "tags": tags or [],
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }

    # 如果 command 为空且 grader == code，尝试推断
    if not command and grader == "code":
        if name.startswith("test-"):
            command = f'python -m pytest {name[5:]}.py -v'
        elif "lint" in name:
            command = f'python -m flake8 . --count'
        elif "build" in name:
            command = f'python setup.py build'

    out_file = EVALS_DIR / f"{name}.json"
    out_file.write_text(json.dumps([eval_data], ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_file)


def run_eval(name: str, runs: int = 1) -> dict:
    """
    运行评估。
    返回结果 dict。
    """
    evals = _load_evals()
    eval_def = next((e for e in evals if e.get("name") == name), None)
    if not eval_def:
        return {"error": f"Eval '{name}' not found. Use define_eval() first."}

    results = []
    for i in range(runs):
        passed, output, dur = run_grader(eval_def)
        results.append({
            "run": i + 1,
            "passed": passed,
            "output": output,
            "duration_ms": dur,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        _save_eval_history(name, results[-1])

    successes = sum(1 for r in results if r["passed"])
    n = len(results)
    return {
        "name": name,
        "type": eval_def.get("type", "capability"),
        "grader": eval_def.get("grader", "code"),
        "runs": n,
        "successes": successes,
        "pass_at_1": successes / n if n >= 1 else 0,
        "pass_at_3": compute_pass_at_k(n, 3, successes),
        "pass_at_5": compute_pass_at_k(n, 5, successes),
        "results": results,
    }


def report(name: str) -> str:
    """生成评估报告"""
    evals = _load_evals()
    eval_def = next((e for e in evals if e.get("name") == name), None)
    history = _load_history(name)

    if not eval_def:
        return f"Eval '{name}' not found."

    # 计算历史 pass@k
    if history:
        n = len(history)
        s = sum(1 for h in history if h.get("passed"))
        historical = {
            "total_runs": n,
            "successes": s,
            "pass@1": s / n if n >= 1 else 0,
            "pass@3": compute_pass_at_k(n, 3, s),
            "pass@5": compute_pass_at_k(n, 5, s),
            "pass^3": all(h.get("passed") for h in history[-3:]) if n >= 3 else None,
        }
    else:
        historical = None

    # 当前状态
    recent = history[-5:] if history else []
    recent_summary = f"{sum(1 for r in recent if r.get('passed'))}/{len(recent)}"

    lines = []
    lines.append("=" * 55)
    lines.append(f"  EVAL REPORT: {name}")
    lines.append("=" * 55)
    lines.append(f"  Type:      {eval_def.get('type', '?')}")
    lines.append(f"  Grader:    {eval_def.get('grader', '?')}")
    lines.append(f"  Desc:      {eval_def.get('description', '?')[:50]}")

    if historical:
        lines.append("")
        lines.append("  [Historical Metrics]")
        lines.append(f"  Total runs:    {historical['total_runs']}")
        lines.append(f"  Pass@1:         {historical['pass@1']:.1%}")
        lines.append(f"  Pass@3:         {historical['pass@3']:.1%}")
        lines.append(f"  Pass@5:         {historical['pass@5']:.1%}")
        if historical.get('pass^3') is not None:
            lines.append(f"  Pass^3:         {'YES' if historical['pass^3'] else 'NO'}")
        lines.append(f"  Recent (5):    {recent_summary}")
    else:
        lines.append("")
        lines.append("  [No history yet]")

    lines.append("=" * 55)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# evolver.py 集成：自动记录到 EvalTracker
# ═══════════════════════════════════════════════════════

def record_to_evolver(name: str, success: bool):
    """
    将评估结果记录到 evolver.py EvalTracker。
    用于：evolver 的 pass@k 指标与 eval-harness 打通。
    """
    try:
        from evolver import EvolverEngine
        engine = EvolverEngine()
        engine.eval_tracker.record_attempt(f"eval:{name}", "eval-run", success)
        return True
    except Exception as e:
        return False


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("qclaw_eval.py — 评估驱动开发（EDD）框架")
        print()
        print("用法:")
        print("  python qclaw_eval.py list                    # 列出所有评估")
        print("  python qclaw_eval.py define <name> <command>  # 定义评估")
        print("  python qclaw_eval.py run <name> [runs]        # 运行评估")
        print("  python qclaw_eval.py report <name>            # 查看报告")
        print("  python qclaw_eval.py trends                  # 查看趋势")
        return

    cmd = sys.argv[1]

    if cmd == "list":
        evals = _load_evals()
        if not evals:
            print("(暂无评估定义)")
        else:
            print(f"共 {len(evals)} 个评估:")
            for e in evals:
                print(f"  [{e.get('type', '?')}] {e.get('name')} ({e.get('grader', '?')}) — {e.get('description', '')[:40]}")

    elif cmd == "define":
        name = sys.argv[2] if len(sys.argv) >= 3 else ""
        command = sys.argv[3] if len(sys.argv) >= 4 else ""
        if not name:
            print("[ERROR] define 需要 <name> [command]")
            return
        path = define_eval(name, f"User-defined eval: {name}", command=command)
        print(f"[OK] 已定义 -> {path}")

    elif cmd == "run":
        name = sys.argv[2] if len(sys.argv) >= 3 else ""
        runs = int(sys.argv[3]) if len(sys.argv) >= 4 else 1
        if not name:
            print("[ERROR] run 需要 <name> [runs]")
            return
        result = run_eval(name, runs=runs)
        if "error" in result:
            print(f"[ERROR] {result['error']}")
            return
        print(f"[EVAL] {name}")
        print(f"  Runs: {result['runs']}, Successes: {result['successes']}")
        print(f"  Pass@1: {result['pass_at_1']:.1%}")
        print(f"  Pass@3: {result['pass_at_3']:.1%}")
        print(f"  Pass@5: {result['pass_at_5']:.1%}")
        for r in result["results"]:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{status}] run {r['run']}: {r['output'][:60]}")

        # 同时记录到 evolver
        for r in result["results"]:
            record_to_evolver(name, r["passed"])

    elif cmd == "report":
        name = sys.argv[2] if len(sys.argv) >= 3 else ""
        if not name:
            print("[ERROR] report 需要 <name>")
            return
        print(report(name))

    elif cmd == "trends":
        evals = _load_evals()
        print(f"  评估趋势总览")
        print(f"  {'='*50}")
        for e in evals:
            ename = e.get("name", "")
            history = _load_history(ename, limit=20)
            if not history:
                print(f"  {ename}: (无历史数据)")
                continue
            n = len(history)
            s = sum(1 for h in history if h.get("passed"))
            print(f"  {ename}: {s}/{n} ({s/n:.0%}) | p@3={compute_pass_at_k(n,3,s):.0%} p@5={compute_pass_at_k(n,5,s):.0%}")


if __name__ == "__main__":
    main()
