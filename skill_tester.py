# -*- coding: utf-8 -*-
"""
skill_tester.py — TDD for Skills 工具

Superpowers 核心原则：No skill without failing test first

流程：
1. RED: 在无 skill 的状态下跑 baseline，记录 agent 的自然行为
2. GREEN: 加载 skill，再跑一次，验证 skill 是否解决了问题
3. REFACTOR: 如果还有漏洞，补上 skill，再测

用法：
  python skill_tester.py test <task> <scenario>
  python skill_tester.py baseline <task> <scenario>
  python skill_tester.py report <skill-name>
"""

import json
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

WORKSPACE = Path(__file__).parent
RESULTS_PATH = WORKSPACE / ".skill_test_results.json"
SKILLS_PATH = WORKSPACE / "skills"


@dataclass
class TestResult:
    """一次测试结果"""
    timestamp: str
    skill_name: str
    scenario: str
    mode: str              # "baseline" | "with_skill"
    agent_behavior: str    # agent 的实际行为（rationalization 等）
    rule_violations: list  # 违反的规则列表
    passed: bool
    notes: str = ""


@dataclass
class SkillTestReport:
    """一个 skill 的测试报告"""
    skill_name: str
    test_count: int
    passed_count: int
    failures: list
    rationalizations: list  # agent 的借口
    defenses: list           # 需要添加的防御


