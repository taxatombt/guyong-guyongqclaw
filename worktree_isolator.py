# -*- coding: utf-8 -*-
"""
worktree_isolator.py - Git Worktree 隔离执行

来源: 顾庸t workspace_tools/worktree_isolator.py
参考: Claude Code /batch worktree isolation

功能:
  1. 在独立 git worktree 中执行任务
  2. 隔离文件系统变更
  3. 执行完成后合并或丢弃

  注意: 需要 git 仓库支持。当前 workspace 没有 .git，
  本模块定义接口，实际使用时需要在有 git 仓库的环境中。
"""

import subprocess
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
from enum import Enum


class WorktreeStatus(Enum):
    CREATED = "created"
    EXECUTING = "executing"
    MERGED = "merged"
    DISCARDED = "discarded"
    ERROR = "error"


@dataclass
class Worktree:
    """Worktree 实例"""
    name: str
    path: Path
    branch: str
    status: WorktreeStatus = WorktreeStatus.CREATED
    original_branch: str = ""
    changes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=0)
    finished_at: float = 0


class WorktreeIsolator:
    """Worktree 隔离器"""
    
    def __init__(self, repo_path: Optional[Path] = None):
        self._repo = repo_path
        self._worktrees: Dict[str, Worktree] = {}
    
    def _run_git(self, *args) -> subprocess.CompletedProcess:
        if not self._repo:
            return subprocess.CompletedProcess(args=[], returncode=1, 
                                               stderr="No repo configured")
        return subprocess.run(
            ["git", "-C", str(self._repo)] + list(args),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        )
    
    def _is_git_repo(self) -> bool:
        if not self._repo:
            return False
        result = self._run_git("rev-parse", "--is-inside-work-tree")
        return result.returncode == 0
    
    def create_worktree(self, name: str, base_branch: Optional[str] = None) -> Optional[Worktree]:
        """创建隔离 worktree"""
        if not self._is_git_repo():
            return None
        
        branch = f"worktree/{name}"
        
        # 获取当前分支
        current = self._run_git("branch", "--show-current")
        original_branch = current.stdout.strip() if current.returncode == 0 else "main"
        base = base_branch or original_branch
        
        # 创建 worktree
        result = self._run_git("worktree", "add", f".worktrees/{name}", "-b", branch, base)
        if result.returncode != 0:
            return None
        
        import time
        wt_path = self._repo / ".worktrees" / name
        
        worktree = Worktree(
            name=name,
            path=wt_path,
            branch=branch,
            status=WorktreeStatus.CREATED,
            original_branch=original_branch,
            created_at=time.time(),
        )
        self._worktrees[name] = worktree
        return worktree
    
    def list_worktrees(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": wt.name,
                "branch": wt.branch,
                "path": str(wt.path),
                "status": wt.status.value,
            }
            for wt in self._worktrees.values()
        ]
    
    def remove_worktree(self, name: str, discard: bool = True) -> bool:
        """移除 worktree"""
        wt = self._worktrees.get(name)
        if not wt:
            return False
        
        import time
        # 移除 worktree
        result = self._run_git("worktree", "remove", str(wt.path), "--force")
        
        # 删除分支
        self._run_git("branch", "-D", wt.branch)
        
        wt.status = WorktreeStatus.DISCARDED if discard else WorktreeStatus.MERGED
        wt.finished_at = time.time()
        return result.returncode == 0
    
    def get_worktree_path(self, name: str) -> Optional[Path]:
        wt = self._worktrees.get(name)
        return wt.path if wt else None


_isolator: Optional[WorktreeIsolator] = None

def get_worktree_isolator() -> WorktreeIsolator:
    global _isolator
    if _isolator is None:
        _isolator = WorktreeIsolator()
    return _isolator
