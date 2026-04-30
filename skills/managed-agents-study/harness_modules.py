# -*- coding: utf-8 -*-
"""
harness_modules.py — Harness 6大模块实现（Anthropic Managed Agents 落地）

对应 CMA / 大厂实践的 Harness 6大模块：
1. 上下文工程 — Write/Select/Compress/Isolate
2. 记忆和状态管理 — Session生命周期 + 检查点
3. 工具和任务编排 — 精选工具集 + 先想后做
4. 验证护栏 — 确定性约束 + 校验 + 恢复
5. 评估和观测 — 追踪 + 验收 + 归因
6. 人类接管 — HITL gate（decide/escalate）

参考：
- Anthropic: Planner + Generator + Evaluator
- Google: Generator + Reviser + Verifier
- Manus: 5次架构重写的教训
- OpenAI Codex: "If a PR requires significant human intervention, the agent is not the problem—the Harness is"
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from enum import Enum

log = logging.getLogger("qclaw.harness_modules")


# ═══════════════════════════════════════════════════════════
# 模块1：上下文工程（Write / Select / Compress / Isolate）
# ═══════════════════════════════════════════════════════════

class ContextEngine:
    """
    上下文工程引擎
    
    四个核心动作：
    - Write：写入持久状态
    - Select：决定检索什么
    - Compress：减少 token 体积
    - Isolate：卸载到子 Agent（上下文防火墙）
    
    关键原则：上下文窗口是稀缺资源，需要的时候再给。
    不是"装不装得下"，而是"该不该装进去"。
    """
    
    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self._store: Dict[str, str] = {}   # key → content
        self._selection_rules: List[Dict] = []
    
    def write(self, key: str, content: str) -> None:
        """写入持久状态"""
        self._store[key] = content
    
    def select(self, query: str, top_k: int = 5) -> List[str]:
        """决定检索什么（基于关键词匹配，简单实现）"""
        results = []
        query_lower = query.lower()
        for key, content in self._store.items():
            if query_lower in key.lower() or query_lower in content[:200].lower():
                results.append(content)
        return results[:top_k]
    
    def compress(self, content: str, target_tokens: int = 2000) -> str:
        """减少 token 体积（简单截断 + 关键行提取）"""
        if len(content) // 4 <= target_tokens:
            return content
        
        # 提取关键行
        key_patterns = ["error", "fail", "success", "pass", "found", "result", "verdict"]
        lines = content.split("\n")
        key_lines = [l for l in lines if any(p in l.lower() for p in key_patterns)]
        
        if key_lines:
            result = "\n".join(key_lines[:20])
        else:
            result = content[:target_tokens * 4]
        
        return result
    
    def isolate(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        卸载到子 Agent（上下文防火墙）
        
        不同子任务在隔离的上下文窗口运行。
        返回子 Agent 的输入规范。
        """
        return {
            "task": task,
            "context_budget": self.max_tokens // 2,  # 子 Agent 用一半 token
            "isolation_mode": "context_firewall",
            "parent_context_summary": self.compress(context, 500) if context else "",
        }


# ═══════════════════════════════════════════════════════════
# 模块2：记忆和状态管理（Session 生命周期 + 检查点）
# ═══════════════════════════════════════════════════════════

@dataclass
class Checkpoint:
    """会话检查点（类似 Git commit）"""
    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    label: str = ""


