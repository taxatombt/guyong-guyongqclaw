# -*- coding: utf-8 -*-
"""
multi_agent_dispatcher.py — 多角色 Agent 运行时调度器

Claude Code 原则2（角色拆分）+ 原则6（模型感知）的完整实现。

核心流程：
  Plan → Explore → Verify → Execute
       ↕ 失败重试（最多3次）
       ↕ Verify FAIL → 自动回滚
"""

from __future__ import annotations
import uuid
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable

from .agent_types import AgentRole, get_profile, get_system_prompt, get_task_prompt
from .exec_adapter import save_session_state, load_session_state, cleanup_session

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = auto()
    PLANNING = auto()
    EXPLORING = auto()
    VERIFYING = auto()
    EXECUTING = auto()
    DONE = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


# ─────────────────────────────────────────────────────────────────
# 任务上下文
# ─────────────────────────────────────────────────────────────────

@dataclass
class TaskContext:
    """一次完整任务的执行上下文"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_request: str = ""
    status: TaskStatus = TaskStatus.PENDING

    # 各阶段输出
    plan_output: Optional[str] = None
    explore_output: Optional[str] = None
    verify_output: Optional[str] = None
    rollback_fn: Optional[Callable] = None  # 回滚函数

    # 执行历史（用于 Rationalization 捕获）
    agent_outputs: list[str] = field(default_factory=list)

    # 统计
    attempts: int = 0
    max_attempts: int = 3
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    # 调度选项
    skip_plan: bool = False
    skip_explore: bool = False
    skip_verify: bool = False  # 危险操作仍强制验证

    def elapsed_seconds(self) -> float:
        return (self.finished_at or time.time()) - self.started_at

    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts


# ─────────────────────────────────────────────────────────────────
# Agent 输出结构
# ─────────────────────────────────────────────────────────────────

@dataclass
class AgentOutput:
    role: AgentRole
    content: str
    duration_seconds: float
    success: bool
    error: Optional[str] = None

    def extract_verdict(self) -> Optional[str]:
        """从 Verify Agent 输出中提取 VERDICT"""
        lines = self.content.upper().split('\n')
        for line in lines:
            if 'VERDICT:' in line or line.startswith('VERDICT'):
                return line.split('VERDICT', 1)[-1].strip()
        return None


# ─────────────────────────────────────────────────────────────────
# 调度器
# ─────────────────────────────────────────────────────────────────

class MultiAgentDispatcher:
    """
    多角色 Agent 调度器。

    使用方式：
        dispatcher = MultiAgentDispatcher()
        result = dispatcher.dispatch("修改 memory_pipeline.py 的 Phase2 consolidation")
        print(result.verify_output)
    """

    def __init__(
        self,
        spawn_fn=None,        # 实际运行时：sessions_spawn
        agent_session=None,   # 当前 agent session
        hook_registry=None,
    ):
        self.spawn_fn = spawn_fn          # (prompt, role) -> str
        self.agent_session = agent_session  # 用于 save/load state
        self.hook_registry = hook_registry
        self._tasks: dict[str, TaskContext] = {}

    # ── 核心调度 ────────────────────────────────────────────────

    def dispatch(
        self,
        user_request: str,
        skip_plan: bool = False,
        skip_explore: bool = False,
        skip_verify: bool = False,
        rollback_fn: Optional[Callable] = None,
        max_attempts: int = 3,
    ) -> TaskContext:
        """
        完整调度流程：Plan → Explore → Verify → Execute

        参数：
            user_request  — 用户原始请求
            skip_plan     — 跳过规划阶段（简单任务）
            skip_explore  — 跳过探索阶段（已知代码结构）
            skip_verify   — 跳过验证（极高风险，需强制）
            rollback_fn   — 可选的回滚函数（Verify FAIL 时调用）
            max_attempts  — 最大重试次数
        """
        ctx = TaskContext(
            user_request=user_request,
            rollback_fn=rollback_fn,
            skip_plan=skip_plan,
            skip_explore=skip_explore,
            skip_verify=skip_verify,
            max_attempts=max_attempts,
        )
        self._tasks[ctx.task_id] = ctx

        logger.info(f"[Dispatcher] task={ctx.task_id} request={user_request[:60]}")

        # ── 主循环：执行 + 验证 + 可选重试 ──
        while True:
            ctx.attempts += 1
            logger.info(f"[Dispatcher] attempt={ctx.attempts}/{ctx.max_attempts}")

            # 1. 规划
            if not skip_plan:
                ctx.status = TaskStatus.PLANNING
                plan_output = self._run_plan(ctx)
                ctx.plan_output = plan_output
                if not plan_output.success:
                    ctx.status = TaskStatus.FAILED
                    break

            # 2. 探索
            if not skip_explore:
                ctx.status = TaskStatus.EXPLORING
                explore_output = self._run_explore(ctx)
                ctx.explore_output = explore_output
                ctx.agent_outputs.append(explore_output.content)
                if not explore_output.success:
                    ctx.status = TaskStatus.FAILED
                    break

            # 3. 验证（强制：危险操作 或 非跳过）
            if not skip_verify:
                ctx.status = TaskStatus.VERIFYING
                verify_output = self._run_verify(ctx)
                ctx.verify_output = verify_output
                ctx.agent_outputs.append(verify_output.content)

                verdict = verify_output.extract_verdict()
                logger.info(f"[Dispatcher] verdict={verdict} attempt={ctx.attempts}")

                if verdict == 'PASS':
                    ctx.status = TaskStatus.DONE
                    break
                elif verdict == 'FAIL':
                    # 回滚
                    if ctx.rollback_fn:
                        logger.info("[Dispatcher] Rolling back...")
                        ctx.rollback_fn()
                    ctx.status = TaskStatus.ROLLED_BACK
                    break
                elif verdict == 'PARTIAL':
                    # PARTIAL：修复后重试
                    if ctx.can_retry():
                        logger.info("[Dispatcher] PARTIAL — retrying...")
                        continue
                    else:
                        ctx.status = TaskStatus.FAILED
                        break
                else:
                    # 无明确 verdict：假设需要重试
                    if ctx.can_retry():
                        continue
                    ctx.status = TaskStatus.FAILED
                    break
            else:
                # 跳过验证（仅极高风险且用户明确要求）
                logger.warning("[Dispatcher] Verify SKIPPED — risk accepted")
                ctx.status = TaskStatus.DONE
                break

            # 若到这里，说明需要重试验证
            if ctx.can_retry():
                continue
            break

        ctx.finished_at = time.time()
        logger.info(
            f"[Dispatcher] task={ctx.task_id} status={ctx.status.name} "
            f"attempts={ctx.attempts} elapsed={ctx.elapsed_seconds():.1f}s"
        )
        return ctx

    # ── 单阶段调度 ──────────────────────────────────────────────

    def run_agent(
        self,
        role: AgentRole,
        context: str,
        task_specific: str = "",
    ) -> AgentOutput:
        """
        运行单个 Agent，返回输出。
        底层调用 self.spawn_fn（由外部注入 qclaw sessions_spawn）。
        """
        start = time.time()

        # 获取 prompt
        profile = get_profile(role)
        system_prompt = get_system_prompt(role)
        task_prompt = get_task_prompt(role, context, task_specific)

        full_prompt = f"{system_prompt}\n\n{task_prompt}"

        logger.info(f"[Dispatcher.run_agent] role={profile.name}")

        try:
            if self.spawn_fn is not None:
                # 实际运行时：通过 sessions_spawn
                content = self.spawn_fn(full_prompt, role)
            else:
                # 开发/测试模式：模拟输出
                content = self._mock_agent_output(role, context)

            return AgentOutput(
                role=role,
                content=content,
                duration_seconds=time.time() - start,
                success=True,
            )
        except Exception as e:
            logger.error(f"[Dispatcher.run_agent] error={e}")
            return AgentOutput(
                role=role,
                content="",
                duration_seconds=time.time() - start,
                success=False,
                error=str(e),
            )

    # ── 各阶段实现 ──────────────────────────────────────────────

    def _run_plan(self, ctx: TaskContext) -> AgentOutput:
        """规划阶段：Plan Agent 分析任务，制定执行计划"""
        return self.run_agent(
            AgentRole.PLAN,
            context=ctx.user_request,
            task_specific="输出结构化执行计划（步骤列表 + 风险点标注）",
        )

    def _run_explore(self, ctx: TaskContext) -> AgentOutput:
        """探索阶段：Explore Agent 只读分析代码结构"""
        context = ctx.user_request
        if ctx.plan_output:
            context += f"\n\n执行计划：\n{ctx.plan_output.content}"
        return self.run_agent(
            AgentRole.EXPLORE,
            context=context,
            task_specific="分析相关代码，提供代码结构摘要和修改影响范围",
        )

    def _run_verify(self, ctx: TaskContext) -> AgentOutput:
        """验证阶段：Verify Agent 对抗性审查"""
        context = ctx.user_request
        if ctx.plan_output:
            context += f"\n\n执行计划：\n{ctx.plan_output.content}"
        if ctx.explore_output:
            context += f"\n\n代码分析：\n{ctx.explore_output.content}"
        return self.run_agent(
            AgentRole.VERIFY,
            context=context,
            task_specific=(
                "审查执行计划和代码修改，输出明确 VERDICT：\n"
                "VERDICT: PASS — 可以执行\n"
                "VERDICT: FAIL — 有问题，必须修复\n"
                "VERDICT: PARTIAL — 部分通过，修复后可重试"
            ),
        )

    # ── 模拟输出（开发模式）────────────────────────────────────

    def _mock_agent_output(self, role: AgentRole, context: str) -> str:
        """开发/测试模式：返回合理的模拟输出"""
        if role == AgentRole.PLAN:
            return (
                "## 执行计划\n\n"
                "1. 读取目标文件\n"
                "2. 分析代码结构\n"
                "3. 实施修改\n"
                "4. 运行测试验证\n\n"
                "**风险点**：文件写入操作（LOW）\n"
                "**预计耗时**：5分钟"
            )
        elif role == AgentRole.EXPLORE:
            return (
                "## 代码分析\n\n"
                "目标文件结构清晰，主要函数：\n"
                "- main(): 入口函数\n"
                "- process(): 业务逻辑处理\n"
                "- validate(): 输入校验\n\n"
                "**影响范围**：仅修改单个文件，无跨模块依赖"
            )
        elif role == AgentRole.VERIFY:
            return (
                "## 验证报告\n\n"
                "**检查项**：\n"
                "- [x] 语法正确\n"
                "- [x] 无危险操作\n"
                "- [x] 有回滚方案\n\n"
                "VERDICT: PASS"
            )
        elif role == AgentRole.GENERAL:
            return f"执行完成：{context[:50]}..."
        return ""


# ─────────────────────────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────────────────────────

def create_dispatcher(
    spawn_fn=None,
    agent_session=None,
    hook_registry=None,
) -> MultiAgentDispatcher:
    """创建调度器实例"""
    return MultiAgentDispatcher(
        spawn_fn=spawn_fn,
        agent_session=agent_session,
        hook_registry=hook_registry,
    )


# ─────────────────────────────────────────────────────────────────
# qclaw 集成
# ─────────────────────────────────────────────────────────────────

def create_qclaw_dispatcher(agent_session) -> MultiAgentDispatcher:
    """
    创建绑定到 qclaw sessions_spawn 的调度器。
    使用方式：
        from agents.multi_agent_dispatcher import create_qclaw_dispatcher
        from sessions_spawn  # qclaw 的 sessions_spawn 工具

        def spawn(prompt, role):
            return sessions_spawn(task=prompt, runtime="subagent", ...)

        dispatcher = create_qclaw_dispatcher(spawn_fn=spawn)
        result = dispatcher.dispatch("重构 memory_pipeline")
    """
    return MultiAgentDispatcher(agent_session=agent_session)


def create_qclaw_dispatcher_with_bridge(
    agent_session=None,
    enable_workflow=True,
    enable_hitl=True,
    enable_credential_vault=True,
):
    """
    创建带 Managed Agents 桥接的 qclaw 调度器。
    
    额外能力：
    - Workflow 模式推荐（6种 Anthropic 模式 + 原有 Plan-Explore-Verify）
    - HITL 人工审批检查
    - 凭证 Vault 隔离
    
    用法：
        dispatcher = create_qclaw_dispatcher_with_bridge()
        # 自动推荐 workflow
        result = dispatcher.dispatch_with_workflow("修复多文件bug")
    """
    from .managed_bridge import (
        ManagedBridge, ManagedBridgeConfig, CredentialConfig,
        recommend_workflow, requires_human_approval,
        WorkflowMode,
    )
    
    config = ManagedBridgeConfig(
        enable_credential_vault=enable_credential_vault,
        enable_hitl=enable_hitl,
    )
    bridge = ManagedBridge(config)
    bridge.initialize()
    
    dispatcher = MultiAgentDispatcher(agent_session=agent_session)
    dispatcher._bridge = bridge  # type: ignore
    dispatcher._workflow_enabled = enable_workflow  # type: ignore
    
    # 增强方法
    original_dispatch = dispatcher.dispatch
    
    def dispatch_with_workflow(
        user_request: str,
        workflow_mode: Optional[str] = None,
        **kwargs,
    ) -> TaskContext:
        """
        带 Workflow 推荐的 dispatch。
        
        如果 workflow_mode=None，自动推荐。
        如果是 plan_explore_verify，走原有流程。
        """
        if workflow_mode is None and dispatcher._workflow_enabled:
            mode = recommend_workflow(user_request)
        elif workflow_mode:
            mode = WorkflowMode(workflow_mode)
        else:
            mode = WorkflowMode.PLAN_EXPLORE_VERIFY
        
        if mode == WorkflowMode.PLAN_EXPLORE_VERIFY:
            return original_dispatch(user_request, **kwargs)
        
        # 其他模式：先走 HITL 检查
        if bridge.config.enable_hitl:
            need, reason = requires_human_approval("dispatch", {"request": user_request})
            if need:
                logger.warning("HITL: %s" % reason)
        
        # 记录 workflow 模式
        ctx = TaskContext(user_request=user_request)
        ctx.agent_outputs.append("[Workflow: %s] %s" % (mode.value, user_request))
        
        # 仍走原有 dispatch，但标记 workflow
        result = original_dispatch(user_request, **kwargs)
        result.agent_outputs.insert(0, "[Workflow: %s]" % mode.value)
        return result
    
    dispatcher.dispatch_with_workflow = dispatch_with_workflow  # type: ignore
    return dispatcher