class SkillTester:
    def __init__(self):
        self.results = self._load()

    def _load(self) -> list:
        if RESULTS_PATH.exists():
            try:
                return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            except:
                return []
        return []

    def _save(self):
        RESULTS_PATH.write_text(
            json.dumps(self.results, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def run_baseline(self, task: str, scenario: str,
                     agent_behavior: str = None, violations: list = None,
                     notes: str = None) -> TestResult:
        """
        RED Phase: 无 skill 跑 baseline
        记录在没有 skill 的情况下，agent 会怎么表现
        """
        result = TestResult(
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
            skill_name="unknown",
            scenario=scenario,
            mode="baseline",
            agent_behavior=agent_behavior or "",
            rule_violations=violations or [],
            passed=False,
            notes=notes or "",
        )
        self.results.append(asdict(result))
        self._save()
        return result

    def run_with_skill(self, skill_name: str, scenario: str,
                       agent_behavior: str = None, violations: list = None,
                       passed: bool = False, notes: str = None) -> TestResult:
        """
        GREEN Phase: 有 skill 跑测试
        验证 skill 是否解决了 baseline 发现的问题
        """
        result = TestResult(
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
            skill_name=skill_name,
            scenario=scenario,
            mode="with_skill",
            agent_behavior=agent_behavior or "",
            rule_violations=violations or [],
            passed=passed,
            notes=notes or "",
        )
        self.results.append(asdict(result))
        self._save()
        return result

    def generate_report(self, skill_name: str) -> SkillTestReport:
        """生成 skill 的测试报告"""
        skill_results = [r for r in self.results if r["skill_name"] == skill_name]

        baseline = [r for r in skill_results if r["mode"] == "baseline"]
        with_skill = [r for r in skill_results if r["mode"] == "with_skill"]

        # 统计失败
        failures = [r for r in with_skill if not r["passed"]]

        # 提取 rationalizations（来自 baseline）
        all_rationalizations = []
        for r in baseline:
            if r["agent_behavior"]:
                all_rationalizations.append(r["agent_behavior"])

        # 生成防御建议
        defenses = []
        for v in [v for r in baseline for v in r.get("rule_violations", [])]:
            defenses.append(f"禁止: {v}")

        return SkillTestReport(
            skill_name=skill_name,
            test_count=len(with_skill),
            passed_count=len(with_skill) - len(failures),
            failures=failures,
            rationalizations=all_rationalizations,
            defenses=defenses,
        )

    def print_report(self, skill_name: str):
        report = self.generate_report(skill_name)
        print(f"\n{'='*50}")
        print(f"Skill: {skill_name}")
        print(f"测试次数: {report.test_count} | 通过: {report.passed_count} | 失败: {len(report.failures)}")
        print(f"{'='*50}")

        if report.rationalizations:
            print(f"\nRED Phase 发现（Rationalizations）:")
            for i, rat in enumerate(report.rationalizations, 1):
                print(f"  {i}. {rat[:80]}")

        if report.failures:
            print(f"\n失败场景:")
            for f in report.failures:
                print(f"  - [{f['scenario']}] {f['agent_behavior'][:60]}")

        if report.defenses:
            print(f"\n建议添加的防御:")
            for d in report.defenses:
                print(f"  > {d}")
        elif report.test_count > 0 and not report.failures:
            print(f"\n[PASS] Skill 通过所有测试")

    def summary(self):
        """全局统计"""
        baseline = [r for r in self.results if r["mode"] == "baseline"]
        with_skill = [r for r in self.results if r["mode"] == "with_skill"]
        passed = [r for r in with_skill if r["passed"]]

        print(f"\nSkill 测试总览")
        print(f"  Baseline 测试: {len(baseline)}")
        print(f"  含 Skill 测试: {len(with_skill)}")
        pct = f"{len(passed)/len(with_skill)*100:.0f}%" if with_skill else "0%"
        print(f"  通过: {len(passed)} ({pct})")

        # 列出未测 skill
        all_skills = self._find_all_skills()
        tested = set(r["skill_name"] for r in self.results if r["skill_name"] != "unknown")
        untested = [s for s in all_skills if s not in tested]
        if untested:
            print(f"\n未测试的 Skill:")
            for s in untested:
                print(f"  - {s}")

    def _find_all_skills(self) -> list:
        """列出所有 skill"""
        skills = []
        if SKILLS_PATH.exists():
            for d in SKILLS_PATH.iterdir():
                if d.is_dir() and (d / "SKILL.md").exists():
                    skills.append(d.name)
        # 也检查 bundled skills 目录
        bundled = Path(WORKSPACE) / ".qclaw" / "skills" if False else []  # skip for now
        return skills


def main():
    if len(sys.argv) < 2:
        print("Skill TDD Tester — Superpowers TDD for Skills")
        print("")
        print("用法:")
        print("  python skill_tester.py baseline <task> <scenario> --behavior '<agent怎么做>' --violations '<违反的规则>'")
        print("  python skill_tester.py test <skill> <scenario> <yes|no> --behavior '<agent怎么做>' --violations '<违反的规则>'")
        print("  python skill_tester.py report <skill>")
        print("  python skill_tester.py summary")
        print("")
        print("流程:")
        print("  RED:    python skill_tester.py baseline '<任务>' '<场景>' --behavior 'agent的借口'")
        print("  GREEN:  python skill_tester.py test '<skill名>' '<场景>' yes|no")
        print("  REPORT: python skill_tester.py report '<skill名>'")
        return

    tester = SkillTester()
    cmd = sys.argv[1]

    if cmd == "baseline" and len(sys.argv) >= 4:
        task = sys.argv[2]
        scenario = sys.argv[3]
        behavior = _get_flag("--behavior", "")
        violations = _get_flag("--violations", "").split(",")
        violations = [v.strip() for v in violations if v.strip()]

        result = tester.run_baseline(task, scenario, behavior, violations)
        print(f"[BASELINE] {scenario}")
        if behavior:
            print(f"  Agent: {behavior[:80]}")
        if violations:
            print(f"  Violations: {', '.join(violations)}")

    elif cmd == "test" and len(sys.argv) >= 5:
        skill = sys.argv[2]
        scenario = sys.argv[3]
        passed = "yes" in sys.argv[4].lower()
        behavior = _get_flag("--behavior", "")
        violations = _get_flag("--violations", "").split(",")
        violations = [v.strip() for v in violations if v.strip()]

        result = tester.run_with_skill(skill, scenario, behavior, violations, passed)
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {skill} @ {scenario}")
        if behavior:
            print(f"  Agent: {behavior[:80]}")

    elif cmd == "report" and len(sys.argv) >= 3:
        tester.print_report(sys.argv[2])

    elif cmd == "summary":
        tester.summary()

    else:
        print("Unknown command:", cmd)


def _get_flag(flag: str, default: str) -> str:
    args = sys.argv
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            return args[idx + 1]
    return default


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════
# Integration: evolver_db → 测试优先级（gstack Superpowers）
# ═══════════════════════════════════════════════════════════════════
def prioritize_from_evolver(skills_path=None, evolver_path=None) -> list:
    """
    基于 evolver_db 中的失败模式，推荐需要测试的 skills。
    evolver_db 中低 confidence 的任务 → 相应 skill 优先测。
    """
    import json, pathlib

    if skills_path is None:
        skills_path = pathlib.Path(__file__).parent / 'skills'
    if evolver_path is None:
        evolver_path = pathlib.Path(__file__).parent / '.evolver_db.json'

    if not evolver_path.exists():
        return []

    try:
        data = json.loads(evolver_path.read_text(encoding='utf-8'))
        rules = data.get('rules', [])
    except:
        return []

    candidates = [(r.get('task', ''), r.get('confidence', 0), r.get('method', ''))
                 for r in rules if r.get('confidence', 1) < 0.7]
    candidates.sort(key=lambda x: x[1])

    result = []
    for task, conf, method in candidates[:10]:
        for d in skills_path.iterdir():
            if not d.is_dir() or not (d / 'SKILL.md').exists():
                continue
            if task.lower() in d.name.lower():
                result.append((d.name, task, conf, method))
                break
    return result


def quality_report() -> None:
    """从 patch.py 导入并执行质量报告"""
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from patch import quality_report as qr
    qr()
