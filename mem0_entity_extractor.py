"""
mem0_entity_extractor.py — 实体提取与链接系统（基于 mem0 v3 架构）

实体类型（4类，来自 mem0 utils/entity_extraction.py）：
1. PROPER   — 大写专有名词序列（人名、地名、品牌、项目名）
2. QUOTED   — 引号内文本（标题、术语）
3. COMPOUND — 名词复合结构（"机器学习"、"趋势跟踪"）
4. NOUN     — 非复合名词回路

核心功能：
- extract(text) → 从文本提取实体
- link_entity(entity_name, memory_id) → 链接实体到记忆
- query_boost(query) → 实体加权检索
- store → memory/entities.json

简化：qclaw 无 spaCy，用规则 + LLM 两层提取

Updated: 2026-05-15 — 落地自 mem0ai/mem0 v3
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# === 规则层：不需要 LLM 的快速提取 ===

# 中文姓氏（常见）
_CN_SURNAMES = {"王","李","张","刘","陈","杨","黄","赵","周","吴","徐","孙","马","胡","朱","郭","何","罗","高","林","郑","梁","谢","宋","唐","许","邓","韩","冯","曹","彭","曾","萧","田","董","潘","袁","蔡","余","蒋","叶","于","杜","苏","魏","吕","丁","任","卢","姚","钟","姜","崔","谭","廖","范","汪","金","陆","郝","孔","白","崔","康","毛","邱","孟","秦","江","史","顾","侯","邵","龙","万","雷","段","钱","汤","尹","易","常","武","乔","贺","赖","龚","文"}

# 项目/工具关键词（qclaw 生态内）
_KNOWN_PROJECTS = {
    "qclaw", "qwenpaw", "copaw", "openclaw", "mem0", "viki",
    "lianghua", "juhuo", "gstack", "hermes", "codex", "qlib",
    "evolver", "gitnexus", "ruflo", "brain", "archon", "symphony",
    "zeushammer", "openspace", "quantdinger", "tradingagents",
    "sensenova", "blender", "mcporter", "playwright",
}

# 关键词匹配模式
_PROJECT_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(p) for p in _KNOWN_PROJECTS) + r')\b',
    re.IGNORECASE
)

# 引号内文本
_QUOTED_PATTERN = re.compile(r'[「『"]([^「『」』"]+)[」』"]')

# 反引号内的代码/技术术语
_BACKTICK_PATTERN = re.compile(r'`([^`]+)`')

# 大驼峰命名（PROPER）
_CAMELCASE_PATTERN = re.compile(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b')

# Markdown 链接 [text](url)
_MD_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\([^)]+\)')


def _extract_proper_nouns(text: str) -> List[str]:
    """提取 PROPER 类型：大写驼峰词 + 中文人名 + 已知项目名."""
    entities = []

    # 驼峰命名
    for m in _CAMELCASE_PATTERN.finditer(text):
        entities.append(m.group(1))

    # 中文人名（2-3字，姓+名）
    for m in re.finditer(r'([%s][\u4e00-\u9fff]{1,2})' % ''.join(_CN_SURNAMES), text):
        name = m.group(1)
        # 过滤掉非人名
        if name not in {"我们", "他们", "你们", "这个", "那个", "一个", "什么", "怎么", "为什么", "可以", "没有", "不是", "不会", "应该", "需要", "可能"}:
            entities.append(name)

    # 已知项目名
    for m in _PROJECT_PATTERN.finditer(text):
        entities.append(m.group(1))

    return entities


def _extract_quoted(text: str) -> List[str]:
    """提取 QUOTED 类型：引号内 / 反引号内."""
    entities = []
    for m in _QUOTED_PATTERN.finditer(text):
        entities.append(m.group(1))
    return entities


def _extract_compound_nouns(text: str) -> List[str]:
    """提取 COMPOUND 类型：关键词组合."""
    entities = []

    # Markdown 链接文本
    for m in _MD_LINK_PATTERN.finditer(text):
        entities.append(m.group(1))

    # 中文 2-4 字关键词（大写开头）
    for m in re.finditer(r'[\u4e00-\u9fff]{2,4}', text):
        word = m.group(0)
        # 过滤纯标点/数字/虚词
        if word[0] not in '的了一是在不和有我这他' and word not in {'这个', '那个', '我们', '什么', '没有'}:
            entities.append(word)

    return entities


def _extract_nouns(text: str) -> List[str]:
    """提取 NOUN 类型：技术术语、文件名、路径."""
    entities = []

    # 反引号内术语
    for m in _BACKTICK_PATTERN.finditer(text):
        term = m.group(1)
        if 3 <= len(term) <= 50:
            entities.append(term)

    # 文件路径
    for m in re.finditer(r'[A-Za-z]:\\[^\s,，。]+|[\w/]+\.(py|md|json|js|ts|html|css|yaml|yml|toml|sh|bat|ps1)', text):
        entities.append(m.group(0))

    # URL
    for m in re.finditer(r'https?://[^\s,，。]+', text):
        entities.append(m.group(0))

    return entities


def extract_entities_rule(text: str) -> List[Tuple[str, str]]:
    """
    规则层实体提取（无 LLM，仅靠正则）。
    返回 [(entity_type, entity_text), ...]
    """
    entities: List[Tuple[str, str]] = []

    for entity in _extract_proper_nouns(text):
        entities.append(("PROPER", entity))

    for entity in _extract_quoted(text):
        entities.append(("QUOTED", entity))

    for entity in _extract_compound_nouns(text):
        entities.append(("COMPOUND", entity))

    for entity in _extract_nouns(text):
        entities.append(("NOUN", entity))

    # 去重（保留最高优先级类型）
    type_pri = {"PROPER": 0, "COMPOUND": 1, "QUOTED": 2, "NOUN": 3}
    best: Dict[str, Tuple[str, str]] = {}
    for etype, etext in entities:
        key = etext.lower().strip()
        if len(key) <= 1:
            continue
        if key not in best or type_pri.get(etype, 99) < type_pri.get(best[key][0], 99):
            best[key] = (etype, etext)

    return list(best.values())


# === LLM 层：精确提取 ===

# 提取 prompt（模拟 mem0 的 ADDITIVE_EXTRACTION_PROMPT 风格）
ENTITY_EXTRACTION_PROMPT = """从以下对话中提取实体（人名、项目名、工具名、技术术语、文件路径等）。

