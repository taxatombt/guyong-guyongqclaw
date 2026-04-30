# -*- coding: utf-8 -*-
"""
agents/managed_bridge.py — Managed Agents → agents/ 集成桥接

把 skills/managed-agents-study/ 的核心能力打通到 agents/ 现有系统。

打通点：
1. workflow_patterns → multi_agent_dispatcher（调度器支持6种workflow模式）
2. exec_isolation → tool_pipeline（凭证隔离注入）
3. session_vault → event_bus（事件持久化到append-only日志）
4. context_layers → prompt_cache_manager（上下文压缩策略升级）
5. harness_modules → agent_types（Harness HITL增强角色安全）
6. skill_metadata → tool_registry（技能渐进式披露）
7. subagent_protocol → multi_agent_dispatcher（子代理协议化委派）
"""

from __future__ import annotations

import sys
import os
import time
import logging
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto

log = logging.getLogger("agents.managed_bridge")

# ── 路径注册：让 managed-agents-study 可导入 ──────────────

_MANAGED_STUDY_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "skills", "managed-agents-study")
)

if _MANAGED_STUDY_PATH not in sys.path:
    sys.path.insert(0, _MANAGED_STUDY_PATH)


# ═══════════════════════════════════════════════════════════
# 1. Workflow → Dispatcher 集成
# ═══════════════════════════════════════════════════════════

class WorkflowMode(Enum):
    """调度器支持的 Workflow 模式（来自 Anthropic 5+1 模式）"""
    PROMPT_CHAIN = "prompt_chain"
    ROUTING = "routing"
    PARALLELIZATION = "parallelization"
    ORCHESTRATOR_WORKERS = "orchestrator_workers"
    EVALUATOR_OPTIMIZER = "evaluator_optimizer"
    AUTONOMOUS = "autonomous"
    # 原有 qclaw 模式
    PLAN_EXPLORE_VERIFY = "plan_explore_verify"  # 默认


def recommend_workflow(task: str) -> WorkflowMode:
    """
    根据任务描述推荐 Workflow 模式。
    
    集成 WorkflowFactory + qclaw 特有逻辑：
    - 默认走 qclaw 原有的 Plan→Explore→Verify→Execute
    - 明确的链式任务 → Prompt Chaining
    - 分类任务 → Routing
    - 需要多视角 → Parallelization
    - 复杂多文件 → Orchestrator-Workers
    - 需要迭代打磨 → Evaluator-Optimizer
    - 开放探索 → Autonomous
    """
    try:
        from workflow_patterns import WorkflowFactory
        rec = WorkflowFactory.recommend(task)
        mapping = {
            "prompt_chaining": WorkflowMode.PROMPT_CHAIN,
            "routing": WorkflowMode.ROUTING,
            "parallelization": WorkflowMode.PARALLELIZATION,
            "orchestrator_workers": WorkflowMode.ORCHESTRATOR_WORKERS,
            "evaluator_optimizer": WorkflowMode.EVALUATOR_OPTIMIZER,
            "autonomous_agent": WorkflowMode.AUTONOMOUS,
            "single_llm_call": WorkflowMode.PLAN_EXPLORE_VERIFY,
        }
        return mapping.get(rec["recommended"], WorkflowMode.PLAN_EXPLORE_VERIFY)
    except ImportError:
        # 降级：简单启发式
        return _fallback_recommend(task)


def _fallback_recommend(task: str) -> WorkflowMode:
    """降级推荐（不依赖 workflow_patterns）"""
    t = task.lower()
    if any(kw in t for kw in ["step by step", "then", "first", "pipeline"]):
        return WorkflowMode.PROMPT_CHAIN
    if any(kw in t for kw in ["classify", "categorize", "route", "不同类型"]):
        return WorkflowMode.ROUTING
    if any(kw in t for kw in ["parallel", "simultaneously", "多个视角", "投票"]):
        return WorkflowMode.PARALLELIZATION
    if any(kw in t for kw in ["complex", "多文件", "coordinate"]):
        return WorkflowMode.ORCHESTRATOR_WORKERS
    if any(kw in t for kw in ["improve", "refine", "iterate", "优化"]):
        return WorkflowMode.EVALUATOR_OPTIMIZER
    if any(kw in t for kw in ["explore", "autonomous", "开放", "swe"]):
        return WorkflowMode.AUTONOMOUS
    return WorkflowMode.PLAN_EXPLORE_VERIFY


