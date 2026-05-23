---
name: anthropic-managed-agents
description: |
  Anthropic Managed Agents 设计模式落地（qclaw 版）。
  来源：Anthropic 工程博客《Scaling Managed Agents: Decoupling the brain from the hands》(2026-04-08)
  URL: https://www.anthropic.com/engineering/managed-agents
  
  6个核心设计模式：
  1. 宠物 vs 牲口 — 无状态组件，可失败可重启
  2. 大脑与双手解耦 — execute(name, input) → string
  3. 会话持久存储 — SessionVault + getEvents()
  4. 多大脑多双手 — 无状态横向扩展
  5. 安全边界 — CredentialVault，token 不进沙箱
  6. 元数据编排 — 对接口有主张，对实现无主张
---

# Anthropic Managed Agents 设计模式

## 落地文件

| 组件 | 文件 | 说明 |
|------|------|------|
| Hand | `agents/tool_pipeline.py` Hand类 | 可失败可重启的"双手" |
| SessionVault | `agents/tool_pipeline.py` SessionVault类 | 仅追加事件日志 |
| CredentialVault | `agents/tool_pipeline.py` CredentialVault类 | 凭证保管库 |
| execute() | `agents/tool_pipeline.py` execute()函数 | 统一执行接口 |

## Hand 用法

```python
from agents.tool_pipeline import Hand, execute

# 方式1：直接用 execute(name, input) → str
result = execute("exec", {"command": "git status"})
if result.startswith("ERROR"):
    # 大脑决定重试
    result = execute("exec", {"command": "git status"})

# 方式2：Hand 实例（支持重启）
hand = Hand(name="sandbox", max_retries=1)
result = hand.execute("exec", {"command": "git status"})
if hand.failed:
    hand.restart()  # 牲口模式：重启而非修复
```

## SessionVault 用法

```python
from agents.tool_pipeline import SessionVault

sv = SessionVault(session_id="abc123", storage_dir="./sessions")

# 记录事件
sv.emit_event({"type": "tool_call", "tool": "exec", "input": {"command": "git status"}})
sv.emit_event({"type": "tool_result", "output": "ok"})

# 读取事件
events = sv.get_events(start=0, limit=10)       # 按位置切片
before = sv.get_events_before(event_idx=5, count=3)  # 回溯
after = sv.get_events_after(event_idx=3, count=5)    # 前进
all_events = sv.wake()                            # 唤醒/恢复
```

## CredentialVault 用法

```python
from agents.tool_pipeline import CredentialVault

cv = CredentialVault()
cv.store("github_token", "ghp_xxx", session_id="abc123")

# 安全获取（会话隔离）
token = cv.get("github_token", session_id="abc123")  # ✅ 返回 token
cv.get("github_token", session_id="other")            # ❌ 返回 None

# 代理调用（自动注入凭证）
result = cv.proxy_call("github_token", "abc123", 
                       call_fn=lambda token: requests.get(url, headers={"Authorization": f"Bearer {token}"}))

# 撤销
cv.revoke("github_token")
```

## 对六层架构贡献

| 层 | 贡献度 | 具体模式 |
|---|--------|---------|
| ② 认知层 | ✅✅ | 元数据编排 + 多大脑调度 |
| ③ 记忆层 | ✅✅✅ | SessionVault + getEvents() + 重放恢复 |
| ④ 执行层 | ✅✅✅ | execute接口 + Hand无状态执行 |
| ⑤ 安全层 | ✅✅✅ | CredentialVault + 会话隔离 + 代理调用 |
| ⑥ 进化层 | ✅ | 接口稳定性支持长期演进 |
