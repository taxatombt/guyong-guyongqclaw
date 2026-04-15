# -*- coding: utf-8 -*-
"""
task_board.py - 任务看板（看板式任务管理）

来源: 顾庸t workspace_tools/task_board.py
参考: Claude Code todo + Hermes task management

列: TODO / IN_PROGRESS / REVIEW / DONE / ARCHIVED

每个任务卡片包含:
  - title, description, priority, assignee, tags
  - created_at, updated_at, due_date
  - status 生命周期
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from enum import Enum
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
BOARD_FILE = WORKSPACE / ".task_board.json"


class TaskStatus(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    ARCHIVED = "archived"


class Priority(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Task:
    """任务卡片"""
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    due_date: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Task":
        d = dict(d)
        d["status"] = TaskStatus(d["status"])
        d["priority"] = Priority(d["priority"])
        return cls(**d)


class TaskBoard:
    """任务看板"""
    
    def __init__(self, file_path: Optional[Path] = None):
        self._file = file_path or BOARD_FILE
        self._tasks: Dict[str, Task] = {}
        self._next_id = 1
        self._load()
    
    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                self._tasks = {
                    tid: Task.from_dict(td) for tid, td in data.get("tasks", {}).items()
                }
                self._next_id = data.get("next_id", len(self._tasks) + 1)
            except (json.JSONDecodeError, KeyError):
                self._tasks = {}
    
    def _save(self) -> None:
        data = {
            "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
            "next_id": self._next_id,
        }
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def create(self, title: str, description: str = "", 
               priority = Priority.MEDIUM, tags: Optional[List[str]] = None,
               due_date: Optional[str] = None) -> Task:
        """创建任务"""
        task_id = f"TASK-{self._next_id:03d}"
        self._next_id += 1
        
        # Accept int or Priority enum
        if isinstance(priority, int):
            priority = Priority(priority)
        
        task = Task(
            id=task_id,
            title=title,
            description=description,
            priority=priority,
            tags=tags or [],
            due_date=due_date,
        )
        self._tasks[task_id] = task
        self._save()
        return task
    
    def move(self, task_id: str, new_status: TaskStatus) -> Optional[Task]:
        """移动任务到新列"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.status = new_status
        task.updated_at = time.time()
        self._save()
        return task
    
    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        """更新任务字段"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.updated_at = time.time()
        self._save()
        return task
    
    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)
    
    def list_by_status(self, status: TaskStatus) -> List[Task]:
        """列出指定状态的任务"""
        return [t for t in self._tasks.values() if t.status == status]
    
    def list_all(self, include_archived: bool = False) -> List[Task]:
        """列出所有任务"""
        tasks = [t for t in self._tasks.values()]
        if not include_archived:
            tasks = [t for t in tasks if t.status != TaskStatus.ARCHIVED]
        return sorted(tasks, key=lambda t: (t.priority.value, -t.created_at), reverse=True)
    
    def board_view(self) -> Dict[str, List[Dict[str, Any]]]:
        """看板视图"""
        view = {}
        for status in TaskStatus:
            tasks = self.list_by_status(status)
            if tasks or status != TaskStatus.ARCHIVED:
                view[status.value] = [
                    {"id": t.id, "title": t.title, "priority": t.priority.name, "tags": t.tags}
                    for t in sorted(tasks, key=lambda x: x.priority.value, reverse=True)
                ]
        return view
    
    def summary(self) -> str:
        """看板摘要"""
        lines = ["# Task Board Summary"]
        for status in TaskStatus:
            tasks = self.list_by_status(status)
            if tasks:
                lines.append(f"\n## {status.value.upper()} ({len(tasks)})")
                for t in sorted(tasks, key=lambda x: x.priority.value, reverse=True):
                    due = f" [due:{t.due_date}]" if t.due_date else ""
                    lines.append(f"  {t.id} [{t.priority.name}] {t.title}{due}")
        return "\n".join(lines)


_board: Optional[TaskBoard] = None

def get_task_board() -> TaskBoard:
    global _board
    if _board is None:
        _board = TaskBoard()
    return _board
