# -*- coding: utf-8 -*-
"""
evolver.py v2.2 — 基于 OpenLIT Rule Engine + Superpowers Rationalization Defense + ECC Hook观察层

v2.1 → v2.2 新增：
- ToolObserver 类：自动记录工具调用到观察日志（参考 ECC continuous-learning-v2）
- Hook观察层：PreToolUse/PostToolUse 模式的启发式实现
- pass@k 指标：eval-driven development 评估（参考 ECC eval-harness）

来源：
- OpenLIT Rule Engine
- Superpowers TDD for Skills（Rationalization Defense）
- CNCF Agent Harness Safety Nets
- ECC continuous-learning-v2（Hook观察层）
- ECC eval-harness（pass@k指标）
"""

import json
import re
import time
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Literal

WORKSPACE = Path(__file__).parent
DB_PATH = WORKSPACE / ".evolver_db.json"
RULES_PATH = WORKSPACE / ".evolver_rules.json"
RATIONALIZATIONS_PATH = WORKSPACE / ".evolver_rationalizations.json"
OBSERVATIONS_PATH = WORKSPACE / ".evolver_observations.jsonl"
INSTINCTS_DIR = WORKSPACE / ".evolver_instincts"
PROJECT_ID_FILE = WORKSPACE / ".evolver_project_id"

# ─── 操作符 ──────────────────────────────────────────────

OPERATORS = {
    "equals": lambda f, v: str(f).lower() == str(v).lower(),
    "not_equals": lambda f, v: str(f).lower() != str(v).lower(),
    "contains": lambda f, v: str(v).lower() in str(f).lower(),
    "not_contains": lambda f, v: str(v).lower() not in str(f).lower(),
    "starts_with": lambda f, v: str(f).lower().startswith(str(v).lower()),
    "ends_with": lambda f, v: str(f).lower().endswith(str(v).lower()),
    "regex": lambda f, v: bool(re.search(str(v), str(f), re.IGNORECASE)),
    "in": lambda f, v: str(f) in v if isinstance(v, list) else str(f) in str(v).split(","),
    "not_in": lambda f, v: str(f) not in v if isinstance(v, list) else str(f) not in str(v).split(","),
    "gt": lambda f, v: float(f) > float(v) if _is_number(f) and _is_number(v) else False,
    "gte": lambda f, v: float(f) >= float(v) if _is_number(f) and _is_number(v) else False,
    "lt": lambda f, v: float(f) < float(v) if _is_number(f) and _is_number(v) else False,
    "lte": lambda f, v: float(f) <= float(v) if _is_number(f) and _is_number(v) else False,
}

def _is_number(v) -> bool:
    try:
        float(v); return True
    except:
        return False


# ═══════════════════════════════════════════════════════
# v2.2 新增：Hook 观察层（ToolObserver）
# 参考 ECC continuous-learning-v2 的 PreToolUse/PostToolUse Hook 模式
# ═══════════════════════════════════════════════════════

@dataclass
class ToolObservation:
    """一次工具调用观察记录（参考 ECC instinct 架构）"""
    timestamp: str
    tool: str                    # 工具名：Read / Write / Edit / Bash / exec / ...
    action: str                  # 操作类型：read / write / edit / exec / search / ...
    target: str                  # 操作目标：文件路径 / URL / 命令
    outcome: str                 # 结果：success / failure
    error: str = ""              # 错误信息（如果有）
    duration_ms: float = 0       # 执行耗时
    task_context: str = ""       # 任务上下文（从输入推断）
    session_id: str = ""         # 会话ID

    def to_instinct_trigger(self) -> str:
        """转化为本能触发条件"""
        triggers = {
            "Bash": f"执行命令: {self.target[:60]}",
            "Read": f"读取文件: {self.target[:60]}",
            "Write": f"写入文件: {self.target[:60]}",
            "Edit": f"编辑文件: {self.target[:60]}",
            "web_search": f"搜索: {self.target[:60]}",
            "web_fetch": f"抓取: {self.target[:60]}",
        }
        return triggers.get(self.tool, f"使用工具: {self.tool}")