class MemoryManager:
    """
    记忆和状态管理器
    
    Session 生命周期：
    - 开始时加载历史状态
    - 执行中实时记录进度
    - 关键节点创建检查点
    - 失败后从检查点继续
    """
    
    def __init__(self):
        self._checkpoints: List[Checkpoint] = []
        self._current_state: Dict[str, Any] = {}
    
    def save_checkpoint(self, session_id: str, label: str = "",
                        state: Dict = None) -> Checkpoint:
        """创建检查点"""
        cp = Checkpoint(
            session_id=session_id,
            state_snapshot=state or dict(self._current_state),
            label=label,
        )
        self._checkpoints.append(cp)
        log.info(f"Checkpoint saved: {cp.checkpoint_id} ({label})")
        return cp
    
    def restore_checkpoint(self, checkpoint_id: str = None) -> Optional[Dict]:
        """从检查点恢复"""
        if checkpoint_id:
            for cp in reversed(self._checkpoints):
                if cp.checkpoint_id == checkpoint_id:
                    self._current_state = dict(cp.state_snapshot)
                    return self._current_state
        elif self._checkpoints:
            cp = self._checkpoints[-1]
            self._current_state = dict(cp.state_snapshot)
            return self._current_state
        return None
    
    def update_state(self, key: str, value: Any) -> None:
        """更新当前状态"""
        self._current_state[key] = value
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """获取当前状态"""
        return self._current_state.get(key, default)


# ═══════════════════════════════════════════════════════════
# 模块3：工具和任务编排（精选工具集 + 先想后做）
# ═══════════════════════════════════════════════════════════

class TaskPhase(Enum):
    PLANNING = "planning"       # 先想
    EXECUTING = "executing"     # 后做
    VERIFYING = "verifying"     # 验证


