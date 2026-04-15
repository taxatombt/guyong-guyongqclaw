# -*- coding: utf-8 -*-
"""
project_isolator.py - 项目级隔离

来源: 顾庸t workspace_tools/project_isolator.py
参考: ECC instinct project isolation (git remote hash)

功能:
  基于项目路径隔离配置、记忆、经验。
  不同项目的 evolver/instinct/memory 互不污染。
  
  隔离键: 项目路径的 hash
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path


@dataclass
class ProjectContext:
    """项目上下文"""
    project_path: str
    project_hash: str
    config: Dict[str, Any] = field(default_factory=dict)
    memory_keys: list = field(default_factory=list)
    evolver_rules: list = field(default_factory=list)
    instincts: list = field(default_factory=list)


class ProjectIsolator:
    """项目隔离器"""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self._storage = storage_dir or Path.home() / ".qclaw" / "workspace" / ".project_isolation"
        self._storage.mkdir(parents=True, exist_ok=True)
        self._contexts: Dict[str, ProjectContext] = {}
    
    @staticmethod
    def compute_hash(project_path: str) -> str:
        """计算项目路径 hash（8位）"""
        normalized = str(Path(project_path).resolve())
        return hashlib.sha256(normalized.encode()).hexdigest()[:8]
    
    def get_context(self, project_path: str) -> ProjectContext:
        """获取项目上下文（自动创建）"""
        p_hash = self.compute_hash(project_path)
        
        if p_hash in self._contexts:
            return self._contexts[p_hash]
        
        # 尝试加载
        context_file = self._storage / f"{p_hash}.json"
        if context_file.exists():
            try:
                data = json.loads(context_file.read_text(encoding="utf-8"))
                ctx = ProjectContext(
                    project_path=data.get("project_path", project_path),
                    project_hash=p_hash,
                    config=data.get("config", {}),
                    memory_keys=data.get("memory_keys", []),
                    evolver_rules=data.get("evolver_rules", []),
                    instincts=data.get("instincts", []),
                )
            except (json.JSONDecodeError, TypeError):
                ctx = ProjectContext(project_path=project_path, project_hash=p_hash)
        else:
            ctx = ProjectContext(project_path=project_path, project_hash=p_hash)
        
        self._contexts[p_hash] = ctx
        return ctx
    
    def save_context(self, project_path: str) -> bool:
        """保存项目上下文"""
        ctx = self.get_context(project_path)
        context_file = self._storage / f"{ctx.project_hash}.json"
        
        data = {
            "project_path": ctx.project_path,
            "project_hash": ctx.project_hash,
            "config": ctx.config,
            "memory_keys": ctx.memory_keys,
            "evolver_rules": ctx.evolver_rules,
            "instincts": ctx.instincts,
        }
        
        try:
            context_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False
    
    def list_projects(self) -> list:
        """列出所有已隔离的项目"""
        projects = []
        for f in self._storage.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                projects.append({
                    "path": data.get("project_path", "?"),
                    "hash": f.stem,
                    "rules": len(data.get("evolver_rules", [])),
                })
            except (json.JSONDecodeError, TypeError):
                pass
        return projects


_isolator: Optional[ProjectIsolator] = None

def get_project_isolator() -> ProjectIsolator:
    global _isolator
    if _isolator is None:
        _isolator = ProjectIsolator()
    return _isolator
