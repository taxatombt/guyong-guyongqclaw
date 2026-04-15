# hermes_study/exec_engine — 并发执行引擎

> 来源：Hermes agent/concurrent.py 逆向
> 文件：thread_pool.py（10KB，360行）

---

## 核心设计

```
ThreadPoolExecutor（Python标准库）
    ↓
max_workers: 3（可配置）
    ↓
execute_actions_concurrent()  ← 并行执行
execute_actions_sequential()   ← 串行执行
    ↓
ToolCall → ActionResult → 聚合返回
```

---

## 两种执行模式

### 并发执行

```python
from thread_pool import execute_actions_concurrent, Action

actions = [
    Action(name="search", tool="web_search", args={"query": "Python"}),
    Action(name="read", tool="read", args={"path": "README.md"}),
    Action(name="eval", tool="exec", args={"command": "ls"}),
]
results = execute_actions_concurrent(actions, max_workers=3)
# 返回 dict: {action_name: ActionResult}
```

### 串行执行

```python
from thread_pool import execute_actions_sequential
results = execute_actions_sequential(actions)
# 返回 list: [ActionResult, ...]
# 遇到错误可中断
```

---

## Action / ActionResult 数据结构

```python
@dataclass
class Action:
    name: str           # 标识名
    tool: str           # 工具名
    args: dict          # 工具参数
    timeout: float = 30.0
    priority: int = 0

@dataclass
class ActionResult:
    name: str
    success: bool
    result: Any = None
    error: str = ""
    duration: float = 0.0
    timestamp: float = 0.0
```

---

## 工具注册机制

```python
from thread_pool import register_executor, execute_actions_sequential

def my_search_tool(query):
    return {"query": query, "results": [...]}

register_executor("web_search", my_search_tool)

actions = [Action(name="s", tool="web_search", args={"query": "AI"})]
results = execute_actions_sequential(actions)
```

---

## 设计原则

1. max_workers=3：平衡并发与资源
2. 超时控制：每个action独立超时
3. 结果聚合：dict/list统一格式
4. 优先级调度：高优先级action优先
5. 零依赖：只用 threading 和 concurrent.futures

---

## 与Evolver集成

```
Evolver.record(task, method, success)
    ↓
如果方法需要多工具并行 → thread_pool调度
    ↓
execute_actions_concurrent()
    ↓
ActionResult → Evolver.record() → evolver_db.json
```

---

## 可移植设计点

| 设计 | 在qclaw中应用 |
|------|------------|
| 并发执行 | 多源信息并行抓取（搜索+读取+API同时） |
| 优先级调度 | 关键路径action优先 |
| 超时隔离 | 单工具超时不影响整体 |
| 工具注册 | OpenClaw tool registry 可复用 |

---

## 落地状态

- thread_pool.py OK（10KB，360行，完整实现）
- SKILL.md OK（本文件）
- 待集成：作为 evolver.py 的并发执行层
