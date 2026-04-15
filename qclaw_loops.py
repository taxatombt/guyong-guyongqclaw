# -*- coding: utf-8 -*-
"""
qclaw_loops.py — qclaw 版 Autonomous Loops（自主循环模式）

参考：ECC autonomous-loops（MIT License）
来源：qclaw sessions_spawn + evolver + patch.py FileSnapshot
适配：qclaw OpenClaw 架构

6种模式（按复杂度排序）：
1. Sequential Pipeline  — 顺序步骤链
2. Persistent Session    — 持久会话（REPL模式）
3. Infinite Loop         — 无限并行（并行子代理）
4. De-Sloppify          — 清理通道（FileSnapshot集成）
5. CI Loop              — CI驱动迭代（轮询+修复）
6. RFC-Driven DAG       — 复杂任务的依赖DAG编排

关键设计原则：
- 每步隔离：避免上下文污染
- 负面指令危险：用独立清理步代替
- 退出条件必须明确：max_runs / max_duration / 完成信号
- 质量门控：每步后验证
"""

import json
import time
import sys
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Callable
from enum import Enum

WORKSPACE = Path(__file__).parent


# ═══════════════════════════════════════════════════════
# 模式选择器
# ═══════════════════════════════════════════════════════

class LoopMode(Enum):
    SEQUENTIAL = "sequential"
    PERSISTENT = "persistent"
    INFINITE = "infinite"
    DESLOPPIFY = "desloppify"
    CI = "ci"
    DAG = "dag"


@dataclass
class TaskProfile:
    """任务画像 — 判断适合的循环模式"""
    is_multi_step: bool
    has_spec: bool
    needs_parallel: bool
    is_critical: bool
    has_risk: bool
    expected_duration: str  # "minutes" / "hours" / "days"

    def recommend_mode(self) -> LoopMode:
        """推荐循环模式"""
        if self.is_critical and self.expected_duration in ("hours", "days"):
            return LoopMode.DAG
        if self.needs_parallel and self.has_spec:
            return LoopMode.INFINITE
        if self.is_critical and self.expected_duration == "hours":
            return LoopMode.CI
        if self.is_multi_step and self.has_risk:
            return LoopMode.DESLOPPIFY
        if self.is_multi_step:
            return LoopMode.SEQUENTIAL
        return LoopMode.PERSISTENT


def profile_task(task_desc: str) -> TaskProfile:
    """
    从任务描述推断任务画像。
    """
    t = task_desc.lower()

    # 多步骤判断
    multi_keywords = ["和", "、", "and", "then", "接下来", "同时", "多个"]
    is_multi = any(k in t for k in multi_keywords)

    # 有规范/文档判断
    has_spec = any(k in t for k in ["spec", "rfc", "prd", "规范", "文档", "设计"])

    # 并行判断
    parallel_keywords = ["并行", "多个版本", "variations", "batch", "批量", "同时生成"]
    needs_parallel = any(k in t for k in parallel_keywords)

    # 关键任务判断
    critical_keywords = ["关键", "critical", "production", "安全", "安全关键", "生产"]
    is_critical = any(k in t for k in critical_keywords)

    # 有风险判断
    risk_keywords = ["重构", "迁移", "数据库", "危险", "删除", "破坏"]
    has_risk = any(k in t for k in risk_keywords)

    # 时长判断
    duration_keywords_short = ["快速", "简单", "fix", "bug"]
    duration_keywords_long = ["大型", "完整", "系统", "架构", "重写", "refactor"]
    if any(k in t for k in duration_keywords_short):
        expected = "minutes"
    elif any(k in t for k in duration_keywords_long):
        expected = "hours"
    else:
        expected = "minutes"

    return TaskProfile(
        is_multi_step=is_multi,
        has_spec=has_spec,
        needs_parallel=needs_parallel,
        is_critical=is_critical,
        has_risk=has_risk,
        expected_duration=expected,
    )


# ═══════════════════════════════════════════════════════
# 1. Sequential Pipeline
# ═══════════════════════════════════════════════════════

@dataclass
class PipelineStep:
    """管道步骤"""
    name: str
    prompt: str
    allowed_tools: list = None
    model: str = ""
    on_failure: str = "stop"  # "stop" | "retry" | "continue"
    verify: str = ""  # 验证命令

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v}


