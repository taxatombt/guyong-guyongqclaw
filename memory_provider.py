"""
memory_provider.py — Hermes 风格记忆提供者架构
借鉴：hermes_study/memory_plugin.py
提供：
  - MemoryProvider ABC（抽象基类）
  - BuiltinMemoryProvider（JSONL追加存储）
  - get_provider() / set_provider() 全局切换
"""
import pathlib, json, abc, sys
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# MemoryProvider ABC
# ============================================================
class MemoryProvider(abc.ABC):
    @abc.abstractmethod
    def read(self, key: str) -> Optional[str]:
        """读取记忆，返回None表示不存在"""
        ...

    @abc.abstractmethod
    def write(self, key: str, content: str) -> None:
        """写入记忆"""
        ...

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        """删除记忆"""
        ...

    @abc.abstractmethod
    def list_keys(self, pattern: str = "*") -> list[str]:
        """列出匹配的key"""
        ...

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """key是否存在"""
        ...


# ============================================================
# BuiltinMemoryProvider — JSONL追加存储
# ============================================================
class BuiltinMemoryProvider(MemoryProvider):
    """
    基于 JSONL 的记忆存储。
    - 追加写入（append-only），适合高频记录
    - 每次write写一行JSON
    - list_keys 扫描所有行（慢但可靠）
    """

    def __init__(self, storage_dir: str = None, index_file: str = None):
        if storage_dir is None:
            storage_dir = str(pathlib.Path.home() / '.qclaw' / 'memories')
        self.storage_dir = pathlib.Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._data_file = self.storage_dir / 'decisions.jsonl'
        self._index_file = pathlib.Path(index_file) if index_file else None
        self._memory_index: dict[str, dict] = {}  # key -> metadata
        self._load_index()

    def _load_index(self):
        """加载索引（key -> 行号映射）"""
        if self._index_file and self._index_file.exists():
            try:
                self._memory_index = json.loads(
                    self._index_file.read_text(encoding='utf-8'))
                return
            except:
                pass
        # 全量扫描建立索引
        self._rebuild_index()

    def _rebuild_index(self):
        """扫描所有行，重建索引"""
        self._memory_index.clear()
        if not self._data_file.exists():
            return
        for lineno, line in enumerate(self._data_file.read_text(
                encoding='utf-8').splitlines()):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                key = record.get('key') or record.get('id')
                if key:
                    self._memory_index[key] = {
                        'line': lineno,
                        'type': record.get('type', 'unknown'),
                        'timestamp': record.get('timestamp', ''),
                    }
            except:
                pass

    def _save_index(self):
        """保存索引"""
        if self._index_file:
            self._index_file.write_text(
                json.dumps(self._memory_index, ensure_ascii=False, indent=2),
                encoding='utf-8')

    # --- 核心CRUD ---
    def read(self, key: str) -> Optional[str]:
        """读取记忆内容（只返回最新一条）"""
        if not self._data_file.exists():
            return None
        results = []
        for line in self._data_file.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if r.get('key') == key or r.get('id') == key:
                    results.append(r)
            except:
                pass
        return results[-1].get('content') if results else None

    def write(self, key: str, content: str, type: str = 'generic',
              metadata: dict = None) -> None:
        """追加一条记忆"""
        record = {
            'key': key,
            'content': content,
            'type': type,
            'timestamp': self._now(),
        }
        if metadata:
            record['metadata'] = metadata

        with self._data_file.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        self._memory_index[key] = {
            'line': self._data_file.stat().st_size,
            'type': type,
            'timestamp': record['timestamp'],
        }
        self._save_index()

    def delete(self, key: str) -> None:
        """标记删除（不物理删除行，追加删除标记）"""
        self.write(key, '[DELETED]', type='delete')

    def list_keys(self, pattern: str = '*') -> list[str]:
        """列出匹配的key"""
        if pattern == '*':
            return list(self._memory_index.keys())
        # 简单前缀匹配
        return [k for k in self._memory_index if k.startswith(
            pattern.rstrip('*'))]

    def exists(self, key: str) -> bool:
        return key in self._memory_index

    def all_records(self, type: str = None) -> list[dict]:
        """获取所有记录（可选过滤type）"""
        if not self._data_file.exists():
            return []
        results = []
        for line in self._data_file.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if type is None or r.get('type') == type:
                    results.append(r)
            except:
                pass
        return results

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


# ============================================================
# 全局Provider切换
# ============================================================
_current_provider: Optional[MemoryProvider] = None
_default_provider: Optional[MemoryProvider] = None


def get_provider() -> MemoryProvider:
    """获取当前记忆提供者（默认BuiltinMemoryProvider）"""
    global _current_provider, _default_provider
    if _current_provider is None:
        if _default_provider is None:
            _default_provider = BuiltinMemoryProvider()
        _current_provider = _default_provider
    return _current_provider


def set_provider(provider: MemoryProvider) -> None:
    """全局切换记忆提供者"""
    global _current_provider
    _current_provider = provider


def reset_provider() -> None:
    """重置为默认提供者"""
    global _current_provider
    _current_provider = None


if __name__ == '__main__':
    # 简单测试
    p = BuiltinMemoryProvider()
    p.write('test-key', 'test content', type='test')
    print('read:', p.read('test-key'))
    print('exists:', p.exists('test-key'))
    print('keys:', p.list_keys())
    p.delete('test-key')
    print('after delete:', p.read('test-key'))
