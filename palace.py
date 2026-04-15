# -*- coding: utf-8 -*-
"""
palace.py - 记忆宫殿（空间化记忆组织）

来源: 顾庸t workspace_tools/palace.py
参考: Memory Palace technique + Claude Code MEMORY.md indexing

功能:
  将记忆组织成"房间"结构，每个房间代表一个知识域。
  
  房间结构:
  - Hall (大厅): 核心知识/最常用
  - Library (图书馆): 学习笔记/源码分析
  - Workshop (工作室): 工具/脚本/技能
  - Garden (花园): 创意/想法/灵感
  - Vault (金库): 重要凭证/敏感信息
  - Observatory (天文台): 长期趋势/洞察

  每个 room 包含多个 item（记忆条目）。
"""

import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path


@dataclass
class MemoryItem:
    """记忆条目"""
    id: str
    content: str
    tags: List[str] = field(default_factory=list)
    importance: int = 1  # 1-5
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    source: str = ""  # 来源任务/文档


@dataclass
class Room:
    """记忆房间"""
    name: str
    display_name: str
    description: str
    items: Dict[str, MemoryItem] = field(default_factory=dict)
    max_items: int = 100
    
    def add_item(self, content: str, tags: Optional[List[str]] = None,
                 importance: int = 1, source: str = "") -> MemoryItem:
        """添加记忆条目"""
        item_id = f"{self.name}-{len(self.items):04d}"
        item = MemoryItem(
            id=item_id,
            content=content,
            tags=tags or [],
            importance=importance,
            source=source,
        )
        
        # 如果满了，移除最不重要的
        if len(self.items) >= self.max_items:
            least_important = min(
                self.items.values(), key=lambda i: (i.importance, i.accessed_at)
            )
            del self.items[least_important.id]
        
        self.items[item_id] = item
        return item
    
    def search(self, query: str, limit: int = 10) -> List[MemoryItem]:
        """搜索房间内的记忆"""
        q = query.lower()
        scored = []
        for item in self.items.values():
            score = 0
            if q in item.content.lower():
                score += 3
            for tag in item.tags:
                if q in tag.lower():
                    score += 2
            if score > 0:
                scored.append((item, score))
                item.accessed_at = time.time()
        
        scored.sort(key=lambda x: (-x[1], -x[0].importance))
        return [item for item, _ in scored[:limit]]
    
    def list_items(self, sort_by: str = "importance") -> List[Dict[str, Any]]:
        """列出所有条目"""
        items = list(self.items.values())
        if sort_by == "importance":
            items.sort(key=lambda i: -i.importance)
        elif sort_by == "recent":
            items.sort(key=lambda i: -i.created_at)
        elif sort_by == "accessed":
            items.sort(key=lambda i: -i.accessed_at)
        
        return [
            {"id": i.id, "content": i.content[:60], "tags": i.tags, 
             "importance": i.importance}
            for i in items
        ]


class MemoryPalace:
    """记忆宫殿"""
    
    def __init__(self, storage_file: Optional[Path] = None):
        self._storage = storage_file or Path.home() / ".qclaw" / "workspace" / ".palace.json"
        self._rooms: Dict[str, Room] = {}
        self._init_default_rooms()
        self._load()
    
    def _init_default_rooms(self) -> None:
        """初始化默认房间"""
        defaults = [
            ("hall", "Hall (大厅)", "Core knowledge, most frequently accessed"),
            ("library", "Library (图书馆)", "Study notes, source code analysis"),
            ("workshop", "Workshop (工作室)", "Tools, scripts, skills"),
            ("garden", "Garden (花园)", "Creative ideas, inspiration"),
            ("vault", "Vault (金库)", "Important credentials, sensitive info"),
            ("observatory", "Observatory (天文台)", "Long-term trends, insights"),
        ]
        for name, display, desc in defaults:
            if name not in self._rooms:
                self._rooms[name] = Room(name=name, display_name=display, description=desc)
    
    def _load(self) -> None:
        """加载持久化数据"""
        if self._storage.exists():
            try:
                data = json.loads(self._storage.read_text(encoding="utf-8"))
                for room_name, room_data in data.get("rooms", {}).items():
                    if room_name in self._rooms:
                        for item_id, item_data in room_data.items():
                            self._rooms[room_name].items[item_id] = MemoryItem(**item_data)
            except (json.JSONDecodeError, TypeError):
                pass
    
    def _save(self) -> None:
        """保存"""
        data = {"rooms": {}}
        for name, room in self._rooms.items():
            data["rooms"][name] = {
                iid: {
                    "id": i.id, "content": i.content, "tags": i.tags,
                    "importance": i.importance, "created_at": i.created_at,
                    "accessed_at": i.accessed_at, "source": i.source,
                }
                for iid, i in room.items.items()
            }
        try:
            self._storage.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    
    def get_room(self, name: str) -> Optional[Room]:
        return self._rooms.get(name)
    
    def list_rooms(self) -> List[Dict[str, str]]:
        return [
            {"name": r.name, "display": r.display_name, 
             "items": len(r.items), "desc": r.description}
            for r in self._rooms.values()
        ]
    
    def add_to_room(self, room_name: str, content: str, **kwargs) -> Optional[MemoryItem]:
        """向指定房间添加记忆"""
        room = self._rooms.get(room_name)
        if not room:
            return None
        item = room.add_item(content, **kwargs)
        self._save()
        return item
    
    def search_all(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索所有房间"""
        results = []
        for room in self._rooms.values():
            items = room.search(query, limit=limit)
            for item in items:
                results.append({
                    "room": room.display_name,
                    "id": item.id,
                    "content": item.content[:80],
                    "importance": item.importance,
                    "tags": item.tags,
                })
        
        results.sort(key=lambda x: -x["importance"])
        return results[:limit]
    
    def stats(self) -> Dict[str, Any]:
        """统计"""
        total_items = sum(len(r.items) for r in self._rooms.values())
        return {
            "rooms": len(self._rooms),
            "total_items": total_items,
            "by_room": {r.display_name: len(r.items) for r in self._rooms.values()},
        }


_palace: Optional[MemoryPalace] = None

def get_palace() -> MemoryPalace:
    global _palace
    if _palace is None:
        _palace = MemoryPalace()
    return _palace
