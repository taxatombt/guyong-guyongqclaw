# -*- coding: utf-8 -*-
"""
session_vault.py — Session 外置持久化（Anthropic Managed Agents 落地）

对应 CMA 的 Session 层：append-only 事件日志，Harness 通过 getEvents() 按需读取。

核心设计：
- 事件持久化到 JSONL 文件（append-only，不可修改）
- getEvents(session_id, from_index) 按需检索事件切片
- wake(session_id) 从 Session 日志恢复 Harness 执行状态
- 事件压缩：超过阈值自动 summarize 旧事件

与 CMA 对照：
  CMA: session.events.send() / session.events.list() / session.events.stream()
  qclaw: emit_event() / get_events() / stream_events()
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Iterator
from datetime import datetime

log = logging.getLogger("qclaw.session_vault")

# ─── 存储路径 ─────────────────────────────────────────────

SESSION_DIR = Path(r"C:\Users\yiseg\.qclaw\sessions_vault")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


# ─── 事件类型 ─────────────────────────────────────────────

class SessionEventType:
    """与 agents/event_bus.py EventType 对齐的 Session 级事件"""
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DECISION = "decision"          # HITL gate（对应 CMA decide/escalate）
    STATE_SNAPSHOT = "state_snapshot"  # Harness 状态快照（用于 wake 恢复）
    CONTEXT_COMPACTED = "context_compacted"
    ERROR = "error"
    CUSTOM = "custom"


# ─── 事件数据结构 ─────────────────────────────────────────

@dataclass
class SessionEvent:
    """Session 事件（append-only，不可修改）"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str = ""
    event_type: str = SessionEventType.CUSTOM
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SessionEvent":
        return cls(
            event_id=d.get("event_id", ""),
            session_id=d.get("session_id", ""),
            event_type=d.get("event_type", SessionEventType.CUSTOM),
            timestamp=d.get("timestamp", ""),
            data=d.get("data", {}),
        )


# ─── Session 状态快照（用于 wake 恢复）───────────────────

@dataclass
class HarnessSnapshot:
    """Harness 状态快照——wake() 时从此恢复"""
    session_id: str = ""
    last_event_index: int = 0
    task_status: str = "pending"
    current_phase: str = ""          # planning / exploring / verifying / executing
    plan_output: str = ""
    explore_output: str = ""
    pending_tools: List[str] = field(default_factory=list)
    rollback_available: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Session Vault 核心 ───────────────────────────────────

