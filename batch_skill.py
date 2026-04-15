# -*- coding: utf-8 -*-
"""
batch_skill.py — 并行工作编排

来源: Claude Code /batch 命令
用途: 将大任务分解为5-30个独立单元，并行执行

不修改任何现有系统代码，纯新建模块。
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed


class WorkUnitStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkUnit:
    """单个工作单元"""
    id: str
    description: str
    instructions: str = ""
    status: WorkUnitStatus = WorkUnitStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class BatchPlan:
    """批量执行计划"""
    task: str
    units: List[WorkUnit] = field(default_factory=list)
    max_parallel: int = 5
    worktree_isolation: bool = True
    e2e_verification: str = ""


@dataclass
class BatchResult:
    """批量执行结果"""
    plan: BatchPlan
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: float = 0.0
    
    @property
    def success_rate(self) -> float:
        total = self.completed + self.failed
        if total == 0:
            return 0.0
        return self.completed / total


def decompose_task(task: str, count: int = 5) -> BatchPlan:
    """
    将大任务分解为独立工作单元
    
    参考 Claude Code /batch：
    1. 进入 Plan Mode → 研究 → 分解
    2. 每个单元一个后台 agent + worktree 隔离
    3. e2e 验证配方
    """
    # 简单的任务分解策略
    units = []
    
    # 按常见模式分解
    patterns = _identify_subtasks(task)
    
    for i, (desc, instructions) in enumerate(patterns[:count]):
        unit = WorkUnit(
            id=f"unit_{i+1:03d}",
            description=desc,
            instructions=instructions,
        )
        units.append(unit)
    
    return BatchPlan(
        task=task,
        units=units,
        max_parallel=min(count, 5),
    )


def _identify_subtasks(task: str) -> List[tuple]:
    """识别子任务"""
    subtasks = []
    task_lower = task.lower()
    
    # 通用分解模式
    if any(kw in task_lower for kw in ["refactor", "重构"]):
        subtasks = [
            ("Analyze current structure", "Read and analyze the current code structure"),
            ("Plan refactoring steps", "Identify specific changes needed"),
            ("Implement changes", "Apply the refactoring changes"),
            ("Run tests", "Execute test suite to verify changes"),
            ("Review results", "Review the refactoring outcome"),
        ]
    elif any(kw in task_lower for kw in ["implement", "实现"]):
        subtasks = [
            ("Design interface", "Define the API/interface"),
            ("Implement core logic", "Write the main implementation"),
            ("Add error handling", "Add validation and error handling"),
            ("Write tests", "Create unit tests"),
            ("Integration test", "Test integration with existing code"),
        ]
    elif any(kw in task_lower for kw in ["migrate", "迁移"]):
        subtasks = [
            ("Audit current state", "Document current implementation"),
            ("Create migration plan", "Plan step-by-step migration"),
            ("Execute migration", "Apply migration changes"),
            ("Validate migration", "Verify migrated code works"),
            ("Cleanup old code", "Remove deprecated code"),
        ]
    else:
        # 默认5步
        subtasks = [
            (f"Research: {task[:50]}", "Investigate and gather information"),
            ("Plan approach", "Design the solution approach"),
            ("Execute step 1", "First implementation step"),
            ("Execute step 2", "Second implementation step"),
            ("Verify and report", "Verify results and report"),
        ]
    
    return subtasks


def generate_worker_instructions(unit: WorkUnit, e2e_recipe: str = "") -> str:
    """
    生成 Worker 指令模板
    
    参考 Claude Code /batch Worker 指令：
    1. Simplify
    2. Run unit tests
    3. Test e2e
    4. Commit & push
    5. Report
    """
    instructions = f"""# Worker: {unit.id}

## Task
{unit.description}

## Instructions
{unit.instructions}

## Execution Protocol
1. **Simplify** — Review code for simplification opportunities
2. **Run unit tests** — Execute the test suite
3. **Test e2e** — {e2e_recipe or 'Verify end-to-end functionality'}
4. **Commit** — Commit changes with descriptive message
5. **Report** — Output summary of changes and test results

## Constraints
- Only modify files related to this task
- Do not change shared interfaces without coordination
- Report any blocking issues immediately
"""
    return instructions


def execute_batch(
    plan: BatchPlan,
    executor_fn: Optional[Callable[[WorkUnit], WorkUnit]] = None,
) -> BatchResult:
    """
    执行批量任务
    
    参考 Claude Code /batch：
    并行执行工作单元，状态表追踪进度
    """
    result = BatchResult(plan=plan)
    
    if executor_fn is None:
        # 默认执行器（模拟）
        executor_fn = _default_executor
    
    import time
    start = time.perf_counter()
    
    # 并行执行
    with ThreadPoolExecutor(max_workers=plan.max_parallel) as pool:
        futures = {}
        for unit in plan.units:
            unit.status = WorkUnitStatus.RUNNING
            future = pool.submit(executor_fn, unit)
            futures[future] = unit
        
        for future in as_completed(futures):
            unit = futures[future]
            try:
                completed_unit = future.result()
                if completed_unit.status == WorkUnitStatus.COMPLETED:
                    result.completed += 1
                elif completed_unit.status == WorkUnitStatus.FAILED:
                    result.failed += 1
                else:
                    result.skipped += 1
            except Exception as e:
                unit.status = WorkUnitStatus.FAILED
                unit.error = str(e)
                result.failed += 1
    
    result.total_duration_ms = (time.perf_counter() - start) * 1000
    
    return result


def _default_executor(unit: WorkUnit) -> WorkUnit:
    """默认执行器（模拟执行）"""
    import time
    time.sleep(0.01)  # 模拟工作
    unit.status = WorkUnitStatus.COMPLETED
    unit.result = f"Completed: {unit.description}"
    return unit


def format_batch_status(result: BatchResult) -> str:
    """格式化批量执行状态表"""
    lines = [
        f"# Batch Execution Report\n",
        f"**Task**: {result.plan.task}",
        f"**Total**: {len(result.plan.units)} units",
        f"**Completed**: {result.completed}",
        f"**Failed**: {result.failed}",
        f"**Success Rate**: {result.success_rate:.0%}",
        f"**Duration**: {result.total_duration_ms:.0f}ms\n",
    ]
    
    lines.append("## Unit Status\n")
    lines.append("| Unit | Description | Status |")
    lines.append("|------|------------|--------|")
    
    for unit in result.plan.units:
        icon = {
            "completed": "✅",
            "failed": "❌",
            "running": "🔄",
            "pending": "⏳",
            "skipped": "⏭️",
        }.get(unit.status.value, "•")
        lines.append(f"| {unit.id} | {unit.description[:40]} | {icon} {unit.status.value} |")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    plan = decompose_task("Refactor the authentication module to use JWT", count=5)
    print(f"Plan: {plan.task}")
    print(f"Units: {len(plan.units)}")
    for u in plan.units:
        print(f"  {u.id}: {u.description}")
    
    # 生成 worker 指令
    instructions = generate_worker_instructions(plan.units[0])
    print(f"\nWorker instructions: {len(instructions)} chars")
    
    # 执行
    result = execute_batch(plan)
    report = format_batch_status(result)
    print(f"\n{report}")
