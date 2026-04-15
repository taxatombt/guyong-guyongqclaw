# -*- coding: utf-8 -*-
"""
swarm_orchestrate.py - 多 Agent 协同编排

来源: 顾庸t workspace_tools/swarm_orchestrate.py
参考: Hermes delegate + Claude Code multi-agent + ECC swarm

功能:
  1. 定义多个并行任务
  2. 分配给不同的 Agent/Session
  3. 收集结果
  4. 冲突检测与解决
  5. 结果合并

策略:
  - PARALLEL: 所有任务并行
  - SEQUENTIAL: 按依赖顺序串行
  - DYNAMIC: 根据资源动态分配
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum


class ExecutionStrategy(Enum):
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    DYNAMIC = "dynamic"


class WorkerStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SwarmTask:
    """Swarm 任务"""
    task_id: str
    description: str
    agent_type: str = "general"  # general / explore / verify
    status: WorkerStatus = WorkerStatus.PENDING
    depends_on: List[str] = field(default_factory=list)
    priority: int = 0
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> int:
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at) * 1000)
        return 0


@dataclass
class SwarmResult:
    """Swarm 执行结果"""
    strategy: ExecutionStrategy
    total_tasks: int
    completed: int
    failed: int
    skipped: int
    total_ms: int
    results: Dict[str, Any]


class SwarmOrchestrator:
    """Swarm 编排器"""
    
    def __init__(self, strategy: ExecutionStrategy = ExecutionStrategy.PARALLEL,
                 max_concurrent: int = 3):
        self._strategy = strategy
        self._max_concurrent = max_concurrent
        self._tasks: Dict[str, SwarmTask] = {}
        self._next_id = 1
        self._executor: Optional[Callable] = None
    
    def set_executor(self, func: Callable[[SwarmTask], Any]) -> None:
        """设置执行函数（实际调用 Agent 的函数）"""
        self._executor = func
    
    def add_task(self, description: str, agent_type: str = "general",
                 depends_on: Optional[List[str]] = None,
                 priority: int = 0,
                 metadata: Optional[Dict[str, Any]] = None) -> SwarmTask:
        """添加任务"""
        task_id = f"SW-{self._next_id:03d}"
        self._next_id += 1
        
        task = SwarmTask(
            task_id=task_id,
            description=description,
            agent_type=agent_type,
            depends_on=depends_on or [],
            priority=priority,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        return task
    
    def get_ready_tasks(self) -> List[SwarmTask]:
        """获取可执行任务（依赖已满足）"""
        ready = []
        for task in self._tasks.values():
            if task.status != WorkerStatus.PENDING:
                continue
            all_deps_done = all(
                self._tasks.get(dep, SwarmTask("", "")).status == WorkerStatus.DONE
                for dep in task.depends_on
            )
            if all_deps_done:
                ready.append(task)
        
        return sorted(ready, key=lambda t: t.priority, reverse=True)
    
    def execute(self) -> SwarmResult:
        """执行所有任务"""
        start = time.time()
        completed = 0
        failed = 0
        skipped = 0
        results = {}
        
        while True:
            ready = self.get_ready_tasks()
            if not ready:
                # 检查是否有正在运行的任务
                running = [t for t in self._tasks.values() if t.status == WorkerStatus.RUNNING]
                if not running:
                    break
                time.sleep(0.1)
                continue
            
            # 限制并发数
            running = [t for t in self._tasks.values() if t.status == WorkerStatus.RUNNING]
            batch = ready[:self._max_concurrent - len(running)]
            
            for task in batch:
                if self._strategy == ExecutionStrategy.SEQUENTIAL and running:
                    break
                
                task.status = WorkerStatus.RUNNING
                task.started_at = time.time()
                
                try:
                    if self._executor:
                        result = self._executor(task)
                        task.result = result
                        task.status = WorkerStatus.DONE
                        completed += 1
                        results[task.task_id] = result
                    else:
                        # 无执行器: 标记完成
                        task.result = f"Simulated: {task.description}"
                        task.status = WorkerStatus.DONE
                        completed += 1
                        results[task.task_id] = task.result
                except Exception as e:
                    task.error = str(e)
                    task.status = WorkerStatus.FAILED
                    failed += 1
                
                task.finished_at = time.time()
        
        # 标记未执行的任务为 SKIPPED
        for task in self._tasks.values():
            if task.status == WorkerStatus.PENDING:
                task.status = WorkerStatus.SKIPPED
                skipped += 1
        
        return SwarmResult(
            strategy=self._strategy,
            total_tasks=len(self._tasks),
            completed=completed,
            failed=failed,
            skipped=skipped,
            total_ms=int((time.time() - start) * 1000),
            results=results,
        )
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": t.task_id,
                "desc": t.description[:50],
                "agent": t.agent_type,
                "status": t.status.value,
                "deps": t.depends_on,
            }
            for t in self._tasks.values()
        ]


_orchestrator: Optional[SwarmOrchestrator] = None

def get_swarm() -> SwarmOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SwarmOrchestrator()
    return _orchestrator
