# SKILL-mempalace.md — MemPalace 记忆系统学习笔记

> 来源：https://github.com/MemPalace/mempalace（54,494⭐）
> 整理：顾庸 | 2026-06-07

## 核心架构

MemPalace 是 Local-first AI 记忆系统，零 API 调用，LongMemEval R@5 96.6%。

### 存储层次

```
Palace（宫殿）
  ├── Wing（翼）— 人/项目
  │   ├── Room（室）— 话题
  │   │   ├── Hall（厅）— 概念类别
  │   │   │   ├── hall_facts — 已做决策
  │   │   │   ├── hall_events — 会话/里程碑
  │   │   │   ├── hall_discoveries — 新发现/突破
  │   │   │   ├── hall_preferences — 习惯/偏好
  │   │   │   └── hall_advice — 建议/解决方案
  │   │   └── Drawer（抽屉）— 原文存储（主检索层）
  │   └── Closet（壁橱）— 摘要层（指向原始内容）
  └── Tunnel（隧道）— 跨 Wing 连接
```

### 关键设计原则

| 原则 | 说明 |
|------|------|
| **Verbatim 存储** | 不总结、不提取、不改写，原文存入 |
| **语义检索** | ChromaDB 向量检索，支持 metadata 过滤（wing/room）|
| **Pluggable Backend** | RFC 001 定义 BaseCollection/BaseBackend 接口 |
| **Tenant 隔离** | PalaceRef.id 强制隔离，namespace 可选隔离 |
| **Local-first** | 默认 ChromaDB，可选 Qdrant/pgvector，零 API 调用 |

### Backend 接口（RFC 001）

```python
# BaseCollection — 每个集合的读写接口
add(documents, ids, metadatas, embeddings) → None
upsert(...) → None
query(query_texts, n_results, where, include) → QueryResult
get(ids, where, limit, offset, include) → GetResult
delete(ids, where) → None
count() → int
lexical_search(query, n_results, where) → LexicalResult  # 可选

# BaseBackend — 每个宫殿的工厂
get_collection(palace, collection_name, create, options) → BaseCollection
close_palace(palace) → None
close() → None
health(palace) → HealthStatus
```

### 支持的 Backend

| Backend | 类型 | 特点 |
|---------|------|------|
| chromadb | 默认 | 内嵌，无需服务 |
| sqlite_exact | 本地 | 精确向量验证 |
| qdrant | 外部 | REST API，支持命名空间隔离 |
| pgvector | 外部 | PostgreSQL，JSONB 存储 |

## 对 qclaw 记忆系统的启发

### 🔥🔥🔥 立即可借鉴

1. **结构化分层**：qclaw 的 memory/ 扁平目录可借鉴 Wing/Room/Hall 层次
   - Wing = 项目（lianghua/ai_study/...）
   - Room = 子话题（review/debug/...）
   - Hall = 类别（facts/events/discoveries）

2. **Pluggable Backend**：qclaw 的 mem0_hybrid_search 可抽象为 backend 接口
   - BaseCollection 接口模式
   - 支持 ChromaDB/Qdrant/sqlite 切换

3. **Verbatim + 语义双轨**：当前 qclaw 只用文件+grep，可增加语义检索

### 🔥🔥 考虑后续

4. **Tunnels 跨域连接**：同一话题在不同项目中出现 → 图遍历发现关联
5. **LongMemEval 基准**：评估 qclaw 记忆系统的检索质量
6. **Drawer 原文存储**：避免只存摘要导致的信息丢失

### 与 qclaw 已有记忆系统对比

| 维度 | qclaw 现状 | MemPalace 方案 |
|------|-----------|---------------|
| 存储方式 | 文件+grep | 向量 DB + 原文 |
| 组织结构 | 扁平目录 | Wing/Room/Hall 4层 |
| 检索方式 | 关键词+全文搜索 | 语义+metadata过滤 |
| 跨域关联 | 无 | Tunnels 图遍历 |
| 评估基准 | 无 | LongMemEval |
| Backend | 固定（文件系统）| 可插拔（ChromaDB/Qdrant/pgvector）|
