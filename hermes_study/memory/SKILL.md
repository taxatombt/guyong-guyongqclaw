# hermes_study/memory — 记忆提供者架构

> 来源：Hermes agent/memory_manager.py 逆向
> 文件：memory_plugin.py（12KB，含 MemoryProvider ABC）

---

## 核心架构

```
用户/Agent
    ↓
MemoryManager（顶层管理）
    ↓
set_provider(provider)  ← 切换记忆提供者
    ↓
MemoryProvider（抽象基类）
    ├── BuiltinMemoryProvider（JSONL，本地文件）
    └── [自定义外部插件，只允许1个]
```

---

## MemoryProvider 接口

```python
class MemoryProvider(ABC):
    @abstractmethod
    def read(self, key: str) -> str | None: ...

    @abstractmethod
    def write(self, key: str, content: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def list_keys(self, pattern: str = "*") -> list[str]: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...
```

---

## BuiltinMemoryProvider

基于 JSONL 的本地记忆存储：

```python
from memory_plugin import BuiltinMemoryProvider, set_provider, get_provider

provider = BuiltinMemoryProvider(storage_dir="~/.qclaw/memories")
provider.write("today_work", "完成了项目A的部署")
content = provider.read("today_work")
provider.delete("today_work")
keys = provider.list_keys("today*")

set_provider(provider)  # 全局切换
current = get_provider()
```

---

## 设计原则

1. 提供者无关：MemoryManager 不关心底层实现
2. 单例切换：通过 set_provider() 全局切换
3. JSONL格式：append-only，高效追加
4. 接口简洁：只有5个方法
5. 外部插件限1个：避免冲突

---

## 可移植设计点

| 设计 | 在qclaw中应用 |
|------|------------|
| Provider ABC | 记忆层抽象化，支持切换后端 |
| set_provider() | 全局注入点 |
| JSONL存储 | 追加写入，高并发友好 |
| 外部插件限1个 | 防止多插件竞争 |

---

## 落地状态

- memory_plugin.py OK（12KB，含 BuiltinMemoryProvider）
- decisions.jsonl OK（记忆内容示例）
- SKILL.md OK（本文件）
- 待集成：与 evolver_db.json 对接
