# -*- coding: utf-8 -*-
"""
hub.py - 顾庸系统 Hub 统一入口

来源: 顾庸t workspace_tools/hub.py
参考: Claude Code Hub + gstack hub 概念

核心功能:
  1. 统一调用入口 - 一个函数调用任何子系统
  2. 子系统注册与发现
  3. 子系统健康检查
  4. 统一日志

子系统清单（当前已注册）:
  - evolver: 经验引擎
  - self_review: 自我复盘
  - instinct: Instinct 系统
  - agents: 多角色 Agent
  - memory: 记忆管理
  - skill_router: Skill 路由
  - context_hygiene: 上下文压缩
  - session_checkpoint: 断点管理
  - handover: 交接文档
  - rule_engine: 规则引擎
  - insights: 洞察分析
  - token_budget: Token 预算
"""

import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from enum import Enum

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")


class SubsystemStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass
class Subsystem:
    """子系统描述"""
    name: str
    description: str
    module_path: str  # 相对 workspace 的模块名
    status: SubsystemStatus = SubsystemStatus.INACTIVE
    functions: List[str] = field(default_factory=list)
    last_check: float = 0


# ─── 子系统注册表 ────────────────────────────────────

SUBSYSTEMS: Dict[str, Subsystem] = {
    "evolver": Subsystem(
        "evolver", "经验引擎 - 记录/召回/进化", "evolver",
        functions=["record", "recall", "get_best", "list_rules"],
    ),
    "self_review": Subsystem(
        "self_review", "自我复盘 - 任务后自动检测漏用/重复错误", "self_review",
        functions=["run_review", "get_corrections", "get_lessons"],
    ),
    "instinct": Subsystem(
        "instinct", "Instinct 原子行为系统", "instinct_model",
        functions=["capture", "promote", "list_instincts"],
    ),
    "agents": Subsystem(
        "agents", "多角色 Agent 系统", "agents",
        functions=["get_tool_registry", "execute_tool", "dispatch"],
    ),
    "memory": Subsystem(
        "memory", "综合记忆管理", "integrated_memory",
        functions=["search_all", "get_all_entries", "format_for_context"],
    ),
    "skill_router": Subsystem(
        "skill_router", "Skill 路由", "skill_router",
        functions=["route", "best_match", "list_rules"],
    ),
    "context_hygiene": Subsystem(
        "context_hygiene", "上下文压缩", "context_hygiene",
        functions=["run_pipeline", "compute_hygiene_level"],
    ),
    "session_checkpoint": Subsystem(
        "session_checkpoint", "Session 断点管理", "session_checkpoint",
        functions=["create_checkpoint", "list_checkpoints", "diff_checkpoints"],
    ),
    "handover": Subsystem(
        "handover", "交接文档生成", "qclaw_handover",
        functions=["build_handover_prompt"],
    ),
    "rule_engine": Subsystem(
        "rule_engine", "Hookify 规则引擎", "rule_engine",
        functions=["evaluate", "get_engine", "list_rules"],
    ),
    "insights": Subsystem(
        "insights", "会话洞察分析", "qclaw_insights",
        functions=["get_quick_summary"],
    ),
    "token_budget": Subsystem(
        "token_budget", "Token 预算管理", "token_budget",
        functions=["check_budget", "allocate"],
    ),
}


class Hub:
    """顾庸系统统一 Hub"""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._status: Dict[str, SubsystemStatus] = {}
    
    def _import(self, module_name: str):
        """动态导入 workspace 模块"""
        if module_name not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        try:
            return __import__(module_name)
        except ImportError:
            return None
    
    def call(self, subsystem: str, function: str, *args, **kwargs) -> Any:
        """
        统一调用入口。
        
        用法: hub.call("evolver", "recall", "安装skill")
        """
        if subsystem not in SUBSYSTEMS:
            raise ValueError(f"Unknown subsystem: {subsystem}")
        
        sub = SUBSYSTEMS[subsystem]
        mod = self._import(sub.module_path)
        if mod is None:
            self._status[subsystem] = SubsystemStatus.ERROR
            raise ImportError(f"Cannot import module: {sub.module_path}")
        
        func = getattr(mod, function, None)
        if func is None:
            raise AttributeError(f"Module {sub.module_path} has no function: {function}")
        
        self._status[subsystem] = SubsystemStatus.ACTIVE
        return func(*args, **kwargs)
    
    def health_check(self, subsystem: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        健康检查。
        subsystem=None → 检查所有
        """
        results = {}
        targets = [subsystem] if subsystem else list(SUBSYSTEMS.keys())
        
        for name in targets:
            sub = SUBSYSTEMS[name]
            start = time.time()
            try:
                mod = self._import(sub.module_path)
                if mod is None:
                    results[name] = {"status": "error", "error": "import_failed"}
                else:
                    elapsed = time.time() - start
                    results[name] = {
                        "status": "ok",
                        "import_ms": round(elapsed * 1000),
                        "functions": [f for f in sub.functions if hasattr(mod, f)],
                    }
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
        
        return results
    
    def list_subsystems(self) -> List[str]:
        """列出所有已注册子系统"""
        return list(SUBSYSTEMS.keys())
    
    def get_subsystem_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取子系统详情"""
        if name not in SUBSYSTEMS:
            return None
        sub = SUBSYSTEMS[name]
        return {
            "name": sub.name,
            "description": sub.description,
            "module": sub.module_path,
            "functions": sub.functions,
            "status": self._status.get(name, "unknown"),
        }


_hub: Optional[Hub] = None

def get_hub() -> Hub:
    global _hub
    if _hub is None:
        _hub = Hub()
    return _hub
