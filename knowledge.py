# -*- coding: utf-8 -*-
"""
knowledge.py — 知识管理系统

从"文件堆砌"升级为"可检索、可关联、可进化"的知识库。

来源：Superpowers + Claude Code 记忆理念
- 只存不可推导的知识
- 新鲜度追踪
- 按主题关联
- TDD for skills 的经验也归档

用法：
  python knowledge.py add <source> <summary>
  python knowledge.py search <query>
  python knowledge.py recent
  python knowledge.py stats
  python knowledge.py link <id1> <id2> <relation>
"""

import json
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

WORKSPACE = Path(__file__).parent
KB_PATH = WORKSPACE / ".knowledge_db.json"


@dataclass
class KnowledgeEntry:
    """一条知识条目"""
    id: str
    source: str           # 来源：superpowers / claude-code / deer-flow / ...
    summary: str          # 摘要（一句话）
    key_points: list      # 关键点
    tags: list            # 标签
    relevance: str         # 对我有什么用
    created_at: str
    last_accessed: str = ""
    access_count: int = 0
    linked_to: list = field(default_factory=list)  # 关联的其他条目


class KnowledgeBase:
    def __init__(self):
        self.entries = self._load()

    def _load(self) -> list:
        if KB_PATH.exists():
            try:
                return json.loads(KB_PATH.read_text(encoding="utf-8"))
            except:
                return []
        return []

    def _save(self):
        KB_PATH.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _new_id(self) -> str:
        n = len(self.entries) + 1
        ts = time.strftime("%Y%m%d")
        return f"kb_{ts}_{n}"

    def add(self, source: str, summary: str, key_points: list = None,
            tags: list = None, relevance: str = "") -> str:
        """添加一条知识"""
        entry = KnowledgeEntry(
            id=self._new_id(),
            source=source,
            summary=summary,
            key_points=key_points or [],
            tags=tags or self._infer_tags(source, summary),
            relevance=relevance,
            created_at=time.strftime("%Y-%m-%d %H:%M"),
        )
        self.entries.append(asdict(entry))
        self._save()
        return entry.id

    def search(self, query: str, limit: int = 5) -> list:
        """检索知识（关键词匹配）"""
        q = query.lower()
        scored = []
        for e in self.entries:
            score = 0
            text = " ".join([e["summary"]] + e.get("key_points", []) + e.get("tags", []))
            text_l = text.lower()

            # 精确匹配分数更高
            if q in e["source"].lower(): score += 3
            if q in e["summary"].lower(): score += 5
            for kw in q.split():
                if kw in text_l: score += 1

            if score > 0:
                # 更新访问记录
                e["access_count"] = e.get("access_count", 0) + 1
                e["last_accessed"] = time.strftime("%Y-%m-%d %H:%M")
                scored.append((score, e))

        scored.sort(key=lambda x: -x[0])
        self._save()
        return [e for _, e in scored[:limit]]

    def recent(self, limit: int = 10) -> list:
        """最近添加的知识"""
        sorted_entries = sorted(self.entries, key=lambda e: e["created_at"], reverse=True)
        return sorted_entries[:limit]

    def link(self, id1: str, id2: str, relation: str):
        """关联两条知识"""
        for e in self.entries:
            if e["id"] == id1 and id2 not in e.get("linked_to", []):
                e.setdefault("linked_to", []).append(f"{id2}|{relation}")
            if e["id"] == id2 and id1 not in e.get("linked_to", []):
                e.setdefault("linked_to", []).append(f"{id1}|{relation}")
        self._save()

    def stats(self) -> dict:
        """统计"""
        by_source = {}
        for e in self.entries:
            src = e["source"]
            by_source[src] = by_source.get(src, 0) + 1
        return {
            "total": len(self.entries),
            "by_source": by_source,
            "most_accessed": sorted(self.entries, key=lambda e: -e.get("access_count", 0))[:3],
        }

    def _infer_tags(self, source: str, summary: str) -> list:
        """自动推断标签"""
        tags = [source]
        text = summary.lower()

        tag_map = {
            "hook": ["hook", "事件", "生命周期"],
            "skill": ["skill", "技能", "skill.md"],
            "tdd": ["tdd", "测试", "baseline"],
            "rationalization": ["rationalization", "借口", "合理化"],
            "token": ["token", "预算", "context"],
            "fork": ["fork", "子agent", "隔离"],
            "compaction": ["compaction", "压缩", "归档"],
            "evolution": ["evolution", "进化", "learning"],
        }

        for tag, keywords in tag_map.items():
            if any(kw in text for kw in keywords):
                tags.append(tag)

        return tags[:5]

    def get_insights(self) -> str:
        """生成知识洞察（跨条目关联）"""
        if len(self.entries) < 3:
            return "(知识量不足，积累更多后生成洞察)"

        by_tag = {}
        for e in self.entries:
            for tag in e.get("tags", []):
                by_tag.setdefault(tag, []).append(e)

        insights = []
        for tag, entries in sorted(by_tag.items(), key=lambda x: -len(x[1])):
            if len(entries) >= 2:
                summaries = [f"  - {e['summary'][:60]}" for e in entries[:3]]
                insights.append(f"[{tag}] ({len(entries)}条)\n" + "\n".join(summaries))

        return "\n\n".join(insights[:5]) if insights else "(暂无关联洞察)"


