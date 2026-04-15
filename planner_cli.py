# -*- coding: utf-8 -*-
"""
planner_cli.py - 任务规划器

来源: 顾庸t workspace_tools/planner_cli.py
参考: Claude Code Plan Agent + Hermes planning

功能:
  1. 分析任务，生成执行计划
  2. 计划步骤依赖关系
  3. 估算每步复杂度和耗时
  4. 检测循环依赖
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any
from enum import Enum


class StepStatus(Enum):
    PENDING = "pending"
    READY = "ready"  # dependencies met
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """计划步骤"""
    step_id: int
    description: str
    status: StepStatus = StepStatus.PENDING
    depends_on: List[int] = field(default_factory=list)  # 依赖的 step_id
    estimated_complexity: int = 1  # 1-5
    estimated_minutes: int = 5
    tools_needed: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    notes: str = ""


class ExecutionPlan:
    """执行计划"""
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        self._steps: Dict[int, PlanStep] = {}
        self._next_id = 1
    
    def add_step(self, description: str, depends_on: Optional[List[int]] = None,
                 complexity: int = 1, minutes: int = 5,
                 tools: Optional[List[str]] = None,
                 risks: Optional[List[str]] = None) -> PlanStep:
        """添加步骤"""
        step_id = self._next_id
        self._next_id += 1
        
        step = PlanStep(
            step_id=step_id,
            description=description,
            depends_on=depends_on or [],
            estimated_complexity=complexity,
            estimated_minutes=minutes,
            tools_needed=tools or [],
            risks=risks or [],
        )
        self._steps[step_id] = step
        return step
    
    def validate(self) -> Tuple[bool, List[str]]:
        """验证计划（检测循环依赖、缺失引用）"""
        errors = []
        
        for sid, step in self._steps.items():
            for dep in step.depends_on:
                if dep not in self._steps:
                    errors.append(f"Step {sid}: dependency {dep} not found")
        
        # 循环依赖检测（DFS）
        visited = set()
        in_stack = set()
        
        def has_cycle(node: int) -> bool:
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in self._steps.get(node, PlanStep(0,"")).depends_on:
                if has_cycle(dep):
                    return True
            in_stack.discard(node)
            return False
        
        for sid in self._steps:
            if has_cycle(sid):
                errors.append(f"Cycle detected involving step {sid}")
                break
        
        return len(errors) == 0, errors
    
    def get_ready_steps(self) -> List[PlanStep]:
        """获取可执行的步骤（依赖已满足）"""
        ready = []
        for step in self._steps.values():
            if step.status != StepStatus.PENDING:
                continue
            all_deps_done = all(
                self._steps[dep].status == StepStatus.DONE
                for dep in step.depends_on
                if dep in self._steps
            )
            if all_deps_done:
                ready.append(step)
        return sorted(ready, key=lambda s: s.step_id)
    
    def complete_step(self, step_id: int) -> Optional[PlanStep]:
        """标记步骤完成"""
        step = self._steps.get(step_id)
        if step:
            step.status = StepStatus.DONE
        return step
    
    def progress(self) -> Dict[str, Any]:
        """计划进度"""
        total = len(self._steps)
        done = sum(1 for s in self._steps.values() if s.status == StepStatus.DONE)
        total_minutes = sum(s.estimated_minutes for s in self._steps.values())
        done_minutes = sum(s.estimated_minutes for s in self._steps.values() if s.status == StepStatus.DONE)
        
        return {
            "task": self.task_name,
            "steps": f"{done}/{total}",
            "percent": round(done/total*100) if total else 0,
            "estimated_time": f"{done_minutes}/{total_minutes} min",
        }
    
    def to_markdown(self) -> str:
        """导出为 Markdown"""
        lines = [f"# Plan: {self.task_name}\n"]
        
        valid, errors = self.validate()
        if not valid:
            lines.append("## Validation Errors")
            for e in errors:
                lines.append(f"  - {e}")
            lines.append("")
        
        lines.append("## Steps\n")
        for step in sorted(self._steps.values(), key=lambda s: s.step_id):
            dep_str = f" (after: {step.depends_on})" if step.depends_on else ""
            status_icon = {"pending": "⬜", "ready": "🟡", "running": "🔵", 
                          "done": "✅", "skipped": "⏭️"}.get(step.status.value, "⬜")
            lines.append(f"{status_icon} **Step {step.step_id}**{dep_str}")
            lines.append(f"   {step.description}")
            if step.tools_needed:
                lines.append(f"   Tools: {', '.join(step.tools_needed)}")
            if step.risks:
                lines.append(f"   Risks: {', '.join(step.risks)}")
            lines.append(f"   Est: L{step.estimated_complexity} / {step.estimated_minutes}min")
            lines.append("")
        
        p = self.progress()
        lines.append(f"## Progress: {p['steps']} ({p['percent']}%) | Time: {p['estimated_time']}")
        
        return "\n".join(lines)


class PlannerCLI:
    """规划器 CLI"""
    
    def __init__(self):
        self._plans: Dict[str, ExecutionPlan] = {}
    
    def create_plan(self, task_name: str) -> ExecutionPlan:
        plan = ExecutionPlan(task_name)
        self._plans[task_name] = plan
        return plan
    
    def get_plan(self, task_name: str) -> Optional[ExecutionPlan]:
        return self._plans.get(task_name)
    
    def list_plans(self) -> List[str]:
        return list(self._plans.keys())


_planner: Optional[PlannerCLI] = None

def get_planner() -> PlannerCLI:
    global _planner
    if _planner is None:
        _planner = PlannerCLI()
    return _planner
