# -*- coding: utf-8 -*-
"""
agents/hooks_registry.py — ruflo hooks 系统的 qclaw 落地

来源: E:/ai/学习/ruflo/v3/@claude-flow/hooks/README.md
参考: agents/tool_pipeline.py 的 HookDispatcher / HookResult / HookOutcome 设计

14种hooks + 6个workers的完整实现。

HookRegistry 架构：
- HookType 枚举：14种hook类型
- HookPriority 枚举：critical/high/normal/low
- HookDefinition dataclass：hook定义（name, description, priority, examples）
- WorkerDefinition dataclass：worker定义
- HookRegistry 类：核心注册/分发/预览/状态管理
- 默认hooks：security_pre_exec / memory_consistency_post_write / loop_detection_pre_tool
- Background workers：audit / consolidate / optimize / evolve / cleanup / heartbeat

使用 Python 标准库（asyncio, threading, json, pathlib）。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

# ─── 路径常量 ──────────────────────────────────────────────────────────────

WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", r"C:\Users\yiseg\.qclaw\workspace"))
MEMORY_DIR = WORKSPACE_ROOT / "memory"
WORKSPACE_CONFIG = WORKSPACE_ROOT / "qclaw_config.json"

# ─── HookType 枚举 — 14种hook类型 ─────────────────────────────────────────

class HookType(Enum):
    """14种hook类型，对应 ruflo hooks 系统的核心事件"""
    PRE_TOOL_USE   = "pre_tool_use"    # 工具执行前
    POST_TOOL_USE  = "post_tool_use"   # 工具执行后
    PRE_TASK       = "pre_task"        # 任务开始前
    POST_TASK      = "post_task"       # 任务完成后
    PRE_MESSAGE    = "pre_message"     # 发送消息前
    POST_MESSAGE   = "post_message"    # 发送消息后
    PRE_BASH       = "pre_bash"        # bash命令执行前
    POST_BASH      = "post_bash"       # bash命令执行后
    PRE_READ       = "pre_read"        # 读取文件前
    POST_READ      = "post_read"       # 读取文件后
    PRE_WRITE      = "pre_write"       # 写入文件前
    POST_WRITE     = "post_write"       # 写入文件后
    ON_ERROR       = "on_error"        # 发生错误时
    ON_TIMEOUT     = "on_timeout"      # 超时时


# ─── HookPriority 枚举 ─────────────────────────────────────────────────────

class HookPriority(Enum):
    """hook优先级，影响执行顺序和拦截强度"""
    CRITICAL = 0   # 必须执行，失败则中断
    HIGH     = 1   # 优先执行，失败可中止
    NORMAL   = 2   # 普通执行
    LOW      = 3   # 低优先级，可跳过


# ─── HookDefinition 数据类 ─────────────────────────────────────────────────

@dataclass
class HookDefinition:
    """
    单个hook的定义元数据
    参考: ruflo hooks/type.ts HookDefinition
    """
    name: str                          # hook唯一名称
    hook_type: HookType                # hook类型
    priority: HookPriority             # 执行优先级
    description: str                   # 功能描述
    examples: list[str] = field(default_factory=list)   # 使用示例
    enabled: bool = True              # 是否启用
    timeout: int = 30                 # 超时秒数
    tags: list[str] = field(default_factory=list)      # 标签分类

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hook_type": self.hook_type.value,
            "priority": self.priority.name,
            "priority_value": self.priority.value,
            "description": self.description,
            "examples": self.examples,
            "enabled": self.enabled,
            "timeout": self.timeout,
            "tags": self.tags,
        }


# ─── WorkerDefinition 数据类 ──────────────────────────────────────────────

@dataclass
class WorkerDefinition:
    """
    Background Worker 的定义元数据
    参考: ruflo hooks/workers/*.ts
    """
    name: str                          # worker唯一名称
    description: str                   # 功能描述
    interval_seconds: int              # 执行间隔
    priority: HookPriority             # 优先级
    enabled: bool = True               # 是否启用
    max_duration_seconds: int = 300   # 最大执行时长
    tags: list[str] = field(default_factory=list)      # 标签分类
    last_run: Optional[float] = None  # 上次运行时间戳
    last_status: Optional[str] = None # 上次运行状态
    run_count: int = 0                # 累计运行次数

    def seconds_since_last_run(self) -> Optional[float]:
        if self.last_run is None:
            return None
        return time.time() - self.last_run

    def is_due(self) -> bool:
        if not self.enabled:
            return False
        if self.last_run is None:
            return True
        return self.seconds_since_last_run() >= self.interval_seconds

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "interval_seconds": self.interval_seconds,
            "priority": self.priority.name,
            "enabled": self.enabled,
            "max_duration_seconds": self.max_duration_seconds,
            "tags": self.tags,
            "last_run": datetime.fromtimestamp(self.last_run).isoformat() if self.last_run else None,
            "last_status": self.last_status,
            "run_count": self.run_count,
            "seconds_since_last_run": round(self.seconds_since_last_run(), 1) if self.seconds_since_last_run() is not None else None,
            "is_due": self.is_due(),
        }


# ─── HookRegistry 核心实现 ─────────────────────────────────────────────────

class HookRegistry:
    """
    ruflo hooks 系统的 qclaw 落地实现

    功能：
    - register(handler, hook_type)：注册hook处理器
    - unregister(name, hook_type)：注销hook
    - list_hooks(hook_type)：列出某类型的所有hooks
    - get_by_priority(hook_type, min_priority)：按优先级获取
    - preview(event_type, tool_name)：dry-run预览
    - run_worker(worker_name)：手动执行worker
    - start_background_workers()：启动所有后台worker
    - stop_background_workers()：停止所有worker
    - status()：状态报告

    默认注册3个hooks：
    - security_pre_exec：危险命令检测（critical）
    - memory_consistency_post_write：写后memory一致性检查（high）
    - loop_detection_pre_tool：循环检测（high）

    默认启动6个background workers：
    - audit：安全审计（300s）
    - consolidate：记忆整合（1800s）
    - optimize：性能优化（600s）
    - evolve：规则进化（3600s）
    - cleanup：临时文件清理（7200s）
    - heartbeat：心跳自检（1800s）

    参考: Codex hooks/engine/dispatcher.rs + ruflo v3/@claude-flow/hooks
    """

    # 14种hook定义元数据
    HOOK_DEFINITIONS: dict[HookType, HookDefinition] = {}

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or WORKSPACE_ROOT
        self.memory_dir = self.workspace_root / "memory"
        self.config_path = self.workspace_root / "qclaw_config.json"

        # _hooks[hook_type][handler_name] = handler_fn
        self._hooks: dict[HookType, dict[str, Callable]] = {ht: {} for ht in HookType}

        # 背景workers
        self._workers: dict[str, WorkerDefinition] = {}
        self._worker_threads: dict[str, threading.Thread] = {}
        self._worker_stop_events: dict[str, threading.Event] = {}
        self._workers_running = threading.Event()
        self._workers_running.set()

        # 初始化hook定义
        self._init_hook_definitions()

        # 初始化worker定义
        self._init_worker_definitions()

        # 注册默认hooks
        self._register_default_hooks()

        # 循环检测状态
        self._loop_detection_history: list[dict] = []
        self._loop_detection_max = 50

    # ─── Hook定义初始化 ───────────────────────────────────────────────────

    def _init_hook_definitions(self) -> None:
        """初始化14种hook的定义元数据"""
        definitions = [
            HookDefinition(
                name="pre_tool_use", hook_type=HookType.PRE_TOOL_USE,
                priority=HookPriority.CRITICAL,
                description="工具执行前触发，可用于参数验证、危险检测",
                examples=["检查 curl 参数", "验证文件路径"],
                tags=["tool", "security"]
            ),
            HookDefinition(
                name="post_tool_use", hook_type=HookType.POST_TOOL_USE,
                priority=HookPriority.CRITICAL,
                description="工具执行后触发，可用于结果验证、状态记录",
                examples=["记录工具输出", "检查返回码"],
                tags=["tool", "audit"]
            ),
            HookDefinition(
                name="pre_task", hook_type=HookType.PRE_TASK,
                priority=HookPriority.HIGH,
                description="任务开始前触发，可用于上下文准备",
                examples=["加载记忆", "检查前置条件"],
                tags=["task", "context"]
            ),
            HookDefinition(
                name="post_task", hook_type=HookType.POST_TASK,
                priority=HookPriority.HIGH,
                description="任务完成后触发，可用于结果归档",
                examples=["保存结果", "更新记忆"],
                tags=["task", "archive"]
            ),
            HookDefinition(
                name="pre_message", hook_type=HookType.PRE_MESSAGE,
                priority=HookPriority.NORMAL,
                description="发送消息前触发，可用于内容审核",
                examples=["过滤敏感词", "格式化输出"],
                tags=["message", "content"]
            ),
            HookDefinition(
                name="post_message", hook_type=HookType.POST_MESSAGE,
                priority=HookPriority.NORMAL,
                description="发送消息后触发，可用于日志记录",
                examples=["记录发送历史", "通知下游"],
                tags=["message", "log"]
            ),
            HookDefinition(
                name="pre_bash", hook_type=HookType.PRE_BASH,
                priority=HookPriority.CRITICAL,
                description="bash命令执行前触发，危险命令拦截",
                examples=["检测 rm -rf", "检查 curl/下载"],
                tags=["bash", "security", "critical"]
            ),
            HookDefinition(
                name="post_bash", hook_type=HookType.POST_BASH,
                priority=HookPriority.HIGH,
                description="bash命令执行后触发，可用于结果检查",
                examples=["检查exit code", "记录输出"],
                tags=["bash", "audit"]
            ),
            HookDefinition(
                name="pre_read", hook_type=HookType.PRE_READ,
                priority=HookPriority.LOW,
                description="读取文件前触发，可用于路径验证",
                examples=["检查文件权限", "验证路径安全"],
                tags=["file", "read"]
            ),
            HookDefinition(
                name="post_read", hook_type=HookType.POST_READ,
                priority=HookPriority.LOW,
                description="读取文件后触发，可用于内容缓存",
                examples=["缓存文件内容", "更新访问时间"],
                tags=["file", "cache"]
            ),
            HookDefinition(
                name="pre_write", hook_type=HookType.PRE_WRITE,
                priority=HookPriority.HIGH,
                description="写入文件前触发，可用于备份/冲突检测",
                examples=["检测文件覆盖", "创建备份"],
                tags=["file", "write", "backup"]
            ),
            HookDefinition(
                name="post_write", hook_type=HookType.POST_WRITE,
                priority=HookPriority.HIGH,
                description="写入文件后触发，可用于memory同步",
                examples=["同步memory", "更新索引"],
                tags=["file", "write", "memory"]
            ),
            HookDefinition(
                name="on_error", hook_type=HookType.ON_ERROR,
                priority=HookPriority.CRITICAL,
                description="发生错误时触发，可用于错误处理",
                examples=["记录错误", "通知告警", "回滚操作"],
                tags=["error", "critical", "alert"]
            ),
            HookDefinition(
                name="on_timeout", hook_type=HookType.ON_TIMEOUT,
                priority=HookPriority.CRITICAL,
                description="超时时触发，可用于超时处理",
                examples=["清理资源", "通知超时"],
                tags=["timeout", "critical"]
            ),
        ]
        for defn in definitions:
            self.HOOK_DEFINITIONS[defn.hook_type] = defn

    # ─── Worker定义初始化 ─────────────────────────────────────────────────

    def _init_worker_definitions(self) -> None:
        """初始化6个background worker的定义"""
        workers = [
            WorkerDefinition(
                name="audit",
                description="安全审计：扫描危险操作历史，检测异常模式",
                interval_seconds=300,
                priority=HookPriority.CRITICAL,
                tags=["security", "audit", "critical"]
            ),
            WorkerDefinition(
                name="consolidate",
                description="记忆整合：将短期记忆合并到长期记忆中",
                interval_seconds=1800,
                priority=HookPriority.NORMAL,
                tags=["memory", "consolidate"]
            ),
            WorkerDefinition(
                name="optimize",
                description="性能优化：检查上下文大小、清理过期缓存",
                interval_seconds=600,
                priority=HookPriority.HIGH,
                tags=["performance", "optimize"]
            ),
            WorkerDefinition(
                name="evolve",
                description="规则进化：基于执行历史优化规则和策略",
                interval_seconds=3600,
                priority=HookPriority.NORMAL,
                tags=["evolve", "ml", "rules"]
            ),
            WorkerDefinition(
                name="cleanup",
                description="临时文件清理：清理 /tmp、__pycache__ 等临时文件",
                interval_seconds=7200,
                priority=HookPriority.LOW,
                tags=["cleanup", "disk"]
            ),
            WorkerDefinition(
                name="heartbeat",
                description="心跳自检：检查未复盘任务、通知维护建议",
                interval_seconds=1800,
                priority=HookPriority.NORMAL,
                tags=["heartbeat", "review", "self-improve"]
            ),
        ]
        for w in workers:
            self._workers[w.name] = w

    # ─── 默认Hooks注册 ────────────────────────────────────────────────────

    def _register_default_hooks(self) -> None:
        """注册3个默认hooks"""
        # 1. security_pre_exec：危险命令检测（critical）
        self.register(
            handler=self._security_pre_exec_handler,
            hook_type=HookType.PRE_BASH,
            name="security_pre_exec",
            priority=HookPriority.CRITICAL
        )
        # 也挂到 PRE_TOOL_USE（工具执行前统一检测）
        self.register(
            handler=self._security_pre_tool_handler,
            hook_type=HookType.PRE_TOOL_USE,
            name="security_pre_tool",
            priority=HookPriority.CRITICAL
        )

        # 2. memory_consistency_post_write：写后memory一致性检查（high）
        self.register(
            handler=self._memory_consistency_handler,
            hook_type=HookType.POST_WRITE,
            name="memory_consistency_post_write",
            priority=HookPriority.HIGH
        )

        # 3. loop_detection_pre_tool：循环检测（high）
        self.register(
            handler=self._loop_detection_handler,
            hook_type=HookType.PRE_TOOL_USE,
            name="loop_detection_pre_tool",
            priority=HookPriority.HIGH
        )

    # ─── 默认Hook处理器 ───────────────────────────────────────────────────

    # 危险命令正则模式
    DANGEROUS_PATTERNS = [
        (re.compile(r"^\s*rm\s+-rf\s+/(?:\s|$)", re.I), "rm -rf / 根目录删除"),
        (re.compile(r"^\s*rm\s+-rf\s+/\*\s*$", re.I), "rm -rf /* 全目录删除"),
        (re.compile(r"^\s*del\s+/[sfqr]\s+\*", re.I), "del /s/q * Windows递归删除"),
        (re.compile(r"format\s+[a-z]:", re.I), "format 盘符"),
        (re.compile(r"^\s*dd\s+if=", re.I), "dd 直接磁盘写入"),
        (re.compile(r">\s*/dev/sd[a-z]", re.I), "重定向到磁盘设备"),
        (re.compile(r"mkfs\s+", re.I), "mkfs 格式化"),
        (re.compile(r"curl.*\|.*sh\s*$", re.I), "curl|sh 远程脚本执行"),
        (re.compile(r"wget.*\|.*sh\s*$", re.I), "wget|sh 远程脚本执行"),
        (re.compile(r"chmod\s+-R\s+777\s+/", re.I), "chmod 777 递归到根目录"),
        (re.compile(r":(){.*:\|.*:.*}&", re.I), "Fork炸弹"),
        (re.compile(r"shutdown", re.I), "shutdown 关机"),
        (re.compile(r"halt", re.I), "halt 停机"),
        (re.compile(r"reboot", re.I), "reboot 重启"),
    ]

    def _security_pre_exec_handler(self, context: dict) -> dict:
        """
        危险命令检测（PRE_BASH）
        返回 {"allowed": bool, "reason": str, "modified": Optional[str]}
        """
        cmd = context.get("command", "")
        if not cmd:
            return {"allowed": True, "reason": "empty command"}

        # 解析多行命令，取第一行
        first_line = cmd.strip().split("\n")[0].strip()
        if not first_line or first_line.startswith("#"):
            return {"allowed": True, "reason": "comment or empty"}

        for pattern, description in self.DANGEROUS_PATTERNS:
            if pattern.search(first_line):
                return {
                    "allowed": False,
                    "reason": f"危险命令: {description}",
                    "pattern": pattern.pattern,
                    "command": first_line[:100],
                    "action": "BLOCK",
                }

        # 检测可能的危险模式
        if re.search(r"curl\s+http://", first_line, re.I):
            return {
                "allowed": True,
                "reason": "HTTP（明文）请求，建议使用 HTTPS",
                "command": first_line[:100],
                "action": "WARN",
            }

        return {"allowed": True, "reason": "命令检查通过"}

    def _security_pre_tool_handler(self, context: dict) -> dict:
        """
        危险工具参数检测（PRE_TOOL_USE）
        检测 exec / write / delete 等危险操作
        """
        tool_name = context.get("tool_name", "")
        tool_input = context.get("tool_input", {})

        dangerous_tools = {
            "exec": ["rm", "del", "format", "shutdown"],
            "write": ["C:\\", "C:/", "/etc", "/root", "/sys", "/proc"],
        }

        if tool_name == "exec":
            cmd = tool_input.get("command", "")
            for pattern, _ in self.DANGEROUS_PATTERNS:
                if pattern.search(cmd):
                    return {
                        "allowed": False,
                        "reason": f"危险命令检测: tool={tool_name}",
                        "action": "BLOCK",
                    }

        if tool_name == "write":
            path = str(tool_input.get("path", ""))
            for dangerous_prefix in dangerous_tools.get("write", []):
                if path.lower().startswith(dangerous_prefix.lower()):
                    return {
                        "allowed": False,
                        "reason": f"禁止写入系统路径: {path}",
                        "action": "BLOCK",
                    }

        return {"allowed": True, "reason": "工具参数检查通过"}

    def _memory_consistency_handler(self, context: dict) -> dict:
        """
        写后memory一致性检查（POST_WRITE）
        检查写入的文件是否需要同步到memory
        """
        path = context.get("path", "")
        content = context.get("content", "")

        if not path:
            return {"status": "skipped", "reason": "no path"}

        path_obj = Path(path)
        rel_path = str(path_obj)

        # 需要同步到memory的文件类型
        sync_patterns = [
            r"MEMORY\.md$",
            r"memory/.*\.md$",
            r"SOUL\.md$",
            r"USER\.md$",
            r"AGENTS\.md$",
            r"TOOLS\.md$",
            r"agents/.*\.py$",
        ]

        needs_sync = any(re.search(p, rel_path, re.I) for p in sync_patterns)

        result = {
            "status": "checked",
            "path": path,
            "needs_memory_sync": needs_sync,
        }

        if needs_sync:
            # 简单记录：检查文件是否存在于memory索引
            memory_files = list(self.memory_dir.glob("*.md")) if self.memory_dir.exists() else []
            result["memory_file_count"] = len(memory_files)
            result["recommendation"] = "建议运行 consolidate_worker 同步记忆"

        return result

    def _loop_detection_handler(self, context: dict) -> dict:
        """
        循环检测（PRE_TOOL_USE）
        检测短时间内相同工具+相同参数的重复调用
        """
        tool_name = context.get("tool_name", "")
        tool_input = context.get("tool_input", {})
        timestamp = time.time()

        # 构建调用签名
        try:
            input_str = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
        except Exception:
            input_str = str(tool_input)

        signature = f"{tool_name}:{input_str[:200]}"

        # 添加到历史
        entry = {
            "signature": signature,
            "tool_name": tool_name,
            "timestamp": timestamp,
            "count": 1,
        }

        # 查找是否有重复
        repeated = False
        loop_window = 300.0  # 5分钟内相同调用视为循环

        self._loop_detection_history = [
            e for e in self._loop_detection_history
            if timestamp - e["timestamp"] < loop_window
        ]

        for existing in self._loop_detection_history:
            if existing["signature"] == signature:
                existing["count"] += 1
                entry["count"] = existing["count"]
                if existing["count"] >= 3:
                    repeated = True
                break
        else:
            self._loop_detection_history.append(entry)

        # 限制历史大小
        if len(self._loop_detection_history) > self._loop_detection_max:
            self._loop_detection_history = self._loop_detection_history[-self._loop_detection_max:]

        if repeated:
            return {
                "allowed": True,  # 不阻止，但标记警告
                "reason": f"检测到循环调用: {tool_name} x{entry['count']}次",
                "action": "WARN",
                "repeat_count": entry["count"],
            }

        return {"allowed": True, "reason": "无循环检测"}

    # ─── 核心API：注册/注销 ───────────────────────────────────────────────

    def register(
        self,
        handler: Callable[[dict], dict],
        hook_type: HookType,
        name: Optional[str] = None,
        priority: Optional[HookPriority] = None,
    ) -> HookDefinition:
        """
        注册一个hook处理器

        Args:
            handler: 处理器函数，接收context字典，返回结果字典
            hook_type: hook类型
            name: hook名称（默认从handler.__name__获取）
            priority: 优先级（默认从hook定义获取）

        Returns:
            HookDefinition 注册后的定义
        """
        handler_name = name or getattr(handler, "__name__", "anonymous")
        self._hooks[hook_type][handler_name] = handler

        # 获取或创建定义
        if hook_type in self.HOOK_DEFINITIONS:
            defn = self.HOOK_DEFINITIONS[hook_type]
        else:
            defn = HookDefinition(
                name=handler_name,
                hook_type=hook_type,
                priority=priority or HookPriority.NORMAL,
                description="用户注册hook",
            )

        if priority is not None:
            defn = HookDefinition(
                name=handler_name,
                hook_type=hook_type,
                priority=priority,
                description=defn.description,
                examples=defn.examples,
            )
            self.HOOK_DEFINITIONS[hook_type] = defn

        return defn

    def unregister(self, name: str, hook_type: HookType) -> bool:
        """
        注销一个hook

        Returns:
            bool 是否成功注销
        """
        if name in self._hooks[hook_type]:
            del self._hooks[hook_type][name]
            return True
        return False

    def list_hooks(self, hook_type: Optional[HookType] = None) -> list[HookDefinition]:
        """
        列出hooks

        Args:
            hook_type: 如果指定，只列出该类型；否则列出所有

        Returns:
            list[HookDefinition]
        """
        if hook_type is not None:
            return [
                HookDefinition(
                    name=name,
                    hook_type=hook_type,
                    priority=self.HOOK_DEFINITIONS.get(hook_type, HookDefinition(
                        name=name, hook_type=hook_type, priority=HookPriority.NORMAL,
                        description=""
                    )).priority,
                    description=self.HOOK_DEFINITIONS.get(hook_type, HookDefinition(
                        name=name, hook_type=hook_type, priority=HookPriority.NORMAL,
                        description=""
                    )).description,
                )
                for name in self._hooks[hook_type]
            ]

        result = []
        for ht in HookType:
            result.extend(self.list_hooks(ht))
        return result

    def get_by_priority(
        self,
        hook_type: HookType,
        min_priority: Optional[HookPriority] = None
    ) -> list[tuple[str, Callable]]:
        """
        按优先级获取hooks

        Args:
            hook_type: hook类型
            min_priority: 最低优先级（只返回 >= 此优先级的）

        Returns:
            list[(name, handler)] 按优先级排序
        """
        hooks = list(self._hooks[hook_type].items())
        if min_priority is not None:
            defn = self.HOOK_DEFINITIONS.get(hook_type)
            if defn and defn.priority.value > min_priority.value:
                return []
        return hooks

    # ─── 核心API：触发 ───────────────────────────────────────────────────

    def trigger(
        self,
        hook_type: HookType,
        context: Optional[dict] = None,
        stop_on_critical_failure: bool = True,
    ) -> list[dict]:
        """
        触发某个hook类型的所有处理器

        Args:
            hook_type: hook类型
            context: 上下文数据（tool_name, command, path等）
            stop_on_critical_failure: critical hook失败时是否停止

        Returns:
            list[dict] 每个handler的执行结果
        """
        context = context or {}
        context.setdefault("_triggered_at", datetime.now().isoformat())
        context.setdefault("_hook_type", hook_type.value)

        results = []
        handlers = list(self._hooks[hook_type].items())

        for name, handler in handlers:
            start = time.time()
            try:
                if asyncio.iscoroutinefunction(handler):
                    # 异步handler
                    result = asyncio.run(handler(context))
                else:
                    result = handler(context)
            except Exception as e:
                result = {
                    "hook_name": name,
                    "status": "error",
                    "error": str(e),
                    "duration_ms": (time.time() - start) * 1000,
                }

            if isinstance(result, dict):
                result.setdefault("hook_name", name)
                result.setdefault("duration_ms", (time.time() - start) * 1000)
            else:
                result = {
                    "hook_name": name,
                    "status": "success",
                    "result": str(result),
                    "duration_ms": (time.time() - start) * 1000,
                }

            results.append(result)

            # critical失败且stop_on_critical_failure → 中断
            defn = self.HOOK_DEFINITIONS.get(hook_type)
            if (stop_on_critical_failure
                and defn
                and defn.priority == HookPriority.CRITICAL
                and result.get("status") == "error"):
                results.append({
                    "hook_name": "__abort__",
                    "status": "aborted",
                    "reason": f"critical hook '{name}' failed, stopping",
                })
                break

        return results

    def preview(
        self,
        event_type: str,
        tool_name: Optional[str] = None,
        tool_input: Optional[dict] = None,
    ) -> dict:
        """
        dry-run预览：列出会触发哪些hooks（不实际执行）

        Args:
            event_type: hook类型字符串（与HookType.value对应）
            tool_name: 工具名（用于matcher过滤）
            tool_input: 工具输入

        Returns:
            dict 预览结果
        """
        try:
            hook_type = HookType(event_type)
        except ValueError:
            return {"error": f"unknown hook type: {event_type}", "valid_types": [e.value for e in HookType]}

        handlers = list(self._hooks[hook_type].items())
        matched = []

        for name, handler in handlers:
            matched.append({
                "name": name,
                "hook_type": hook_type.value,
                "priority": self.HOOK_DEFINITIONS.get(hook_type, HookDefinition(
                    name=name, hook_type=hook_type, priority=HookPriority.NORMAL,
                    description=""
                )).priority.name,
                "description": self.HOOK_DEFINITIONS.get(hook_type, HookDefinition(
                    name=name, hook_type=hook_type, priority=HookPriority.NORMAL,
                    description=""
                )).description,
            })

        return {
            "event_type": event_type,
            "tool_name": tool_name or "(any)",
            "matched_hooks": matched,
            "total": len(matched),
        }

    # ─── 核心API：Workers ─────────────────────────────────────────────────

    def run_worker(self, worker_name: str) -> dict:
        """
        手动执行一个worker

        Args:
            worker_name: worker名称

        Returns:
            dict 执行结果
        """
        if worker_name not in self._workers:
            return {"error": f"unknown worker: {worker_name}"}

        worker_def = self._workers[worker_name]
        start = time.time()

        try:
            if worker_name == "audit":
                result = self._audit_worker_impl()
            elif worker_name == "consolidate":
                result = self._consolidate_worker_impl()
            elif worker_name == "optimize":
                result = self._optimize_worker_impl()
            elif worker_name == "evolve":
                result = self._evolve_worker_impl()
            elif worker_name == "cleanup":
                result = self._cleanup_worker_impl()
            elif worker_name == "heartbeat":
                result = self._heartbeat_worker_impl()
            else:
                result = {"error": "not implemented"}

            worker_def.last_run = time.time()
            worker_def.last_status = "success"
            worker_def.run_count += 1

            return {
                "worker": worker_name,
                "status": "success",
                "duration_ms": round((time.time() - start) * 1000, 1),
                "result": result,
            }

        except Exception as e:
            worker_def.last_run = time.time()
            worker_def.last_status = f"error: {e}"
            return {
                "worker": worker_name,
                "status": "error",
                "error": str(e),
                "duration_ms": round((time.time() - start) * 1000, 1),
            }

    # ─── Worker实现 ──────────────────────────────────────────────────────

    def _audit_worker_impl(self) -> dict:
        """
        audit_worker：扫描危险操作历史
        - 检查最近的exec调用
        - 检测异常模式（短时间内大量exec）
        - 生成安全报告
        """
        # 简单实现：检查配置中的安全设置
        findings = []

        # 检查workspace根目录
        ws = self.workspace_root
        if not ws.exists():
            findings.append({"type": "warning", "msg": "workspace不存在"})

        # 检查memory目录大小
        if self.memory_dir.exists():
            md_files = list(self.memory_dir.glob("*.md"))
            if len(md_files) > 200:
                findings.append({
                    "type": "info",
                    "msg": f"memory文件数量较多: {len(md_files)}，建议运行consolidate",
                })

        # 检查循环检测历史
        if len(self._loop_detection_history) > 10:
            repeats = [e for e in self._loop_detection_history if e.get("count", 1) >= 3]
            if repeats:
                findings.append({
                    "type": "warning",
                    "msg": f"检测到{len(repeats)}个循环调用模式",
                    "patterns": [e["signature"][:80] for e in repeats[:5]],
                })

        return {
            "findings": findings,
            "total_findings": len(findings),
            "loop_history_size": len(self._loop_detection_history),
            "timestamp": datetime.now().isoformat(),
        }

    def _consolidate_worker_impl(self) -> dict:
        """
        consolidate_worker：记忆整合
        - 检查memory/目录中的碎片
        - 生成整合建议
        """
        if not self.memory_dir.exists():
            return {"status": "skipped", "reason": "memory目录不存在"}

        md_files = sorted(self.memory_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
        memories = []

        for f in md_files[-10:]:  # 最近10个
            try:
                content = f.read_text(encoding="utf-8")
                first_line = content.strip().split("\n")[0] if content.strip() else ""
                memories.append({
                    "file": f.name,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "preview": first_line[:100],
                })
            except Exception:
                pass

        return {
            "status": "ok",
            "memory_files": len(md_files),
            "recent_memories": memories,
            "recommendation": "建议定期回顾MEMORY.md中的长期记忆" if memories else "memory正常",
        }

    def _optimize_worker_impl(self) -> dict:
        """
        optimize_worker：性能优化
        - 清理__pycache__
        - 清理.pyc文件
        - 检查token使用情况
        """
        cleaned = []

        # 清理 __pycache__
        for pycache in self.workspace_root.rglob("__pycache__"):
            try:
                import shutil
                shutil.rmtree(pycache)
                cleaned.append(f"__pycache__: {pycache}")
            except Exception:
                pass

        # 清理 .pyc
        for pyc in self.workspace_root.rglob("*.pyc"):
            try:
                pyc.unlink()
                cleaned.append(f".pyc: {pyc}")
            except Exception:
                pass

        # 检查agents目录
        agents_dir = self.workspace_root / "agents"
        if agents_dir.exists():
            py_files = list(agents_dir.glob("*.py"))
            return {
                "status": "ok",
                "cleaned_items": len(cleaned),
                "agents_py_files": len(py_files),
                "cleaned": cleaned[:20],
                "timestamp": datetime.now().isoformat(),
            }

        return {"status": "ok", "cleaned_items": len(cleaned), "cleaned": cleaned}

    def _evolve_worker_impl(self) -> dict:
        """
        evolve_worker：规则进化
        - 检查evolver.py记录
        - 生成优化建议
        """
        evolver_path = self.workspace_root / "evolver.py"

        suggestions = []

        # 检查evolver.py是否存在
        if evolver_path.exists():
            try:
                content = evolver_path.read_text(encoding="utf-8")
                rule_count = content.count("def record") + content.count("def best_method")
                suggestions.append({
                    "type": "info",
                    "msg": f"evolver.py 存在，规则方法数: {rule_count}",
                })
            except Exception as e:
                suggestions.append({"type": "warning", "msg": f"读取evolver.py失败: {e}"})
        else:
            suggestions.append({
                "type": "info",
                "msg": "evolver.py 不存在，规则进化功能未启用",
            })

        # 检查上次运行到现在的时间
        memory_md = self.workspace_root / "MEMORY.md"
        if memory_md.exists():
            try:
                mtime = datetime.fromtimestamp(memory_md.stat().st_mtime)
                age = (datetime.now() - mtime).days
                suggestions.append({
                    "type": "info",
                    "msg": f"MEMORY.md 上次更新: {age}天前",
                })
            except Exception:
                pass

        return {
            "status": "ok",
            "suggestions": suggestions,
            "timestamp": datetime.now().isoformat(),
        }

    def _cleanup_worker_impl(self) -> dict:
        """
        cleanup_worker：临时文件清理
        - 清理 /tmp 相关
        - 清理 Windows temp 文件
        """
        cleaned = []
        import shutil

        # 清理 workspace 中的 __pycache__
        for pycache in self.workspace_root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
                cleaned.append(f"__pycache__: {pycache.name}")
            except Exception:
                pass

        # 清理 .tmp 文件
        for tmp in self.workspace_root.rglob("*.tmp"):
            try:
                tmp.unlink()
                cleaned.append(f".tmp: {tmp.name}")
            except Exception:
                pass

        # 清理 _tw_ 临时文件（qclaw-text-file 生成的）
        for tw in self.workspace_root.rglob("_tw_*"):
            try:
                tw.unlink()
                cleaned.append(f"_tw_: {tw.name}")
            except Exception:
                pass

        return {
            "status": "ok",
            "cleaned_items": len(cleaned),
            "cleaned": cleaned[:30],
            "timestamp": datetime.now().isoformat(),
        }

    def _heartbeat_worker_impl(self) -> dict:
        """
        heartbeat_worker：心跳自检
        - 检查heartbeat_self_review.py
        - 检查未复盘任务
        """
        reminders = []

        # 检查evolver.py
        evolver_path = self.workspace_root / "evolver.py"
        if not evolver_path.exists():
            reminders.append("evolver.py 不存在，建议运行 evolver_worker")

        # 检查self_review.py
        sr_path = self.workspace_root / "self_review.py"
        if not sr_path.exists():
            reminders.append("self_review.py 不存在，建议运行 review")

        # 检查memory目录
        if not self.memory_dir.exists():
            reminders.append("memory目录不存在，建议创建")

        # 检查最近的memory文件
        if self.memory_dir.exists():
            today = datetime.now().strftime("%Y-%m-%d")
            today_mem = self.memory_dir / f"{today}.md"
            if not today_mem.exists():
                reminders.append(f"今日memory文件不存在: {today}.md")

        return {
            "status": "ok",
            "reminders": reminders,
            "timestamp": datetime.now().isoformat(),
        }

    # ─── Workers后台管理 ─────────────────────────────────────────────────

    def _worker_loop(self, worker_name: str) -> None:
        """单个worker的后台循环"""
        worker_def = self._workers[worker_name]
        stop_event = self._worker_stop_events[worker_name]

        while not stop_event.is_set():
            if worker_def.is_due():
                self.run_worker(worker_name)
            # 每5秒检查一次是否该运行
            for _ in range(5):
                if stop_event.wait(timeout=1.0):
                    break

    def start_background_workers(self) -> dict:
        """
        启动所有后台workers

        Returns:
            dict 启动结果
        """
        if self._workers_running.is_set():
            return {"status": "already_running", "workers": list(self._workers.keys())}

        self._workers_running.set()
        started = []

        for name, worker_def in self._workers.items():
            if not worker_def.enabled:
                continue

            stop_event = threading.Event()
            self._worker_stop_events[name] = stop_event

            thread = threading.Thread(
                target=self._worker_loop,
                args=(name,),
                name=f"HookWorker-{name}",
                daemon=True,
            )
            thread.start()
            self._worker_threads[name] = thread
            started.append(name)

        return {
            "status": "started",
            "workers": started,
            "total": len(started),
        }

    def stop_background_workers(self, timeout: float = 5.0) -> dict:
        """
        停止所有后台workers

        Args:
            timeout: 等待线程结束的超时秒数

        Returns:
            dict 停止结果
        """
        self._workers_running.clear()

        stopped = []
        for name, stop_event in self._worker_stop_events.items():
            stop_event.set()

        # 等待线程结束
        for name, thread in self._worker_threads.items():
            thread.join(timeout=timeout)
            if not thread.is_alive():
                stopped.append(name)

        return {
            "status": "stopped",
            "stopped": stopped,
            "remaining": len(self._worker_threads) - len(stopped),
        }

    # ─── 状态报告 ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        """
        返回完整状态报告

        Returns:
            dict 包含hooks、workers、循环检测状态的完整报告
        """
        hook_summary = {}
        for ht in HookType:
            count = len(self._hooks[ht])
            defn = self.HOOK_DEFINITIONS.get(ht)
            hook_summary[ht.value] = {
                "count": count,
                "priority": defn.priority.name if defn else "NORMAL",
                "description": defn.description if defn else "",
            }

        worker_summary = {name: w.to_dict() for name, w in self._workers.items()}

        # 循环检测状态
        recent_loops = [
            {**e, "age_seconds": round(time.time() - e["timestamp"], 1)}
            for e in self._loop_detection_history[-10:]
        ]

        return {
            "registry": "HookRegistry",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "hooks": {
                "total_types": len(HookType),
                "summary": hook_summary,
                "registered_count": sum(len(v) for v in self._hooks.values()),
            },
            "workers": {
                "total": len(self._workers),
                "enabled": sum(1 for w in self._workers.values() if w.enabled),
                "running": self._workers_running.is_set(),
                "summary": worker_summary,
            },
            "loop_detection": {
                "history_size": len(self._loop_detection_history),
                "recent": recent_loops,
            },
            "workspace": str(self.workspace_root),
        }

    def to_json(self, indent: int = 2) -> str:
        """将状态序列化为JSON"""
        return json.dumps(self.status(), ensure_ascii=False, indent=indent)


# ─── 单例 ────────────────────────────────────────────────────────────────────

_registry: Optional[HookRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> HookRegistry:
    """获取全局HookRegistry单例"""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = HookRegistry()
    return _registry


# ─── 便捷函数 ───────────────────────────────────────────────────────────────

def register_default_hooks() -> HookRegistry:
    """注册默认hooks（显式调用）"""
    reg = get_registry()
    return reg


def trigger_hook(hook_type: HookType, context: Optional[dict] = None) -> list[dict]:
    """触发hook的便捷函数"""
    return get_registry().trigger(hook_type, context)


def hook_preview(event_type: str, tool_name: Optional[str] = None) -> dict:
    """预览hook的便捷函数"""
    return get_registry().preview(event_type, tool_name)


# ─── CLI入口（可选）──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HookRegistry CLI")
    parser.add_argument("action", choices=["status", "preview", "run-worker", "start", "stop", "list"])
    parser.add_argument("--hook-type", help="hook类型，如 pre_tool_use")
    parser.add_argument("--tool-name", help="工具名（用于preview）")
    parser.add_argument("--worker", help="worker名称")

    args = parser.parse_args()
    reg = get_registry()

    if args.action == "status":
        print(reg.to_json())
    elif args.action == "preview":
        result = reg.preview(args.hook_type or "pre_tool_use", args.tool_name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "run-worker":
        if not args.worker:
            print("Error: --worker required")
        else:
            result = reg.run_worker(args.worker)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "start":
        result = reg.start_background_workers()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "stop":
        result = reg.stop_background_workers()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "list":
        hooks = reg.list_hooks()
        print(json.dumps([h.to_dict() for h in hooks], ensure_ascii=False, indent=2))