@dataclass
class TaskPlan:
    """任务计划（先想后做）"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    steps: List[Dict[str, str]] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    estimated_steps: int = 0
    phase: TaskPhase = TaskPhase.PLANNING


class TaskOrchestrator:
    """
    工具和任务编排器
    
    核心原则：
    - 先想后做：让 Agent 在执行前就有清晰计划
    - 精选工具集：不给 Agent 它不需要的工具
    - 沙箱隔离：每个任务在隔离环境中运行
    """
    
    def __init__(self, available_tools: List[str] = None):
        self.available_tools = available_tools or []
        self._active_tasks: Dict[str, TaskPlan] = {}
    
    def plan(self, task_description: str, required_tools: List[str] = None) -> TaskPlan:
        """
        规划任务（先想）
        
        Vercel 的教训：给 Agent 太多工具反而降低性能。
        精选工具集 = 只给需要的。
        """
        tools = required_tools or [t for t in self.available_tools if self._is_needed(t, task_description)]
        plan = TaskPlan(
            description=task_description,
            required_tools=tools,
            estimated_steps=max(1, len(tools)),
            phase=TaskPhase.PLANNING,
        )
        self._active_tasks[plan.task_id] = plan
        return plan
    
    def execute_step(self, task_id: str, step_index: int) -> Dict[str, Any]:
        """执行任务步骤（后做）"""
        plan = self._active_tasks.get(task_id)
        if not plan:
            return {"error": f"Task {task_id} not found"}
        if step_index >= len(plan.steps):
            return {"error": f"Step {step_index} out of range"}
        
        plan.phase = TaskPhase.EXECUTING
        step = plan.steps[step_index]
        return {"task_id": task_id, "step": step, "status": "executing"}
    
    def _is_needed(self, tool: str, task: str) -> bool:
        """简单判断工具是否被需要"""
        task_lower = task.lower()
        # 通用映射
        tool_keywords = {
            "read": ["read", "view", "check", "inspect", "cat"],
            "write": ["write", "create", "save", "edit", "modify"],
            "exec": ["run", "execute", "shell", "command", "build"],
            "search": ["search", "find", "grep", "look"],
            "web": ["web", "url", "fetch", "browse", "http"],
        }
        keywords = tool_keywords.get(tool.lower(), [tool.lower()])
        return any(k in task_lower for k in keywords)


# ═══════════════════════════════════════════════════════════
# 模块4：验证护栏（确定性约束 + 校验 + 恢复）
# ═══════════════════════════════════════════════════════════

class GateResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    RETRY = "retry"


@dataclass
class ValidationResult:
    """验证结果"""
    gate: str = ""
    result: GateResult = GateResult.PASS
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class ValidationGuardrails:
    """
    验证护栏
    
    类比汽车刹车系统：不是为了阻止前进，而是为了让人能放心加速。
    
    四层防护：
    1. 确定性约束（自定义 linter、架构规则）
    2. 校验机制（单元测试、类型检查）
    3. 恢复机制（自动重试、回滚到稳定状态）
    4. 评估机制（多维度评分，低于阈值打回重做）
    """
    
    def __init__(self):
        self._rules: List[Dict[str, Any]] = []
        self._max_retries: int = 3
    
    def add_rule(self, name: str, check_fn: Callable, severity: str = "error") -> None:
        """添加验证规则"""
        self._rules.append({
            "name": name,
            "check_fn": check_fn,
            "severity": severity,  # error / warning / info
        })
    
    def validate(self, output: str, context: Dict = None) -> List[ValidationResult]:
        """运行所有验证规则"""
        results = []
        for rule in self._rules:
            try:
                passed, message = rule["check_fn"](output, context or {})
                results.append(ValidationResult(
                    gate=rule["name"],
                    result=GateResult.PASS if passed else GateResult.FAIL,
                    message=message,
                    details={"severity": rule["severity"]},
                ))
            except Exception as e:
                results.append(ValidationResult(
                    gate=rule["name"],
                    result=GateResult.RETRY,
                    message=f"Validation error: {e}",
                ))
        return results
    
    def should_retry(self, results: List[ValidationResult], attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self._max_retries:
            return False
        has_fail = any(r.result == GateResult.FAIL for r in results)
        has_error_severity = any(
            r.details.get("severity") == "error" and r.result == GateResult.FAIL
            for r in results
        )
        return has_fail and has_error_severity


# ═══════════════════════════════════════════════════════════
# 模块5：评估和观测（追踪 + 验收 + 归因）
# ═══════════════════════════════════════════════════════════

@dataclass
class Observation:
    """观测记录"""
    obs_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    event_type: str = ""        # tool_call / decision / error / checkpoint
    actor: str = ""             # harness / agent / tool
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0


class ObservationEngine:
    """
    评估和观测引擎
    
    没有观测，就无法理解和改进。
    观测让 Harness 具备自我进化的能力。
    """
    
    def __init__(self, max_observations: int = 1000):
        self._observations: List[Observation] = []
        self._max_observations = max_observations
    
    def record(self, event_type: str, actor: str = "",
               details: Dict = None, duration_ms: float = 0) -> Observation:
        """记录观测"""
        obs = Observation(
            event_type=event_type,
            actor=actor,
            details=details or {},
            duration_ms=duration_ms,
        )
        self._observations.append(obs)
        # 环形缓冲
        if len(self._observations) > self._max_observations:
            self._observations = self._observations[-self._max_observations:]
        return obs
    
    def get_summary(self) -> Dict[str, Any]:
        """获取观测摘要"""
        type_counts = {}
        actor_counts = {}
        total_duration = 0
        for obs in self._observations:
            type_counts[obs.event_type] = type_counts.get(obs.event_type, 0) + 1
            actor_counts[obs.actor] = actor_counts.get(obs.actor, 0) + 1
            total_duration += obs.duration_ms
        
        return {
            "total_observations": len(self._observations),
            "type_counts": type_counts,
            "actor_counts": actor_counts,
            "total_duration_ms": total_duration,
        }
    
    def find_anomalies(self) -> List[Observation]:
        """检测异常（简单的基于规则的异常检测）"""
        anomalies = []
        for obs in self._observations:
            # 工具调用超时
            if obs.event_type == "tool_call" and obs.duration_ms > 30000:
                anomalies.append(obs)
            # 错误事件
            if obs.event_type == "error":
                anomalies.append(obs)
        return anomalies


# ═══════════════════════════════════════════════════════════
# 模块6：人类接管（HITL Gate — decide/escalate）
# ═══════════════════════════════════════════════════════════

class HITLDecision(Enum):
    """人类接管决策"""
    APPROVE = "approve"         # 批准继续
    REJECT = "reject"           # 拒绝，Agent 需换方案
    ESCALATE = "escalate"       # 升级到更高级别确认
    MODIFY = "modify"           # 修改后继续


@dataclass
class HITLRequest:
    """人类接管请求"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: str = ""                    # 要执行的操作描述
    risk_level: str = "medium"          # low / medium / high / critical
    reason: str = ""                    # 为什么需要人工确认
    context: str = ""                   # 相关上下文
    options: List[str] = field(default_factory=list)  # 可选操作