# ═══════════════════════════════════════════════════════════
# 2. Credential Isolation → Tool Pipeline 集成
# ═══════════════════════════════════════════════════════════

@dataclass
class CredentialConfig:
    """凭证隔离配置"""
    enabled: bool = True
    vault_path: str = ""  # 空=内存模式
    auto_inject: bool = True  # 自动注入环境变量
    auto_clear: bool = True  # 执行后自动清除
    leak_detection: bool = True  # 泄露检测


def create_credential_vault(config: CredentialConfig = None):
    """
    创建凭证 Vault（桥接 exec_isolation.CredentialVault）
    
    用法：
        vault = create_credential_vault()
        vault.store("DB_PASSWORD", "secret123", source="config")
        # tool_pipeline 执行时自动注入+清除
    """
    try:
        from exec_isolation import CredentialVault
        return CredentialVault()
    except ImportError:
        log.warning("exec_isolation not available, using in-memory vault")
        return _InMemoryVault()


class _InMemoryVault:
    """降级：内存 Vault（exec_isolation 不可用时）"""
    def __init__(self):
        self._store: Dict[str, Tuple[str, str]] = {}  # key → (value, source)
    
    def store(self, key: str, value: str, source: str = "manual"):
        self._store[key] = (value, source)
    
    def retrieve(self, key: str) -> Optional[str]:
        return self._store.get(key, (None, ""))[0]
    
    def inject_to_env(self, sandbox_id: str = "") -> Dict[str, str]:
        return {k: v[0] for k, v in self._store.items()}
    
    def clear_injection(self, sandbox_id: str = ""):
        pass
    
    def scan_for_leaks(self, text: str) -> List[Dict[str, str]]:
        leaks = []
        for key, (value, source) in self._store.items():
            if value in text:
                leaks.append({"key": key, "source": source})
        return leaks


# ═══════════════════════════════════════════════════════════
# 3. Session Vault → Event Bus 集成
# ═══════════════════════════════════════════════════════════

class SessionEventLogger:
    """
    将 event_bus 事件持久化到 session_vault 的 append-only 日志。
    
    集成方式：
        bus = get_event_bus()
        logger = SessionEventLogger(session_id="my_session")
        bus.subscribe(EventType.TOOL_STARTED, logger.on_event)
        bus.subscribe(EventType.TOOL_COMPLETED, logger.on_event)
        # ... 所有事件自动持久化
    """
    
    def __init__(self, session_id: str = ""):
        self.session_id = session_id or f"sess_{int(time.time())}"
        self._vault = None
        self._fallback_log: List[Dict] = []
        
        try:
            from session_vault import SessionVault
            self._vault = SessionVault()
            self._vault.create_session(self.session_id, metadata={"bridge": "managed_bridge"})
        except ImportError:
            log.warning("session_vault not available, using in-memory fallback")
    
    def on_event(self, event):
        """EventBus 订阅回调——事件自动持久化"""
        event_data = {
            "event_type": event.event_type.value if hasattr(event, 'event_type') else str(type(event)),
            "timestamp": event.timestamp if hasattr(event, 'timestamp') else None,
            "data": self._serialize_event(event),
        }
        
        if self._vault:
            try:
                from session_vault import emit as vault_emit
                vault_emit(self.session_id, event_data["event_type"], event_data["data"])
            except Exception as e:
                log.error(f"Failed to persist event to vault: {e}")
                self._fallback_log.append(event_data)
        else:
            self._fallback_log.append(event_data)
    
    def get_history(self) -> List[Dict]:
        """获取完整事件历史"""
        if self._vault:
            try:
                from session_vault import get as vault_get
                return vault_get(self.session_id)
            except Exception:
                pass
        return self._fallback_log
    
    @staticmethod
    def _serialize_event(event) -> Dict:
        """序列化事件对象"""
        result = {}
        for attr in ['tool_name', 'tool_input', 'duration_ms', 'error',
                      'tool_result', 'tokens_used', 'model_name', 'role']:
            if hasattr(event, attr):
                val = getattr(event, attr)
                if val is not None:
                    result[attr] = str(val) if not isinstance(val, (int, float, bool, str)) else val
        return result


# ═══════════════════════════════════════════════════════════
# 4. Context Layers → Prompt Cache 集成
# ═══════════════════════════════════════════════════════════

