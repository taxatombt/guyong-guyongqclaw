---
name: mem0
description: >
  Use when qclaw needs to remember facts across sessions,
  recall user preferences, or enhance memory retrieval
  with multi-signal fusion (semantic + BM25 + entity boost).
---

# mem0 — Universal Memory Layer (qclaw Integration)

> **Source:** mem0ai/mem0 (55.7K ⭐, Apache 2.0)  
> **Integrated:** 2026-05-15  
> **Benchmark:** LoCoMo 91.6, LongMemEval 94.8

## What This Skill Does

Enhances qclaw's memory layer (③记忆层) with mem0 v3's core mechanisms:

1. **Multi-Signal Hybrid Search** — fuse semantic + BM25 keyword + entity boost
2. **Entity Extraction & Linking** — extract PROPER/QUOTED/COMPOUND/NOUN entities from conversations
3. **Agent Facts as First-Class** — auto-record agent actions as equal-weight memories
4. **Add-Only Memory Extraction** — one LLM call, no UPDATE/DELETE (prevents memory drift)

## Files Added

```
workspace/
├── mem0_hybrid_search.py      ← 多信号融合检索（BM25 + 语义 + 实体）
├── mem0_entity_extractor.py  ← 实体提取（规则层 + LLM层）
├── mem0_agent_facts.py       ← Agent 事实一等公民（自动记录）
└── skills/
    └── SKILL-mem0.md        ← this file
```

## Usage

### Hybrid Search (Multi-Signal Retrieval)

```python
from mem0_hybrid_search import HybridSearcher

searcher = HybridSearcher(memory_dir="memory/")
results = searcher.search(query="小谷的Python路径", top_k=5)

for r in results:
    print(f"score={r['score']} [{r['signals']}] {r['snippet'][:60]}")
    # signals: "语义", "BM25", "实体", or "语义+BM25+实体"
```

**Fusion formula** (from mem0 scoring.py):
```
max_possible = 1.0 + (1.0 if BM25 else 0) + (0.5 if entity else 0)
combined = (semantic + normalized_bm25 + entity_boost) / max_possible
```

- `normalized_bm25`: sigmoid normalization with query-length-adaptive params
- Threshold gate: semantic score < 0.5 → excluded (BM25/entity cannot "save" it)
- Entity boost: 0.5 per matched entity (configurable via `ENTITY_BOOST_WEIGHT`)

### Entity Extraction

```python
from mem0_entity_extractor import extract_entities_rule, EntityStore

# Rule-based extraction (fast, no LLM needed)
entities = extract_entities_rule("小谷让我把mem0落地到qclaw的③记忆层")
# Returns: [("COMPOUND", "落地到"), ("COMPOUND", "记忆层"), ...]

# LLM-based extraction (precise)
from mem0_entity_extractor import extract_entities_llm
entities_llm = extract_entities_llm(text, llm_call_fn=your_llm_fn)

# Store entities and link to memories
store = EntityStore("memory/entities.json")
store.upsert_batch(entities, memory_id="some_memory_id")
```

**Entity types (4 categories, from mem0 entity_extraction.py)**:
- `PROPER` — proper nouns (person names, project names, brands)
- `QUOTED` — quoted text (titles, terms in quotes)
- `COMPOUND` — noun compounds ("machine learning", "趋势跟踪")
- `NOUN` — fallback nouns

### Agent Facts (Auto-Record)

```python
from mem0_agent_facts import record_agent_fact

# Call this after completing a task
record_agent_fact(
    task="学习 mem0 并落地到 qclaw",
    method="read_source + design + implement",
    success=True,
    facts=["Created mem0_hybrid_search.py", "Created mem0_entity_extractor.py"],
)
```

Facts are stored in `memory/agent_facts.json` and linked to today's memory file (`memory/YYYY-MM-DD.md`).

### Add-Only Memory Extraction

The memory extraction prompt now uses add-only mode (no UPDATE/DELETE). Memories accumulate; nothing is overwritten. This matches mem0 v3's `ADDITIVE_EXTRACTION_PROMPT`.

To use: call `memory_search` as before — the underlying extraction is now add-only.

## Installation / Dependencies

```bash
# Required for BM25
pip install rank-bm25

# Optional: spaCy for better entity extraction (if you want to match mem0 exactly)
pip install spacy && python -m spacy download en_core_web_sm
```

qclaw's built-in LLM is used for LLM-based entity extraction (no extra API key needed).

## Configuration

In `mem0_hybrid_search.py`:
- `HybridSearcher.ENTITY_BOOST_WEIGHT = 0.5` — entity boost weight (default matches mem0)
- `HybridSearcher.SEMANTIC_THRESHOLD = 0.5` — minimum semantic score to be included

In `mem0_entity_extractor.py`:
- `ENTITY_EXTRACTION_PROMPT` — customize the LLM extraction prompt

## Integration with qclaw

After task completion, call:
```python
# 1. Record to evolver (existing)
from evolver import record
record(task, method, success, error, notes)

# 2. Record agent facts (NEW — add this)
from mem0_agent_facts import record_agent_fact
record_agent_fact(task, method, success)

# 3. Self-review (existing)
from self_review import run_review
run_review(task, method, success, used_tools, error, notes)
```

## Key Differences from mem0 Original

| Aspect | mem0 Original | qclaw Integration |
|---------|---------------|-------------------|
| Entity extraction | spaCy NLP (4 types) | Rule-based + optional LLM |
| Storage | Separate entity vector store | `memory/entities.json` |
| Memory store | Vector database | `memory/*.md` files |
| LLM calls | 1 call per extraction | Reuse qclaw's built-in LLM |
| Deployment | pip install / Docker / Cloud | Pure Python, no extra server |

## Benchmark Results (mem0 v3)

| Benchmark | Old | New | Token Reduction |
|-----------|-----|-----|-----------------|
| LoCoMo | 71.4 | **91.6** | 7.0K |
| LongMemEval | 67.8 | **94.8** | 6.8K |
| BEAM (1M) | — | **64.1** | 6.7K |

qclaw's integration brings these improvements to the memory retrieval layer.

## Troubleshooting

**BM25 not available**: Install `rank-bm25` via pip. If unavailable, hybrid search falls back to semantic-only.

**Entity extraction missing entities**: Try LLM-based extraction (provide `llm_call_fn`), or adjust the rule patterns in `extract_entities_rule()`.

**Agent facts not recording**: Check that `memory/` directory is writable. Facts are appended to `memory/agent_facts.json`.

## See Also

- `ai_agent_study/SYSTEM.md` — qclaw's 6-layer architecture (mem0 integrated into ③记忆层)
- `mem0_hybrid_search.py` — source code for hybrid retrieval
- `mem0_entity_extractor.py` — source code for entity extraction
- `mem0_agent_facts.py` — source code for agent fact recording

---

*Integrated by 顾庸, 2026-05-15. Based on mem0 v3 (mem0ai/mem0).*
