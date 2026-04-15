# Hermes Agent 完整仓库研究

_来源: E:\ai\资源\8hermes-agent-main\hermes-agent-main_

## 核心架构

### 规模
- `run_agent.py` — 530KB（完整 agent 运行时）
- `cli.py` — 433KB
- `gateway/run.py` — 394KB
- 70 工具文件 / 26 skill 目录 / 533 测试

### 关键模块

#### 1. MemoryManager（agent/memory_manager.py）

**设计**：内置 provider + 最多 1 个外部 plugin provider
- `BuiltinMemoryProvider` — 始终注册，不可移除
- 外部 plugin — 只允许 1 个（防 schema 膨胀和冲突）
- 失败隔离：一个 provider 出错不影响另一个

**核心 API**：
- `build_system_prompt()` — 构建记忆 system prompt
- `prefetch_all(user_message)` — 预取相关记忆
- `sync_all(user_msg, assistant_response)` — 同步写入
- `queue_prefetch_all(user_msg)` — 异步预取下一轮

**Context fencing**：
```xml
<memory-context>
[System note: The following is recalled memory context, NOT new user input.]
...记忆内容...
</memory-context>
```
防止模型将记忆上下文误认为用户新输入。

#### 2. Delegate Tool（tools/delegate_tool.py）

**子代理架构**：
- 每个子代理获得：新对话（无父级历史）、独立 task_id、受限工具集、专注 prompt
- 父级只看到摘要结果，不看到中间过程

**安全限制**：
- `DELEGATE_BLOCKED_TOOLS`: delegate_task（禁止递归）、clarify（无用户交互）、memory（不写共享记忆）、send_message（无跨平台副作用）、execute_code（子代理应推理而非写脚本）
- `MAX_DEPTH = 2`：parent(0) → child(1) → grandchild 被拒绝(2)
- `max_concurrent_children = 3`（可配置）

**模式**：单任务 + 批量并行

#### 3. Memory Tool（tools/memory_tool.py）

**两存储**：
- `MEMORY.md` — agent 个人笔记（环境事实、项目约定、工具技巧）
- `USER.md` — 用户偏好（沟通风格、期望、工作流习惯）

**冻结快照模式**：
- 会话开始时注入 system prompt（冻结快照）
- 会话中写入立即持久化到磁盘（耐用），但不更新 system prompt（保持 prefix cache）
- 下一个会话开始时刷新快照

**安全扫描**：
- `_MEMORY_THREAT_PATTERNS`：12 种威胁模式
  - prompt injection（ignore previous instructions、you are now...）
  - exfiltration（curl/wget with secrets、cat .env）
  - persistence（authorized_keys、.ssh）
- 隐形字符检测（zero-width chars）

**工具 API**：单工具 + action 参数
- `add` — 添加条目
- `replace` — 替换（短唯一子串匹配）
- `remove` — 删除
- `read` — 读取

#### 4. Budget Config（tools/budget_config.py）

**三层持久化**：
- Layer 1: 默认结果大小 100,000 chars
- Layer 2: 每工具阈值（pinned > overrides > registry > default）
- Layer 3: 每轮预算 200,000 chars
- Preview: 1,500 chars

**Pinned 阈值**：`read_file: inf`（防止无限 persist→read→persist 循环）

#### 5. ContextCompressor（agent/context_compressor.py）

**778行完整压缩引擎**：
- `should_compress()` — 判断是否需要压缩
- `_prune_old_tool_results()` — 裁剪旧工具结果
- `_compute_summary_budget()` — 计算摘要 token 预算
- `_generate_summary()` — 生成摘要（使用 auxiliary client）
- `_find_tail_cut_by_tokens()` — 按 token 数裁剪尾部
- `_align_boundary_forward/backward()` — 边界对齐
- `compress()` — 主压缩方法

#### 6. Auxiliary Client（agent/auxiliary_client.py）

**2486行多provider客户端**：
- CodexAuxiliaryClient — OpenAI Codex 适配
- AnthropicAuxiliaryClient — Anthropic 适配
- CopilotACPClient — GitHub Copilot ACP 适配
- Provider 优先级链：custom → OpenRouter → Nous → Codex → Anthropic
- 支付失败自动回退（`_try_payment_fallback`）
- 连接错误重试
- 异步客户端管理 + stale cleanup

## 与 qclaw 的差距和可落地项

| 特性 | Hermes | qclaw | 落地 |
|------|--------|-------|------|
| Memory fencing | `<memory-context>` 防混淆 | 无 | 🔴 新建 memory_fence.py |
| Delegate tool | 子代理+受限工具+MAX_DEPTH | multi_agent_dispatcher 🟡 | 🟡 |
| 冻结快照 | 系统prompt不随写入更新 | 无 | 🔴 |
| 安全扫描 | 12种威胁模式+隐形字符 | 无 | 🔴 新建 memory_guard.py |
| Budget 3层 | per-result/per-tool/per-turn | 无 | 🟡 |
| ContextCompressor | 778行完整引擎 | 有 qclaw_compactor | 🟡 |
| Auxiliary client | 5 provider 自动回退 | 无 | 🟡 |
