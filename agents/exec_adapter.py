# -*- coding: utf-8 -*-
"""
agents/exec_adapter.py — exec工具适配器

Claude Code 原则7落地：
- 产品化在于处理第二天：cleanup chain
- 脏状态清理、进程泄漏、session恢复

功能：
- exec_command: 带timeout和cleanup的shell执行
- SessionTracker: 追踪活跃的shell进程
- cleanup_all: 全量清理（runAgent cleanup chain）
"""

import subprocess
import psutil
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# ─── 全局进程追踪器 ───────────────────────────────────────

_active_processes: dict[int, dict] = {}
_process_lock = threading.Lock()


@dataclass
class TrackedProcess:
    """被追踪的子进程"""
    pid: int
    cmd: str
    started_at: float
    session_id: str = ""
    agent_id: str = ""
    cwd: str = ""


def _track_process(pid: int, cmd: str, session_id: str = "", cwd: str = "") -> None:
    """内部：注册一个追踪的进程"""
    with _process_lock:
        _active_processes[pid] = {
            "pid": pid,
            "cmd": cmd[:100],
            "started_at": time.time(),
            "session_id": session_id,
            "cwd": cwd,
        }


def _untrack_process(pid: int) -> None:
    """内部：取消追踪"""
    with _process_lock:
        _active_processes.pop(pid, None)


def get_active_processes() -> dict[int, dict]:
    """获取当前所有活跃追踪进程"""
    with _process_lock:
        return dict(_active_processes)


# ─── exec_command ─────────────────────────────────────────

def exec_command(
    command: str,
    workdir: Optional[str] = None,
    timeout: int = 30,
    shell: bool = True,
    capture: bool = True,
    env: dict = None,
) -> dict:
    """
    执行shell命令，带完整治理。
    
    返回 dict:
    - stdout: str
    - stderr: str  
    - returncode: int
    - timed_out: bool
    - pid: int
    """
    cwd = workdir or os.getcwd()
    start = time.time()
    pid = None
    
    try:
        kwargs = {
            "shell": shell,
            "capture_output": capture,
            "text": True,
            "cwd": cwd,
        }
        if env:
            kwargs["env"] = {**os.environ, **env}
        
        proc = subprocess.Popen(command, **kwargs)
        pid = proc.pid
        _track_process(pid, command, cwd=cwd)
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True
        
        duration = time.time() - start
        
        return {
            "stdout": stdout or "",
            "stderr": stderr or "",
            "returncode": proc.returncode,
            "timed_out": timed_out,
            "pid": pid,
            "duration": duration,
            "cmd": command[:100],
        }
    
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "timed_out": False,
            "pid": pid or -1,
            "error": str(e),
        }
    
    finally:
        if pid:
            _untrack_process(pid)


def exec_background(
    command: str,
    workdir: Optional[str] = None,
    session_id: str = "",
) -> dict:
    """
    在后台启动进程（不等待结果）。
    用于长时间运行的任务。
    """
    cwd = workdir or os.getcwd()
    
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    _track_process(proc.pid, command, session_id=session_id, cwd=cwd)
    
    return {
        "pid": proc.pid,
        "session_id": session_id,
        "cmd": command[:100],
        "started_at": time.time(),
    }


# ─── cleanup chain（第二天问题核心）───────────────────────

def kill_process_tree(pid: int, force: bool = False) -> dict:
    """
    杀死进程树（包含所有子进程）。
    Claude Code runAgent.ts 里的 killShellTasksForAgent()。
    """
    killed = []
    errors = []
    
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        for child in children:
            try:
                if force:
                    child.kill()
                else:
                    child.terminate()
                killed.append(child.pid)
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                errors.append(f"child {child.pid}: {e}")
        
        # 最后杀父进程
        try:
            if force:
                parent.kill()
            else:
                parent.terminate()
            killed.append(pid)
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            errors.append(f"parent {pid}: {e}")
    
    except psutil.NoSuchProcess:
        return {"killed": [], "errors": [f"Process {pid} not found"]}
    except Exception as e:
        return {"killed": [], "errors": [str(e)]}
    
    return {"killed": killed, "errors": errors}