只输出 JSON 数组，每个元素包含 type 和 text：
- type: PROPER(专有名词/人名/项目名) / COMPOUND(复合术语) / QUOTED(引用的内容) / NOUN(文件/路径/URL)
- text: 实体文本

对话内容：
{conversation}

只输出 JSON，不要任何其他文字。"""


def extract_entities_llm(text: str, llm_call_fn=None) -> List[Tuple[str, str]]:
    """
    LLM 层实体提取。
    llm_call_fn: 可选的 LLM 调用函数，签名 (prompt: str) -> str
    """
    if llm_call_fn is None:
        return []

    prompt = ENTITY_EXTRACTION_PROMPT.format(conversation=text[:3000])
    try:
        response = llm_call_fn(prompt)
        # 提取 JSON
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group(0))
            return [(item["type"], item["text"]) for item in items if item.get("text")]
    except Exception:
        pass
    return []


# === 实体存储 ===

class EntityStore:
    """实体存储与链接管理."""

    def __init__(self, store_path: str = "memory/entities.json"):
        self.store_path = Path(store_path)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.store_path.exists():
            try:
                self._data = json.loads(self.store_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def upsert(
        self,
        entity_name: str,
        entity_type: str,
        memory_id: Optional[str] = None,
        source: str = "conversation",
    ) -> None:
        """插入或更新实体。"""
        key = entity_name.lower().strip()

        if key in self._data:
            # 更新现有实体
            existing = self._data[key]
            if memory_id and memory_id not in existing.get("linked_memory_ids", []):
                existing.setdefault("linked_memory_ids", []).append(memory_id)
            existing["updated_at"] = datetime.now(timezone.utc).isoformat()
            existing["count"] = existing.get("count", 0) + 1
        else:
            # 新建实体
            self._data[key] = {
                "name": entity_name,
                "type": entity_type,
                "linked_memory_ids": [memory_id] if memory_id else [],
                "source": source,
                "count": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        self._save()

    def upsert_batch(
        self,
        entities: List[Tuple[str, str]],
        memory_id: Optional[str] = None,
    ) -> int:
        """批量插入实体。返回新增数."""
        added = 0
        for etype, etext in entities:
            key = etext.lower().strip()
            if key not in self._data:
                added += 1
            self.upsert(etext, etype, memory_id)
        return added

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """搜索实体。"""
        query_lower = query.lower()
        results = []

        for key, data in self._data.items():
            # 简单匹配：实体名在 query 中，或 query 在实体名中
            if query_lower in key or key in query_lower:
                results.append(data)

        # 按 count（出现频率）排序
        results.sort(key=lambda x: x.get("count", 0), reverse=True)
        return results[:top_k]

    def get_boosted_memory_ids(self, query: str) -> Dict[str, float]:
        """
        获取查询相关的实体加权。
        返回 {memory_id: boost_weight, ...}
        """
        entities = self.search(query, top_k=20)
        boosts: Dict[str, float] = {}

        for entity in entities:
            weight = 0.5 * min(entity.get("count", 1) / 5.0, 1.0)  # 出现频率越高，权重越大
            for mid in entity.get("linked_memory_ids", []):
                boosts[mid] = boosts.get(mid, 0) + weight

        return boosts

    def remove_memory(self, memory_id: str) -> None:
        """从所有实体中移除指定的 memory 链接."""
        modified = False
        for key, data in self._data.items():
            linked = data.get("linked_memory_ids", [])
            if memory_id in linked:
                linked.remove(memory_id)
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                modified = True
                # 如果链接为空且 count=1，考虑清理
        if modified:
            self._save()

    def get_stats(self) -> Dict[str, Any]:
        """获取实体存储统计."""
        types = {}
        for data in self._data.values():
            t = data.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        return {
            "total_entities": len(self._data),
            "by_type": types,
            "total_links": sum(len(d.get("linked_memory_ids", [])) for d in self._data.values()),
        }


# === CLI 测试 ===

if __name__ == "__main__":
    store = EntityStore()

    # 测试文本
    test_texts = [
        "小谷让我把mem0落地到qclaw的③记忆层",
        "QwenPaw配置在C:\\Users\\yiseg\\.copaw\\，不是.qwenpaw",
        "evolver.py要加AgentFact，跟self_review联动",
        "我写了'mem0_hybrid_search.py'这个文件",
    ]

    for text in test_texts:
        entities = extract_entities_rule(text)
        print(f"\n--- 文本: {text[:60]}... ---")
        for etype, etext in entities:
            print(f"  [{etype}] {etext}")
        store.upsert_batch(entities)

    print(f"\n=== 实体存储统计 ===")
    stats = store.get_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    # 搜索测试
    print(f"\n=== 搜索 'qclaw' ===")
    for r in store.search("qclaw"):
        print(f"  {r['name']} ({r['type']}) — 出现{r['count']}次")