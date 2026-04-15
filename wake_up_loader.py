# -*- coding: utf-8 -*-
"""
wake_up_loader.py - 启动加载器（会话初始化）

来源: 顾庸t workspace_tools/wake_up_loader.py
参考: Claude Code session init + Hermes wake-up sequence

功能:
  会话启动时自动加载的初始化序列:
  1. 加载 SOUL.md（人格）
  2. 加载 USER.md（用户信息）
  3. 加载 MEMORY.md（长期记忆）
  4. 加载 memory/今日.md（今日记忆）
  5. 运行健康检查
  6. 恢复上下文
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path


WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")


@dataclass
class WakeUpResult:
    """启动结果"""
    success: bool
    steps: List[Dict[str, Any]]
    errors: List[str]
    loaded_files: List[str]
    start_time: float
    end_time: float = 0
    
    @property
    def duration_ms(self) -> int:
        return int((self.end_time - self.start_time) * 1000)
    
    @property
    def summary(self) -> str:
        ok = sum(1 for s in self.steps if s.get("status") == "ok")
        fail = sum(1 for s in self.steps if s.get("status") == "error")
        return f"{ok} ok, {fail} failed, {self.duration_ms}ms"


class WakeUpLoader:
    """启动加载器"""
    
    def __init__(self, workspace: Optional[Path] = None):
        self._ws = workspace or WORKSPACE
    
    def wake_up(self) -> WakeUpResult:
        """执行启动序列"""
        start = time.time()
        steps = []
        errors = []
        loaded = []
        
        # 1. SOUL.md
        step = self._load_file("SOUL.md", required=True)
        steps.append(step)
        if step.get("content"):
            loaded.append("SOUL.md")
        
        # 2. USER.md
        step = self._load_file("USER.md", required=False)
        steps.append(step)
        if step.get("content"):
            loaded.append("USER.md")
        
        # 3. MEMORY.md
        step = self._load_file("MEMORY.md", required=False)
        steps.append(step)
        if step.get("content"):
            loaded.append("MEMORY.md")
        
        # 4. HEARTBEAT.md
        step = self._load_file("HEARTBEAT.md", required=False)
        steps.append(step)
        if step.get("content"):
            loaded.append("HEARTBEAT.md")
        
        # 5. memory/今日.md
        from datetime import datetime
        today_file = f"memory/{datetime.now().strftime('%Y-%m-%d')}.md"
        step = self._load_file(today_file, required=False)
        steps.append(step)
        if step.get("content"):
            loaded.append(today_file)
        
        # 6. TOOLS.md
        step = self._load_file("TOOLS.md", required=False)
        steps.append(step)
        if step.get("content"):
            loaded.append("TOOLS.md")
        
        # 7. 健康检查
        health_step = self._health_check()
        steps.append(health_step)
        if health_step.get("status") == "error":
            errors.append(health_step.get("message", "health check failed"))
        
        success = all(s.get("status") != "error" for s in steps if s.get("required", False))
        
        return WakeUpResult(
            success=success,
            steps=steps,
            errors=errors,
            loaded_files=loaded,
            start_time=start,
            end_time=time.time(),
        )
    
    def _load_file(self, rel_path: str, required: bool = False) -> Dict[str, Any]:
        """加载文件"""
        file_path = self._ws / rel_path
        if not file_path.exists():
            status = "error" if required else "skip"
            return {
                "file": rel_path,
                "status": status,
                "message": "Not found",
                "required": required,
            }
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return {
                "file": rel_path,
                "status": "ok",
                "size": len(content),
                "content": content,
                "required": required,
            }
        except Exception as e:
            return {
                "file": rel_path,
                "status": "error",
                "message": str(e),
                "required": required,
            }
    
    def _health_check(self) -> Dict[str, Any]:
        """健康检查"""
        checks = []
        
        # workspace 可写
        try:
            test_file = self._ws / ".wake_up_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            checks.append(("workspace_writable", "ok"))
        except Exception as e:
            checks.append(("workspace_writable", f"error: {e}"))
        
        # memory 目录
        mem_dir = self._ws / "memory"
        if mem_dir.exists():
            checks.append(("memory_dir", "ok"))
        else:
            checks.append(("memory_dir", "missing"))
        
        errors = [msg for _, msg in checks if msg.startswith("error")]
        
        return {
            "step": "health_check",
            "status": "error" if errors else "ok",
            "checks": dict(checks),
            "message": "; ".join(errors) if errors else "All checks passed",
        }
    
    def format_result(self, result: WakeUpResult) -> str:
        """格式化启动结果"""
        status = "WAKE UP OK" if result.success else "WAKE UP FAILED"
        lines = [
            f"# {status}",
            f"Duration: {result.duration_ms}ms | {result.summary}",
            "",
        ]
        
        for step in result.steps:
            icon = {"ok": "✅", "skip": "⏭️", "error": "❌"}.get(step.get("status", "?"), "?")
            file_name = step.get("file", step.get("step", "?"))
            size_str = f" ({step.get('size', 0)} chars)" if step.get("size") else ""
            msg = step.get("message", "")
            lines.append(f"  {icon} {file_name}{size_str} {msg}")
        
        if result.loaded_files:
            lines.append(f"\nLoaded: {', '.join(result.loaded_files)}")
        
        return "\n".join(lines)


_loader: Optional[WakeUpLoader] = None

def get_wake_up_loader() -> WakeUpLoader:
    global _loader
    if _loader is None:
        _loader = WakeUpLoader()
    return _loader
