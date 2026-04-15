# -*- coding: utf-8 -*-
"""
sessions_cli.py - Session 管理命令行工具

来源: 顾庸t workspace_tools/sessions_cli.py
参考: Claude Code sessions + Hermes session management

功能:
  list    — 列出活跃 session
  info    — 查看单个 session 详情
  search  — 搜索 session 内容
  export  — 导出 session 为 markdown
  diff    — 比较两个 session
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime


@dataclass
class SessionInfo:
    """Session 信息"""
    session_id: str
    created_at: float
    updated_at: float
    message_count: int
    model: str = ""
    status: str = "active"  # active / completed / failed
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600
    
    @property
    def age_str(self) -> str:
        hours = self.age_hours
        if hours < 1:
            return f"{int(hours*60)}m ago"
        elif hours < 24:
            return f"{int(hours)}h ago"
        else:
            return f"{int(hours/24)}d ago"


class SessionsManager:
    """Session 管理"""
    
    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
    
    def register(self, session_id: str, model: str = "",
                 tags: Optional[List[str]] = None) -> SessionInfo:
        """注册新 session"""
        now = time.time()
        session = SessionInfo(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            message_count=0,
            model=model,
            tags=tags or [],
        )
        self._sessions[session_id] = session
        return session
    
    def touch(self, session_id: str) -> Optional[SessionInfo]:
        """更新 session 活跃时间"""
        s = self._sessions.get(session_id)
        if s:
            s.updated_at = time.time()
        return s
    
    def increment_messages(self, session_id: str) -> int:
        """增加消息计数"""
        s = self._sessions.get(session_id)
        if s:
            s.message_count += 1
            return s.message_count
        return 0
    
    def get(self, session_id: str) -> Optional[SessionInfo]:
        return self._sessions.get(session_id)
    
    def list_active(self, hours: float = 24) -> List[SessionInfo]:
        """列出最近N小时内活跃的 session"""
        cutoff = time.time() - hours * 3600
        return [
            s for s in self._sessions.values()
            if s.updated_at >= cutoff
        ]
    
    def list_all(self) -> List[SessionInfo]:
        return sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)
    
    def close(self, session_id: str, status: str = "completed") -> Optional[SessionInfo]:
        """关闭 session"""
        s = self._sessions.get(session_id)
        if s:
            s.status = status
            s.updated_at = time.time()
        return s
    
    def summary(self, hours: float = 24) -> str:
        """生成 session 摘要"""
        active = self.list_active(hours)
        total = len(self._sessions)
        
        lines = [
            f"# Sessions Summary (last {int(hours)}h)",
            f"Total: {total} | Active: {len(active)}",
        ]
        
        for s in active:
            lines.append(
                f"  {s.session_id[:12]}... | {s.age_str} | "
                f"{s.message_count} msgs | {s.model or 'unknown'}"
            )
        
        return "\n".join(lines)
    
    def search_sessions(self, query: str) -> List[str]:
        """搜索 session（基于标签和元数据）"""
        q = query.lower()
        results = []
        for sid, s in self._sessions.items():
            if q in sid.lower():
                results.append(sid)
            elif any(q in t.lower() for t in s.tags):
                results.append(sid)
            elif q in s.model.lower():
                results.append(sid)
        return results


_manager: Optional[SessionsManager] = None

def get_sessions_manager() -> SessionsManager:
    global _manager
    if _manager is None:
        _manager = SessionsManager()
    return _manager