def run_sequential_pipeline(steps: list[PipelineStep], max_runs: int = 3) -> dict:
    """
    顺序管道执行器。
    每步在独立子代理中运行。
    """
    from sessions_spawn import sessions_spawn

    results = []
    for i, step in enumerate(steps):
        print(f"[PIPELINE] Step {i+1}/{len(steps)}: {step.name}")

        attempt = 0
        success = False
        output = ""

        while attempt < max_runs and not success:
            attempt += 1
            if attempt > 1:
                print(f"  [RETRY {attempt}/{max_runs}]")

            # 运行子代理
            try:
                result = sessions_spawn(
                    task=step.prompt,
                    mode="run",
                    run_timeout_seconds=300,
                )
                output = str(result)[:500] if result else ""
                success = "error" not in output.lower() and "fail" not in output.lower()
            except Exception as e:
                output = str(e)
                success = False

        # 验证
        if success and step.verify:
            print(f"  [VERIFY] {step.verify[:60]}...")
            v_ok = subprocess.run(step.verify, shell=True, capture_output=True).returncode == 0
            if not v_ok:
                print(f"  [VERIFY FAIL] {step.name}")
                success = False

        results.append({
            "step": step.name,
            "success": success,
            "attempts": attempt,
            "output": output[:200],
        })
        print(f"  -> {'OK' if success else 'FAIL'}")

        if not success and step.on_failure == "stop":
            break

    return {
        "mode": "sequential",
        "total_steps": len(steps),
        "completed_steps": len(results),
        "failed_step": next((r["step"] for r in results if not r["success"]), None),
        "results": results,
    }


# ═══════════════════════════════════════════════════════
# 2. Persistent Session (NanoClaw REPL 模式)
# ═══════════════════════════════════════════════════════

def create_persistent_session(label: str, initial_task: str = "", skills: list = None) -> str:
    """
    创建持久会话。
    返回 session_key。
    """
    from sessions_spawn import sessions_spawn

    prompt_parts = []
    if initial_task:
        prompt_parts.append(f"任务：{initial_task}")
    if skills:
        prompt_parts.append(f"使用技能：{', '.join(skills)}")
    prompt_parts.append("\n完成当前任务后，等待下一步指令。")

    prompt = "\n".join(prompt_parts)

    result = sessions_spawn(
        task=prompt,
        label=label,
        mode="session",
        run_timeout_seconds=600,
    )
    return str(result) if result else ""


def send_to_session(session_key: str, message: str) -> str:
    """向持久会话发送消息"""
    from sessions_send import sessions_send
    result = sessions_send(session_key=session_key, message=message)
    return str(result) if result else ""


# ═══════════════════════════════════════════════════════
# 3. Infinite Loop (并行子代理)
# ═══════════════════════════════════════════════════════

@dataclass
class LoopConfig:
    """无限循环配置"""
    spec_file: str = ""  # 规范文件路径
    output_dir: str = ""  # 输出目录
    count: int = 3  # 并行数
    infinite: bool = False  # 无限模式
    wave_size: int = 3  # 每波数量
    context_threshold: float = 0.3  # 上下文低于30%停止

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


def run_infinite_loop(config: LoopConfig, orchestrator_prompt: str) -> dict:
    """
    无限循环执行器。
    编排器分析规范，然后并行部署子代理。
    """
    from sessions_spawn import sessions_spawn

    results = []
    wave = 0

    # 读取规范
    spec_content = ""
    if config.spec_file:
        spec_path = Path(config.spec_file)
        if spec_path.exists():
            spec_content = spec_path.read_text(encoding="utf-8")

    # 主循环
    while True:
        wave += 1
        agents_this_wave = min(config.wave_size, config.count - len(results)) if not config.infinite else config.wave_size

        if agents_this_wave <= 0 and not config.infinite:
            break

        print(f"[INFINITE LOOP] Wave {wave}: deploying {agents_this_wave} agents...")

        wave_results = []
        for i in range(agents_this_wave):
            agent_num = len(results) + i + 1
            prompt = f"""
{orchestrator_prompt}

[AGENT CONTEXT]
Iteration: {agent_num}
Spec:
{spec_content[:2000] if spec_content else '无规范文件'}

请专注于你的分配任务，生成独特的内容。
"""
            try:
                result = sessions_spawn(task=prompt, mode="run", run_timeout_seconds=300)
                wave_results.append({
                    "agent": agent_num,
                    "success": "error" not in str(result).lower(),
                    "result": str(result)[:200] if result else "",
                })
            except Exception as e:
                wave_results.append({
                    "agent": agent_num,
                    "success": False,
                    "result": str(e)[:100],
                })

        results.extend(wave_results)
        print(f"  Wave {wave} done: {sum(1 for r in wave_results if r['success'])}/{len(wave_results)} succeeded")

        # 无限模式检查
        if config.infinite:
            if len(results) >= config.count:
                break

        # 检查退出条件
        if not config.infinite and len(results) >= config.count:
            break

    return {
        "mode": "infinite",
        "total_agents": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "waves": wave,
        "results": results,
    }


