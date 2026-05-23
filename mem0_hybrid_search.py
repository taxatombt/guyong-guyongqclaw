"""
mem0_hybrid_search.py — 多信号融合检索（基于 mem0 v3 架构）

融合三种信号：
1. 语义检索（通过 memory_search 工具）
2. BM25 关键词匹配（rank-bm25 + sigmoid 归一化）
3. 实体加权（从 mem0_entity_extractor 获取）

融合公式（来自 mem0 utils/scoring.py）：
  max_possible = 1.0 + (1.0 if bm25 else 0) + (0.5 if entity else 0)
  combined = (semantic + normalized_bm25 + entity_boost) / max_possible

阈值门控：语义分数不达标的直接排除，不允许 BM25/实体"救回来"

Updated: 2026-05-15 — 落地自 mem0ai/mem0 v3
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


# === BM25 查询长度自适应 Sigmoid 参数（来自 mem0 utils/scoring.py） ===

def get_bm25_params(num_terms: int) -> Tuple[float, float]:
    """查询长度自适应的 sigmoid 参数 (midpoint, steepness)."""
    if num_terms <= 3:
        return 5.0, 0.7
    elif num_terms <= 6:
        return 7.0, 0.6
    elif num_terms <= 9:
        return 9.0, 0.5
    elif num_terms <= 15:
        return 10.0, 0.5
    else:
        return 12.0, 0.5


def normalize_bm25(raw_score: float, midpoint: float, steepness: float) -> float:
    """Sigmoid 归一化 BM25 到 [0, 1]."""
    return 1.0 / (1.0 + math.exp(-steepness * (raw_score - midpoint)))


# === 主类 ===

class HybridSearcher:
    """
    多信号融合检索器。

    Usage:
        searcher = HybridSearcher(memory_dir="memory/")
        results = searcher.search("小谷的Python路径", top_k=10)
    """

    ENTITY_BOOST_WEIGHT = 0.5  # 实体加成权重（与 mem0 一致）
    SEMANTIC_THRESHOLD = 0.5   # 语义分最低阈值

    def __init__(
        self,
        memory_dir: str = "memory/",
        entity_file: str = "memory/entities.json",
    ):
        self.memory_dir = Path(memory_dir)
        self.entity_file = Path(entity_file)
        self._bm25 = None
        self._doc_ids: List[str] = []       # 文档 ID 列表
        self._doc_texts: List[str] = []     # 文档文本列表
        self._entities: Dict[str, Any] = {}  # 实体索引

    # ----- 文档加载 -----

    def load_memory_docs(self) -> None:
        """从 memory/ 目录加载所有 .md 文件作为文档."""
        self._doc_ids = []
        self._doc_texts = []

        if not self.memory_dir.exists():
            return

        for md_file in sorted(self.memory_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # 按段落分割文档
            sections = self._split_into_sections(text, md_file.stem)
            for sec_id, sec_text in enumerate(sections):
                doc_id = f"{md_file.stem}#{sec_id}"
                self._doc_ids.append(doc_id)
                self._doc_texts.append(sec_text)

    def _split_into_sections(self, text: str, base_id: str) -> List[str]:
        """将文档按 ## 标题分割为段落."""
        sections = []
        current_section = []
        for line in text.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections.append("\n".join(current_section))
                current_section = [line]
            else:
                current_section.append(line)
        if current_section:
            sections.append("\n".join(current_section))
        return sections if sections else [text]  # 至少一个段落

    def _tokenize(self, text: str) -> List[str]:
        """简单中文+英文分词."""
        # 中文字符间加空格
        text = re.sub(r'([\u4e00-\u9fff])', r' \1 ', text)
        # 去除标点、转小写
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9_]+', text.lower())
        return tokens

    # ----- BM25 -----

    def build_bm25(self) -> None:
        """构建 BM25 索引."""
        if not HAS_BM25:
            return
        tokenized = [self._tokenize(doc) for doc in self._doc_texts]
        self._bm25 = BM25Okapi(tokenized)

    def _bm25_search(self, query: str, top_k: int = 10) -> Dict[str, float]:
        """BM25 关键词检索，返回 {doc_id: normalized_score}."""
        if self._bm25 is None or not self._doc_texts:
            return {}

        tokens = self._tokenize(query)
        num_terms = len(tokens)
        midpoint, steepness = get_bm25_params(num_terms)

        raw_scores = self._bm25.get_scores(tokens)
        result = {}
        for i, raw in enumerate(raw_scores):
            if raw <= 0:
                continue
            normalized = normalize_bm25(raw, midpoint, steepness)
            if normalized > 0.05:  # 忽略极低分
                result[self._doc_ids[i]] = normalized

        # 取 top_k
        sorted_items = sorted(result.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_items[:top_k])

    # ----- 实体加权 -----

    def load_entities(self) -> None:
        """加载实体索引."""
        if self.entity_file.exists():
            self._entities = json.loads(self.entity_file.read_text(encoding="utf-8"))

    def _entity_boost(self, query: str) -> Dict[str, float]:
        """
        实体加权检索。
        如果 query 命中某个实体名，给该实体关联的所有 memory 加权。
        """
        if not self._entities:
            return {}

        boosts: Dict[str, float] = {}
        query_lower = query.lower()

        for entity_name, entity_data in self._entities.items():
            if entity_name.lower() in query_lower:
                linked_ids = entity_data.get("linked_memory_ids", [])
                weight = self.ENTITY_BOOST_WEIGHT
                for mid in linked_ids:
                    # 查找该 ID 在哪些 doc_id 里
                    for doc_id in self._doc_ids:
                        if mid in doc_id:
                            boosts[doc_id] = boosts.get(doc_id, 0) + weight

        return boosts

    # ----- 融合检索 -----

    def search(
        self,
        query: str,
        semantic_results: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        多信号融合检索。

        Args:
            query: 查询文本
            semantic_results: 外部语义检索结果（来自 memory_search）
            top_k: 返回结果数

        Returns:
            排序后的结果列表，每条含 {id, score, text, snippet}
        """
        # 1. 构建/刷新 BM25
        self.load_memory_docs()
        self.build_bm25()
        self.load_entities()

        # 2. BM25 关键词检索
        bm25_scores = self._bm25_search(query, top_k=top_k * 2)

        # 3. 实体加权
        entity_boosts = self._entity_boost(query)

        # 4. 加载文档文本索引
        doc_text_map = dict(zip(self._doc_ids, self._doc_texts))

        # 5. 融合评分
        return self._score_and_rank(
            query=query,
            semantic_results=semantic_results or [],
            bm25_scores=bm25_scores,
            entity_boosts=entity_boosts,
            doc_text_map=doc_text_map,
            top_k=top_k,
        )

    def search_simple(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """纯 BM25 + 实体检索（无外部语义输入时使用）."""
        return self.search(query, semantic_results=[], top_k=top_k)

    def _score_and_rank(
        self,
        query: str,
        semantic_results: List[Dict[str, Any]],
        bm25_scores: Dict[str, float],
        entity_boosts: Dict[str, float],
        doc_text_map: Dict[str, str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        融合评分（mem0 风格 additive scoring）。
        combined = (semantic + bm25 + entity) / max_possible
        """

        has_bm25 = bool(bm25_scores)
        has_entity = bool(entity_boosts)

        max_possible = 1.0
        if has_bm25:
            max_possible += 1.0
        if has_entity:
            max_possible += self.ENTITY_BOOST_WEIGHT

        scored: List[Dict[str, Any]] = []

        # 收集所有候选 ID
        all_ids = set()

        # 来自语义检索
        semantic_map = {}
        for r in semantic_results:
            rid = str(r.get("id") or r.get("path") or "")
            if rid:
                all_ids.add(rid)
                semantic_map[rid] = r.get("score", 0.0)

        # 来自 BM25
        all_ids.update(bm25_scores.keys())

        # 来自实体加权
        all_ids.update(entity_boosts.keys())

        # 计算融合分数
        for rid in all_ids:
            sem = semantic_map.get(rid, 0.0)
            bm25 = bm25_scores.get(rid, 0.0)
            entity = entity_boosts.get(rid, 0.0)

            # 如果有语义检索结果，用阈值过滤
            if semantic_map and sem < self.SEMANTIC_THRESHOLD:
                continue

            raw_combined = sem + bm25 + entity
            combined = min(raw_combined / max_possible, 1.0)

            # 获取文本片段
            text = doc_text_map.get(rid, "")
            snippet = text[:200] + "..." if len(text) > 200 else text

            scored.append({
                "id": rid,
                "score": round(combined, 4),
                "semantic": round(sem, 4),
                "bm25": round(bm25, 4),
                "entity_boost": round(entity, 4),
                "snippet": snippet,
                "text": text,
                "signals": self._describe_signals(sem, bm25, entity),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _describe_signals(sem: float, bm25: float, entity: float) -> str:
        """描述使用了哪些信号."""
        parts = []
        if sem > 0:
            parts.append("语义")
        if bm25 > 0:
            parts.append("BM25")
        if entity > 0:
            parts.append("实体")
        return "+".join(parts) if parts else "无信号"

    # ----- 统计 -----

    def get_stats(self) -> Dict[str, Any]:
        """获取检索器统计."""
        return {
            "total_docs": len(self._doc_ids),
            "total_sections": len(self._doc_texts),
            "total_entities": len(self._entities),
            "has_bm25": HAS_BM25 and self._bm25 is not None,
            "has_entity_store": bool(self._entities),
        }


# === CLI 测试 ===

if __name__ == "__main__":
    import sys

    searcher = HybridSearcher()
    searcher.load_memory_docs()
    searcher.build_bm25()
    searcher.load_entities()

    query = sys.argv[1] if len(sys.argv) > 1 else "小谷"
    print(f"\n=== 融合检索: '{query}' ===")
    print(f"文档数: {len(searcher._doc_texts)}, 实体数: {len(searcher._entities)}")

    results = searcher.search(query, top_k=5)
    for i, r in enumerate(results):
        print(f"\n--- #{i+1} score={r['score']} [{r['signals']}] ---")
        print(f"  sem={r['semantic']}, bm25={r['bm25']}, entity={r['entity_boost']}")
        print(f"  {r['snippet'][:150]}")