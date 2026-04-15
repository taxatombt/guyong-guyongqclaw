# -*- coding: utf-8 -*-
"""
session_checkpoint.py - Session 断点导出与恢复

功能:
  1. 导出: 将当前会话状态保存为 JSON
  2. 恢复: 从 JSON 恢复会话状态
  3. 差异: 找出两次 checkpoint 之间的差异

导出内容:
  - messages (去敏感化)
  - task state
  - compressor state
  - evolver state
  - timestamp
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
CHECKPOINT_DIR = WORKSPACE / "memory" / "checkpoints"


@dataclass
class Checkpoint:
    """会话检查点"""
    session_id: str
    created_at: str
    message_count: int
    message_hash: str  # 内容指纹，用于差异检测
    compressor_state: Dict[str, Any] = field(default_factory=dict)
    evolver_summary: Dict[str, Any] = field(default_factory=dict)
    task_summary: str = ""
    tags: List[str] = field(default_factory=list)
    file_path: Optional[str] = None


def _hash_messages(messages: List[Dict[str, Any]]) -> str:
    """对消息内容生成指纹"""
    content = "".join(str(m.get("content", "")) for m in messages)
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]


def _sanitize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    去敏感化: 移除敏感内容用于导出。
    - 移除 long tool outputs (>1000 chars)
    - 移除可能的 token/key 内容
    """
    sanitized = []
    for msg in messages:
        content = str(msg.get("content", ""))
        role = msg.get("role", "")
        
        # 截断超长内容
        if len(content) > 1000:
            content = content[:500] + f"\n... [{len(content) - 500} chars truncated] ..."
        
        # 移除可能的 key/token 内容
        for pattern in [r"(sk-[a-zA-Z0-9]{20,})", r"(token[:\s]+[a-zA-Z0-9]{10,})"]:
            import re
            content = re.sub(pattern, "[REDACTED]", content, flags=re.IGNORECASE)
        
        sanitized.append({
            "role": role,
            "content": content,
            "tool_use_id": msg.get("tool_use_id"),
        })
    
    return sanitized


def create_checkpoint(
    session_id: str,
    messages: List[Dict[str, Any]],
    compressor_state: Optional[Dict[str, Any]] = None,
    evolver_summary: Optional[Dict[str, Any]] = None,
    task_summary: str = "",
    tags: Optional[List[str]] = None,
) -> Checkpoint:
    """
    创建检查点。
    """
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    
    sanitized = _sanitize_messages(messages)
    msg_hash = _hash_messages(messages)
    
    ts = datetime.now(timezone.utc).isoformat()
    
    # 保存消息到单独文件
    ts_safe = ts.replace(":", "-").replace(".", "-")
    msg_file = CHECKPOINT_DIR / f"{session_id}_{ts_safe}_messages.json"
    msg_file.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    checkpoint = Checkpoint(
        session_id=session_id,
        created_at=ts,
        message_count=len(messages),
        message_hash=msg_hash,
        compressor_state=compressor_state or {},
        evolver_summary=evolver_summary or {},
        task_summary=task_summary,
        tags=tags or [],
        file_path=str(msg_file),
    )
    
    # 保存 checkpoint 元数据
    ckpt_file = CHECKPOINT_DIR / f"{session_id}_{ts_safe}_checkpoint.json"
    ckpt_file.write_text(
        json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return checkpoint


def list_checkpoints(session_id: str) -> List[Checkpoint]:
    """列出某 session 的所有检查点"""
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    checkpoints = []
    
    prefix = f"{session_id}_"
    for f in sorted(CHECKPOINT_DIR.glob(f"{prefix}*checkpoint.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            checkpoints.append(Checkpoint(**data))
        except Exception:
            pass
    
    return checkpoints


def diff_checkpoints(ckpt_a: Checkpoint, ckpt_b: Checkpoint) -> Dict[str, Any]:
    """
    比较两个检查点的差异。
    """
    return {
        "session_id": ckpt_a.session_id,
        "a_created": ckpt_a.created_at,
        "b_created": ckpt_b.created_at,
        "a_messages": ckpt_a.message_count,
        "b_messages": ckpt_b.message_count,
        "message_delta": ckpt_b.message_count - ckpt_a.message_count,
        "a_hash": ckpt_a.message_hash,
        "b_hash": ckpt_b.message_hash,
        "hash_changed": ckpt_a.message_hash != ckpt_b.message_hash,
        "compressor_changed": ckpt_a.compressor_state != ckpt_b.compressor_state,
        "evolver_changed": ckpt_a.evolver_summary != ckpt_b.evolver_summary,
    }


def load_messages(checkpoint: Checkpoint) -> List[Dict[str, Any]]:
    """从检查点加载消息"""
    if not checkpoint.file_path:
        return []
    
    path = Path(checkpoint.file_path)
    if not path.exists():
        return []
    
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def export_summary(checkpoint: Checkpoint) -> str:
    """格式化检查点为摘要"""
    lines = [
        f"Checkpoint: {checkpoint.session_id}",
        f"Created: {checkpoint.created_at}",
        f"Messages: {checkpoint.message_count}",
        f"Hash: {checkpoint.message_hash}",
    ]
    if checkpoint.task_summary:
        lines.append(f"Task: {checkpoint.task_summary}")
    if checkpoint.tags:
        lines.append(f"Tags: {', '.join(checkpoint.tags)}")
    return "\n".join(lines)
