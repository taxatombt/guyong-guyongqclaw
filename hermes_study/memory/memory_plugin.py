# memory_plugin.py
# 顾庸 · 记忆层插件系统 v1.0
# 灵感来源: Hermes agent/memory_manager.py (NousResearch)
# 对标: BuiltinMemoryProvider + HermesMemoryProvider 双模式

from typing import Protocol, List, Dict, Optional, Callable, Any
import json
import pathlib
from datetime import datetime


# ─────────────────────────────────────────
# MemoryProvider 协议（对标 Hermes Plugin Architecture）
# ─────────────────────────────────────────
class MemoryProvider(Protocol):
    """记忆提供者接口——实现此 Protocol 即插即用"""

    def log(self, key: str, value: Any) -> None:
        """记录记忆"""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """读取记忆"""
        ...

    def get_decisions(self, limit: int = 10) -> List[Dict]:
        """获取历史决策"""
        ...

    def get_lessons(self, limit: int = 10) -> List[Dict]:
        """获取教训"""
        ...

    def recall_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """语义检索相似记忆"""
        ...

    def suggest_skipped(self) -> List[Dict]:
        """建议跳过的维度"""
        ...

    def summary(self, limit: int = 5) -> str:
        """生成记忆摘要"""
        ...


# ─────────────────────────────────────────
# BuiltinMemoryProvider（内置 JSONL 实现）
# ─────────────────────────────────────────
class BuiltinMemoryProvider:

    """
    内置记忆存储——JSONL 文件落地，完全兼容原有 evolver 格式。
    """

    MEMORY_DIR = pathlib.Path(__file__).parent
    MEMORY_FILE = MEMORY_DIR / 'memory_store.jsonl'
    DECISIONS_FILE = MEMORY_DIR / 'decisions.jsonl'
    LESSONS_FILE = MEMORY_DIR / 'lessons.jsonl'

    def __init__(self):
        self.MEMORY_FILE.parent.mkdir(exist_ok=True)

    def log(self, key: str, value: Any) -> None:
        entry = {
            'timestamp': datetime.now().isoformat(),
            'key': key,
            'value': value,
        }
        with open(self.MEMORY_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def get(self, key: str, default: Any = None) -> Any:
        if not self.MEMORY_FILE.exists():
            return default
        results = []
        with open(self.MEMORY_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('key') == key:
                        results.append(entry['value'])
                except Exception:
                    continue
        return results[-1] if results else default

    def get_decisions(self, limit: int = 10) -> List[Dict]:
        if not self.DECISIONS_FILE.exists():
            return []
        results = []
        with open(self.DECISIONS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except Exception:
                    continue
        return results[-limit:]

    def get_lessons(self, limit: int = 10) -> List[Dict]:
        if not self.LESSONS_FILE.exists():
            return []
        results = []
        with open(self.LESSONS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except Exception:
                    continue
        return results[-limit:]

    def recall_similar(self, query: str, limit: int = 5) -> List[Dict]:
        # 简单关键词匹配（可替换为 embedding 检索）
        results = []
        if not self.MEMORY_FILE.exists():
            return results
        q_lower = query.lower()
        with open(self.MEMORY_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    val_str = json.dumps(entry.get('value', ''), ensure_ascii=False).lower()
                    if q_lower in val_str:
                        results.append(entry)
                except Exception:
                    continue
        return results[-limit:]

    def suggest_skipped(self) -> List[Dict]:
        # 分析高频跳过维度
        suggestions = []
        if self.DECISIONS_FILE.exists():
            skip_count = {}
            with open(self.DECISIONS_FILE, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        if d.get('skipped_dimensions'):
                            for dim in d['skipped_dimensions']:
                                skip_count[dim] = skip_count.get(dim, 0) + 1
                    except Exception:
                        continue
            for dim, count in sorted(skip_count.items(), key=lambda x: -x[1])[:3]:
                suggestions.append({
                    'dimension': dim,
                    'skip_count': count,
                    'suggestion': '高频跳过，可能需要重新评估此维度',
                })
        return suggestions

    def summary(self, limit: int = 5) -> str:
        lines = ['=== 记忆摘要 ===']
        decisions = self.get_decisions(limit)
        lessons = self.get_lessons(limit)
        if decisions:
            lines.append(f'近期决策 {len(decisions)} 条')
            for d in decisions[-3:]:
                lines.append('  - {}'.format(d.get('task', '未知')[:50]))
        if lessons:
            lines.append(f'教训 {len(lessons)} 条')
            for l in lessons[-2:]:
                lines.append('  ! {}'.format(l.get('lesson', '')[:50]))
        if not decisions and not lessons:
            lines.append('暂无记忆记录')
        return '\n'.join(lines)


# ─────────────────────────────────────────
# HermesMemoryProvider（对接 Hermes Agent API）
# ─────────────────────────────────────────
class HermesMemoryProvider:

    """
    对接 Hermes Agent 的记忆 API。
    当 Hermes 运行在 localhost 时使用。

    用法:
        set_provider('hermes', api_url='http://localhost:18765')
    """

    def __init__(self, api_url: str = 'http://localhost:18765'):
        self.api_url = api_url.rstrip('/')
        self._client = None

    def _get_client(self):
        if self._client is None:
            import urllib.request
            self._client = urllib.request
        return self._client

    def _get(self, path: str) -> Optional[Dict]:
        try:
            req = self._get_client().Request(
                '{}/{}'.format(self.api_url, path.lstrip('/')),
                headers={'Accept': 'application/json'}
            )
            with self._get_client().urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def log(self, key: str, value: Any) -> None:
        self._post('memory/log', {'key': key, 'value': value})

    def get(self, key: str, default: Any = None) -> Any:
        result = self._get('memory/get/{}'.format(key))
        return result.get('value', default) if result else default

    def get_decisions(self, limit: int = 10) -> List[Dict]:
        result = self._get('memory/decisions?limit={}'.format(limit))
        return result.get('decisions', []) if result else []

    def get_lessons(self, limit: int = 10) -> List[Dict]:
        result = self._get('memory/lessons?limit={}'.format(limit))
        return result.get('lessons', []) if result else []

    def recall_similar(self, query: str, limit: int = 5) -> List[Dict]:
        result = self._get('memory/search?q={}'.format(query))
        return result.get('results', [])[:limit] if result else []

    def suggest_skipped(self) -> List[Dict]:
        result = self._get('memory/suggest_skipped')
        return result.get('suggestions', []) if result else []

    def summary(self, limit: int = 5) -> str:
        result = self._get('memory/summary')
        return result.get('summary', 'Hermes 记忆系统') if result else 'Hermes 记忆系统'


# ─────────────────────────────────────────
# 提供者注册表（对标 Hermes memory_manager 插件加载）
# ─────────────────────────────────────────
_provider: MemoryProvider = BuiltinMemoryProvider()
_registered: Dict[str, Callable] = {
    'builtin': BuiltinMemoryProvider,
    'hermes': HermesMemoryProvider,
}


def set_provider(name: str, **kwargs) -> None:
    """
    切换记忆提供者。

    用法:
        set_provider('builtin')              # 内置 JSONL（默认）
        set_provider('hermes', api_url='http://localhost:18765')  # Hermes
    """
    global _provider
    if name not in _registered:
        raise ValueError('Unknown provider: {}. Available: {}'.format(
            name, list(_registered.keys())))
    _provider = _registered[name](**kwargs)


def get_provider() -> MemoryProvider:
    """获取当前记忆提供者"""
    return _provider


def list_providers() -> List[str]:
    """列出可用提供者"""
    return list(_registered.keys())


def register_provider(name: str, factory: Callable) -> None:
    """注册新的记忆提供者"""
    _registered[name] = factory


# ─────────────────────────────────────────
# 兼容层（兼容原有 evolver.py 的调用方式）
# ─────────────────────────────────────────
def log_decision(task: str, decision: str, **kwargs) -> None:
    """记录决策"""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'task': task,
        'decision': decision,
        **kwargs,
    }
    f = BuiltinMemoryProvider.DECISIONS_FILE
    f.parent.mkdir(exist_ok=True)
    with open(f, 'a', encoding='utf-8') as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + '\n')


def get_decisions(limit: int = 10) -> List[Dict]:
    return get_provider().get_decisions(limit)


def log_lesson(lesson: str, context: str = '') -> None:
    """记录教训"""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'lesson': lesson,
        'context': context,
    }
    f = BuiltinMemoryProvider.LESSONS_FILE
    f.parent.mkdir(exist_ok=True)
    with open(f, 'a', encoding='utf-8') as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + '\n')


def get_lessons(limit: int = 10) -> List[Dict]:
    return get_provider().get_lessons(limit)


def recall(query: str, limit: int = 5) -> List[Dict]:
    return get_provider().recall_similar(query, limit)


def summary(limit: int = 5) -> str:
    return get_provider().summary(limit)


__all__ = [
    'MemoryProvider', 'BuiltinMemoryProvider', 'HermesMemoryProvider',
    'set_provider', 'get_provider', 'list_providers', 'register_provider',
    'log_decision', 'get_decisions', 'log_lesson', 'get_lessons',
    'recall', 'summary',
]
