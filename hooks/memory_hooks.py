# -*- coding: utf-8 -*-
"""
memory_hooks.py - 记忆系统 Hook（Claude-Mem 风格）

来源: Claude-Mem 5 生命周期 Hook
参考: study_notes_memory_systems_20260420.md

生命周期:
  SessionStart → UserPromptSubmit → PostToolUse → Summary → SessionEnd

功能:
  1. 自动捕获工具调用（PostToolUse）
  2. 捕获用户消息（UserPromptSubmit）
  3. 会话摘要（SessionEnd）
  4. 存储到 Palace 结构
"""

import time
import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
MEMORY_LOG = WORKSPACE / ".memory_hooks_log.jsonl"
PALACE_DIR = WORKSPACE / "memory" / "palace"


@dataclass
class MemoryEvent:
    """记忆事件"""
    event_type: str  # session_start / user_prompt / tool_use / session_end
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Palace 结构
    wing: str = ""     # 人/项目
    room: str = ""     # 天/会话
    drawer_id: str = ""  # 原话块 ID


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    start_time: float
    user_prompts: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)  # 涉及的人/项目


class MemoryHooks:
    """记忆系统 Hook"""
    
    def __init__(self, log_path: Optional[Path] = None, palace_dir: Optional[Path] = None):
        self._log_path = log_path or MEMORY_LOG
        self._palace_dir = palace_dir or PALACE_DIR
        self._palace_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_session: Optional[SessionState] = None
        self._events: List[MemoryEvent] = []
    
    # ===== 生命周期 Hook =====
    
    def on_session_start(self, session_id: str = "") -> MemoryEvent:
        """SessionStart Hook"""
        if not session_id:
            session_id = self._generate_session_id()
        
        self._current_session = SessionState(
            session_id=session_id,
            start_time=time.time(),
        )
        
        event = MemoryEvent(
            event_type="session_start",
            session_id=session_id,
            content=f"Session {session_id} started",
            metadata={"start_time": datetime.now().isoformat()},
        )
        
        self._record(event)
        return event
    
    def on_user_prompt_submit(self, prompt: str, session_id: str = "") -> MemoryEvent:
        """UserPromptSubmit Hook"""
        session_id = session_id or self._get_current_session_id()
        
        # 提取实体（简单启发式）
        entities = self._extract_entities(prompt)
        
        if self._current_session:
            self._current_session.user_prompts.append(prompt)
            self._current_session.entities.extend(entities)
        
        # 隐私检查
        content = self._check_privacy(prompt)
        
        event = MemoryEvent(
            event_type="user_prompt",
            session_id=session_id,
            content=content,
            metadata={
                "prompt_length": len(prompt),
                "entities": entities,
            },
            wing=entities[0] if entities else "general",
            room=datetime.now().strftime("%Y-%m-%d"),
        )
        
        self._record(event)
        return event
    
    def on_post_tool_use(self, tool_name: str, tool_input: Dict[str, Any],
                          tool_output: Any, duration_ms: float = 0,
                          error: str = "", session_id: str = "") -> MemoryEvent:
        """PostToolUse Hook"""
        session_id = session_id or self._get_current_session_id()
        
        # 摘要化输入输出（防止过长）
        input_summary = self._summarize(tool_input, max_len=200)
        output_summary = self._summarize(tool_output, max_len=200)
        
        if self._current_session:
            self._current_session.tool_calls.append({
                "tool": tool_name,
                "input_summary": input_summary,
                "output_summary": output_summary,
                "duration_ms": duration_ms,
                "error": error[:100] if error else None,
            })
        
        event = MemoryEvent(
            event_type="tool_use",
            session_id=session_id,
            content=f"[{tool_name}] {input_summary} → {output_summary}",
            metadata={
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "error": error[:100] if error else None,
            },
        )
        
        self._record(event)
        return event
    
    def on_session_end(self, summary: str = "", session_id: str = "") -> MemoryEvent:
        """SessionEnd Hook"""
        session_id = session_id or self._get_current_session_id()
        
        # 生成会话摘要
        if not summary and self._current_session:
            summary = self._generate_session_summary()
        
        event = MemoryEvent(
            event_type="session_end",
            session_id=session_id,
            content=summary,
            metadata={
                "end_time": datetime.now().isoformat(),
                "prompts_count": len(self._current_session.user_prompts) if self._current_session else 0,
                "tools_count": len(self._current_session.tool_calls) if self._current_session else 0,
            },
        )
        
        self._record(event)
        
        # 保存到 Palace
        self._save_to_palace()
        
        # 清理会话状态
        self._current_session = None
        
        return event
    
    # ===== Palace 存储 =====
    
    def _save_to_palace(self) -> None:
        """保存会话到 Palace 结构"""
        if not self._current_session:
            return
        
        session = self._current_session
        
        # 确定 Wing（人/项目）
        wings = list(set(session.entities)) if session.entities else ["general"]
        
        # 确定 Room（天）
        room = datetime.now().strftime("%Y-%m-%d")
        
        # 创建 Drawer
        drawer = {
            "session_id": session.session_id,
            "start_time": datetime.fromtimestamp(session.start_time).isoformat(),
            "prompts": session.user_prompts,
            "tool_calls": session.tool_calls,
            "entities": list(set(session.entities)),
        }
        
        drawer_id = self._generate_drawer_id(drawer)
        drawer["drawer_id"] = drawer_id
        
        # 保存到文件
        for wing in wings:
            wing_dir = self._palace_dir / wing
            wing_dir.mkdir(parents=True, exist_ok=True)
            
            room_file = wing_dir / f"{room}.jsonl"
            with open(room_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(drawer, ensure_ascii=False) + "\n")
    
    # ===== 辅助方法 =====
    
    def _generate_session_id(self) -> str:
        """生成会话 ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
    
    def _get_current_session_id(self) -> str:
        """获取当前会话 ID"""
        if self._current_session:
            return self._current_session.session_id
        return self._generate_session_id()
    
    def _generate_drawer_id(self, drawer: Dict[str, Any]) -> str:
        """生成 Drawer ID"""
        content = json.dumps(drawer, sort_keys=True, ensure_ascii=False)
        return "drawer_" + hashlib.md5(content.encode()).hexdigest()[:8]
    
    def _extract_entities(self, text: str) -> List[str]:
        """提取实体（简单启发式）"""
        entities = []
        
        # 人名模式（中文）
        # TODO: 使用 NER 模型或更复杂的规则
        
        # 项目名模式
        keywords = ["项目", "project", "工作", "task"]
        for kw in keywords:
            if kw in text.lower():
                entities.append("work")
        
        return entities[:3]  # 最多 3 个
    
    def _check_privacy(self, content: str) -> str:
        """检查隐私标签"""
        # <private> 标签内容不存储
        if "<private>" in content and "</private>" in content:
            # 移除 private 标签内的内容
            import re
            content = re.sub(r'<private>.*?</private>', '[PRIVATE]', content, flags=re.DOTALL)
        return content
    
    def _summarize(self, obj: Any, max_len: int = 200) -> str:
        """摘要化对象"""
        if obj is None:
            return "None"
        
        if isinstance(obj, str):
            return obj[:max_len] + "..." if len(obj) > max_len else obj
        
        if isinstance(obj, dict):
            keys = list(obj.keys())[:5]
            return f"dict({', '.join(keys)}...)"
        
        if isinstance(obj, list):
            return f"list({len(obj)} items)"
        
        return str(obj)[:max_len]
    
    def _generate_session_summary(self) -> str:
        """生成会话摘要"""
        if not self._current_session:
            return "No session"
        
        session = self._current_session
        prompts = len(session.user_prompts)
        tools = len(session.tool_calls)
        entities = list(set(session.entities))
        
        return f"Session: {prompts} prompts, {tools} tool calls, entities: {entities}"
    
    def _record(self, event: MemoryEvent) -> None:
        """记录事件"""
        self._events.append(event)
        
        # 追加到日志文件
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "event_type": event.event_type,
                    "timestamp": event.timestamp,
                    "session_id": event.session_id,
                    "content": event.content,
                    "metadata": event.metadata,
                    "wing": event.wing,
                    "room": event.room,
                    "drawer_id": event.drawer_id,
                }, ensure_ascii=False) + "\n")
        except OSError:
            pass
    
    # ===== 查询接口 =====
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取当前会话统计"""
        if not self._current_session:
            return {"active": False}
        
        session = self._current_session
        return {
            "active": True,
            "session_id": session.session_id,
            "duration_sec": round(time.time() - session.start_time, 1),
            "prompts": len(session.user_prompts),
            "tools": len(session.tool_calls),
            "entities": list(set(session.entities)),
        }
    
    def recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """最近事件"""
        return [
            {
                "type": e.event_type,
                "time": datetime.fromtimestamp(e.timestamp).strftime("%H:%M:%S"),
                "content": e.content[:100],
            }
            for e in self._events[-limit:]
        ]