def main():
    if len(sys.argv) < 2:
        print("Knowledge Base — 知识管理系统")
        print("")
        print("用法:")
        print("  python knowledge.py add <source> <summary> [tags...]")
        print("  python knowledge.py search <query>")
        print("  python knowledge.py recent [limit]")
        print("  python knowledge.py link <id1> <id2> <relation>")
        print("  python knowledge.py stats")
        print("  python knowledge.py insights")
        return

    kb = KnowledgeBase()
    cmd = sys.argv[1]

    if cmd == "add" and len(sys.argv) >= 4:
        source = sys.argv[2]
        summary = sys.argv[3]
        tags = sys.argv[4:] if len(sys.argv) > 4 else None
        eid = kb.add(source, summary, tags=tags)
        print(f"[ADDED] {eid} from {source}")
        print(f"  {summary[:80]}")

    elif cmd == "search" and len(sys.argv) >= 3:
        query = " ".join(sys.argv[2:])
        results = kb.search(query)
        if not results:
            print("[NONE] 没有找到相关知识")
        for e in results:
            age = _age(e["created_at"])
            print(f"\n[{e['id']}] {e['source']} ({age})")
            print(f"  {e['summary']}")
            if e.get("key_points"):
                for p in e["key_points"][:3]:
                    print(f"  > {p[:80]}")

    elif cmd == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        for e in kb.recent(limit):
            age = _age(e["created_at"])
            print(f"[{e['id']}] {e['source']} {age}")
            print(f"  {e['summary'][:70]}")

    elif cmd == "link" and len(sys.argv) >= 5:
        kb.link(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"[LINKED] {sys.argv[2]} --{sys.argv[4]}--> {sys.argv[3]}")

    elif cmd == "stats":
        s = kb.stats()
        print(f"Total: {s['total']} 条知识")
        print(f"\nBy source:")
        for src, count in s["by_source"].items():
            print(f"  {src}: {count}")
        if s["most_accessed"]:
            print(f"\nMost accessed:")
            for e in s["most_accessed"]:
                print(f"  x{e['access_count']} {e['summary'][:60]}")

    elif cmd == "insights":
        print(kb.get_insights())

    else:
        print("Unknown command:", cmd)


def _age(timestamp: str) -> str:
    """转为人可读的时间差"""
    try:
        past = time.mktime(time.strptime(timestamp, "%Y-%m-%d %H:%M"))
        diff = time.time() - past
        days = int(diff / 86400)
        hours = int(diff / 3600)
        if days > 0:
            return f"{days}d ago"
        elif hours > 0:
            return f"{hours}h ago"
        else:
            return "just now"
    except:
        return timestamp


if __name__ == "__main__":
    main()