def cleanup_session(session_id: str) -> dict:
    """
    清理某个会话的所有相关进程。
    对应 Claude Code runAgent.ts 的 cleanupAgentTracking()。
    """
    results = []
    
    with _process_lock:
        pids = [pid for pid, info in _active_processes.items()
                if info.get("session_id") == session_id]
    
    for pid in pids:
        r = kill_process_tree(pid)
        results.append({"pid": pid, **r})
        _untrack_process(pid)
    
    return {
        "session_id": session_id,
        "cleaned": len(results),
        "results": results,
    }


def cleanup_all() -> dict:
    """
    全量清理：杀死所有追踪的进程。
    对应 Claude Code 的 agent cleanup chain。
    """
    results = []
    
    with _process_lock:
        all_pids = list(_active_processes.keys())
    
    for pid in all_pids:
        r = kill_process_tree(pid)
        results.append({"pid": pid, **r})
        _untrack_process(pid)
    
    return {
        "total_cleaned": len(results),
        "results": results,
    }


def cleanup_stale_processes(max_age_seconds: int = 3600) -> dict:
    """
    清理超过max_age秒的僵尸进程。
    """
    now = time.time()
    stale = []
    
    with _process_lock:
        for pid, info in list(_active_processes.items()):
            age = now - info["started_at"]
            if age > max_age_seconds:
                stale.append(pid)
    
    cleaned = []
    for pid in stale:
        r = kill_process_tree(pid)
        cleaned.append({"pid": pid, **r})
        _untrack_process(pid)
    
    return {
        "stale_cleaned": len(cleaned),
        "max_age": max_age_seconds,
        "results": cleaned,
    }


# ─── 会话状态恢复（第二天问题）────────────────────────────

def save_session_state(session_id: str, state: dict, path: str = None) -> str:
    """
    保存会话状态快照（用于中断恢复）。
    Claude Code recordSidechainTranscript() + writeAgentMetadata()
    """
    import json
    
    if path is None:
        state_dir = Path.home() / ".qclaw" / "sessions" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = str(state_dir / f"{session_id}.state.json")
    
    state["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["session_id"] = session_id
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    return path


def load_session_state(session_id: str) -> Optional[dict]:
    """加载会话状态快照（用于恢复）"""
    import json
    
    state_dir = Path.home() / ".qclaw" / "sessions" / "state"
    path = state_dir / f"{session_id}.state.json"
    
    if not path.exists():
        return None
    
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ─── 主入口 ──────────────────────────────────────────────

def main():
    print("=== exec_adapter 诊断 ===")
    
    # 当前活跃进程
    procs = get_active_processes()
    print(f"活跃追踪进程: {len(procs)}")
    for pid, info in procs.items():
        age = time.time() - info["started_at"]
        print(f"  PID {pid}: {info['cmd'][:40]} ({age:.0f}s)")
    
    # 测试exec_command
    r = exec_command("echo hello from exec_adapter")
    print(f"\nexec test: returncode={r['returncode']} stdout={r['stdout'].strip()!r}")
    
    # 清理僵尸进程（1小时以上）
    if procs:
        result = cleanup_stale_processes(3600)
        print(f"Stale cleanup: {result['stale_cleaned']}")


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────────
# read_file — tool_pipeline 的 read 工具实现
# ─────────────────────────────────────────────────────────────────

def read_file(
    path: str,
    offset: int = None,
    limit: int = None,
    encoding: str = "utf-8",
    errors: str = "ignore",
) -> str:
    """
    读取文件内容（供 tool_pipeline 的 read 工具使用）。
    
    等同于 exec tool_pipeline._execute_tool 中的 read 工具实现。
    """
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"File not found: {path}"
        
        # 读取文件
        content = p.read_text(encoding=encoding, errors=errors)
        
        # 应用 offset + limit
        if offset is not None or limit is not None:
            lines = content.split('\n')
            start = max(0, (offset or 1) - 1)  # offset 是1-indexed
            end = start + (limit or len(lines))
            return '\n'.join(lines[start:end])
        
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"
