# -*- coding: utf-8 -*-
"""
query_state.py - 会话状态查询

来源: 顾庸t workspace_tools/query_state.py
参考: Hermes query_state + Claude Code session state

功能:
  1. 记录和查询会话级状态变量
  2. 状态作用域: session / global / task
  3. 状态版本控制（可回滚）
  4. 状态变更日志
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class Scope(Enum):
    SESSION = "session"
    GLOBAL = "global"
    TASK = "task"


@dataclass
class StateEntry:
    """状态条目"""
    key: str
    value: Any
    scope: Scope
    updated_at: float = field(default_factory=time.time)
    updated_by: str = ""
    version: int = 1


@dataclass
class StateChange:
    """状态变更记录"""
    key: str
    old_value: Any
    new_value: Any
    scope: Scope
    timestamp: float = field(default_factory=time.time)
    changed_by: str = ""


class StateManager:
    """状态管理器"""
    
    def __init__(self):
        self._states: Dict[str, Dict[str, StateEntry]] = {
            Scope.SESSION.value: {},
            Scope.GLOBAL.value: {},
            Scope.TASK.value: {},
        }
        self._log: List[StateChange] = []
    
    def set(self, key: str, value: Any, scope: Scope = Scope.SESSION,
            changed_by: str = "") -> StateEntry:
        """设置状态"""
        scope_map = self._states[scope.value]
        
        old_value = None
        if key in scope_map:
            old_value = scope_map[key].value
            version = scope_map[key].version + 1
        else:
            version = 1
        
        entry = StateEntry(
            key=key,
            value=value,
            scope=scope,
            updated_at=time.time(),
            updated_by=changed_by,
            version=version,
        )
        scope_map[key] = entry
        
        self._log.append(StateChange(
            key=key,
            old_value=old_value,
            new_value=value,
            scope=scope,
            changed_by=changed_by,
        ))
        
        return entry
    
    def get(self, key: str, scope: Scope = Scope.SESSION, 
            default: Any = None) -> Any:
        """获取状态"""
        scope_map = self._states[scope.value]
        entry = scope_map.get(key)
        return entry.value if entry else default
    
    def delete(self, key: str, scope: Scope = Scope.SESSION) -> bool:
        """删除状态"""
        scope_map = self._states[scope.value]
        if key in scope_map:
            old = scope_map.pop(key)
            self._log.append(StateChange(
                key=key, old_value=old.value, new_value=None,
                scope=scope, changed_by="delete",
            ))
            return True
        return False
    
    def list_keys(self, scope: Optional[Scope] = None) -> Dict[str, Dict[str, Any]]:
        """列出状态键"""
        result = {}
        scopes = [scope] if scope else list(Scope)
        for s in scopes:
            scope_map = self._states[s.value]
            if scope_map:
                result[s.value] = {
                    k: {"value": str(v.value)[:50], "version": v.version, "age_h": round((time.time()-v.updated_at)/3600,1)}
                    for k, v in scope_map.items()
                }
        return result
    
    def changes(self, key: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """查询变更日志"""
        entries = self._log
        if key:
            entries = [e for e in entries if e.key == key]
        entries = entries[-limit:]
        return [
            {
                "key": e.key,
                "old": str(e.old_value)[:30] if e.old_value else "None",
                "new": str(e.new_value)[:30] if e.new_value else "None",
                "scope": e.scope.value,
                "by": e.changed_by,
            }
            for e in entries
        ]
    
    def clear_scope(self, scope: Scope) -> int:
        """清空作用域"""
        count = len(self._states[scope.value])
        self._states[scope.value] = {}
        return count
    
    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """导出快照"""
        return {
            scope: {
                k: {"value": v.value, "version": v.version}
                for k, v in entries.items()
            }
            for scope, entries in self._states.items()
            if entries
        }


_state: Optional[StateManager] = None

def get_state_manager() -> StateManager:
    global _state
    if _state is None:
        _state = StateManager()
    return _state