class ToolObserver:
    """
    工具观察器 — ECC continuous-learning-v2 Hook 模式的启发式实现
    
    与 ECC 的区别：
    - ECC 使用 PreToolUse/PostToolUse Hook（100%可靠）
    - 我们使用手动记录（调用 record_observation() 即可）
    - 在 OpenClaw Hook 系统成熟后可以迁移到真正的 Hook
    
    观察 → 模式检测 → Instinct 创建 → confidence 评分 → 项目级隔离
    """

    # 危险操作模式（参考 ECC safety-guard）
    DANGEROUS_PATTERNS = [
        "rm -rf", "git push --force", "DROP TABLE", "git reset --hard",
        "git checkout .", "docker system prune", "kubectl delete",
        "chmod 777", "sudo rm", "--no-verify",
    ]

    def __init__(self, observations_path=OBSERVATIONS_PATH):
        self.observations_path = observations_path
        INSTINCTS_DIR.mkdir(exist_ok=True)

    def _get_project_id(self) -> str:
        """获取当前项目ID（参考 ECC 的 git remote URL hash 方案）"""
        if PROJECT_ID_FILE.exists():
            return PROJECT_ID_FILE.read_text(encoding="utf-8").strip()
        # 尝试从 git 获取
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                remote = result.stdout.strip()
                pid = str(abs(hash(remote)))[:12]
                PROJECT_ID_FILE.write_text(pid, encoding="utf-8")
                return pid
        except:
            pass
        # fallback：用 workspace 路径 hash
        pid = str(abs(hash(str(WORKSPACE))))[:12]
        PROJECT_ID_FILE.write_text(pid, encoding="utf-8")
        return pid

    def record_observation(self, tool: str, action: str, target: str,
                           outcome: str = "success", error: str = "",
                           duration_ms: float = 0, task_context: str = "",
                           session_id: str = ""):
        """记录一次工具调用观察"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool,
            "action": action,
            "target": target,
            "outcome": outcome,
            "error": error,
            "duration_ms": duration_ms,
            "task_context": task_context,
            "session_id": session_id,
            "project_id": self._get_project_id(),
            "is_dangerous": any(p in target for p in self.DANGEROUS_PATTERNS),
        }
        # 追加到 JSONL 文件
        with open(self.observations_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def detect_patterns(self, min_count: int = 3) -> list:
        """
        从观察日志中检测模式（参考 ECC instinct 聚类）
        返回：[{pattern, count, examples, confidence}]
        """
        if not self.observations_path.exists():
            return []

        observations = []
        with open(self.observations_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    observations.append(json.loads(line.strip()))
                except:
                    continue

        if len(observations) < min_count:
            return []

        # 检测1：重复的目标路径
        target_counts = {}
        for obs in observations:
            key = f"{obs['tool']}:{obs['action']}:{obs.get('target','')[:50]}"
            if key not in target_counts:
                target_counts[key] = {"count": 0, "examples": [], "obs": []}
            target_counts[key]["count"] += 1
            if len(target_counts[key]["examples"]) < 3:
                target_counts[key]["examples"].append(obs.get("target", ""))

        patterns = []
        for key, info in target_counts.items():
            if info["count"] >= min_count:
                confidence = min(0.3 + info["count"] * 0.1, 0.9)
                patterns.append({
                    "pattern": key,
                    "count": info["count"],
                    "examples": info["examples"],
                    "confidence": confidence,
                    "trigger": observations[0].get("task_context", ""),
                    "project_id": observations[0].get("project_id", ""),
                })

        return sorted(patterns, key=lambda x: -x["count"])

    def get_recent_observations(self, limit: int = 50) -> list:
        """获取最近的观察记录"""
        if not self.observations_path.exists():
            return []
        observations = []
        with open(self.observations_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    observations.append(json.loads(line.strip()))
                except:
                    continue
        return observations[-limit:]

    def warn_dangerous(self, tool: str, target: str) -> Optional[str]:
        """检测危险操作并返回警告信息"""
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in target:
                return f"[安全警告] 检测到危险操作: {pattern} in {target}"
        return None

    def get_stats(self) -> dict:
        """获取观察统计"""
        obs = self.get_recent_observations(limit=1000)
        if not obs:
            return {"total": 0, "dangerous": 0, "by_tool": {}}
        dangerous = sum(1 for o in obs if o.get("is_dangerous"))
        by_tool = {}
        for o in obs:
            t = o.get("tool", "unknown")
            by_tool[t] = by_tool.get(t, 0) + 1
        return {
            "total": len(obs),
            "dangerous": dangerous,
            "by_tool": by_tool,
            "recent_dangerous": [o for o in obs[-20:] if o.get("is_dangerous")],
        }


# ═══════════════════════════════════════════════════════
# Rationalization 捕获系统（来自 v2.1）
# ═══════════════════════════════════════════════════════

@dataclass
class Rationalization:
    """一次 rationalization（合理化借口）记录"""
    timestamp: str
    task: str
    best_method: str
    actual_method: str
    why_not_best: str
    outcome: str
    lesson: str = ""

    def to_teachable_point(self) -> str:
        if self.outcome == "failure":
            return f"没用 {self.best_method} → {self.why_not_best} → 失败"
        return f"用了 {self.actual_method} 但 {self.best_method} 更好：{self.lesson}"


class RationalizationTracker:
    def __init__(self, path=RATIONALIZATIONS_PATH):
        self.path = path

    def _load(self) -> list:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except:
                return []
        return []

    def _save(self, data: list):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(self, task: str, best_method: str, actual_method: str,
               why_not_best: str, outcome: str = "failure", lesson: str = ""):
        if best_method == actual_method:
            return
        data = self._load()
        entry = Rationalization(
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
            task=task,
            best_method=best_method,
            actual_method=actual_method,
            why_not_best=why_not_best,
            outcome=outcome,
            lesson=lesson,
        )
        data.append(asdict(entry))
        if len(data) > 50:
            data = data[-50:]
        self._save(data)

    def get_defense_patterns(self) -> dict:
        data = self._load()
        patterns = {}
        for entry in data:
            key = entry["why_not_best"]
            if key not in patterns:
                patterns[key] = {"count": 0, "examples": [], "task": entry["task"]}
            patterns[key]["count"] += 1
            if len(patterns[key]["examples"]) < 2:
                patterns[key]["examples"].append(entry["task"])
        return dict(sorted(patterns.items(), key=lambda x: -x[1]["count"]))

    def get_teachable_points(self) -> list:
        data = self._load()
        return [Rationalization(**e).to_teachable_point() for e in data[-10:]]

    def suggest_defense(self) -> str:
        patterns = self.get_defense_patterns()
        if not patterns:
            return ""
        suggestions = []
        for rat, info in list(patterns.items())[:3]:
            suggestions.append(f"- \"{rat}\" 出现了 {info['count']} 次 → 规则要明确禁止")
        return "\n".join(suggestions) if suggestions else ""


# ═══════════════════════════════════════════════════════
# Skill CSO 检查（来自 v2.1）
# ═══════════════════════════════════════════════════════

def check_skill_cso(skill_path: str) -> dict:
    result = {"path": skill_path, "passed": True, "issues": [], "suggestions": []}
    try:
        content = Path(skill_path).read_text(encoding="utf-8")
    except Exception as e:
        result["passed"] = False
        result["issues"].append(f"无法读取文件: {e}")
        return result

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        result["issues"].append("无 YAML frontmatter")
        result["suggestions"].append("添加 ---name/description--- 前端")
        return result

    fm = _parse_mini_yaml(match.group(1))
    desc = fm.get("description", "")

    if not desc:
        result["issues"].append("description 为空")
        result["passed"] = False
        return result

    if not re.match(r"^[Uu]se\s+when", desc):
        result["issues"].append(f"description 不以 'Use when' 开头: {desc[:60]}")
        result["suggestions"].append("改为: Use when + 触发条件（症状），不是工作流")
        result["passed"] = False

    bad_patterns = [
        "dispatches subagent", "runs subagent", "writes test first",
        "write test first", "minimal code", "watch it fail",
        "red-green-refactor", "TDD cycle",
    ]
    for bp in bad_patterns:
        if bp.lower() in desc.lower():
            result["issues"].append(f"description 包含工作流总结: '{bp}'")
            result["suggestions"].append("description = 触发条件，不是工作流程")
            result["passed"] = False

    return result


def _parse_mini_yaml(text: str) -> dict:
    result = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ": " in line:
            key, val = line.split(": ", 1)
            result[key.strip()] = val.strip().strip('"\'')
        elif ":" in line:
            key = line.split(":")[0].strip()
            result[key] = ""
    return result


# ═══════════════════════════════════════════════════════
# pass@k 评估系统（v2.2 新增，参考 ECC eval-harness）
# ═══════════════════════════════════════════════════════

@dataclass
class EvalResult:
    """一次评估结果"""
    task: str
    method: str
    k: int                    # 总尝试次数
    successes: int            # 成功次数
    timestamp: str

    @property
    def pass_at_k(self) -> float:
        """pass@k = 至少一次成功"""
        if self.k == 0:
            return 0.0
        return 1.0 - self._fail_prob()

    @property
    def pass_all_k(self) -> float:
        """pass^k = 全部成功"""
        if self.k == 0:
            return 0.0
        return self.successes / self.k

    def _fail_prob(self) -> float:
        """计算连续k次全部失败的概率"""
        if self.successes == 0:
            return 1.0
        fail_prob = 1.0 - (self.successes / self.k)
        return fail_prob ** self.k


# ═══════════════════════════════════════════════════════════════════════
# IterationBudget + GraceCall（参考 Hermes AIAgent, run_agent.py line 185）
# Hermes 核心设计：per-TURN 预算控制 + 宽限调用机制
# ═══════════════════════════════════════════════════════════════════════

class IterationBudget:
    """
    迭代预算控制器。

    Hermes 设计（run_agent.py line 185）：
    - per-TURN 预算，不是全局预算
    - 宽限调用（grace call）：预算耗尽后给模型一次机会自己决定结束
    - refund 机制：错误不计入预算（重试不扣分）

    使用方式：
        budget = IterationBudget(max_total=10)
        while budget.remaining > 0 or budget.grace_available:
            if not budget.consume():
                break  # 预算真正耗尽
            result = try_api_call()
            if result.is_error:
                budget.refund()  # 不算这次
    """

    def __init__(self, max_total: int = 90):
        self.max_total = max_total
        self._used = 0
        self._grace_used = False

    def consume(self) -> bool:
        """
        消耗一次预算。
        Returns False when budget is exhausted (should stop).
        """
        if self._used >= self.max_total:
            return False
        self._used += 1
        return True

    def refund(self) -> None:
        """
        退回一次预算（用于错误/重试场景）。
        重试不应该消耗预算。
        """
        if self._used > 0:
            self._used -= 1

    def grant_grace(self) -> None:
        """
        授予宽限调用权限。
        预算耗尽后给模型一次机会自己决定是否结束。
        """
        self._grace_used = False  # 重置宽限

    def use_grace(self) -> bool:
        """
        使用宽限调用。
        Returns False if grace was already used.
        """
        if self._grace_used:
            return False
        self._grace_used = True
        return True

    @property
    def remaining(self) -> int:
        """剩余迭代次数"""
        return max(0, self.max_total - self._used)

    @property
    def used(self) -> int:
        """已使用迭代次数"""
        return self._used

    @property
    def grace_available(self) -> bool:
        """宽限调用是否可用"""
        return self._used >= self.max_total and not self._grace_used

    @property
    def exhausted(self) -> bool:
        """预算是否已耗尽"""
        return self._used >= self.max_total

    def __repr__(self) -> str:
        return f"IterationBudget({self._used}/{self.max_total}, grace={'available' if self.grace_available else 'used' if self._grace_used else 'unused'})"


class EvalTracker:
    """
    评估追踪器 — 参考 ECC eval-harness 的 pass@k 指标
    """
    EVAL_DB = WORKSPACE / ".evolver_evals.json"

    def __init__(self):
        self.evals = self._load()

    def _load(self) -> dict:
        if self.EVAL_DB.exists():
            try:
                return json.loads(self.EVAL_DB.read_text(encoding="utf-8"))
            except:
                return {}
        return {}

    def _save(self):
        self.EVAL_DB.write_text(json.dumps(self.evals, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_attempt(self, task: str, method: str, success: bool):
        """记录一次评估尝试"""
        key = f"{task}|{method}"
        if key not in self.evals:
            self.evals[key] = {"task": task, "method": method, "attempts": [], "created_at": time.strftime("%Y-%m-%d %H:%M")}
        self.evals[key]["attempts"].append({
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    def get_eval(self, task: str, method: str) -> Optional[EvalResult]:
        key = f"{task}|{method}"
        if key not in self.evals:
            return None
        data = self.evals[key]
        successes = sum(1 for a in data["attempts"] if a["success"])
        k = len(data["attempts"])
        return EvalResult(task=task, method=method, k=k, successes=successes, timestamp=data["created_at"])

    def pass_at_k(self, task: str, method: str, k: int = None) -> float:
        """计算 pass@k"""
        eval_result = self.get_eval(task, method)
        if not eval_result or eval_result.k == 0:
            return 0.0
        if k is None:
            k = eval_result.k
        if k > eval_result.k:
            # 用现有数据估算
            successes = eval_result.successes
            fail_prob = 1.0 - (successes / eval_result.k)
            return 1.0 - (fail_prob ** k)
        # 重新计算前k次
        attempts = eval_result.k
        successes_in_k = min(successes, k)
        fail_prob = 1.0 - (successes_in_k / k)
        return 1.0 - (fail_prob ** k)

    def summary(self) -> str:
        """生成评估摘要"""
        lines = ["=== Eval Summary ==="]
        for key, data in self.evals.items():
            successes = sum(1 for a in data["attempts"] if a["success"])
            k = len(data["attempts"])
            if k == 0:
                continue
            p1 = successes / k if k > 0 else 0
            fail_prob = 1.0 - p1
            p3 = 1.0 - (fail_prob ** 3)
            p5 = 1.0 - (fail_prob ** 5)
            task = data["task"][:40]
            lines.append(f"  {task}: pass@1={p1:.0%} | pass@3={p3:.0%} | pass@5={p5:.0%} ({successes}/{k})")
        return "\n".join(lines) if lines else "  (暂无评估数据)"


# ═══════════════════════════════════════════════════════
# 规则引擎核心
# ═══════════════════════════════════════════════════════

@dataclass
class Rule:
    id: str
    task: str
    method: str
    conditions: list
    group_op: str = "AND"
    success_count: int = 0
    total_count: int = 0
    consecutive_failures: int = 0
    is_active: bool = True
    priority: int = 0
    last_success: str = ""
    last_failure: str = ""
    created_at: str = ""
    rationalizations: list = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_count == 0: return 0.0
        return self.success_count / self.total_count

    @property
    def confidence(self) -> float:
        base = self.success_rate
        sample_weight = min(self.total_count / 10, 1.0)
        priority_weight = (self.priority + 1) / 10
        return base * (0.7 + 0.2 * sample_weight + 0.1 * priority_weight)


class EvolverEngine:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.rat_tracker = RationalizationTracker()
        self.observer = ToolObserver()
        self.eval_tracker = EvalTracker()
        self.rules = self._load()

    def _load(self) -> list:
        if self.db_path.exists():
            try:
                data = json.loads(self.db_path.read_text(encoding="utf-8"))
                return [Rule(**r) for r in data.get("rules", [])]
            except:
                return []
        return []

    def _save(self):
        data = {"rules": [asdict(r) for r in self.rules]}
        self.db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _match_condition(self, field_value, condition: dict) -> bool:
        op = condition.get("operator", "equals")
        expected = condition.get("value")
        negate = condition.get("negate", False)
        if op not in OPERATORS: return False
        matched = OPERATORS[op](field_value, expected)
        return not matched if negate else matched

    def _match_rule(self, rule: Rule, input_fields: dict) -> bool:
        if not rule.is_active: return False
        results = []
        for cond in rule.conditions:
            field = cond.get("field", "")
            value = input_fields
            for key in field.split("."):
                if isinstance(value, dict):
                    value = value.get(key, "")
                else:
                    value = ""
            results.append(self._match_condition(value, cond))
        if not results: return False
        return all(results) if rule.group_op == "AND" else any(results)

    def evaluate(self, input_fields: dict) -> list:
        matches = []
        for rule in self.rules:
            if self._match_rule(rule, input_fields):
                matches.append({
                    "rule": rule,
                    "confidence": rule.confidence,
                    "success_rate": rule.success_rate,
                    "attempts": rule.total_count,
                })
        matches.sort(key=lambda x: -x["confidence"])
        return matches

    def best_method(self, input_fields: dict) -> Optional[dict]:
        matches = self.evaluate(input_fields)
        if not matches: return None
        best = matches[0]
        return {
            "method": best["rule"].method,
            "task": best["rule"].task,
            "confidence": best["confidence"],
            "success_rate": best["success_rate"],
            "attempts": best["attempts"],
            "alternatives": [{"method": m["rule"].method, "confidence": m["confidence"]} for m in matches[1:4]],
        }

    def record(self, task: str, method: str, success: bool,
               input_fields: dict = None, error: str = None,
               notes: str = None,
               best_method: str = None,
               why_not_best: str = None):
        now = time.strftime("%Y-%m-%d %H:%M")
        input_fields = input_fields or {}
        input_fields["task"] = task
        input_fields["method"] = method
        if error:
            input_fields["error"] = error

        # pass@k 评估记录（v2.2 新增）
        self.eval_tracker.record_attempt(task, method, success)

        if best_method and why_not_best:
            self.rat_tracker.record(
                task=task, best_method=best_method, actual_method=method,
                why_not_best=why_not_best, outcome="success" if success else "failure",
                lesson=notes or "",
            )

        existing = None
        for r in self.rules:
            if r.task == task and r.method == method:
                existing = r; break

        if existing:
            existing.total_count += 1
            if success:
                existing.success_count += 1
                existing.consecutive_failures = 0
                existing.last_success = now
            else:
                existing.consecutive_failures += 1
                existing.last_failure = now
            if existing.consecutive_failures >= 3:
                existing.is_active = False
                existing.priority = max(0, existing.priority - 1)
        else:
            new_rule = Rule(
                id=f"rule_{len(self.rules) + 1}_{int(time.time())}",
                task=task, method=method,
                conditions=self._infer_conditions(task, method, input_fields),
                group_op="OR", total_count=1,
                success_count=1 if success else 0,
                consecutive_failures=0 if success else 1,
                last_success=now if success else "",
                last_failure=now if not success else "",
                created_at=now,
            )
            self.rules.append(new_rule)

        self._save()

        # v2.3: auto-record agent facts (mem0 Agent Facts as First-Class)
        try:
            record_agent_fact(task=task, method=method, success=success)
        except Exception:
            pass

        try:
            import self_review as sr_module
            # 检测是否有工具使用记录（从 input_fields 传递）
            used_tools = input_fields.get("_used_tools", []) if input_fields else []
            sr_module.run_review(
                task=task,
                method=method,
                success=success,
                used_tools=used_tools,
                error=error,
                notes=notes,
            )
        except Exception:
            # self_review 失败不影响 evolver 核心功能
            pass

    def _infer_conditions(self, task: str, method: str, fields: dict) -> list:
        conditions = []
        keywords = [w for w in re.split(r"[\s,，。、！？]", task) if len(w) >= 2]
        if keywords:
            conditions.append({"field": "task", "operator": "contains", "value": keywords[0]})
        conditions.append({"field": "method", "operator": "equals", "value": method})
        return conditions

    def get_stats(self) -> dict:
        total = len(self.rules)
        active = sum(1 for r in self.rules if r.is_active)
        success_rates = [r.success_rate for r in self.rules if r.total_count > 0]
        avg_rate = sum(success_rates) / len(success_rates) if success_rates else 0
        tripped = [r for r in self.rules if r.consecutive_failures >= 3]
        obs_stats = self.observer.get_stats()
        return {
            "total_rules": total,
            "active_rules": active,
            "inactive_rules": total - active,
            "avg_success_rate": avg_rate,
            "tripped_rules": len(tripped),
            "rationalization_count": len(self.rat_tracker._load()),
            "rationalization_defense": self.rat_tracker.suggest_defense(),
            "observations_total": obs_stats.get("total", 0),
            "observations_dangerous": obs_stats.get("dangerous", 0),
        }

    def compact(self):
        now = time.time()
        to_keep, to_archive = [], []
        for r in self.rules:
            last_ts = r.last_success or r.last_failure or r.created_at
            try:
                age_days = (now - time.mktime(time.strptime(last_ts, "%Y-%m-%d %H:%M"))) / 86400
                if age_days > 30 and r.success_rate < 0.5:
                    to_archive.append(r)
                else:
                    to_keep.append(r)
            except:
                to_keep.append(r)
        if len(to_keep) > 50:
            to_keep.sort(key=lambda r: -r.success_rate)
            to_keep = to_keep[:50]
        self.rules = to_keep
        self._save()
        return {"kept": len(to_keep), "archived": len(to_archive)}


# ═══════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════

def record(task: str, method: str, success: bool, error: str = None,
           notes: str = None, best_method: str = None, why_not_best: str = None):
    engine = EvolverEngine()
    engine.record(task, method, success, error=error, notes=notes,
                   best_method=best_method, why_not_best=why_not_best)


def recall(task: str, **fields) -> Optional[dict]:
    engine = EvolverEngine()
    fields["task"] = task
    return engine.best_method(fields)


def observe(tool: str, action: str, target: str, outcome: str = "success",
            error: str = "", duration_ms: float = 0, task_context: str = ""):
    """记录一次工具调用观察（含 ISC 安全检查）"""
    # ISC Defense: 执行链安全预检（来自 safety_monitor.py）
    try:
        from safety_monitor import check_tool_call
        result = check_tool_call(tool, target)
        if not result.safe:
            import logging
            logging.warning(f"🚨 ISC 安全检查拦截: tool={tool}, reason={result.reason}, block={result.block}")
            if result.block:
                print(f"🚨 ISC 安全拦截: {result.reason}")
                # 安全规则阻断 → 不记录此次观察（因为操作被阻止了）
                return {"blocked": True, "reason": result.reason, "risk_level": result.risk_level.name}
    except ImportError:
        pass  # safety_monitor.py 未安装时静默降级
    observer = ToolObserver()
    observer.record_observation(tool, action, target, outcome, error, duration_ms, task_context)


def patterns():
    """检测观察到的模式"""
    observer = ToolObserver()
    patterns = observer.detect_patterns()
    if not patterns:
        print("(未检测到模式，至少需要3次相同观察)")
        return
    print(f"检测到 {len(patterns)} 个模式:")
    for p in patterns:
        print(f"  [{p['confidence']:.1f}] {p['pattern'][:60]} (x{p['count']})")
        for ex in p['examples'][:2]:
            print(f"    e.g. {ex[:60]}")


def eval_summary():
    """显示 pass@k 评估摘要"""
    engine = EvolverEngine()
    print(engine.eval_tracker.summary())


def rationalizations():
    tracker = RationalizationTracker()
    patterns = tracker.get_defense_patterns()
    print(f"Rationalization 模式 ({len(patterns)} 种):")
    for rat, info in patterns.items():
        print(f"  x{info['count']}: {rat}")
        print(f"    e.g. {info['task'][:50]}")
    print()
    print("防御建议:")
    print(tracker.suggest_defense() or "  (暂无)")


def check_skill(skill_path: str):
    result = check_skill_cso(skill_path)
    status = "[PASS]" if result["passed"] else "[FAIL]"
    print(f"{status} {result['path']}")
    for issue in result["issues"]:
        print(f"  ! {issue}")
    for sug in result["suggestions"]:
        print(f"  > {sug}")


# ═══════════════════════════════════════════════════════
# ECC instinct 系统集成（v2.3 新增）
# 参考：ECC continuous-learning-v2 instinct-cli.py
# ═══════════════════════════════════════════════════════

def instinct_status():
    """显示 instinct 状态（ECC instinct 模型）"""
    from instinct_model import status_text, detect_project, load_all_instincts
    project = detect_project()
    instincts = load_all_instincts(project)
    print(status_text())


def instinct_promote(instinct_id: str, dry_run: bool = False):
    """将 instinct 从项目级 promote 到全局"""
    from instinct_model import promote_instinct
    success, msg = promote_instinct(instinct_id, dry_run=dry_run)
    if not success:
        print(f"[SKIP] {msg}")
    else:
        print(f"[OK] {msg}")


def instinct_create_from_rule(rule_dict: dict) -> bool:
    """将 evolver Rule 转换为 instinct 并保存"""
    from instinct_model import instinct_from_rule, save_instinct
    try:
        inst = instinct_from_rule(rule_dict)
        path = save_instinct(inst)
        print(f"[INSTINCT] Created: {inst.id} -> {path}")
        return True
    except FileExistsError:
        print(f"[INSTINCT] Already exists: {rule_dict.get('task','')}/{rule_dict.get('method','')}")
        return False
    except Exception as e:
        print(f"[INSTINCT] Error: {e}")
        return False


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("evolver.py v2.2 — 规则引擎 + Hook观察层 + pass@k评估")
        print()
        print("用法:")
        print("  evolver.py record <task> <method> <yes|no> [error] [best_method] [why_not_best]")
        print("  evolver.py recall <task>")
        print("  evolver.py stats")
        print("  evolver.py compact")
        print("  evolver.py observe <tool> <action> <target> [outcome] [error]")
        print("  evolver.py patterns")
        print("  evolver.py evals")
        print("  evolver.py rationalizations")
        print("  evolver.py check-skill <path>")
        print("  evolver.py instinct-status")
        print("  evolver.py instinct-promote <id> [--dry-run]")
        print("  evolver.py facts")
        print("  evolver.py record-agent-fact <task> <method> <yes|no>")
        return

    engine = EvolverEngine()
    cmd = sys.argv[1]

    if cmd == "record" and len(sys.argv) >= 5:
        task = sys.argv[2]
        method = sys.argv[3]
        success = "yes" in sys.argv[4].lower()
        error = sys.argv[5] if len(sys.argv) > 5 else None
        best = sys.argv[6] if len(sys.argv) > 6 else None
        why = sys.argv[7] if len(sys.argv) > 7 else None
        engine.record(task, method, success, error=error,
                       best_method=best, why_not_best=why)
        print(f"[OK] {task} @ {method} -> {'OK' if success else 'FAIL'}")
        # pass@k 反馈
        eval_result = engine.eval_tracker.get_eval(task, method)
        if eval_result and eval_result.k >= 2:
            p1 = eval_result.success_rate
            fail_prob = 1.0 - p1
            p3 = 1.0 - (fail_prob ** 3)
            print(f"    pass@1={p1:.0%} | pass@3={p3:.0%} ({eval_result.successes}/{eval_result.k})")
        if why:
            print(f"    Rationalization: {why}")

    elif cmd == "recall" and len(sys.argv) >= 3:
        task = " ".join(sys.argv[2:])
        result = recall(task)
        if result:
            print(f"[BEST] {result['method']} (confidence={result['confidence']:.2f})")
            if result.get("alternatives"):
                print("[ALT] " + " | ".join(a["method"] for a in result["alternatives"][:3]))
        else:
            print("[NONE] no matching rules")

    elif cmd == "stats":
        s = engine.get_stats()
        print(f"Total: {s['total_rules']} | Active: {s['active_rules']} | Tripped: {s['tripped_rules']}")
        print(f"Avg success rate: {s['avg_success_rate']:.1%}")
        print(f"Rationalizations captured: {s['rationalization_count']}")
        print(f"Tool observations: {s['observations_total']} (dangerous: {s['observations_dangerous']})")
        if s["rationalization_defense"]:
            print("\nDefenses:")
            print(s["rationalization_defense"])

    elif cmd == "compact":
        result = engine.compact()
        print(f"[COMPACT] kept={result['kept']}, archived={result['archived']}")

    elif cmd == "observe" and len(sys.argv) >= 5:
        tool, action, target = sys.argv[2], sys.argv[3], sys.argv[4]
        outcome = sys.argv[5] if len(sys.argv) > 5 else "success"
        error = sys.argv[6] if len(sys.argv) > 6 else ""
        observe(tool, action, target, outcome, error)
        print(f"[OBSERVE] {tool}:{action} -> {target[:50]} [{outcome}]")

    elif cmd == "patterns":
        patterns()

    elif cmd == "evals":
        eval_summary()

    elif cmd == "rationalizations":
        rationalizations()

    elif cmd == "check-skill" and len(sys.argv) >= 3:
        for p in sys.argv[2:]:
            check_skill(p)

    elif cmd == "instinct-status":
        instinct_status()

    elif cmd == "instinct-promote":
        instinct_id = sys.argv[2] if len(sys.argv) >= 3 else None
        dry_run = "--dry-run" in sys.argv
        if not instinct_id:
            print("[ERROR] instinct-promote 需要 instinct_id")
            return
        instinct_promote(instinct_id, dry_run=dry_run)

    elif cmd == "facts":
        stats = agent_facts_stats()
        print(f"Agent Facts: total={stats['total']}, success={stats['success']}, failure={stats['failure']}")

    elif cmd == "record-agent-fact" and len(sys.argv) >= 5:
        task_name = sys.argv[2]
        method_name = sys.argv[3]
        is_success = "yes" in sys.argv[4].lower()
        fact_list = sys.argv[5:] if len(sys.argv) > 5 else None
        record_agent_fact(task_name, method_name, is_success, fact_list)
        print(f"[FACT RECORDED] {task_name[:60]}, success={is_success}")

    elif cmd == "suggest-skill":
        # Hermes 风格：基于evolover DB 自动判断是否应创建skill
        results = suggest_skill_creation()
        if not results:
            print("[SKILL] 无需创建新skill，当前规则覆盖充分")
        else:
            print(f"[SKILL] 发现 {len(results)} 个 skill 创建建议：\n")
            for r in results:
                print(f"  ★ {r['name']}")
                print(f"    原因: {r['reason']}")
                print(f"    触发条件: {r['trigger']}")
                print(f"    建议操作: {r['action']}")
                print()

    else:
        print("Unknown command:", cmd)


# Hermes 风格 Skill 创建建议系统
# 来源: Hermes agent/skill_manager_tool.py 工具描述 + 自主进化机制
# ═══════════════════════════════════════════════════════════════════════════

# Hermes 的 skill_create 触发条件（从 skill_manager_tool.py 提取）
HERMES_CREATE_CONDITIONS = {
    "complex_task": {
        "threshold": 5,  # 5+ 工具调用
        "description": "复杂任务成功完成（5+ 工具调用）",
        "weight": 1.5,
    },
    "error_overcome": {
        "description": "克服了错误/障碍后成功",
        "weight": 1.3,
    },
    "user_corrected": {
        "description": "用户纠正后方法生效",
        "weight": 1.2,
    },
    "nontrivial_workflow": {
        "description": "发现了非平凡工作流",
        "weight": 1.1,
    },
    "repeated_pattern": {
        "threshold": 3,  # 同一任务类型重复3次
        "description": "同一任务类型重复出现3次以上",
        "weight": 1.4,
    },
    "user_requested": {
        "description": "用户明确要求记住某个流程",
        "weight": 2.0,
    },
}

# 更新触发条件（当发现错误/用户纠正时）
HERMES_UPDATE_CONDITIONS = [
    "instructions_stale",    # 指令过时/错误
    "os_specific_failure",  # OS特定失败
    "missing_steps",        # 缺失步骤
    "pitfalls_found",       # 发现新坑
]


def _analyze_rule_for_skill(rule) -> dict | None:
    """
    分析一条规则，判断是否应创建/更新 skill。
    兼容 Rule dataclass 和 dict。
    """
    # Convert dataclass Rule to dict (include @property fields too)
    if hasattr(rule, '__dataclass_fields__'):
        r = {f: getattr(rule, f) for f in rule.__dataclass_fields__}
        # Add @property fields
        for prop in ['success_rate', 'confidence']:
            if hasattr(rule, prop):
                r[prop] = getattr(rule, prop)
    elif hasattr(rule, 'asdict'):
        r = rule.asdict()
        for prop in ['success_rate', 'confidence']:
            if hasattr(rule, prop):
                r[prop] = getattr(rule, prop)
    else:
        r = rule

    reason = ""
    action = "create"
    trigger = ""

    total = r.get("total_count", 0)
    success_rate = r.get("success_rate", 0)
    failed = r.get("failure_count", 0)
    method = r.get("method", "")
    errors = r.get("errors", [])
    rationalizations = r.get("rationalizations", [])
    last_error = errors[-1] if errors else ""
    task_name = r.get("task", "unnamed")

    # 条件1：复杂任务（5+ 调用）
    if total >= 5 and success_rate >= 0.6:
        reason = f"复杂任务成功({total}次调用, 成功率{success_rate:.0%})，值得固化为 skill"
        trigger = "当遇到类似任务时，自动加载此 skill"
        action = "create"

    # 条件2：重复模式（3+ 次同一任务）
    elif total >= 3 and success_rate >= 0.7:
        reason = f"任务重复出现({total}次)，已有成熟方案，固化为 skill"
        trigger = "当此任务类型再次出现时"
        action = "create"

    # 条件3：克服错误
    elif failed >= 1 and success_rate >= 0.5:
        reason = f"成功克服错误（最后失败: {last_error[:50] if last_error else '无'}），记录为坑点"
        trigger = "当使用此方法时，预判可能的错误"
        action = "create"

    # 条件4：指令过时
    elif r.get("last_failure") and last_error and any(
        kw in last_error.lower()
        for kw in ["not found", "no such file", "error", "failed", "timeout"]
    ):
        reason = f"发现执行错误，需更新 skill 记录坑点"
        trigger = "执行此方法时，预判错误并准备 fallback"
        action = "update"

    # 条件5：低信心度但高使用频率
    elif total >= 5 and success_rate < 0.5:
        reason = f"使用频繁但成功率低({success_rate:.0%})，需要改进或添加 fallback"
        trigger = "加载此 skill 时，同步加载改进建议"
        action = "update"

    else:
        return None  # 不触发

    # 生成 skill 名称
    task_slug = task_name.lower().replace(" ", "-")[:30]
    method_slug = method.lower().replace(" ", "-")[:20] if method else "method"
    skill_name = f"{task_slug}-{method_slug}"

    return {
        "name": skill_name,
        "reason": reason,
        "trigger": trigger,
        "action": action,
        "confidence": min(r.get("confidence", 0.5) + 0.1, 0.99),
        "rule_ref": f"task={task_name}, method={method}",
        "metrics": {
            "total": total,
            "success_rate": success_rate,
            "failed": failed,
        },
    }


def suggest_skill_creation() -> list[dict]:
    """
    分析 evolver_db，输出 Hermes 风格的 skill 创建建议。
    对应 Hermes: skill_manage 工具描述中的 "Create when:" 触发条件。
    """
    engine = EvolverEngine()
    raw_rules = engine._load()
    # Convert Rule dataclasses to dicts (include @property fields)
    rules = []
    for r in raw_rules:
        if hasattr(r, '__dataclass_fields__'):
            rd = {f: getattr(r, f) for f in r.__dataclass_fields__}
            for prop in ['success_rate', 'confidence']:
                if hasattr(r, prop):
                    rd[prop] = getattr(r, prop)
            rules.append(rd)
        elif hasattr(r, 'asdict'):
            rd = r.asdict()
            for prop in ['success_rate', 'confidence']:
                if hasattr(r, prop):
                    rd[prop] = getattr(r, prop)
            rules.append(rd)
        else:
            rules.append(r)
    suggestions = []
    seen_names = set()

    for rule in rules:
        # 跳过熔断器触发的规则
        if rule.get("circuit_tripped"):
            continue

        r = _analyze_rule_for_skill(rule)
        if r and r["name"] not in seen_names:
            seen_names.add(r["name"])
            suggestions.append(r)

    # 按 confidence 排序
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    return suggestions


def skill_create_from_suggestion(suggestion: dict, skill_content: str) -> dict:
    """
    根据建议创建 skill 文件。
    返回创建结果。
    """
    # skill 存放目录：workspace/skills/
    skills_dir = WORKSPACE / "skills"
    skills_dir.mkdir(exist_ok=True)

    skill_dir = skills_dir / suggestion["name"]
    skill_dir.mkdir(exist_ok=True)

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(skill_content, encoding="utf-8")

    # 创建 .skill_id 文件（OpenSpace 风格）
    import hashlib, time
    fix_ts = int(time.time())
    skill_hash = hashlib.md5(suggestion["name"].encode()).hexdigest()[:8]
    skill_id = f"{suggestion['name']}__v0_{skill_hash}"
    (skill_dir / ".skill_id").write_text(skill_id, encoding="utf-8")

    # 创建 .meta.json
    meta = {
        "name": suggestion["name"],
        "skill_id": skill_id,
        "created_from": "evolver-suggestion",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_rule": suggestion.get("rule_ref", ""),
        "confidence": suggestion.get("confidence", 0),
        "trigger": suggestion.get("trigger", ""),
    }
    (skill_dir / ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "skill_dir": str(skill_dir),
        "skill_id": skill_id,
        "files": [str(skill_md), str(skill_dir / ".skill_id"), str(skill_dir / ".meta.json")],
    }


# ═════════════════════════════════════════════════════
# mem0 Agent Facts Recording (v2.3)
# Source: mem0 v3 — Agent Facts as First-Class Citizens
# ═════════════════════════════════════════════════════

FACTS_PATH = WORKSPACE / "memory" / "agent_facts.json"


def record_agent_fact(task: str, method: str, success: bool, facts=None):
    """
    Record agent facts — mem0 v3 Agent Facts as First-Class.
    Call after task completion to persist what the agent learned.
    
    Args:
        task: task description
        method: method used
        success: whether task succeeded
        facts: list of fact strings (auto-generated if None)
    """
    if facts is None:
        facts = [f"{task[:100]} — {'OK' if success else 'FAIL'} via {method[:50]}"]
    if not isinstance(facts, list):
        facts = [facts]
    
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
        "task": task,
        "method": method,
        "success": success,
        "facts": facts,
    }
    
    FACTS_PATH.parent.mkdir(exist_ok=True)
    data = []
    if FACTS_PATH.exists():
        try:
            data = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = []
    data.append(entry)
    if len(data) > 200:
        data = data[-200:]
    FACTS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def agent_facts_stats():
    """Get agent facts statistics."""
    if not FACTS_PATH.exists():
        return {"total": 0, "success": 0, "failure": 0}
    try:
        data = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
        return {
            "total": len(data),
            "success": sum(1 for d in data if d.get("success")),
            "failure": sum(1 for d in data if not d.get("success")),
        }
    except Exception:
        return {"total": 0, "success": 0, "failure": 0}


if __name__ == "__main__":
    main()