class ContextBridge:
    """
    桥接 context_layers 的三层上下文 → prompt_cache_manager。
    
    核心：当 prompt_cache 管理器检测到上下文紧张时，
    使用 context_layers 的压缩策略（Auto/Micro/Reactive/Snip）。
    """
    
    def __init__(self):
        self._context_manager = None
        try:
            from context_layers import ContextManager, CompactStrategy
            self._context_manager = ContextManager()
            self.CompactStrategy = CompactStrategy
        except ImportError:
            log.warning("context_layers not available")
            self.CompactStrategy = None
    
    def append_event(self, role: str, content: str, token_count: int = 0):
        """添加事件到上下文管理器"""
        if self._context_manager:
            self._context_manager.append_event(role, content, token_count=token_count)
    
    def compact_if_needed(self, strategy=None) -> Optional[Dict]:
        """按需压缩"""
        if not self._context_manager:
            return None
        s = strategy or (self.CompactStrategy.AUTO_COMPACT if self.CompactStrategy else None)
        if s:
            return self._context_manager.compact(s)
        return None
    
    def render_view(self, system_prompt: str = "") -> str:
        """渲染当前上下文视图"""
        if self._context_manager:
            return self._context_manager.render_view(system_prompt)
        return system_prompt
    
    def get_stats(self) -> Dict:
        """获取上下文统计"""
        if self._context_manager:
            return self._context_manager.get_stats()
        return {"error": "context_layers not available"}


# ═══════════════════════════════════════════════════════════
# 5. Harness HITL → Agent Types 安全增强
# ═══════════════════════════════════════════════════════════

# HITL 危险操作列表（来自 harness_modules.HITLDecision）
HITL_DANGEROUS_OPERATIONS = {
    "drop_database", "delete_all", "rm_rf",
    "charge_fee", "make_payment",
    "modify_production", "deploy_to_prod",
    "grant_permission", "escalate_privilege",
    "access_sensitive_data", "export_data",
}


def requires_human_approval(tool_name: str, tool_input: Dict) -> Tuple[bool, str]:
    """
    检查工具调用是否需要人工审批。
    
    集成 harness_modules.HITL + agent_types 角色权限。
    
    规则：
    1. HITL 危险操作 → 强制人工确认
    2. Explore Agent + 写操作 → 拦截（违反只读铁律）
    3. 危险 pattern（rm -rf / curl|bash 等）→ 强制确认
    """
    # 检查 HITL 危险操作
    input_str = str(tool_input).lower()
    # 同时检查下划线和空格版本
    input_str_normalized = input_str.replace(" ", "_")
    for op in HITL_DANGEROUS_OPERATIONS:
        if op in input_str or op in input_str_normalized:
            return True, f"HITL: dangerous operation '{op}' requires human approval"
    
    # 检查危险 pattern
    dangerous_patterns = [
        (r"rm\s+-rf", "destructive file deletion"),
        (r"curl.*\|\s*bash", "remote code execution"),
        (r"sudo.*--no-check", "sudo with disabled verification"),
        (r"DROP\s+TABLE", "SQL drop table"),
        (r"DELETE\s+FROM.*WHERE\s+1", "SQL delete all"),
    ]
    import re
    for pattern, reason in dangerous_patterns:
        if re.search(pattern, input_str, re.IGNORECASE):
            return True, f"HITL: dangerous pattern detected ({reason})"
    
    # 尝试使用 harness_modules 的 HITL
    try:
        from harness_modules import Harness
        h = Harness()
        req = h.hitl.check_required(input_str)
        if req is not None:
            required = getattr(req, 'required', False) or (req.get('required', False) if hasattr(req, 'get') else False)
            if required:
                reason_text = getattr(req, 'reason', '') or (req.get('reason', '') if hasattr(req, 'get') else 'HITL required')
                return True, reason_text
    except ImportError:
        pass
    
    return False, ""


# ═══════════════════════════════════════════════════════════
# 6. Skill Metadata → Tool Registry 集成
# ═══════════════════════════════════════════════════════════

def discover_skills_for_registry() -> List[Dict[str, str]]:
    """
    扫描所有技能，返回 tool_registry 可用的技能列表。
    
    渐进式披露：返回所有发现的技能元数据。
    """
    try:
        from skill_metadata import SkillRegistry
        registry = SkillRegistry()
        count = registry.scan()
        skills = registry.list_skills()  # 不传 tier，获取全部
        return [
            {
                "name": getattr(s, 'name', str(s)),
                "description": getattr(s, 'description', ''),
                "category": getattr(s, 'category', ''),
            }
            for s in skills
        ]
    except ImportError:
        log.warning("skill_metadata not available")
        return []