class SessionVault:
    """
    Session 外置持久化存储
    
    对应 CMA 的 Session 接口：
    - emitEvent(id, event)  → emit_event()
    - getEvents()           → get_events()
    - wake(sessionId)       → wake()
    
    存储格式：{SESSION_DIR}/{session_id}.jsonl
    每行一个 SessionEvent 的 JSON 序列化。
    """

    def __init__(self, session_dir: Path = SESSION_DIR):
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        # 内存缓存（最近访问的 session）
        self._cache: Dict[str, List[SessionEvent]] = {}

    # ─── 事件写入 ─────────────────────────────────────────

    def emit_event(self, session_id: str, event_type: str,
                   data: Dict[str, Any] = None) -> SessionEvent:
        """
        追加写入事件（对应 CMA: session.events.send()）
        
        append-only：事件一旦写入不可修改。
        """
        event = SessionEvent(
            session_id=session_id,
            event_type=event_type,
            data=data or {},
        )
        self._append_to_file(session_id, event)
        # 更新缓存
        if session_id in self._cache:
            self._cache[session_id].append(event)
        return event

    def emit_snapshot(self, session_id: str, snapshot: HarnessSnapshot) -> SessionEvent:
        """
        写入 Harness 状态快照（用于崩溃后 wake 恢复）
        """
        return self.emit_event(
            session_id,
            SessionEventType.STATE_SNAPSHOT,
            asdict(snapshot),
        )

    # ─── 事件读取 ─────────────────────────────────────────

    def get_events(self, session_id: str, from_index: int = 0,
                   event_type: str = None) -> List[SessionEvent]:
        """
        检索事件切片（对应 CMA: session.events.list()）
        
        Args:
            session_id: 会话 ID
            from_index: 从第几条事件开始读取
            event_type: 可选，只返回特定类型的事件
        """
        events = self._read_all(session_id)
        result = events[from_index:]
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        return result

    def stream_events(self, session_id: str, from_index: int = 0) -> Iterator[SessionEvent]:
        """
        流式读取事件（对应 CMA: session.events.stream()）
        
        用于实时监控 Session 事件流。
        """
        events = self._read_all(session_id)
        for event in events[from_index:]:
            yield event

    # ─── Harness 恢复 ─────────────────────────────────────

    def wake(self, session_id: str) -> Optional[HarnessSnapshot]:
        """
        从 Session 日志恢复 Harness 状态（对应 CMA: wake(sessionId)）
        
        找到最后一个 STATE_SNAPSHOT 事件，反序列化为 HarnessSnapshot。
        """
        snapshots = self.get_events(session_id, event_type=SessionEventType.STATE_SNAPSHOT)
        if not snapshots:
            log.warning(f"No snapshot found for session {session_id}")
            return None
        last_snapshot = snapshots[-1]
        return HarnessSnapshot(**last_snapshot.data)

    # ─── Session 管理 ─────────────────────────────────────

    def create_session(self, agent_id: str = "", metadata: Dict = None) -> str:
        """创建新 Session，返回 session_id"""
        session_id = f"ses_{uuid.uuid4().hex[:8]}"
        self.emit_event(session_id, SessionEventType.CUSTOM, {
            "action": "session_created",
            "agent_id": agent_id,
            "metadata": metadata or {},
        })
        return session_id

    def list_sessions(self) -> List[str]:
        """列出所有 Session ID"""
        return [p.stem for p in self.session_dir.glob("*.jsonl")]

    def session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 统计信息"""
        events = self._read_all(session_id)
        type_counts = {}
        for e in events:
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1
        return {
            "session_id": session_id,
            "total_events": len(events),
            "type_counts": type_counts,
            "first_event": events[0].timestamp if events else None,
            "last_event": events[-1].timestamp if events else None,
        }

    # ─── 内部方法 ─────────────────────────────────────────

    def _session_file(self, session_id: str) -> Path:
        return self.session_dir / f"{session_id}.jsonl"

    def _append_to_file(self, session_id: str, event: SessionEvent) -> None:
        """追加写入单条事件到 JSONL 文件"""
        filepath = self._session_file(session_id)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def _read_all(self, session_id: str) -> List[SessionEvent]:
        """读取 Session 的全部事件（带缓存）"""
        if session_id in self._cache:
            return self._cache[session_id]
        filepath = self._session_file(session_id)
        if not filepath.exists():
            return []
        events = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(SessionEvent.from_dict(json.loads(line)))
                except json.JSONDecodeError:
                    log.warning(f"Corrupt event in {session_id}: {line[:80]}")
        self._cache[session_id] = events
        return events


# ─── 便捷函数 ─────────────────────────────────────────────

_vault: Optional[SessionVault] = None

def get_vault() -> SessionVault:
    """获取全局 SessionVault 实例"""
    global _vault
    if _vault is None:
        _vault = SessionVault()
    return _vault


def emit(session_id: str, event_type: str, data: Dict = None) -> SessionEvent:
    """便捷函数：写入事件"""
    return get_vault().emit_event(session_id, event_type, data)


def get(session_id: str, from_index: int = 0) -> List[SessionEvent]:
    """便捷函数：读取事件"""
    return get_vault().get_events(session_id, from_index)


def wake(session_id: str) -> Optional[HarnessSnapshot]:
    """便捷函数：恢复 Harness"""
    return get_vault().wake(session_id)
