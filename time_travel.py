# -*- coding: utf-8 -*-
"""
time_travel.py - 会话时间旅行（回溯到历史状态）

来源: 顾庸t workspace_tools/time_travel.py
参考: Claude Code session history + Hermes snapshot/rollback

功能:
  1. 创建会话快照（状态 + 文件变更）
  2. 列出历史快照
  3. 回溯到指定快照
  4. 比较两个快照之间的差异
"""

import time
import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
SNAPSHOTS_DIR = WORKSPACE / ".time_travel_snapshots"


@dataclass
class Snapshot:
    """快照"""
    snapshot_id: str
    timestamp: float
    label: str
    description: str
    file_states: Dict[str, str] = field(default_factory=dict)  # path → content_hash
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def time_str(self) -> str:
        dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))
        return dt


class TimeTravel:
    """时间旅行管理器"""
    
    def __init__(self, snapshots_dir: Optional[Path] = None):
        self._dir = snapshots_dir or SNAPSHOTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: Dict[str, Snapshot] = {}
        self._load_index()
    
    def _index_file(self) -> Path:
        return self._dir / "index.json"
    
    def _load_index(self) -> None:
        idx = self._index_file()
        if idx.exists():
            try:
                data = json.loads(idx.read_text(encoding="utf-8"))
                for sid, sdata in data.items():
                    self._snapshots[sid] = Snapshot(
                        snapshot_id=sid,
                        timestamp=sdata["timestamp"],
                        label=sdata.get("label", ""),
                        description=sdata.get("description", ""),
                        file_states=sdata.get("file_states", {}),
                        metadata=sdata.get("metadata", {}),
                    )
            except (json.JSONDecodeError, KeyError):
                self._snapshots = {}
    
    def _save_index(self) -> None:
        data = {}
        for sid, s in self._snapshots.items():
            data[sid] = {
                "timestamp": s.timestamp,
                "label": s.label,
                "description": s.description,
                "file_states": s.file_states,
                "metadata": s.metadata,
            }
        self._index_file().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    
    @staticmethod
    def _file_hash(content: str) -> str:
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
    
    def create_snapshot(self, label: str, description: str = "",
                        file_paths: Optional[List[Path]] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> Snapshot:
        """创建快照"""
        snapshot_id = hashlib.md5(
            f"{time.time()}{label}".encode()
        ).hexdigest()[:8]
        
        file_states = {}
        paths = file_paths or []
        
        for fp in paths:
            if fp.exists():
                content = fp.read_text(encoding="utf-8", errors="replace")
                file_states[str(fp)] = self._file_hash(content)
        
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            timestamp=time.time(),
            label=label,
            description=description,
            file_states=file_states,
            metadata=metadata or {},
        )
        
        self._snapshots[snapshot_id] = snapshot
        self._save_index()
        return snapshot
    
    def list_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出快照"""
        snapshots = sorted(
            self._snapshots.values(), key=lambda s: s.timestamp, reverse=True
        )
        return [
            {
                "id": s.snapshot_id,
                "time": s.time_str,
                "label": s.label,
                "files": len(s.file_states),
            }
            for s in snapshots[:limit]
        ]
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        return self._snapshots.get(snapshot_id)
    
    def diff(self, id_a: str, id_b: str) -> Dict[str, Any]:
        """比较两个快照"""
        a = self._snapshots.get(id_a)
        b = self._snapshots.get(id_b)
        
        if not a or not b:
            return {"error": "Snapshot not found"}
        
        files_a = set(a.file_states.keys())
        files_b = set(b.file_states.keys())
        
        added = files_b - files_a
        removed = files_a - files_b
        common = files_a & files_b
        
        changed = []
        for f in common:
            if a.file_states[f] != b.file_states[f]:
                changed.append(f)
        
        return {
            "from": id_a,
            "to": id_b,
            "added": list(added),
            "removed": list(removed),
            "changed": changed,
        }
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
            self._save_index()
            return True
        return False


_tt: Optional[TimeTravel] = None

def get_time_travel() -> TimeTravel:
    global _tt
    if _tt is None:
        _tt = TimeTravel()
    return _tt