# ═══════════════════════════════════════════════════════════
# 7. Subagent Protocol → Dispatcher 集成
# ═══════════════════════════════════════════════════════════

def create_protocol_dispatcher(task: str, role: str = "EXPLORE",
                                max_depth: int = 2,
                                max_concurrent: int = 3):
    """
    使用 subagent_protocol 创建协议化的子代理调度器。
    
    与 MultiAgentDispatcher 的区别：
    - 有明确的消息协议（Request → Response）
    - 有权限隔离（DELEGATE_BLOCKED_TOOLS）
    - 有结果压缩（extract_key_findings）
    - 有深度限制（MAX_DEPTH=2）
    """
    try:
        from subagent_protocol import SubagentRequest, SubagentRole, SubagentDispatcher
        role_map = {
            "EXPLORE": SubagentRole.EXPLORE,
            "PLAN": SubagentRole.PLAN,
            "VERIFY": SubagentRole.VERIFY,
            "EXECUTE": SubagentRole.EXECUTE,
        }
        sub_role = role_map.get(role.upper(), SubagentRole.EXPLORE)
        req = SubagentRequest(task=task, role=sub_role, max_depth=max_depth)
        dispatcher = SubagentDispatcher()
        return req, dispatcher
    except ImportError:
        log.warning("subagent_protocol not available")
        return None, None


# ═══════════════════════════════════════════════════════════
# 一键初始化
# ═══════════════════════════════════════════════════════════

@dataclass
class ManagedBridgeConfig:
    """桥接配置"""
    enable_credential_vault: bool = True
    enable_session_logging: bool = True
    enable_context_bridge: bool = True
    enable_hitl: bool = True
    enable_skill_discovery: bool = True
    enable_subagent_protocol: bool = True
    enable_workflow_recommendation: bool = True
    credential_config: CredentialConfig = field(default_factory=CredentialConfig)


class ManagedBridge:
    """
    一键初始化：将 Managed Agents 能力桥接到 agents/ 系统。
    
    用法：
        bridge = ManagedBridge()
        bridge.initialize()
        
        # 获取推荐 workflow
        mode = bridge.recommend("修复多文件bug")
        
        # 获取凭证 vault
        vault = bridge.vault
        
        # 获取事件日志器
        logger = bridge.event_logger
    """
    
    def __init__(self, config: ManagedBridgeConfig = None):
        self.config = config or ManagedBridgeConfig()
        self.vault = None
        self.event_logger = None
        self.context_bridge = None
        self._initialized = False
    
    def initialize(self) -> Dict[str, bool]:
        """初始化所有桥接组件，返回各组件状态"""
        results = {}
        
        if self.config.enable_credential_vault:
            try:
                self.vault = create_credential_vault(self.config.credential_config)
                results["credential_vault"] = True
            except Exception as e:
                log.error(f"Credential vault init failed: {e}")
                results["credential_vault"] = False
        
        if self.config.enable_session_logging:
            try:
                self.event_logger = SessionEventLogger()
                results["session_logging"] = True
            except Exception as e:
                log.error(f"Session logging init failed: {e}")
                results["session_logging"] = False
        
        if self.config.enable_context_bridge:
            try:
                self.context_bridge = ContextBridge()
                results["context_bridge"] = True
            except Exception as e:
                log.error(f"Context bridge init failed: {e}")
                results["context_bridge"] = False
        
        self._initialized = True
        return results
    
    def recommend(self, task: str) -> WorkflowMode:
        """推荐 Workflow 模式"""
        return recommend_workflow(task)
    
    def check_approval(self, tool_name: str, tool_input: Dict) -> Tuple[bool, str]:
        """检查是否需要人工审批"""
        if not self.config.enable_hitl:
            return False, ""
        return requires_human_approval(tool_name, tool_input)
    
    def status(self) -> Dict[str, Any]:
        """获取桥接状态"""
        return {
            "initialized": self._initialized,
            "vault_active": self.vault is not None,
            "event_logger_active": self.event_logger is not None,
            "context_bridge_active": self.context_bridge is not None,
            "hitl_enabled": self.config.enable_hitl,
        }


# 便捷函数
def create_bridge(config: ManagedBridgeConfig = None) -> ManagedBridge:
    """创建并初始化桥接"""
    bridge = ManagedBridge(config)
    bridge.initialize()
    return bridge
