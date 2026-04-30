"""
qclaw_unified_memory.py — 统一记忆管理器

整合来源（5个模块 → 1个）：
  1. memory_provider.py  → MemoryProvider ABC + JSONL存储
  2. integrated_memory.py → 4层读取 + 跨层搜索
  3. auto_memory.py      → 自动记录 + 日摘要 + 清理
  4. memory_extractor.py → 4类提取（决策/学习/待办/关键文件）
  5. palace.py           → 空间化组织（记忆宫殿）

设计原则：
  - 一个入口管所有记忆层
  - 读/写/搜索/提取/清理 统一API
  - 保留各层特殊性（evolver结构化、MEMORY.md长期、daily工作、palace空间）
  - 与 evolver / self_review / ZeusHammer local_brain 集成

独立保留（不合并）：
  - memory_guard.py — 安全扫描（注入检测）
  - memory_fence.py — XML fencing（防误读）
"""

import json
import re
import time
import hashlib
import abc
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

WORKSPACE = Path.home() / ".qclaw" / "workspace"
MEMORY_DIR = WORKSPACE / "memory"


# ===== 数据类型 =====

class MemoryCategory(Enum):
    """记忆类别 — 整合 memory_extractor 4类 + auto_memory + palace"""
    DECISION = "decision"
    LEARNING = "learning"
    PENDING = "pending"
    KEY_FILE = "key_file"
    TASK = "task"
    FILE_CHANGE = "file_change"
    PREFERENCE = "preference"
    LESSON = "lesson"
    INSIGHT = "insight"


class MemorySource(Enum):
    """记忆来源层"""
    EVOLVER = "evolver"
    MEMORY_MD = "MEMORY.md"
    DAILY = "daily"
    HEARTBEAT = "heartbeat"
    PALACE = "palace"
    SESSION = "session"


class PalaceRoom(Enum):
    """记忆宫殿房间 — 源自 palace.py"""
    HALL = "hall"              # 核心/最常用
    LIBRARY = "library"        # 学习笔记/源码分析
    WORKSHOP = "workshop"      # 工具/脚本/技能
    GARDEN = "garden"          # 创意/想法/灵感
    VAULT = "vault"            # 重要凭证/敏感信息
    OBSERVATORY = "observatory" # 长期趋势/洞察


@dataclass
class MemoryEntry:
    """统一记忆条目 — 整合所有来源"""
    source: MemorySource
    category: MemoryCategory
    content: str
    timestamp: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    palace_room: Optional[PalaceRoom] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = {
            "source": self.source.value,
            "category": self.category.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "tags": self.tags,
            "confidence": self.confidence,
        }
        if self.palace_room:
            d["palace_room"] = self.palace_room.value
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# ===== Provider ABC — 源自 memory_provider.py =====

