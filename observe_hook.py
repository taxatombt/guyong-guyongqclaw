# -*- coding: utf-8 -*-
"""
observe_hook.py - 观察模式 Hook（无干预监控）

来源: 顾庸t workspace_tools/observe_hook.py
参考: ECC observe_hook + Hermes PreToolUse/PostToolUse

功能:
  记录所有工具调用，不干预，只观察。
  用于:
  1. 行为分析（哪些工具最常用）
  2. 异常检测（不寻常的调用模式）
  3. 使用统计（每日/每周报告）
  4. 合规审计
"""

import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
from collections import Counter

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
OBSERVE_LOG = WORKSPACE / ".observe_hook_log.jsonl"


@dataclass
class ToolCall:
    """工具调用记录"""
    tool_name: str
    action: str  # call / result / error
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None
    input_summary: str = ""
    output_summary: str = ""
    error: str = ""
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ObserveHook:
    """观察模式 Hook"""
    
    def __init__(self, log_path: Optional[Path] = None):
        self._log_path = log_path or OBSERVE_LOG
        self._calls: List[ToolCall] = []
        self._loaded = False
    
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._log_path.exists():
            try:
                for line in self._log_path.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        d = json.loads(line)
                        self._calls.append(ToolCall(**d))
            except (json.JSONDecodeError, TypeError):
                pass
    
    def record(self, tool_name: str, action: str = "call",
               duration_ms: Optional[float] = None,
               input_summary: str = "", output_summary: str = "",
               error: str = "", session_id: str = "",
               metadata: Optional[Dict[str, Any]] = None) -> ToolCall:
        """记录工具调用"""
        call = ToolCall(
            tool_name=tool_name,
            action=action,
            duration_ms=duration_ms,
            input_summary=input_summary[:200],
            output_summary=output_summary[:200],
            error=error,
            session_id=session_id,
            metadata=metadata or {},
        )
        self._calls.append(call)
        
        # 追加到日志文件
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "tool_name": call.tool_name,
                    "action": call.action,
                    "timestamp": call.timestamp,
                    "duration_ms": call.duration_ms,
                    "input_summary": call.input_summary,
                    "output_summary": call.output_summary,
                    "error": call.error,
                    "session_id": call.session_id,
                    "metadata": call.metadata,
                }, ensure_ascii=False) + "\n")
        except OSError:
            pass
        
        return call
    
    def stats(self, hours: float = 24) -> Dict[str, Any]:
        """使用统计"""
        self._load()
        cutoff = time.time() - hours * 3600
        recent = [c for c in self._calls if c.timestamp >= cutoff]
        
        if not recent:
            return {"period_hours": hours, "total_calls": 0}
        
        tool_counts = Counter(c.tool_name for c in recent)
        action_counts = Counter(c.action for c in recent)
        error_count = sum(1 for c in recent if c.error)
        
        # 平均耗时
        durations = [c.duration_ms for c in recent if c.duration_ms is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "period_hours": hours,
            "total_calls": len(recent),
            "unique_tools": len(tool_counts),
            "top_tools": tool_counts.most_common(10),
            "actions": dict(action_counts),
            "errors": error_count,
            "avg_duration_ms": round(avg_duration, 1),
        }
    
    def recent_calls(self, limit: int = 20) -> List[Dict[str, Any]]:
        """最近调用记录"""
        self._load()
        return [
            {
                "tool": c.tool_name,
                "action": c.action,
                "time": time.strftime("%H:%M:%S", time.localtime(c.timestamp)),
                "duration_ms": c.duration_ms,
                "error": c.error[:50] if c.error else None,
            }
            for c in self._calls[-limit:]
        ]
    
    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """异常检测（简单启发式）"""
        self._load()
        anomalies = []
        
        if len(self._calls) < 10:
            return anomalies
        
        recent_50 = self._calls[-50:]
        tool_counts = Counter(c.tool_name for c in recent_50)
        
        # 短时间内大量调用同一工具
        for tool, count in tool_counts.items():
            if count > 20:
                anomalies.append({
                    "type": "high_frequency",
                    "tool": tool,
                    "count": count,
                    "message": f"{tool} called {count} times in last 50 calls",
                })
        
        # 连续错误
        recent_errors = [c for c in self._calls[-20:] if c.error]
        if len(recent_errors) >= 5:
            anomalies.append({
                "type": "error_streak",
                "count": len(recent_errors),
                "message": f"{len(recent_errors)} errors in last 20 calls",
            })
        
        return anomalies


_observer: Optional[ObserveHook] = None

def get_observer() -> ObserveHook:
    global _observer
    if _observer is None:
        _observer = ObserveHook()
    return _observer
