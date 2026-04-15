# -*- coding: utf-8 -*-
"""
auto_memory.py - 自动会话记忆管理

来源: 顾庸t workspace_tools/auto_memory.py
参考: Claude Code agentMemory + Hermes memory_tool + ECC auto-memory skill

功能:
  1. 自动收集会话数据（决策/学习/待办/文件变更）
  2. 生成结构化摘要写入 memory/日期.md
  3. 定期清理过旧记忆
  4. 摘要去重 + 合并
"""

import os
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
MEMORY_DIR = WORKSPACE / "memory"


@dataclass
class MemoryEntry:
    """记忆条目"""
    timestamp: str
    category: str  # decision / learning / pending / file_change / task
    content: str
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5


class AutoMemory:
    """自动记忆管理器"""
    
    def __init__(self, memory_dir: Optional[Path] = None):
        self._dir = memory_dir or MEMORY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
    
    def _today_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self._dir / f"{today}.md"
    
    def _date_file(self, date_str: str) -> Path:
        return self._dir / f"{date_str}.md"
    
    def record(self, category: str, content: str, tags: Optional[List[str]] = None) -> MemoryEntry:
        """记录一条记忆"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = MemoryEntry(
            timestamp=now,
            category=category,
            content=content,
            tags=tags or [],
        )
        
        # 追加到日期文件
        date_file = self._today_file()
        tag_str = ", ".join(f"#{t}" for t in entry.tags) if entry.tags else ""
        line = f"\n- [{entry.category}] {entry.content} {tag_str}"
        
        existing = ""
        if date_file.exists():
            existing = date_file.read_text(encoding="utf-8", errors="replace")
        
        # 去重: 同类别同内容前50字
        prefix = content[:50]
        if prefix not in existing:
            with open(date_file, "a", encoding="utf-8") as f:
                f.write(line)
        
        return entry
    
    def record_decision(self, content: str, **kwargs) -> MemoryEntry:
        return self.record("decision", content, tags=["decision"], **kwargs)
    
    def record_learning(self, content: str, **kwargs) -> MemoryEntry:
        return self.record("learning", content, tags=["learning"], **kwargs)
    
    def record_pending(self, content: str, **kwargs) -> MemoryEntry:
        return self.record("pending", content, tags=["todo"], **kwargs)
    
    def record_file(self, content: str, **kwargs) -> MemoryEntry:
        return self.record("file_change", content, tags=["file"], **kwargs)
    
    def read_today(self) -> str:
        """读取今日记忆"""
        f = self._today_file()
        if f.exists():
            return f.read_text(encoding="utf-8", errors="replace")
        return ""
    
    def read_date(self, date_str: str) -> str:
        """读取指定日期记忆"""
        f = self._date_file(date_str)
        if f.exists():
            return f.read_text(encoding="utf-8", errors="replace")
        return ""
    
    def search(self, query: str, days: int = 30) -> List[Dict[str, str]]:
        """搜索最近N天的记忆"""
        results = []
        today = datetime.now()
        
        for i in range(days + 1):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            content = self.read_date(date)
            if not content:
                continue
            
            for line in content.split("\n"):
                if line.strip() and query.lower() in line.lower():
                    results.append({
                        "date": date,
                        "line": line.strip(),
                    })
        
        return results
    
    def list_dates(self, days: int = 30) -> List[str]:
        """列出有记忆的日期"""
        dates = []
        today = datetime.now()
        for i in range(days + 1):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            f = self._date_file(date)
            if f.exists() and f.stat().st_size > 0:
                dates.append(date)
        return sorted(dates, reverse=True)
    
    def summarize_day(self, date_str: Optional[str] = None) -> str:
        """生成日摘要"""
        content = self.read_date(date_str) if date_str else self.read_today()
        if not content:
            return "No memories found."
        
        lines = [l.strip() for l in content.split("\n") if l.strip() and l.startswith("-")]
        
        categories = {}
        for line in lines:
            cat_match = re.match(r"\[(\w+)\]", line)
            cat = cat_match.group(1) if cat_match else "other"
            categories.setdefault(cat, []).append(line)
        
        summary = [f"# Day Summary: {date_str or datetime.now().strftime('%Y-%m-%d')}"]
        cat_labels = {
            "decision": "Decisions",
            "learning": "Learnings",
            "pending": "Pending",
            "file_change": "File Changes",
            "task": "Tasks",
        }
        for cat, items in categories.items():
            label = cat_labels.get(cat, cat.title())
            summary.append(f"\n## {label} ({len(items)})")
            for item in items:
                summary.append(f"  {item}")
        
        return "\n".join(summary)
    
    def cleanup_old(self, keep_days: int = 90) -> int:
        """清理过旧记忆文件"""
        cutoff = datetime.now() - timedelta(days=keep_days)
        removed = 0
        
        for f in self._dir.glob("*.md"):
            try:
                # 从文件名解析日期
                date_str = f.stem  # YYYY-MM-DD
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    f.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        
        return removed


_memory: Optional[AutoMemory] = None

def get_auto_memory() -> AutoMemory:
    global _memory
    if _memory is None:
        _memory = AutoMemory()
    return _memory