# 全局实例
_memory_hooks: Optional[MemoryHooks] = None

def get_memory_hooks() -> MemoryHooks:
    global _memory_hooks
    if _memory_hooks is None:
        _memory_hooks = MemoryHooks()
    return _memory_hooks


# ===== 便捷函数 =====

def start_session(session_id: str = "") -> str:
    """开始会话"""
    hooks = get_memory_hooks()
    event = hooks.on_session_start(session_id)
    return event.session_id

def record_prompt(prompt: str, session_id: str = "") -> None:
    """记录用户消息"""
    hooks = get_memory_hooks()
    hooks.on_user_prompt_submit(prompt, session_id)

def record_tool(tool_name: str, tool_input: Dict[str, Any], 
                tool_output: Any, duration_ms: float = 0,
                error: str = "", session_id: str = "") -> None:
    """记录工具调用"""
    hooks = get_memory_hooks()
    hooks.on_post_tool_use(tool_name, tool_input, tool_output, duration_ms, error, session_id)

def end_session(summary: str = "", session_id: str = "") -> None:
    """结束会话"""
    hooks = get_memory_hooks()
    hooks.on_session_end(summary, session_id)


if __name__ == "__main__":
    # 测试
    print("Testing memory_hooks.py...")
    
    # 开始会话
    sid = start_session()
    print(f"Session started: {sid}")
    
    # 记录用户消息
    record_prompt("帮我整理文件")
    record_prompt("学习 claude-mem 项目")
    
    # 记录工具调用
    record_tool("exec", {"command": "ls"}, "file1.txt\nfile2.txt", 150)
    record_tool("read", {"file": "test.md"}, "# Test content", 50)
    
    # 结束会话
    end_session()
    
    # 打印统计
    hooks = get_memory_hooks()
    print("\nSession stats:")
    print(json.dumps(hooks.get_session_stats(), indent=2, ensure_ascii=False))
    
    print("\nRecent events:")
    for e in hooks.recent_events(10):
        print(f"  {e['time']} [{e['type']}] {e['content'][:50]}")
    
    print("\n✅ Test passed!")
