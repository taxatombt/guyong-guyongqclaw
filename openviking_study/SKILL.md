---
name: openviking-context
description: |
  OpenViking Context Manager, landed from volcengine/OpenViking (24K stars).
  Enhanced: Experience 3-section, Working Memory 7-section, Directory-first Retrieval, Two-Phase Commit.
  Trigger words: openviking, viking, context db, agent context, memory taxonomy, experience, working memory
---

# OpenViking Context Manager - qclaw Enhanced Edition

## Source
**volcengine/OpenViking** by ByteDance (24K+ stars, AGPL-3.0)
This is an independent reimplementation of design patterns only.

## What Changed (v2 Enhanced)

| Feature | v1 | v2 |
|---------|----|----|
| Memory categories | 8 | **10** (+ experiences, trajectories) |
| Experience format | None | **3-section** (Situation/Approach/Reflect) |
| Working Memory | None | **7-section** with L0/L1 auto-gen |
| Retrieval | Flat text match | **Directory-first** (1.2x boost) |
| Session commit | Sync only | **Two-Phase** (pending/done) |
| L0/L1 auto-gen | None | **Automatic** on add_memory |

## Core Concepts

### 1. VikingURI (viking://scope/path)
```python
from openviking_study.openviking_context import VikingURI

uri = VikingURI.build("user", "memories/profile.md")
# viking://user/memories/profile.md
uri.parent    # viking://user/memories
uri.name      # "profile.md"
uri.join("entities")  # viking://user/memories/entities
```

### 2. Experience (3-Section Format)
The core innovation: executable, machine-readable agent experiences.

```python
from openviking_study.openviking_context import Experience

exp = Experience(
    name='docx_conversion_handling',
    situation={
        'intent': 'convert document format',
        'constraint': 'source is .doc (legacy)'
    },
    approach=[
        'Use soffice.py --headless --convert-to docx',
        'Set LANG=zh_CN.UTF-8 for CJK documents',
        'Verify output with pandoc --track-changes=all'
    ],
    reflect=[
        'Do NOT use pandoc directly for .doc files',
        'Do NOT skip encoding check for CJK content',
        'Do NOT hardcode encoding - detect from source'
    ]
)
exp.save(workspace)  # writes agent/memories/experiences/docx_conversion_handling.md
```

**Key rules:**
- Approach: ONLY positive commands (IF/THEN/ELSE)
- Reflect: ONLY negative constraints (NEVER/DON'T)
- Mutually exclusive: no overlap between Approach and Reflect
- Machine-readable: imperative voice, directly executable
- `supersedes` field: auto-deprecate old versions

### 3. Working Memory (7-Section)
Session-level structured summary, stored at L1 layer.

```python
from openviking_study.openviking_context import WorkingMemoryManager

wmm = WorkingMemoryManager(workspace)
wmm.start_session("review_001")
wmm.update("Session Title", "Code review: trading bot v2.3")
wmm.update("Current State", "Reviewing trading loop, 50% complete")
wmm.update("Task & Goals", "Verify thread safety, check signal logic")
wmm.update("Key Facts & Decisions", "Approved for production use")
wmm.update("Errors & Corrections", "Fixed: max_trades NameError")
wmm.update("Files & Context", "E:\\lianghua\\trend_trader.py (107KB)")
wmm.update("Open Issues", "16 modules zero integration")
wmm.commit()  # saves + auto-generates L0 (.abstract) and L1 (.overview)
```

**7 Sections:**
1. Session Title - one-line title
2. Current State - progress
3. Task & Goals - objectives/todo
4. Key Facts & Decisions - key facts/decisions
5. Files & Context - involved files
6. Errors & Corrections - errors and fixes
7. Open Issues - unresolved items

**Section-level merge:** Each section can be KEEP (preserve old) or UPDATE (replace).

### 4. Directory-first Retrieval
```python
results = workspace.find("trading bot", use_dir_first=True)
# Returns directories first if dir_score > max_child_score * 1.2
# Then individual files within those directories
```

Algorithm:
1. Score all files by text match count
2. Aggregate scores by directory: `dir_score = max(child_scores) * 1.2`
3. Return high-score directories before their children
4. Sort by score descending

### 5. Two-Phase Commit (SessionContextAdapter)
```python
adapter = SessionContextAdapter(workspace)
adapter.add_message("user", "I decided to deploy the project")
result = adapter.commit()
# Phase 1: sync write to .pending/ -> returns task_id
# Phase 2: async extraction -> 10 categories checked
# poll_pending() to check status
```

### 6. 10 Memory Categories

| Category | Scope | Strategy | Description |
|----------|-------|----------|-------------|
| profile | user | merge | Identity, role, style |
| preferences | user | merge | Topic preferences |
| entities | user | append | People, projects |
| events | user | append | Decisions, milestones |
| cases | agent | no_update | Learned cases |
| patterns | agent | merge | Reusable patterns |
| tools | agent | merge | Tool knowledge |
| skills | agent | merge | Skill knowledge |
| **experiences** | **agent** | **replace** | **3-section format** |
| **trajectories** | **agent** | **append** | **Call trajectory history** |

### 7. L0/L1/L2 Auto-generation
Every `add_memory()` call automatically generates:
- `*.abstract.md` (L0, ~100 tokens) - one-sentence overview
- `*.overview.md` (L1, ~2k tokens) - structured summary with WM sections
- Original file (L2) - full content

## Six-Layer Architecture Contribution

| Layer | Contribution | Rating |
|-------|-------------|--------|
| 3 Memory | 10-category taxonomy + progressive L0/L1/L2 + Experience 3-section + WM 7-section | 4 fire |
| 2 Cognitive | Context type classification (Resource/Memory/Skill) | 3 fire |
| 6 Evolution | Experience format + Session->Commit->Extract pipeline | 3 fire |

## Integration with Existing Systems

| System | Role | OpenViking Role |
|--------|------|----------------|
| TDAI | How to extract | How to organize |
| mem0 | How to retrieve | How to store/classify |
| Evolver | Error recording | Experience format + Reflect |
| Viki | Compiled wiki | VikingURI namespace |

## Experimental Data (from OpenViking paper)
- Task completion: 35.65% -> 52.08% (+46%)
- Token consumption: -83% to -96%
- Source: OpenClaw Plugin integration experiment