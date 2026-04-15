# Hermes V2 全量落地汇报 — 2026-04-15

## 啃读范围
15个Hermes源码模块: prompt_builder / error_classifier / trajectory_compressor /
hermes_state / skills_guard / approval / checkpoint_manager / subdirectory_hints /
smart_model_routing / rate_limit_tracker / redact / gateway_hooks /
session_search_tool / mixture_of_agents_tool / hermes_constants / AGENTS.md

## 落地成果

### hermes_study_v2/ 目录 (9个模块，全部测试通过)

| 模块 | 大小 | 来源 | 测试结果 |
|------|------|------|---------|
| secret_redactor.py | 4.2KB | redact.py | ✅ sk-→mask, ENV, JSON, DB connstr |
| rate_limit_display.py | 5.9KB | rate_limit_tracker.py | ✅ 80%预警, 4 bucket |
| subdirectory_hint_tracker.py | 6.1KB | subdirectory_hints.py | ✅ tool call触发, 父目录遍历 |
| smart_model_router.py | 4.9KB | smart_model_routing.py | ✅ 160字/28词检测 |
| trajectory_compress.py | 8.9KB | trajectory_compressor.py | ✅ 5140→1964 tokens (38%) |
| approval_patterns.py | 6.5KB | approval.py | ✅ contextvar隔离, 35+危险模式 |
| fts5_session_store.py | 9.2KB | hermes_state.py | ✅ FTS5搜索, WAL模式 |
| shadow_git_checkpoints.py | 10.2KB | checkpoint_manager.py | ✅ list+restore通过 |
| moa_ensemble.py | 6.5KB | mixture_of_agents_tool.py | ✅ 4参考模型+Aggregator |

## 关键新认知

### 1. approval.py 比 qclaw safe_exec.py 多出的
- Git破坏性: reset --hard / push --force / clean -f / branch -D
- 自我终止保护: pkill hermes / kill $(pgrep) / killall hermes
- Heredoc执行: python3 << EOF
- contextvars.ContextVar 隔离并发session的approval队列

### 2. 两层技能缓存 (prompt_builder.py)
- L1: 进程内LRU (max 8条目)
- L2: 磁盘快照 (.skills_prompt_snapshot.json + mtime manifest)

### 3. Shadow Git Repo (checkpoint_manager.py)
- GIT_DIR + GIT_WORK_TREE 分离
- 每目录每轮次去重
- hash防注入验证

### 4. 渐进子目录上下文 (subdirectory_hints.py)
- Block/goose灵感
- 每次tool call触发, 向上5层遍历
- 结果追加到tool result, 不改system prompt

### 5. FTS5查询消毒 (hermes_state.py)
- 5步处理: 保护双引号短语 / 剥离FTS5特殊字符 / 包裹点分词为短语

## Evolver 更新
+10条规则 → 104条规则
