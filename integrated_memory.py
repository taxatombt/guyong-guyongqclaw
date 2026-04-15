# -*- coding: utf-8 -*-
"""
integrated_memory.py - 综合记忆管理

整合多个记忆层:
  1. evolver.db   — 结构化经验 (任务/方法/成功/失败)
  2. MEMORY.md     — 长期记忆精华
  3. memory/*.md   — 工作记忆 (按日期)
  4. HEARTBEAT.md  — 心跳协议

统一接口，掩盖底层差异。
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
MEMORY_DIR = WORKSPACE / "memory"


@dataclass
class MemoryEntry:
    """统一记忆条目"""
    source: str  # evolver / MEMORY.md / daily / heartbeat
    category: str  # task / decision / learning / preference / lesson
    content: str
    timestamp: str
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


# ─── Layer 1: Evolver ─────────────────────────────────

def read_evolver() -> List[MemoryEntry]:
    """从 evolver_db.json 读取结构化经验"""
    path = WORKSPACE / ".evolver_db.json"
    if not path.exists():
        return []
    
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for rule in data.get("rules", []):
            outcome = "success" if rule.get("total_count", 0) > 0 else "unknown"
            entries.append(MemoryEntry(
                source="evolver",
                category="lesson",
                content=f"{rule.get('task', '')} → {rule.get('method', '')} [{outcome}]",
                timestamp=rule.get("last_success", ""),
                tags=["evolver", rule.get("task", "")],
            ))
        return entries
    except Exception:
        return []


def search_evolver(query: str, max_results: int = 5) -> List[MemoryEntry]:
    """搜索 evolver 经验"""
    all_entries = read_evolver()
    q = query.lower()
    scored = []
    for e in all_entries:
        score = 0
        content = e.content.lower()
        if q in content:
            score = content.count(q)
        if score > 0:
            scored.append((score, e))
    scored.sort(reverse=True)
    return [e for _, e in scored[:max_results]]


# ─── Layer 2: MEMORY.md ──────────────────────────────

def read_memory_md() -> List[MemoryEntry]:
    """从 MEMORY.md 读取长期记忆"""
    path = WORKSPACE / "MEMORY.md"
    if not path.exists():
        return []
    
    try:
        text = path.read_text(encoding="utf-8")
        entries = []
        current_section = "general"
        
        for line in text.split("\n"):
            if line.startswith("## "):
                current_section = line[3:].strip().lower()
            elif line.strip() and not line.startswith("#"):
                content = line.strip().lstrip("-*• ").strip()
                if len(content) > 10:
                    entries.append(MemoryEntry(
                        source="MEMORY.md",
                        category=current_section,
                        content=content,
                        timestamp="",
                        tags=["memory"],
                    ))
        
        return entries[:50]  # 最多50条
    except Exception:
        return []


# ─── Layer 3: Daily logs ──────────────────────────────

def read_daily_logs(days: int = 7) -> List[MemoryEntry]:
    """读取最近 N 天的工作记忆"""
    MEMORY_DIR.mkdir(exist_ok=True)
    entries = []
    
    today = datetime.now(timezone.utc)
    for i in range(days):
        dt = today.replace(day=today.day - i)
        date_str = dt.strftime("%Y-%m-%d")
        path = MEMORY_DIR / f"{date_str}.md"
        
        if not path.exists():
            continue
        
        try:
            text = path.read_text(encoding="utf-8")
            for line in text.split("\n"):
                content = line.strip().lstrip("-*•# ").strip()
                if len(content) > 15:
                    entries.append(MemoryEntry(
                        source=f"daily:{date_str}",
                        category="work_log",
                        content=content,
                        timestamp=date_str,
                        tags=["daily"],
                    ))
        except Exception:
            pass
    
    return entries


# ─── Layer 4: HEARTBEAT.md ───────────────────────────

def read_heartbeat() -> Dict[str, Any]:
    """读取心跳状态"""
    path = WORKSPACE / "HEARTBEAT.md"
    if not path.exists():
        return {}
    
    try:
        text = path.read_text(encoding="utf-8")
        result = {}
        for line in text.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                result[k.strip()] = v.strip()
        return result
    except Exception:
        return {}


# ─── Unified Search ────────────────────────────────────

def search_all(query: str, 
               max_per_layer: int = 3) -> Dict[str, List[MemoryEntry]]:
    """
    跨所有记忆层搜索。
    返回: {layer_name: [entries]}
    """
    results = {
        "evolver": search_evolver(query, max_per_layer),
        "MEMORY.md": [],
        "daily": [],
    }
    
    # MEMORY.md 搜索
    all_memory = read_memory_md()
    q = query.lower()
    for e in all_memory:
        if q in e.content.lower():
            results["MEMORY.md"].append(e)
    results["MEMORY.md"] = results["MEMORY.md"][:max_per_layer]
    
    # Daily 搜索
    daily = read_daily_logs(3)
    for e in daily:
        if q in e.content.lower():
            results["daily"].append(e)
    results["daily"] = results["daily"][:max_per_layer]
    
    return {k: v for k, v in results.items() if v}


def get_all_entries() -> List[MemoryEntry]:
    """获取所有记忆层的内容（用于上下文注入）"""
    entries = []
    entries.extend(read_evolver()[:20])
    entries.extend(read_memory_md()[:30])
    entries.extend(read_daily_logs(3)[:20])
    return entries


def format_for_context(entries: List[MemoryEntry], max_chars: int = 2000) -> str:
    """格式化记忆条目为上下文注入字符串"""
    if not entries:
        return "No memory entries found."
    
    lines = ["## Relevant Memory\n"]
    current_source = None
    
    for e in entries:
        if e.source != current_source:
            lines.append(f"\n### {e.source}\n")
            current_source = e.source
        
        tag_str = " #" + " #".join(e.tags[:3]) if e.tags else ""
        ts = f" ({e.timestamp})" if e.timestamp else ""
        lines.append(f"- {e.content}{tag_str}{ts}\n")
        
        if sum(len(l) for l in lines) > max_chars:
            break
    
    return "".join(lines)