# ═══════════════════════════════════════════════════════
# 4. De-Sloppify Pattern
# ═══════════════════════════════════════════════════════

DE_SLOP_PATTERN = """
清理规则（必须执行）：
1. 删除测试语言特性/框架行为的测试代码
2. 删除冗余的类型检查（类型系统已保证的部分）
3. 删除过于防御性的错误处理（不可能到达的状态）
4. 删除 console.log / print 语句
5. 删除注释掉的代码
6. 删除空行过多、格式混乱的文件
7. 删除临时文件、调试代码
8. 删除与业务逻辑无关的注释

保留：
- 所有业务逻辑测试
- 真实边界条件检查
- 必要的错误处理（用户输入、网络失败等）
- 有意义的注释（解释"为什么"，不是"是什么"）

执行后运行测试套件确保不破坏功能。
"""


def run_desloppify(target_paths: list[str] = None, test_command: str = "") -> dict:
    """
    清理模式：去除代码中的"slop"（垃圾代码）。
    使用 patch.py 的 FileSnapshot 在清理前自动快照。
    """
    from patch import PatchEngine
    from sessions_spawn import sessions_spawn

    engine = PatchEngine()

    # 如果没有指定路径，扫描 workspace
    if not target_paths:
        paths = list(WORKSPACE.glob("*.py"))
        paths += [f for f in WORKSPACE.glob("skills/**/*.md") if f.is_file()]
        target_paths = [str(p.relative_to(WORKSPACE)) for p in paths[:20]]

    if not target_paths:
        return {"error": "No files to clean"}

    print(f"[DESLOPPIFY] Cleaning {len(target_paths)} files...")

    # Step 1: 快照所有目标文件
    snapshot_results = []
    for path in target_paths:
        try:
            snap = engine.snapshot(path)
            snapshot_results.append(snap)
            print(f"  [SNAPSHOT] {path}")
        except Exception as e:
            print(f"  [SKIP] {path}: {e}")

    # Step 2: 清理
    prompt = f"""
请清理以下文件中的代码垃圾：

目标文件：{', '.join(target_paths)}

清理规则：
{DE_SLOP_PATTERN}

请逐一修改每个文件。对于每个文件：
1. 读取当前内容
2. 根据清理规则修改
3. 写回文件
4. 报告修改了什么

修改完成后（如果指定了测试命令）：
运行命令: {test_command or '(无)'}
"""

    try:
        result = sessions_spawn(task=prompt, mode="run", run_timeout_seconds=300)
        success = "error" not in str(result).lower()
    except Exception as e:
        result = str(e)
        success = False

    # Step 3: 验证
    verify_ok = False
    if test_command:
        print(f"[VERIFY] Running: {test_command}")
        v = subprocess.run(test_command, shell=True, capture_output=True, text=True)
        verify_ok = v.returncode == 0
        print(f"  -> {'PASS' if verify_ok else 'FAIL'}")
    else:
        print("[DESLOPPIFY] 完成（无验证命令）")

    return {
        "mode": "desloppify",
        "files_snapshotted": len(snapshot_results),
        "cleanup_success": success,
        "verify_passed": verify_ok,
        "snapshots": [str(s) for s in snapshot_results],
        "can_restore": True,
    }


# ═══════════════════════════════════════════════════════
# 5. CI Loop (轮询 CI 状态 + 自动修复)
# ═══════════════════════════════════════════════════════

@dataclass
class CILoopConfig:
    """CI 循环配置"""
    check_interval: int = 60  # 检查间隔（秒）
    max_retries: int = 3  # 最大自动修复次数
    ci_command: str = "python -m pytest"  # CI 检查命令
    notify_on: str = "all"  # "all" | "fail" | "never"


