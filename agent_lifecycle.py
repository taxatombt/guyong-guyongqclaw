# -*- coding: utf-8 -*-
"""
agent_lifecycle.py - 任务5阶段生命周期管理

来源: 顾庸t workspace_tools/agent_lifecycle.py
参考: Claude Code agent lifecycle + Hermes delegate lifecycle

5阶段:
  1. INIT       — 任务接收，复杂度评估
  2. PLANNING   — 制定计划，拆解步骤
  3. EXECUTING  — 执行步骤，工具调用
  4. REVIEWING  — 结果验证，质量检查
  5. COMPLETED  — 结果输出，进化记录

每阶段有明确的进入/退出条件。
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum


class LifecyclePhase(Enum):
    INIT = "init"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Step:
    """单个执行步骤"""
    description: str
    status: str = "pending"  # pending / running / done / failed / skipped
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TaskLifecycle:
    """任务生命周期"""
    task_id: str
    description: str
    phase: LifecyclePhase = LifecyclePhase.INIT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    steps: List[Step] = field(default_factory=list)
    complexity_level: int = 0
    plan: str = ""
    result: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── 生命周期管理器 ──────────────────────────────────

class LifecycleManager:
    """任务生命周期管理"""
    
    def __init__(self):
        self._tasks: Dict[str, TaskLifecycle] = {}
    
    def create(self, task_id: str, description: str, 
               complexity_level: int = 0) -> TaskLifecycle:
        """创建新任务"""
        task = TaskLifecycle(
            task_id=task_id,
            description=description,
            complexity_level=complexity_level,
        )
        self._tasks[task_id] = task
        return task
    
    def transition(self, task_id: str, new_phase: LifecyclePhase) -> TaskLifecycle:
        """阶段转换"""
        task = self._get(task_id)
        
        # 验证转换合法性
        valid = self._valid_transition(task.phase, new_phase)
        if not valid:
            raise ValueError(
                f"Invalid transition: {task.phase.value} → {new_phase.value}"
            )
        
        task.phase = new_phase
        task.updated_at = time.time()
        return task
    
    def _valid_transition(self, current: LifecyclePhase, 
                           target: LifecyclePhase) -> bool:
        """验证阶段转换是否合法"""
        transitions = {
            LifecyclePhase.INIT: {LifecyclePhase.PLANNING, LifecyclePhase.FAILED},
            LifecyclePhase.PLANNING: {LifecyclePhase.EXECUTING, LifecyclePhase.FAILED},
            LifecyclePhase.EXECUTING: {LifecyclePhase.REVIEWING, 
                                        LifecyclePhase.COMPLETED, LifecyclePhase.FAILED},
            LifecyclePhase.REVIEWING: {LifecyclePhase.COMPLETED, 
                                        LifecyclePhase.EXECUTING, LifecyclePhase.FAILED},
            LifecyclePhase.COMPLETED: set(),
            LifecyclePhase.FAILED: set(),
        }
        return target in transitions.get(current, set())
    
    def add_step(self, task_id: str, description: str) -> Step:
        """添加执行步骤"""
        task = self._get(task_id)
        step = Step(description=description)
        task.steps.append(step)
        task.updated_at = time.time()
        return step
    
    def start_step(self, task_id: str, step_index: int) -> Step:
        """开始执行步骤"""
        task = self._get(task_id)
        step = task.steps[step_index]
        step.status = "running"
        step.started_at = time.time()
        task.updated_at = time.time()
        return step
    
    def complete_step(self, task_id: str, step_index: int, 
                       result: Optional[str] = None) -> Step:
        """完成步骤"""
        task = self._get(task_id)
        step = task.steps[step_index]
        step.status = "done"
        step.finished_at = time.time()
        step.result = result
        task.updated_at = time.time()
        return step
    
    def fail_step(self, task_id: str, step_index: int, 
                   error: str) -> Step:
        """步骤失败"""
        task = self._get(task_id)
        step = task.steps[step_index]
        step.status = "failed"
        step.finished_at = time.time()
        step.error = error
        task.updated_at = time.time()
        return step
    
    def set_plan(self, task_id: str, plan: str) -> None:
        """设置执行计划"""
        task = self._get(task_id)
        task.plan = plan
        task.updated_at = time.time()
    
    def set_result(self, task_id: str, result: str) -> None:
        """设置最终结果"""
        task = self._get(task_id)
        task.result = result
        task.updated_at = time.time()
    
    def _get(self, task_id: str) -> TaskLifecycle:
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        return self._tasks[task_id]
    
    def get(self, task_id: str) -> Optional[TaskLifecycle]:
        """安全获取任务"""
        return self._tasks.get(task_id)
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务摘要"""
        return [
            {
                "task_id": t.task_id,
                "phase": t.phase.value,
                "steps": len(t.steps),
                "complexity": t.complexity_level,
                "description": t.description[:50],
            }
            for t in sorted(self._tasks.values(), key=lambda x: x.created_at, reverse=True)
        ]
    
    def progress(self, task_id: str) -> Dict[str, Any]:
        """任务进度"""
        task = self._get(task_id)
        total = len(task.steps)
        done = sum(1 for s in task.steps if s.status == "done")
        failed = sum(1 for s in task.steps if s.status == "failed")
        running = sum(1 for s in task.steps if s.status == "running")
        
        return {
            "task_id": task_id,
            "phase": task.phase.value,
            "progress": f"{done}/{total}",
            "percent": round(done / total * 100) if total > 0 else 0,
            "done": done,
            "running": running,
            "failed": failed,
            "pending": total - done - running - failed,
        }


_manager: Optional[LifecycleManager] = None

def get_lifecycle_manager() -> LifecycleManager:
    global _manager
    if _manager is None:
        _manager = LifecycleManager()
    return _manager
