"""
cold_memory.py — FTS5 冷记忆检索系统

来源：Hermes Agent Guide 第7册（四温记忆模型 + FTS5零部署检索）
设计：SQLite + FTS5全文索引，按需加载只取3-5条

核心流程：
1. 写入：每次对话结束后，提取关键信息存入SQLite
2. 检索：用户输入 → 提取关键词 → FTS5 → top3-5 → 注入上下文

表设计（5张核心表，参考Hermes Guide）：
- conversations  — 会话元数据
- messages        — 消息内容+token统计
- memory_fragments — 提取的关键记忆(重要性评分+分类)
- tool_calls      — 工具调用记录
- fts_index       — FTS5虚拟表（全文检索）
"""

import sqlite3
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field

log = logging.getLogger("qclaw.cold_memory")

WORKSPACE = Path(r"C:\Users\yiseg\.qclaw\workspace")
DB_PATH = WORKSPACE / "memory" / "cold_memory.db"

# 记忆分类
CATEGORIES = [
    "decision",      # 决策
    "preference",    # 偏好
    "lesson",        # 教训
    "task",          # 任务
    "person",        # 人物
    "project",       # 项目
    "technical",     # 技术
    "schedule",      # 日程
    "error",         # 错误
    "insight",       # 洞察
]


@dataclass
class MemoryFragment:
    """记忆碎片"""
    id: str = ""
    content: str = ""
    category: str = "general"
    importance: float = 0.5  # 0.0-1.0
    source: str = ""         # 来源（session_id / file / manual）
    tags: str = ""           # 逗号分隔标签
    created_at: float = 0.0
    accessed_at: float = 0.0
    access_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class ColdMemoryStore:
    """FTS5冷记忆存储"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库和FTS5索引"""
        with self._conn() as c:
            # 主表
            c.execute("""
                CREATE TABLE IF NOT EXISTS memory_fragments (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    importance REAL DEFAULT 0.5,
                    source TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    created_at REAL,
                    accessed_at REAL,
                    access_count INTEGER DEFAULT 0
                )
            """)

            # FTS5虚拟表（全文检索）
            try:
                c.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_index
                    USING fts5(content, tags, category,
                              tokenize='unicode61')
                """)
            except sqlite3.OperationalError:
                # FTS5不可用时降级为LIKE搜索
                log.warning("[cold_memory] FTS5不可用，降级为LIKE搜索")
                c.execute("""
                    CREATE TABLE IF NOT EXISTS fts_fallback (
                        id TEXT PRIMARY KEY,
                        content TEXT NOT NULL
                    )
                """)

            # 对话记录表
            c.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    started_at REAL,
                    ended_at REAL,
                    message_count INTEGER DEFAULT 0,
                    summary TEXT DEFAULT ''
                )
            """)

            # 工具调用表
            c.execute("""
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    tool_input TEXT DEFAULT '',
                    result_summary TEXT DEFAULT '',
                    success INTEGER DEFAULT 1,
                    timestamp REAL,
                    session_id TEXT DEFAULT ''
                )
            """)

            c.commit()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _gen_id(self, content: str) -> str:
        return hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()[:16]

    # === 写入 ===

    def store_fragment(self, content: str, category: str = "general",
                       importance: float = 0.5, source: str = "",
                       tags: str = "") -> str:
        """存储一条记忆碎片"""
        frag_id = self._gen_id(content)
        now = time.time()

        with self._conn() as c:
            c.execute("""
                INSERT OR REPLACE INTO memory_fragments
                (id, content, category, importance, source, tags, created_at, accessed_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (frag_id, content, category, importance, source, tags, now, now))

            # FTS5索引
            try:
                c.execute("INSERT INTO fts_index (rowid, content, tags, category) VALUES (?, ?, ?, ?)",
                         (int(frag_id, 16) % (2**31), content, tags, category))
            except sqlite3.OperationalError:
                # FTS5不可用，写入fallback表
                c.execute("INSERT OR REPLACE INTO fts_fallback (id, content) VALUES (?, ?)",
                         (frag_id, content))

            c.commit()

        log.debug(f"[cold_memory] stored: {frag_id} [{category}] {content[:50]}")
        return frag_id

    def store_tool_call(self, tool_name: str, tool_input: str = "",
                        result_summary: str = "", success: bool = True,
                        session_id: str = "") -> int:
        """记录一次工具调用"""
        with self._conn() as c:
            c.execute("""
                INSERT INTO tool_calls (tool_name, tool_input, result_summary, success, timestamp, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tool_name, tool_input[:500], result_summary[:500],
                  1 if success else 0, time.time(), session_id))
            c.commit()
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    # === 检索 ===

    def search(self, query: str, limit: int = 5, category: str = "",
               min_importance: float = 0.0) -> List[MemoryFragment]:
        """
        FTS5全文检索，返回最相关的记忆碎片

        Args:
            query: 搜索关键词
            limit: 最多返回几条
            category: 只搜某个分类
            min_importance: 最低重要性
        """
        results = []

        with self._conn() as c:
            try:
                # 优先使用FTS5
                if category:
                    sql = """
                        SELECT m.id, m.content, m.category, m.importance, m.source, m.tags,
                               m.created_at, m.accessed_at, m.access_count
                        FROM memory_fragments m
                        JOIN fts_index f ON f.rowid = CAST(m.id AS INTEGER) % 2147483647
                        WHERE f.memory_fragments MATCH ? AND m.category = ? AND m.importance >= ?
                        ORDER BY m.importance DESC, m.accessed_at DESC
                        LIMIT ?
                    """
                    rows = c.execute(sql, (query, category, min_importance, limit)).fetchall()
                else:
                    sql = """
                        SELECT m.id, m.content, m.category, m.importance, m.source, m.tags,
                               m.created_at, m.accessed_at, m.access_count
                        FROM memory_fragments m
                        JOIN fts_index f ON f.rowid = CAST(m.id AS INTEGER) % 2147483647
                        WHERE f.memory_fragments MATCH ? AND m.importance >= ?
                        ORDER BY m.importance DESC, m.accessed_at DESC
                        LIMIT ?
                    """
                    rows = c.execute(sql, (query, min_importance, limit)).fetchall()
            except sqlite3.OperationalError:
                # FTS5不可用，降级为LIKE
                like_query = f"%{query}%"
                if category:
                    rows = c.execute("""
                        SELECT id, content, category, importance, source, tags, created_at, accessed_at, access_count
                        FROM memory_fragments
                        WHERE content LIKE ? AND category = ? AND importance >= ?
                        ORDER BY importance DESC, accessed_at DESC LIMIT ?
                    """, (like_query, category, min_importance, limit)).fetchall()
                else:
                    rows = c.execute("""
                        SELECT id, content, category, importance, source, tags, created_at, accessed_at, access_count
                        FROM memory_fragments
                        WHERE content LIKE ? AND importance >= ?
                        ORDER BY importance DESC, accessed_at DESC LIMIT ?
                    """, (like_query, min_importance, limit)).fetchall()

            for row in rows:
                frag = MemoryFragment(
                    id=row[0], content=row[1], category=row[2],
                    importance=row[3], source=row[4], tags=row[5],
                    created_at=row[6], accessed_at=row[7], access_count=row[8]
                )
                results.append(frag)
                # 更新访问计数
                c.execute("""
                    UPDATE memory_fragments SET accessed_at=?, access_count=access_count+1
                    WHERE id=?
                """, (time.time(), frag.id))

            c.commit()

        return results

    def get_recent(self, category: str = "", limit: int = 5) -> List[MemoryFragment]:
        """获取最近存储的记忆碎片"""
        with self._conn() as c:
            if category:
                rows = c.execute("""
                    SELECT id, content, category, importance, source, tags, created_at, accessed_at, access_count
                    FROM memory_fragments WHERE category=?
                    ORDER BY created_at DESC LIMIT ?
                """, (category, limit)).fetchall()
            else:
                rows = c.execute("""
                    SELECT id, content, category, importance, source, tags, created_at, accessed_at, access_count
                    FROM memory_fragments
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()

        return [MemoryFragment(
            id=r[0], content=r[1], category=r[2], importance=r[3],
            source=r[4], tags=r[5], created_at=r[6], accessed_at=r[7], access_count=r[8]
        ) for r in rows]

    def get_tool_stats(self, limit_days: int = 7) -> Dict[str, Any]:
        """获取工具调用统计（用于5-tool-call检测）"""
        cutoff = time.time() - limit_days * 86400
        with self._conn() as c:
            # 按工具名统计调用次数
            rows = c.execute("""
                SELECT tool_name, COUNT(*) as cnt,
                       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as success_cnt,
                       SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as fail_cnt
                FROM tool_calls WHERE timestamp >= ?
                GROUP BY tool_name ORDER BY cnt DESC
            """, (cutoff,)).fetchall()

            return {
                "tools": [{"name": r[0], "total": r[1], "success": r[2], "fail": r[3]} for r in rows],
                "period_days": limit_days,
            }

    # === 维护 ===

    def cleanup(self, max_age_days: int = 90, min_importance: float = 0.3):
        """清理过期低价值记忆"""
        cutoff = time.time() - max_age_days * 86400
        with self._conn() as c:
            deleted = c.execute("""
                DELETE FROM memory_fragments
                WHERE created_at < ? AND importance < ?
            """, (cutoff, min_importance)).rowcount
            c.commit()
        return deleted

    def stats(self) -> Dict[str, Any]:
        """数据库统计"""
        with self._conn() as c:
            frag_count = c.execute("SELECT COUNT(*) FROM memory_fragments").fetchone()[0]
            tool_count = c.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
            conv_count = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            avg_importance = c.execute("SELECT AVG(importance) FROM memory_fragments").fetchone()[0] or 0

        return {
            "fragments": frag_count,
            "tool_calls": tool_count,
            "conversations": conv_count,
            "avg_importance": round(avg_importance, 3),
            "db_size_kb": self.db_path.stat().st_size // 1024 if self.db_path.exists() else 0,
        }


# 全局单例
_store: Optional[ColdMemoryStore] = None

def get_cold_memory() -> ColdMemoryStore:
    global _store
    if _store is None:
        _store = ColdMemoryStore()
    return _store

def recall(query: str, limit: int = 5) -> List[MemoryFragment]:
    """快捷检索：从冷记忆中查找相关内容"""
    return get_cold_memory().search(query, limit)

def remember(content: str, category: str = "general",
             importance: float = 0.5, tags: str = "") -> str:
    """快捷存储：存一条记忆碎片"""
    return get_cold_memory().store_fragment(content, category, importance, tags=tags)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # 自测
    store = ColdMemoryStore()

    # 存几条测试记忆
    id1 = store.store_fragment("小谷的生日是1992-07-11", "person", 0.9, tags="小谷,生日")
    id2 = store.store_fragment("juhuo项目只给建议不动手", "decision", 0.95, tags="juhuo,红线")
    id3 = store.store_fragment("PowerShell GBK编码问题用Python脚本绕过", "lesson", 0.8, tags="PowerShell,编码,GBK")

    # 检索
    results = store.search("小谷")
    print(f"搜索'小谷': {len(results)}条")
    for r in results:
        print(f"  [{r.category}] {r.content} (importance={r.importance})")

    results2 = store.search("编码")
    print(f"搜索'编码': {len(results2)}条")
    for r in results2:
        print(f"  [{r.category}] {r.content}")

    # 统计
    print(f"\nStats: {store.stats()}")

    # 清理测试数据
    with store._conn() as c:
        c.execute("DELETE FROM memory_fragments WHERE source=''")
        c.commit()
    print("Test data cleaned. OK")