def run_ci_loop(config: CILoopConfig, task_prompt: str) -> dict:
    """
    CI 循环：持续运行任务，CI 失败时自动修复。
    """
    from sessions_spawn import sessions_spawn

    print(f"[CI LOOP] Starting with max_retries={config.max_retries}")

    iteration = 0
    retry_count = 0
    history = []

    while iteration < config.max_retries * 2:
        iteration += 1
        print(f"\n[CI LOOP] Iteration {iteration}")

        # Run task
        try:
            result = sessions_spawn(task=task_prompt, mode="run", run_timeout_seconds=600)
            task_output = str(result)[:300] if result else ""
        except Exception as e:
            task_output = str(e)
            result = None

        # Run CI check
        print(f"  [CI CHECK] {config.ci_command}")
        ci = subprocess.run(
            config.ci_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        ci_passed = ci.returncode == 0
        ci_output = ci.stdout.strip()[:200]

        history.append({
            "iteration": iteration,
            "ci_passed": ci_passed,
            "task_preview": task_output[:100],
            "ci_output": ci_output[:100],
        })

        if ci_passed:
            print(f"  [CI PASS] Iteration {iteration}")
            if config.notify_on in ("all", "pass"):
                pass
            break
        else:
            print(f"  [CI FAIL] Iteration {iteration} — triggering fix...")
            retry_count += 1
            if retry_count >= config.max_retries:
                print(f"  [CI LOOP] Max retries reached ({config.max_retries})")
                break

            # 自动修复
            fix_prompt = f"""
CI 检查失败。请修复以下问题：

上次任务输出：{task_output[:500]}

CI 失败原因：{ci_output}

请修复代码，然后重新运行 CI。
"""
            try:
                sessions_spawn(task=fix_prompt, mode="run", run_timeout_seconds=600)
            except Exception as e:
                print(f"  [FIX ERROR] {e}")

    return {
        "mode": "ci",
        "total_iterations": iteration,
        "successful_retries": retry_count,
        "final_pass": history[-1]["ci_passed"] if history else False,
        "history": history,
    }


# ═══════════════════════════════════════════════════════
# 6. RFC-Driven DAG（复杂度最高，概念验证）
# ═══════════════════════════════════════════════════════

@dataclass
class WorkUnit:
    """工作单元（RFC DAG 中的节点）"""
    id: str
    name: str
    description: str
    deps: list  # 依赖的 unit id
    tier: str = "small"  # "trivial" | "small" | "medium" | "large"
    acceptance: list = None

    def __post_init__(self):
        if self.acceptance is None:
            self.acceptance = []


def parse_rfc_units(rfc_content: str) -> list[WorkUnit]:
    """
    从 RFC 内容解析工作单元。
    简化版：按 ## 标题 分节，每节作为一个 work unit。
    """
    units = []
    current = {}

    for line in rfc_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            if current:
                units.append(WorkUnit(**current))
            current = {
                "id": re.sub(r"[^a-z0-9-]", "-", stripped[3:].lower())[:30],
                "name": stripped[3:].strip(),
                "description": "",
                "deps": [],
                "tier": "small",
            }
        elif current:
            current["description"] += stripped + "\n"

    if current:
        units.append(WorkUnit(**current))

    # 构建 DAG：按顺序假设无依赖
    for u in units:
        u.deps = []

    return units


def topological_sort(units: list[WorkUnit]) -> list[list[WorkUnit]]:
    """拓扑排序，按层返回可并行的工作单元"""
    remaining = {u.id: u for u in units}
    layers = []

    while remaining:
        # 找没有依赖的单元
        ready = [u for u in remaining.values() if all(d not in remaining for d in u.deps)]
        if not ready:
            # 循环依赖，随便取一个
            ready = [list(remaining.values())[0]]

        layers.append(ready)
        for u in ready:
            del remaining[u.id]

    return layers


def run_rfc_dag(rfc_content: str, task_template: str) -> dict:
    """
    RFC-Driven DAG 执行器。
    """
    from sessions_spawn import sessions_spawn

    units = parse_rfc_units(rfc_content)
    print(f"[RFC-DAG] {len(units)} work units, {len(topological_sort(units))} layers")

    results = {}
    for layer_idx, layer_units in enumerate(topological_sort(units)):
        print(f"\n[RFC-DAG] Layer {layer_idx + 1}: {len(layer_units)} units (parallel)")

        layer_results = []
        for unit in layer_units:
            prompt = task_template.format(
                unit_id=unit.id,
                unit_name=unit.name,
                unit_description=unit.description,
            )
            print(f"  [UNIT] {unit.id}")
            try:
                result = sessions_spawn(task=prompt, mode="run", run_timeout_seconds=600)
                success = "error" not in str(result).lower()
                layer_results.append({"unit": unit.id, "success": success, "result": str(result)[:200]})
                results[unit.id] = success
            except Exception as e:
                layer_results.append({"unit": unit.id, "success": False, "result": str(e)})
                results[unit.id] = False

        print(f"  Layer {layer_idx + 1} done: {sum(1 for r in layer_results if r['success'])}/{len(layer_results)}")

    return {
        "mode": "dag",
        "total_units": len(units),
        "layers": len(topological_sort(units)),
        "results": results,
        "all_passed": all(results.values()),
    }


# ═══════════════════════════════════════════════════════
# 快速执行入口（直接根据任务描述推荐并执行）
# ═══════════════════════════════════════════════════════

def auto_run(task: str, **kwargs) -> dict:
    """
    自动选择模式并执行。
    给定任务描述，自动判断合适的循环模式。
    """
    profile = profile_task(task)
    mode = profile.recommend_mode()

    print(f"[AUTO RUN] Task profile: multi={profile.is_multi_step}, spec={profile.has_spec}, "
          f"parallel={profile.needs_parallel}, critical={profile.is_critical}, "
          f"risk={profile.has_risk}, duration={profile.expected_duration}")
    print(f"[AUTO RUN] Recommended mode: {mode.value}")

    if mode == LoopMode.SEQUENTIAL:
        steps = kwargs.get("steps", [])
        if steps:
            return run_sequential_pipeline([PipelineStep(**s) for s in steps])
        return {"error": "Sequential mode requires 'steps' parameter"}

    elif mode == LoopMode.PERSISTENT:
        label = kwargs.get("label", f"auto-{int(time.time())}")
        skills = kwargs.get("skills", [])
        return {"session_key": create_persistent_session(label, task, skills)}

    elif mode == LoopMode.INFINITE:
        config = LoopConfig(
            count=kwargs.get("count", 3),
            infinite=kwargs.get("infinite", False),
            spec_file=kwargs.get("spec_file", ""),
        )
        return run_infinite_loop(config, task)

    elif mode == LoopMode.DESLOPPIFY:
        return run_desloppify(
            target_paths=kwargs.get("paths", None),
            test_command=kwargs.get("test_command", ""),
        )

    elif mode == LoopMode.CI:
        config = CILoopConfig(
            max_retries=kwargs.get("max_retries", 3),
            ci_command=kwargs.get("ci_command", "python -m pytest"),
        )
        return run_ci_loop(config, task)

    elif mode == LoopMode.DAG:
        rfc = kwargs.get("rfc_content", "")
        template = kwargs.get("task_template", "实现：{unit_name}\n\n{unit_description}")
        return run_rfc_dag(rfc, template)

    return {"error": f"Unknown mode: {mode}"}


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("qclaw_loops.py — Autonomous Loops 循环模式选择器")
        print()
        print("用法:")
        print("  python qclaw_loops.py auto <task>            # 自动选择并执行")
        print("  python qclaw_loops.py profile <task>        # 分析任务画像")
        print("  python qclaw_loops.py sequential <steps>   # 顺序管道")
        print("  python qclaw_loops.py desloppify            # 清理模式")
        print()
        print("6种循环模式:")
        print("  sequential    — 顺序步骤链（最简单）")
        print("  persistent    — 持久会话 REPL")
        print("  infinite      — 并行无限循环")
        print("  desloppify    — 清理通道（FileSnapshot）")
        print("  ci            — CI 驱动迭代")
        print("  dag           — RFC 依赖 DAG（最复杂）")
        return

    cmd = sys.argv[1]

    if cmd == "profile":
        task = " ".join(sys.argv[2:]) or "实现 OAuth2 登录功能"
        p = profile_task(task)
        print(f"Task: {task}")
        print(f"  Multi-step:   {p.is_multi_step}")
        print(f"  Has spec:     {p.has_spec}")
        print(f"  Needs parallel: {p.needs_parallel}")
        print(f"  Critical:     {p.is_critical}")
        print(f"  Risk:         {p.has_risk}")
        print(f"  Duration:     {p.expected_duration}")
        print(f"  Recommended:  {p.recommend_mode().value}")

    elif cmd == "auto":
        task = " ".join(sys.argv[2:]) or "修复所有 linter 错误"
        print(f"[AUTO] Task: {task}")
        result = auto_run(task)
        print(f"[RESULT] {json.dumps(result, ensure_ascii=False)[:300]}")

    elif cmd == "desloppify":
        paths = [a for a in sys.argv[2:] if not a.startswith("--")]
        test_cmd = next((a[5:] for a in sys.argv[2:] if a.startswith("--test=")), "")
        result = run_desloppify(paths or None, test_cmd)
        print(f"[RESULT] {json.dumps(result, ensure_ascii=False)[:300]}")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
