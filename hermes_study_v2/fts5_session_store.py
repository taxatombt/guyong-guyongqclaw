"""FTS5 Session Store - SQLite-backed Session Storage with Full-Text Search

Based on Hermes hermes_state.py (1238 lines).
SQLite with WAL mode, FTS5 virtual table for message search,
and sanitized query handling.

Usage:
    from fts5_session_store import SessionStore
    store = SessionStore()
    store.create_session("cli", "user123")
    store.append_message(sid, "user", "Hello")
    results = store.search_messages("python error", limit=10)
"""

import json
import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    user_id TEXT,
    model TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    message_count INTEGER DEFAULT 0,
    title TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    finish_reason TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);
CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


class SessionStore:
    """SQLite-backed session storage with FTS5 search."""

    def __init__(self, db_path: str = "~/.qclaw/sessions.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA_SQL)
            conn.executescript(FTS_SQL)
            conn.commit()
            conn.close()

    def _execute_write(self, fn) -> Any:
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                return fn(conn)
            finally:
                conn.commit()
                conn.close()

    def create_session(self, source: str, user_id: str = None, model: str = None) -> str:
        import uuid
        sid = str(uuid.uuid4())

        def _do(conn):
            conn.execute(
                "INSERT INTO sessions (id, source, user_id, model, started_at) VALUES (?, ?, ?, ?, ?)",
                (sid, source, user_id, model, time.time()),
            )
        self._execute_write(_do)
        return sid

    def end_session(self, session_id: str, reason: str = None) -> None:
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (time.time(), session_id),
            )
        self._execute_write(_do)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str = None,
        tool_name: str = None,
        token_count: int = None,
        finish_reason: str = None,
    ) -> int:
        def _do(conn):
            cursor = conn.execute(
                """INSERT INTO messages (session_id, role, content, tool_name, timestamp, token_count, finish_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, tool_name, time.time(), token_count, finish_reason),
            )
            msg_id = cursor.lastrowid
            conn.execute(
                "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                (session_id,),
            )
            return msg_id
        return self._execute_write(_do)

    def get_messages(self, session_id: str) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.execute(
                "SELECT id, session_id, role, content, tool_name, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY timestamp, id",
                (session_id,),
            )
            msgs = []
            for row in cursor.fetchall():
                msgs.append(dict(zip(
                    ["id", "session_id", "role", "content", "tool_name", "timestamp"],
                    row
                )))
            conn.close()
            return msgs

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Sanitize FTS5 query. Protect quoted phrases, strip special chars."""
        quoted = []
        def _protect(m):
            quoted.append(m.group(0))
            return f"\x00Q{len(quoted)-1}\x00"
        sanitized = re.sub(r'"[^"]*"', _protect, query)
        sanitized = re.sub(r'[+{}()\"^]', " ", sanitized)
        sanitized = re.sub(r"\*+", "*", sanitized)
        sanitized = re.sub(r"(^|\s)\*", r"\1", sanitized)
        sanitized = re.sub(r"(?i)^(AND|OR|NOT)\b\s*", "", sanitized.strip())
        sanitized = re.sub(r"(?i)\s+(AND|OR|NOT)\s*$", "", sanitized.strip())
        sanitized = re.sub(r"\b(\w+(?:[.-]\w+)+)\b", r'"\1"', sanitized)
        for i, q in enumerate(quoted):
            sanitized = sanitized.replace(f"\x00Q{i}\x00", q)
        return sanitized.strip()

    def search_messages(
        self,
        query: str,
        source_filter: list[str] = None,
        role_filter: list[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        if not query or not query.strip():
            return []
        query = self._sanitize_fts5_query(query)
        if not query:
            return []

        params = [query]
        where = ["messages_fts MATCH ?"]
        if source_filter:
            ph = ",".join("?" * len(source_filter))
            where.append(f"s.source IN ({ph})")
            params.extend(source_filter)
        if role_filter:
            ph = ",".join("?" * len(role_filter))
            where.append(f"m.role IN ({ph})")
            params.extend(role_filter)
        where_sql = " AND ".join(where)
        params.extend([limit])

        sql = f"""
            SELECT m.id, m.session_id, m.role,
                   snippet(messages_fts, 0, '>>>', '<<<', '...', 40) AS snippet,
                   m.content, m.timestamp, s.source, s.model
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE {where_sql}
            ORDER BY rank
            LIMIT ? OFFSET 0
        """

        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                cursor = conn.execute(sql, params)
                results = []
                for row in cursor.fetchall():
                    r = dict(zip(
                        ["id", "session_id", "role", "snippet", "content", "timestamp", "source", "model"],
                        row
                    ))
                    r.pop("content", None)
                    results.append(r)
            except sqlite3.OperationalError:
                results = []
            finally:
                conn.close()
        return results

    def list_sessions(self, limit: int = 20, offset: int = 0) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.execute(
                "SELECT id, source, user_id, model, started_at, message_count, title "
                "FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            cols = ["id", "source", "user_id", "model", "started_at", "message_count", "title"]
            results = [dict(zip(cols, row)) for row in cursor.fetchall()]
            conn.close()
            return results


if __name__ == "__main__":
    store = SessionStore()
    sid = store.create_session("test", "test_user")
    print(f"Created: {sid}")
    store.append_message(sid, "user", "Hello world")
    store.append_message(sid, "assistant", "Hi!")
    results = store.search_messages("hello")
    print(f"Search: {len(results)} results")