@dataclass
class HITLResponse:
    """人类接管响应"""
    request_id: str = ""
    decision: HITLDecision = HITLDecision.APPROVE
    modified_action: str = ""           # 修改后的操作
    feedback: str = ""                  # 人类反馈


class HITLGate:
    """
    人类接管门控（Human-In-The-Loop）
    
    对应 CMA 的 decide/escalate 机制。
    
    设计原则：
    - 及时：在操作执行前暂停
    - 清晰：说明为什么需要接管
    - 可回退：拒绝后 Agent 能继续其他任务
    
    必须暂停等待确认的场景：
    - 删数据库
    - 扣费操作
    - 修改生产配置
    - 权限变更
    - 敏感数据访问
    """
    
    # 危险操作模式（自动触发 HITL）
    DANGEROUS_PATTERNS = [
        r"(?i)(drop|delete|remove)\s+(database|table|collection)",
        r"(?i)(charge|bill|payment|purchase)",
        r"(?i)(production|prod|live)\s*(config|deploy|release)",
        r"(?i)(permission|auth|role|admin)\s*(grant|change|modify)",
        r"(?i)(ssh|root|sudo|admin)\s*(into|access|login)",
    ]
    
    def __init__(self):
        self._pending_requests: Dict[str, HITLRequest] = {}
        self._decision_callback: Optional[Callable] = None
    
    def set_callback(self, callback: Callable[[HITLRequest], HITLResponse]) -> None:
        """设置人类决策回调函数"""
        self._decision_callback = callback
    
    def check_required(self, action: str, context: str = "") -> Optional[HITLRequest]:
        """
        检查操作是否需要人类确认
        
        Returns: HITLRequest 如果需要确认，None 如果可以自动执行
        """
        import re
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, action):
                risk = "critical" if "drop" in action.lower() or "delete" in action.lower() else "high"
                return HITLRequest(
                    action=action,
                    risk_level=risk,
                    reason=f"Action matches dangerous pattern: {pattern}",
                    context=context[:500],
                    options=["approve", "reject", "modify"],
                )
        return None
    
    def request_decision(self, request: HITLRequest) -> HITLResponse:
        """
        请求人类决策
        
        如果设置了 callback，直接调用；
        否则默认批准（生产环境必须设置 callback！）。
        """
        if self._decision_callback:
            return self._decision_callback(request)
        
        # 默认：自动批准（仅开发环境使用！）
        log.warning(f"Auto-approving HITL request (no callback set): {request.action[:50]}")
        return HITLResponse(
            request_id=request.request_id,
            decision=HITLDecision.APPROVE,
        )


# ═══════════════════════════════════════════════════════════
# Harness 总线：6大模块统一接口
# ═══════════════════════════════════════════════════════════

class Harness:
    """
    Harness 总线——6大模块的统一入口
    
    对应 Anthropic 的 meta-harness 设计：
    只承诺几类长期稳定的接口，具体实现随模型能力迭代不断重写。
    """
    
    def __init__(self, max_context_tokens: int = 128000):
        self.context = ContextEngine(max_tokens=max_context_tokens)
        self.memory = MemoryManager()
        self.orchestrator = TaskOrchestrator()
        self.guardrails = ValidationGuardrails()
        self.observation = ObservationEngine()
        self.hitl = HITLGate()
    
    def get_status(self) -> Dict[str, Any]:
        """获取 Harness 状态"""
        return {
            "modules": {
                "context": "active",
                "memory": f"{len(self.memory._checkpoints)} checkpoints",
                "orchestrator": f"{len(self.orchestrator._active_tasks)} active tasks",
                "guardrails": f"{len(self.guardrails._rules)} rules",
                "observation": f"{len(self.observation._observations)} observations",
                "hitl": "callback_set" if self.hitl._decision_callback else "auto_approve",
            }
        }
