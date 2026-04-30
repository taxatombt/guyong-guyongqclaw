# 学习归档 - Hermes Agent

> 从 MEMORY.md 迁出，2026-04-24 精简时归档

## Hermes 源码逆向工程（2026-04-12，完成）

**落地**：`hermes_study/`（47KB，9文件，5个SKILL文档）

**核心成果**：
- KawaiiSpinner：9种动画 + 心情表情 + 皮肤系统
- MoodOutput：心情化输出系统（thinking/success/error/working）
- FileSnapshot：文件快照 + unified_diff 预览 + 回滚
- MemoryProvider：可切换的记忆提供者架构（内置JSONL + 外部插件限1个）
- ThreadPool：并发/串行执行引擎，max_workers=3

## Hermes Agent Guide 学习（2026-04-24，完成）

**来源**：https://github.com/jwangkun/hermes-agent-guide（16册30万+字，鲲鹏Talk）

**落地**：hermes_guide_study/SKILL.md（4.6KB）

**核心新认知**：
1. 五层架构：入口编排→Agent核心→工具注册→持久化→平台适配
2. 四温记忆模型：热(上下文)/温(MEMORY.md~2200字符+USER.md~1375字符)/冷(SQLite+FTS5)/外(Honcho/Mem0)
3. 有界记忆：MEMORY.md满时必须取舍，不是无限塞
4. 5-tool-call规则：5次以上工具调用成功→质量评分(频率×0.3+重要性×0.4+结构性×0.3>0.7)→自动生成SKILL.md
5. 上下文溢出5级降级：compact→FIFO截断→缩减冷记忆→缩减温记忆→报错
6. 预算三维度：max_turns / max_tool_calls / max_cost_usd
7. FTS5零部署全文检索：SQLite内置，不需要向量数据库
8. USER.md自动建模：显式反馈+隐式行为+错误模式+任务偏好

**Hermes源码深度分析（hermes_study/SKILL-deep.md，8KB）**：
- run_agent.py 518KB全解析：13项独有设计
- flush_memories Sentinel / 记忆注入用户消息 / 4种错误恢复

**Hermes × Codex对比（hermes_study/SKILL-deep-codex.md，8KB）**：
- Codex Phase1/Phase2 SQL selection diff全解析
- 架构对比 + qclaw集成方案

**深度系统研究（hermes_study/SKILL-deep-systems.md，6KB）**：
- context_compressor.py：4步压缩 + Structured Summary Template
- prompt_caching.py：system_and_3（4个cache_control断点）
- insights.py：用量报告结构

## qclaw落地

- `agents/token_budget.py`（11KB）：TokenBudgetController + 5级降级 + 3维预算
- 已测试通过，已加入agents/__init__.py导出