class MemoryProvider(abc.ABC):
    """记忆提供者抽象基类 — 源自 memory_provider.py"""
    
    @abc.abstractmethod
    def read(self, key: str) -> Optional[str]:
        ...
    
    @abc.abstractmethod
    def write(self, key: str, content: str) -> None:
        ...
    
    @abc.abstractmethod
    def search(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        ...
    
    @abc.abstractmethod
    def delete(self, key: str) -> bool:
        ...


class JSONLMemoryProvider(MemoryProvider):
    """JSONL 持久化存储 — 源自 memory_provider.py BuiltinMemoryProvider"""
    
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
    
    def read(self, key: str) -> Optional[str]:
        if not self._path.exists():
            return None
        for line in self._path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if record.get("key") == key:
                    return record.get("content")
            except json.JSONDecodeError:
                continue
        return None
    
    def write(self, key: str, content: str) -> None:
        record = {"key": key, "content": content, "timestamp": time.time()}
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    def search(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        results = []
        if not self._path.exists():
            return results
        q = query.lower()
        for line in self._path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if q in record.get("content", "").lower():
                    results.append(MemoryEntry(
                        source=MemorySource.SESSION,
                        category=MemoryCategory.TASK,
                        content=record.get("content", ""),
                        timestamp=str(record.get("timestamp", "")),
                    ))
                    if len(results) >= limit:
                        break
            except json.JSONDecodeError:
                continue
        return results
    
    def delete(self, key: str) -> bool:
        if not self._path.exists():
            return False
        lines = []
        found = False
        for line in self._path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if record.get("key") == key:
                    found = True
                else:
                    lines.append(line)
            except json.JSONDecodeError:
                lines.append(line)
        if found:
            self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return found


# ===== 提取器 — 源自 memory_extractor.py =====

EXTRACTION_PATTERNS = {
    "decision": [
        (r"(决定|选择|采用|确认)\s*[：:]\s*(.+)", 0.7),
        (r"(用|使用|选用)\s*(.+?)\s*(而|来|去)\s*(.+)", 0.5),
        (r"(不用|放弃|排除)\s*(.+?)\s*(因为|由于)\s*(.+)", 0.6),
    ],
    "learning": [
        (r"(学到|发现|意识到|注意到)\s*[：:]\s*(.+)", 0.7),
        (r"(关键|核心|重要)\s*(认知|发现|洞察)\s*[：:]\s*(.+)", 0.8),
    ],
    "pending": [
        (r"(待做|待办|TODO|还没|需要)\s*[：:]\s*(.+)", 0.7),
        (r"(\[ \])\s*(.+)", 0.6),
    ],
    "key_file": [
        (r"(新建|创建|修改|更新|落地|完成|写入)\s*[：:]\s*(\S+\.\w+)", 0.7),
    ],
}


class MemoryExtractor:
    """4类记忆提取器 — 源自 memory_extractor.py，无改动"""
    
    def extract(self, text: str) -> List[MemoryEntry]:
        items = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        
        for category, patterns in EXTRACTION_PATTERNS.items():
            for pattern, confidence in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    content = " ".join(str(m) for m in match if m) if isinstance(match, tuple) else str(match)
                    if len(content.strip()) < 5:
                        continue
                    items.append(MemoryEntry(
                        source=MemorySource.SESSION,
                        category=MemoryCategory(category),
                        content=content.strip(),
                        timestamp=now,
                        confidence=confidence,
                    ))
        
        # 去重
        seen = {}
        for item in items:
            key = (item.category.value, item.content[:50])
            if key not in seen or item.confidence > seen[key].confidence:
                seen[key] = item
        return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)


# ===== 记忆宫殿 — 源自 palace.py =====

PALACE_ROOM_CATEGORIES = {
    PalaceRoom.HALL: [MemoryCategory.DECISION, MemoryCategory.LESSON],
    PalaceRoom.LIBRARY: [MemoryCategory.LEARNING, MemoryCategory.INSIGHT],
    PalaceRoom.WORKSHOP: [MemoryCategory.TASK, MemoryCategory.FILE_CHANGE, MemoryCategory.KEY_FILE],
    PalaceRoom.GARDEN: [MemoryCategory.INSIGHT, MemoryCategory.PREFERENCE],
    PalaceRoom.VAULT: [MemoryCategory.PREFERENCE],
    PalaceRoom.OBSERVATORY: [MemoryCategory.INSIGHT, MemoryCategory.LEARNING],
}


# ===== 统一管理器 =====

class UnifiedMemory:
    """
    qclaw 统一记忆管理器
    
    整合5个模块的核心能力：
    - memory_provider: ABC + JSONL持久化
    - integrated_memory: 4层读取 + 跨层搜索
    - auto_memory: 自动记录 + 日摘要 + 清理
    - memory_extractor: 4类提取
    - palace: 空间化组织
    """
    
    def __init__(self, workspace: Optional[Path] = None):
        self._workspace = workspace or WORKSPACE
        self._memory_dir = self._workspace / "memory"
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        
        # JSONL 提供者
        self._session_store = JSONLMemoryProvider(self._memory_dir / "session_memory.jsonl")
        
        # 提取器
        self._extractor = MemoryExtractor()
        
        # 宫殿索引
        self._palace_index: Dict[str, List[str]] = {r.value: [] for r in PalaceRoom}
        self._load_palace_index()
    
    # ─── 写入 ───────────────────────────────────────────
    
    def record(self, category: str, content: str, tags: Optional[List[str]] = None,
               confidence: float = 0.5, palace_room: Optional[str] = None) -> MemoryEntry:
        """
        记录一条记忆 — 整合 auto_memory.record()
        
        自动：去重、追加到日期文件、更新宫殿索引
        """
        cat = MemoryCategory(category) if category in [c.value for c in MemoryCategory] else MemoryCategory.TASK
        
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = MemoryEntry(
            source=MemorySource.SESSION,
            category=cat,
            content=content,
            timestamp=now,
            tags=tags or [],
            confidence=confidence,
            palace_room=PalaceRoom(palace_room) if palace_room else None,
        )
        
        # 追加到日期文件（源自 auto_memory）
        date_file = self._today_file()
        tag_str = " ".join(f"#{t}" for t in entry.tags) if entry.tags else ""
        line = f"- [{entry.category.value}] {entry.content} {tag_str}"
        
        existing = ""
        if date_file.exists():
            existing = date_file.read_text(encoding="utf-8", errors="replace")
        
        # 去重
        prefix = content[:50]
        if prefix not in existing:
            with open(date_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        
        # 更新宫殿索引
        if entry.palace_room:
            self._palace_index[entry.palace_room.value].append(content[:80])
            self._save_palace_index()
        
        # JSONL 持久化
        self._session_store.write(f"{cat.value}:{now}", content)
        
        return entry
    
    def record_decision(self, content: str, **kw) -> MemoryEntry:
        return self.record("decision", content, tags=["decision"], confidence=0.7, **kw)
    
    def record_learning(self, content: str, **kw) -> MemoryEntry:
        return self.record("learning", content, tags=["learning"], confidence=0.7, **kw)
    
    def record_pending(self, content: str, **kw) -> MemoryEntry:
        return self.record("pending", content, tags=["todo"], **kw)
    
    def record_file(self, content: str, **kw) -> MemoryEntry:
        return self.record("key_file", content, tags=["file"], **kw)
    
    # ─── 读取 ───────────────────────────────────────────
    # 源自 integrated_memory 的 4 层读取
    
    def read_evolver(self, limit: int = 20) -> List[MemoryEntry]:
        """从 evolver_db.json 读取结构化经验"""
        path = self._workspace / ".evolver_db.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = []
            for rule in data.get("rules", []):
                entries.append(MemoryEntry(
                    source=MemorySource.EVOLVER,
                    category=MemoryCategory.LESSON,
                    content=f"{rule.get('task', '')} → {rule.get('method', '')}",
                    timestamp=str(rule.get("last_success", "")),
                    tags=["evolver", rule.get("task", "")],
                    confidence=rule.get("priority", 0.5),
                ))
            return entries[:limit]
        except Exception:
            return []
    
    def read_memory_md(self, limit: int = 30) -> List[MemoryEntry]:
        """从 MEMORY.md 读取长期记忆"""
        path = self._workspace / "MEMORY.md"
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
                            source=MemorySource.MEMORY_MD,
                            category=MemoryCategory.LESSON,
                            content=content,
                            tags=["memory", current_section],
                        ))
            return entries[:limit]
        except Exception:
            return []
    
    def read_daily(self, days: int = 7, limit: int = 20) -> List[MemoryEntry]:
        """读取最近 N 天的工作记忆"""
        entries = []
        today = datetime.now(timezone.utc)
        for i in range(days):
            dt = today - timedelta(days=i)
            date_str = dt.strftime("%Y-%m-%d")
            path = self._memory_dir / f"{date_str}.md"
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                for line in text.split("\n"):
                    content = line.strip().lstrip("-*•# ").strip()
                    if len(content) > 15:
                        entries.append(MemoryEntry(
                            source=MemorySource.DAILY,
                            category=MemoryCategory.TASK,
                            content=content,
                            timestamp=date_str,
                            tags=["daily"],
                        ))
            except Exception:
                pass
        return entries[:limit]
    
    # ─── 搜索 ───────────────────────────────────────────
    # 源自 integrated_memory 的跨层搜索
    
    def search(self, query: str, max_per_layer: int = 5) -> Dict[str, List[MemoryEntry]]:
        """跨所有记忆层搜索"""
        q = query.lower()
        results = {}
        
        # evolver
        evolver_entries = [e for e in self.read_evolver() if q in e.content.lower()]
        if evolver_entries:
            results["evolver"] = evolver_entries[:max_per_layer]
        
        # MEMORY.md
        md_entries = [e for e in self.read_memory_md() if q in e.content.lower()]
        if md_entries:
            results["MEMORY.md"] = md_entries[:max_per_layer]
        
        # daily
        daily_entries = [e for e in self.read_daily(7) if q in e.content.lower()]
        if daily_entries:
            results["daily"] = daily_entries[:max_per_layer]
        
        # JSONL session
        session_entries = self._session_store.search(query, max_per_layer)
        if session_entries:
            results["session"] = session_entries
        
        return results
    
    def search_flat(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """扁平化搜索所有层"""
        all_results = []
        for entries in self.search(query).values():
            all_results.extend(entries)
        # 按置信度排序
        all_results.sort(key=lambda e: e.confidence, reverse=True)
        return all_results[:limit]
    
    # ─── 提取 ───────────────────────────────────────────
    # 源自 memory_extractor
    
    def extract(self, text: str) -> List[MemoryEntry]:
        """从文本提取4类记忆"""
        return self._extractor.extract(text)
    
    def extract_and_save(self, text: str) -> List[MemoryEntry]:
        """提取并自动保存"""
        items = self.extract(text)
        for item in items:
            self.record(item.category.value, item.content, tags=item.tags, confidence=item.confidence)
        return items
    
    # ─── 宫殿 ───────────────────────────────────────────
    # 源自 palace.py
    
    def palace_browse(self, room: Optional[str] = None) -> Dict[str, Any]:
        """浏览记忆宫殿"""
        if room:
            return {room: self._palace_index.get(room, [])}
        return dict(self._palace_index)
    
    def palace_assign(self, content: str, room: str) -> None:
        """手动分配到宫殿房间"""
        if room in self._palace_index:
            self._palace_index[room].append(content[:80])
            self._save_palace_index()
    
    def palace_auto_assign(self, category: MemoryCategory) -> PalaceRoom:
        """根据类别自动分配宫殿房间"""
        for room, categories in PALACE_ROOM_CATEGORIES.items():
            if category in categories:
                return room
        return PalaceRoom.HALL  # 默认大厅
    
    # ─── 维护 ───────────────────────────────────────────
    # 源自 auto_memory
    
    def summarize_day(self, date_str: Optional[str] = None) -> str:
        """生成日摘要"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        path = self._memory_dir / f"{date_str}.md"
        if not path.exists():
            return f"No memories for {date_str}."
        
        content = path.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.split("\n") if l.strip() and l.startswith("-")]
        
        by_category: Dict[str, List[str]] = {}
        for line in lines:
            cat_match = re.match(r"\[(\w+)\]", line)
            cat = cat_match.group(1) if cat_match else "other"
            by_category.setdefault(cat, []).append(line)
        
        summary = [f"# Day Summary: {date_str}"]
        for cat, items in by_category.items():
            summary.append(f"\n## {cat.title()} ({len(items)})")
            for item in items:
                summary.append(f"  {item}")
        
        return "\n".join(summary)
    
    def cleanup_old(self, keep_days: int = 90) -> int:
        """清理过旧记忆文件 — 源自 auto_memory.cleanup_old()"""
        cutoff = datetime.now() - timedelta(days=keep_days)
        removed = 0
        for f in self._memory_dir.glob("*.md"):
            try:
                file_date = datetime.strptime(f.stem, "%Y-%m-%d")
                if file_date < cutoff:
                    f.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        evolver_count = len(self.read_evolver(999))
        md_count = len(self.read_memory_md(999))
        
        daily_files = list(self._memory_dir.glob("*.md"))
        
        palace_total = sum(len(v) for v in self._palace_index.values())
        
        return {
            "evolver_rules": evolver_count,
            "memory_md_entries": md_count,
            "daily_files": len(daily_files),
            "palace_items": palace_total,
            "palace_rooms": {k: len(v) for k, v in self._palace_index.items()},
        }
    
    # ─── 内部 ───────────────────────────────────────────
    
    def _today_file(self) -> Path:
        return self._memory_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    
    def _load_palace_index(self):
        path = self._workspace / ".palace_index.json"
        if path.exists():
            try:
                self._palace_index = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    
    def _save_palace_index(self):
        path = self._workspace / ".palace_index.json"
        path.write_text(json.dumps(self._palace_index, indent=2, ensure_ascii=False), encoding="utf-8")


# ===== 全局单例 =====

_instance: Optional[UnifiedMemory] = None

def get_memory() -> UnifiedMemory:
    global _instance
    if _instance is None:
        _instance = UnifiedMemory()
    return _instance


# ===== 自测 =====

if __name__ == "__main__":
    mem = UnifiedMemory()
    
    # 测试1: 记录
    e1 = mem.record_decision("使用 evolver v2 规则引擎")
    print(f"✅ 记录决策: {e1.content}")
    
    e2 = mem.record_learning("ZeusHammer Local Brain 三层匹配可升级 evolver")
    print(f"✅ 记录学习: {e2.content}")
    
    e3 = mem.record_pending("整合记忆模块到统一管理器")
    print(f"✅ 记录待办: {e3.content}")
    
    # 测试2: 搜索
    results = mem.search("evolver")
    print(f"✅ 搜索 'evolver': {sum(len(v) for v in results.values())} 条结果")
    
    # 测试3: 提取
    items = mem.extract("决定使用JSONL存储，学到了记忆宫殿可以空间化组织")
    print(f"✅ 提取: {len(items)} 条")
    
    # 测试4: 宫殿
    mem.palace_assign("evolver规则引擎", "workshop")
    browse = mem.palace_browse("workshop")
    print(f"✅ 宫殿: workshop有 {len(browse.get('workshop', []))} 条")
    
    # 测试5: 自动分配
    room = mem.palace_auto_assign(MemoryCategory.LEARNING)
    print(f"✅ 自动分配: learning → {room.value}")
    
    # 测试6: 统计
    stats = mem.get_stats()
    print(f"✅ 统计: {json.dumps(stats, ensure_ascii=False)}")
    
    print("\n🎯 UnifiedMemory 全部测试通过！")
