# SKILL-viki.md — Viki 知识库系统（源码级分析）

> 来源：`E:\qwenpaw\viki\`（小谷的个人知识库，基于 Karpathy LLM Wiki 理念）

## 系统架构

```
raw/（原始资料，gitignore）
  ↓ compile.py（增量/全量）
wiki/（LLM 编译产出，Obsidian 兼容）
  ↓ ask 模式
Q&A 回答 + 建议新文章
```

## 核心文件

| 文件 | 大小 | 功能 |
|------|------|------|
| `compile.py` | 8KB | 编译引擎 + Q&A + CLI |
| `config.py` | 0.4KB | LLM 配置 + 路径 + 字数限制 |
| `init.py` | 1.6KB | 初始化（建目录 + 写 index） |

## 编译流程（compile.py）

### 增量编译（核心）
1. `read_raw_files()` — 扫描 raw/，过滤 ≥50字的文件
2. `load_cache()` — 读 `_viki_cache.json`（存 raw_hashes + articles）
3. 对每个 raw 文件算 MD5 hash → 与 cache 对比
4. **hash 变了才重新编译**，未变跳过（增量核心）
5. `compile_article()` — 调 LLM 生成 200-500 字 wiki 文章
6. 写入 `wiki/{slug}.md`
7. `build_wiki_index()` — 生成 `wiki/_index.md`（按分类导航）

### 全量编译
- `--full` 参数 → 清空 articles，所有 raw 重编译

### Q&A 模式
- 读 wiki/ 最多 20 篇文章（8000 字上下文）
- LLM 结合 wiki 内容回答 + 推荐 2-3 个新文章标题
- **不用 RAG**，直接拼接上下文

## 关键设计

### 1. 增量检测（MD5 hash）
```python
cache["raw_hashes"][path] = md5[:8]  # 只存前8位
# 下次编译时对比，变了才重编译
```

### 2. LLM Prompt 模板
- 角色：知识库管理员
- 输入：raw 文件名 + 前500字摘要
- 输出：200-500字 wiki 文章 + 3个 Related 反向链接
- 中文输出

### 3. 分类猜测
- 文件名含 agent → "AI Agent"
- 含 skill → "Skills"
- 含 llm/model → "LLM"
- 含 code/repo → "代码"
- 默认 → "通用"

### 4. Standalone 模式
- 无 LLM 时输出占位内容（待编译标记）
- 不报错，降级运行

## 配置（config.py）

```python
LLM_MODEL = "MiniMax-M2.7"        # 用 MiniMax 驱动
LLM_PROVIDER = "minimax"          # minimax | openai | ollama
MIN_RAW_WORDS = 50                # raw 文件最低字数
MAX_WIKI_WORDS = 500              # wiki 文章上限
```

## 当前状态

- raw/ 有 7 篇资料（ai-agent / engineering-lessons / juhuo / qwenpaw / skill-format / viki-knowledge / html-output）
- wiki/ 有对应 7 篇编译产出 + `_index.md` + `_viki_cache.json`
- 已初始化，可编译

## qclaw 可借鉴的点

1. **增量编译理念** → evolver 也应是增量的，不全量重建
2. **MD5 hash 变更检测** → 比 evolver 当前的"全量扫描"更高效
3. **Q&A 不用 RAG** → 40万字以下直接拼接上下文够用
4. **Category 自动猜测** → 可用于 qclaw skill 分类
5. **Standalone 降级模式** → 无 LLM 时优雅降级而非报错

## 与 qclaw 的关系

- Viki 是**小谷的个人知识库**（qwenpaw 驱动）
- qclaw 的 memory/ 可参考 Viki 的 raw→wiki 流程
- 但 qclaw 不需要替代 Viki，两者定位不同：
  - Viki = 结构化知识库（编译产出）
  - memory/ = 工作记忆（日志+即时上下文）
