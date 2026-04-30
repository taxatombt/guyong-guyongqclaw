# -*- coding: utf-8 -*-
"""
workflow_patterns.py — Anthropic 5种Workflow + Agent 模式（qclaw 落地）

来源：Anthropic "Building Effective Agents" (2026)
      https://www.anthropic.com/engineering/building-effective-agents

5种 Workflow：
1. Prompt Chaining — 任务分解为固定步骤链
2. Routing — 分类输入，路由到专用处理
3. Parallelization — 并行子任务 + 投票聚合
4. Orchestrator-Workers — 中央LLM动态分解+委派+综合
5. Evaluator-Optimizer — 生成+评估反馈循环

+ Autonomous Agent — LLM自主决策+工具使用循环

Anthropic 三个核心原则：
- Maintain simplicity in your agent's design
- Prioritize transparency by explicitly showing the agent's planning steps
- Carefully craft your agent-computer interface (ACI) through thorough tool documentation and testing

适用场景：
- Prompt Chaining → 可分解的固定子任务（写大纲→检查→写全文）
- Routing → 不同类别需不同处理（客服分类→专用流程）
- Parallelization → 子任务独立或需要多视角（安全审查×3投票）
- Orchestrator-Workers → 子任务不可预测（多文件代码修改）
- Evaluator-Optimizer → 有明确评估标准+迭代有价值（翻译/搜索）
- Agent → 开放式问题，步数不可预测（SWE-bench / computer use）
"""

from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple
from enum import Enum

log = logging.getLogger("qclaw.workflow_patterns")


# ═══════════════════════════════════════════════════════════
# 基础构建块：增强型 LLM 调用
# ═══════════════════════════════════════════════════════════

@dataclass
class LLMCall:
    """增强型 LLM 调用（带检索/工具/记忆）"""
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    prompt: str = ""
    system: str = ""
    tools: List[Dict[str, str]] = field(default_factory=list)
    context: str = ""          # 检索上下文
    memory: str = ""           # 记忆注入
    response: str = ""
    token_count: int = 0
    duration_ms: float = 0


@dataclass
class WorkflowResult:
    """Workflow 执行结果"""
    workflow_type: str = ""
    success: bool = True
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_output: str = ""
    total_calls: int = 0
    total_tokens: int = 0
    total_duration_ms: float = 0


# ═══════════════════════════════════════════════════════════
# Workflow 1: Prompt Chaining（提示链）
# ═══════════════════════════════════════════════════════════

class PromptChain:
    """
    提示链：将任务分解为固定步骤序列
    
    每个 LLM 调用处理上一步的输出。
    中间步骤可加 gate（程序化检查点）。
    
    何时用：任务可干净分解为固定子任务
    例子：生成营销文案 → 翻译 → 检查
    
    核心权衡：延迟换准确性（每步更简单→更准确）
    """
    
    def __init__(self):
        self._steps: List[Dict[str, Any]] = []
        self._gates: Dict[int, Callable] = {}   # step_index → gate_fn
    
    def add_step(self, name: str, prompt_template: str,
                 system: str = "") -> 'PromptChain':
        """
        添加步骤
        
        prompt_template 支持 {prev_output} 占位符
        """
        self._steps.append({
            "name": name,
            "prompt_template": prompt_template,
            "system": system,
        })
        return self
    
    def add_gate(self, after_step: int, 
                 gate_fn: Callable[[str], Tuple[bool, str]]) -> 'PromptChain':
        """
        在指定步骤后添加 gate（检查点）
        
        gate_fn 输入：上一步输出
        gate_fn 输出：(passed, reason)
        如果 not passed，链终止
        """
        self._gates[after_step] = gate_fn
        return self
    
    def run(self, initial_input: str,
            llm_fn: Callable[[str, str], str] = None) -> WorkflowResult:
        """
        执行提示链
        
        Args:
            initial_input: 初始输入
            llm_fn: LLM 调用函数 (prompt, system) → response
                    默认：直接返回 prompt（测试用）
        """
        if not llm_fn:
            llm_fn = lambda p, s: f"[LLM response to: {p[:50]}...]"
        
        start_time = time.time()
        current_output = initial_input
        steps_log = []
        total_calls = 0
        
        for i, step in enumerate(self._steps):
            prompt = step["prompt_template"].replace("{prev_output}", current_output)
            
            t0 = time.time()
            response = llm_fn(prompt, step.get("system", ""))
            duration = (time.time() - t0) * 1000
            
            current_output = response
            total_calls += 1
            steps_log.append({
                "step": i,
                "name": step["name"],
                "output_preview": response[:100],
                "duration_ms": duration,
            })
            
            # 检查 gate
            if i in self._gates:
                passed, reason = self._gates[i](current_output)
                if not passed:
                    return WorkflowResult(
                        workflow_type="prompt_chaining",
                        success=False,
                        steps=steps_log,
                        final_output=f"GATE FAILED at step {i}: {reason}",
                        total_calls=total_calls,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )
        
        return WorkflowResult(
            workflow_type="prompt_chaining",
            success=True,
            steps=steps_log,
            final_output=current_output,
            total_calls=total_calls,
            total_duration_ms=(time.time() - start_time) * 1000,
        )


# ═══════════════════════════════════════════════════════════
# Workflow 2: Routing（路由）
# ═══════════════════════════════════════════════════════════

class Router:
    """
    路由：分类输入，导向专用处理
    
    允许关注点分离，构建更专业的 prompt。
    
    何时用：不同类别需不同处理
    例子：客服问题 → 账户/计费/技术/产品 专用流程
    例子：简单问题→Haiku 4.5，困难问题→Sonnet 4.5
    """
    
    def __init__(self):
        self._routes: Dict[str, Dict[str, Any]] = {}
    
    def add_route(self, name: str, condition: str,
                  handler_fn: Callable = None,
                  system: str = "",
                  prompt_template: str = "") -> 'Router':
        """
        添加路由
        
        Args:
            name: 路由名称
            condition: 路由匹配条件描述
            handler_fn: 处理函数
            system: 专用 system prompt
            prompt_template: 专用 prompt 模板
        """
        self._routes[name] = {
            "condition": condition,
            "handler_fn": handler_fn,
            "system": system,
            "prompt_template": prompt_template,
        }
        return self
    
    def classify(self, input_text: str,
                 classifier_fn: Callable[[str, List[str]], str] = None) -> str:
        """
        分类输入
        
        Args:
            input_text: 输入文本
            classifier_fn: 分类函数 (input, route_names) → route_name
                           默认：关键词匹配
        """
        if classifier_fn:
            return classifier_fn(input_text, list(self._routes.keys()))
        
        # 简单关键词匹配（降级方案）
        input_lower = input_text.lower()
        best_route = "default"
        best_score = 0
        
        for name, route in self._routes.items():
            condition_words = route["condition"].lower().split()
            score = sum(1 for w in condition_words if w in input_lower)
            if score > best_score:
                best_score = score
                best_route = name
        
        return best_route
    
    def run(self, input_text: str,
            classifier_fn: Callable = None,
            llm_fn: Callable[[str, str], str] = None) -> WorkflowResult:
        """
        执行路由
        
        1. 分类输入
        2. 路由到专用处理
        3. 返回结果
        """
        start_time = time.time()
        
        # 分类
        route_name = self.classify(input_text, classifier_fn)
        route = self._routes.get(route_name)
        
        if not route:
            return WorkflowResult(
                workflow_type="routing",
                success=False,
                final_output=f"No route found for: {route_name}",
                total_duration_ms=(time.time() - start_time) * 1000,
            )
        
        # 处理
        if route.get("handler_fn"):
            output = route["handler_fn"](input_text)
        elif llm_fn:
            prompt = route.get("prompt_template", "{input}").replace("{input}", input_text)
            output = llm_fn(prompt, route.get("system", ""))
        else:
            output = f"[Route: {route_name}] {input_text}"
        
        return WorkflowResult(
            workflow_type="routing",
            success=True,
            steps=[{"route": route_name, "condition": route["condition"]}],
            final_output=output,
            total_calls=1,
            total_duration_ms=(time.time() - start_time) * 1000,
        )


# ═══════════════════════════════════════════════════════════
# Workflow 3: Parallelization（并行化）
# ═══════════════════════════════════════════════════════════

class ParallelMode(Enum):
    SECTIONING = "sectioning"    # 分割：独立子任务并行
    VOTING = "voting"            # 投票：同一任务多次执行


class Parallelizer:
    """
    并行化：多个 LLM 同时工作，输出聚合
    
    两种变体：
    - Sectioning：任务拆分为独立子任务并行
    - Voting：同一任务执行多次，获取多样输出
    
    何时用：
    - Sectioning → 子任务可并行加速（安全护栏+核心响应分离）
    - Voting → 需要多视角/高置信度（代码漏洞审查×3）
    """
    
    def __init__(self, mode: ParallelMode = ParallelMode.SECTIONING):
        self.mode = mode
        self._tasks: List[Dict[str, Any]] = []
    
    def add_task(self, name: str, prompt: str,
                 system: str = "") -> 'Parallelizer':
        """添加并行任务"""
        self._tasks.append({"name": name, "prompt": prompt, "system": system})
        return self
    
    def run(self, input_text: str = "",
            llm_fn: Callable[[str, str], str] = None,
            aggregate_fn: Callable[[List[str]], str] = None) -> WorkflowResult:
        """
        执行并行化
        
        Args:
            input_text: 输入文本（用于 Voting 模式）
            llm_fn: LLM 调用函数
            aggregate_fn: 聚合函数 (responses) → final_output
                         默认：拼接（Sectioning）/ 多数投票（Voting）
        """
        if not llm_fn:
            llm_fn = lambda p, s: f"[Response: {p[:30]}]"
        
        start_time = time.time()
        responses = []
        steps_log = []
        
        if self.mode == ParallelMode.VOTING:
            # Voting：同一个 prompt 执行 N 次
            for task in self._tasks:
                t0 = time.time()
                resp = llm_fn(task.get("prompt", input_text), task.get("system", ""))
                responses.append(resp)
                steps_log.append({
                    "task": task["name"],
                    "response_preview": resp[:80],
                    "duration_ms": (time.time() - t0) * 1000,
                })
        else:
            # Sectioning：不同 prompt 并行
            for task in self._tasks:
                prompt = task["prompt"].replace("{input}", input_text)
                t0 = time.time()
                resp = llm_fn(prompt, task.get("system", ""))
                responses.append(resp)
                steps_log.append({
                    "task": task["name"],
                    "response_preview": resp[:80],
                    "duration_ms": (time.time() - t0) * 1000,
                })
        
        # 聚合
        if aggregate_fn:
            final = aggregate_fn(responses)
        elif self.mode == ParallelMode.VOTING:
            # 简单多数投票
            from collections import Counter
            counts = Counter(responses)
            final = counts.most_common(1)[0][0] if counts else responses[0]
        else:
            final = "\n---\n".join(responses)
        
        return WorkflowResult(
            workflow_type=f"parallelization_{self.mode.value}",
            success=True,
            steps=steps_log,
            final_output=final,
            total_calls=len(self._tasks),
            total_duration_ms=(time.time() - start_time) * 1000,
        )


# ═══════════════════════════════════════════════════════════
# Workflow 4: Orchestrator-Workers（编排器-工人）
# ═══════════════════════════════════════════════════════════

@dataclass
class WorkerTask:
    """Worker 子任务"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:6])
    description: str = ""
    assigned_to: str = ""       # worker 名称
    result: str = ""
    status: str = "pending"     # pending / running / done / failed


class OrchestratorWorkers:
    """
    编排器-工人：中央LLM动态分解+委派+综合
    
    与并行化的关键区别：子任务不是预定义的，
    而是由编排器根据具体输入动态决定。
    
    何时用：子任务不可预测（多文件代码修改、多源搜索）
    例子：Codex 修改 N 个文件，文件数和修改性质取决于任务
    """
    
    def __init__(self, max_workers: int = 5, max_iterations: int = 3):
        self.max_workers = max_workers
        self.max_iterations = max_iterations
    
    def run(self, task: str,
            planner_fn: Callable[[str], List[Dict]] = None,
            worker_fn: Callable[[Dict], str] = None,
            synthesizer_fn: Callable[[str, List[Dict]], str] = None) -> WorkflowResult:
        """
        执行编排器-工人模式
        
        流程：
        1. Planner 分析任务，生成子任务列表
        2. Workers 执行子任务
        3. Synthesizer 综合结果
        4. 如果不完整，回到步骤1（最多 max_iterations 轮）
        """
        if not planner_fn:
            planner_fn = self._default_planner
        if not worker_fn:
            worker_fn = self._default_worker
        if not synthesizer_fn:
            synthesizer_fn = self._default_synthesizer
        
        start_time = time.time()
        all_worker_results = []
        steps_log = []
        current_task = task
        
        for iteration in range(self.max_iterations):
            # 1. Plan
            subtasks = planner_fn(current_task)
            steps_log.append({
                "phase": "planning",
                "iteration": iteration,
                "subtask_count": len(subtasks),
            })
            
            if not subtasks:
                break
            
            # 2. Execute workers
            for i, subtask in enumerate(subtasks[:self.max_workers]):
                result = worker_fn(subtask)
                subtask["result"] = result
                subtask["status"] = "done"
                all_worker_results.append(subtask)
                
                steps_log.append({
                    "phase": "worker",
                    "worker_id": i,
                    "task_preview": subtask.get("description", "")[:60],
                    "result_preview": result[:60],
                })
            
            # 3. Synthesize
            synthesis = synthesizer_fn(task, all_worker_results)
            steps_log.append({
                "phase": "synthesis",
                "iteration": iteration,
                "output_preview": synthesis[:100],
            })
            
            # 检查是否完成（简单启发式）
            if len(synthesis) > 50 or iteration >= self.max_iterations - 1:
                return WorkflowResult(
                    workflow_type="orchestrator_workers",
                    success=True,
                    steps=steps_log,
                    final_output=synthesis,
                    total_calls=1 + len(subtasks) + 1,  # plan + workers + synthesize
                    total_duration_ms=(time.time() - start_time) * 1000,
                )
        
        return WorkflowResult(
            workflow_type="orchestrator_workers",
            success=False,
            steps=steps_log,
            final_output="Max iterations reached without completion",
            total_duration_ms=(time.time() - start_time) * 1000,
        )
    
    @staticmethod
    def _default_planner(task: str) -> List[Dict]:
        """默认规划器（简单任务拆分）"""
        return [
            {"description": f"Research: {task}", "worker_type": "researcher"},
            {"description": f"Execute: {task}", "worker_type": "executor"},
            {"description": f"Verify: {task}", "worker_type": "verifier"},
        ]
    
    @staticmethod
    def _default_worker(subtask: Dict) -> str:
        """默认 Worker"""
        return f"[Worker result for: {subtask.get('description', '')[:50]}]"
    
    @staticmethod
    def _default_synthesizer(original_task: str, results: List[Dict]) -> str:
        """默认综合器"""
        summaries = [r.get("result", "") for r in results]
        return f"Synthesis of {len(results)} worker results for: {original_task[:50]}\n" + "\n".join(summaries[:5])


# ═══════════════════════════════════════════════════════════
# Workflow 5: Evaluator-Optimizer（评估器-优化器）
# ═══════════════════════════════════════════════════════════

class EvaluatorOptimizer:
    """
    评估器-优化器：一个LLM生成，另一个评估+反馈，循环迭代
    
    何时用：
    - 有明确评估标准
    - 迭代改进有可测量价值
    - 两个信号：人类反馈能改进LLM输出 + LLM能给出有用反馈
    
    例子：文学翻译（微妙语境需反复打磨）
    例子：复杂搜索（多轮搜索+分析，评估器决定是否继续）
    """
    
    def __init__(self, max_iterations: int = 3, pass_threshold: float = 0.8):
        self.max_iterations = max_iterations
        self.pass_threshold = pass_threshold
    
    def run(self, task: str,
            generator_fn: Callable[[str, str], str] = None,
            evaluator_fn: Callable[[str, str], Tuple[float, str]] = None) -> WorkflowResult:
        """
        执行评估器-优化器循环
        
        Args:
            task: 任务描述
            generator_fn: (task, feedback) → output
            evaluator_fn: (task, output) → (score, feedback)
                         score 0.0-1.0, feedback 文本
        """
        if not generator_fn:
            generator_fn = lambda t, f: f"[Generated for: {t[:40]}]" + (f" (revised: {f[:20]})" if f else "")
        if not evaluator_fn:
            evaluator_fn = lambda t, o: (0.9, "Looks good") if len(o) > 20 else (0.5, "Too short")
        
        start_time = time.time()
        current_output = ""
        feedback = ""
        steps_log = []
        
        for iteration in range(self.max_iterations):
            # Generate
            current_output = generator_fn(task, feedback)
            steps_log.append({
                "phase": "generate",
                "iteration": iteration,
                "output_preview": current_output[:80],
            })
            
            # Evaluate
            score, new_feedback = evaluator_fn(task, current_output)
            steps_log.append({
                "phase": "evaluate",
                "iteration": iteration,
                "score": score,
                "feedback_preview": new_feedback[:80],
            })
            
            # Check threshold
            if score >= self.pass_threshold:
                return WorkflowResult(
                    workflow_type="evaluator_optimizer",
                    success=True,
                    steps=steps_log,
                    final_output=current_output,
                    total_calls=(iteration + 1) * 2,
                    total_duration_ms=(time.time() - start_time) * 1000,
                )
            
            feedback = new_feedback
        
        # Max iterations reached
        return WorkflowResult(
            workflow_type="evaluator_optimizer",
            success=False,
            steps=steps_log,
            final_output=current_output,
            total_calls=self.max_iterations * 2,
            total_duration_ms=(time.time() - start_time) * 1000,
        )


# ═══════════════════════════════════════════════════════════
# Autonomous Agent（自主智能体）
# ═══════════════════════════════════════════════════════════

class AgentState(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_FEEDBACK = "waiting_feedback"
    COMPLETED = "completed"
    FAILED = "failed"


class AutonomousAgent:
    """
    自主智能体：LLM自主决策+工具使用循环
    
    Anthropic 核心：
    "Agents can handle sophisticated tasks, but their implementation
     is often straightforward. They are typically just LLMs using tools
     based on environmental feedback in a loop."
    
    关键设计：
    - 每步获取 ground truth（工具调用结果/代码执行）
    - 可在检查点暂停等待人类反馈
    - 设置停止条件（最大迭代数）
    - 工具集和文档要清晰周全（ACI设计）
    
    何时用：开放式问题，步数不可预测
    例子：SWE-bench / computer use
    """
    
    def __init__(self, max_iterations: int = 10,
                 tools: List[Dict[str, str]] = None):
        self.max_iterations = max_iterations
        self.tools = tools or []
        self.state = AgentState.IDLE
        self._iteration = 0
        self._history: List[Dict[str, Any]] = []
    
    def run(self, task: str,
            llm_fn: Callable[[str, List[Dict]], Dict] = None,
            tool_fn: Callable[[str, Dict], str] = None,
            feedback_fn: Callable[[str, str], Optional[str]] = None) -> WorkflowResult:
        """
        执行自主智能体循环
        
        Args:
            task: 任务描述
            llm_fn: (prompt, tools) → {"response": str, "tool_calls": [...]}
            tool_fn: (tool_name, tool_input) → result_str
            feedback_fn: (iteration, status) → Optional[human_feedback]
                        返回 None = 继续自主执行
        """
        if not llm_fn:
            llm_fn = lambda p, t: {"response": f"[Agent thinking about: {p[:30]}]", "tool_calls": []}
        if not tool_fn:
            tool_fn = lambda n, i: f"[Tool {n} result]"
        
        start_time = time.time()
        self.state = AgentState.PLANNING
        current_context = task
        steps_log = []
        total_calls = 0
        
        for self._iteration in range(self.max_iterations):
            # 1. LLM 决策
            self.state = AgentState.EXECUTING
            llm_result = llm_fn(current_context, self.tools)
            total_calls += 1
            
            response = llm_result.get("response", "")
            tool_calls = llm_result.get("tool_calls", [])
            
            self._history.append({
                "iteration": self._iteration,
                "response": response,
                "tool_calls": tool_calls,
            })
            
            steps_log.append({
                "iteration": self._iteration,
                "phase": "think",
                "response_preview": response[:80],
                "tool_call_count": len(tool_calls),
            })
            
            # 2. 执行工具调用（获取 ground truth）
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                tool_input = tc.get("input", {})
                tool_result = tool_fn(tool_name, tool_input)
                current_context += f"\n[Tool {tool_name}]: {tool_result}"
                total_calls += 1
                
                steps_log.append({
                    "iteration": self._iteration,
                    "phase": "tool",
                    "tool": tool_name,
                    "result_preview": tool_result[:80],
                })
            
            # 3. 检查是否完成
            if not tool_calls and "done" in response.lower():
                self.state = AgentState.COMPLETED
                return WorkflowResult(
                    workflow_type="autonomous_agent",
                    success=True,
                    steps=steps_log,
                    final_output=response,
                    total_calls=total_calls,
                    total_duration_ms=(time.time() - start_time) * 1000,
                )
            
            # 4. 检查人类反馈
            if feedback_fn:
                self.state = AgentState.WAITING_FEEDBACK
                human_input = feedback_fn(str(self._iteration), response)
                if human_input:
                    current_context += f"\n[Human feedback]: {human_input}"
                    steps_log.append({
                        "iteration": self._iteration,
                        "phase": "human_feedback",
                        "feedback_preview": human_input[:80],
                    })
        
        # Max iterations
        self.state = AgentState.FAILED
        return WorkflowResult(
            workflow_type="autonomous_agent",
            success=False,
            steps=steps_log,
            final_output=f"Max iterations ({self.max_iterations}) reached",
            total_calls=total_calls,
            total_duration_ms=(time.time() - start_time) * 1000,
        )
    
    def get_state(self) -> Dict[str, Any]:
        """获取 Agent 当前状态"""
        return {
            "state": self.state.value,
            "iteration": self._iteration,
            "history_length": len(self._history),
            "tools": len(self.tools),
        }


# ═══════════════════════════════════════════════════════════
# Workflow 工厂：根据任务自动选择模式
# ═══════════════════════════════════════════════════════════

class WorkflowFactory:
    """
    Workflow 工厂——根据任务特征自动选择最合适的模式
    
    决策逻辑（基于 Anthropic 原则）：
    1. 简单任务 → 单次 LLM 调用（不需要 workflow）
    2. 可分解+固定步骤 → Prompt Chaining
    3. 需分类+专用处理 → Routing
    4. 子任务独立/需多视角 → Parallelization
    5. 子任务不可预测 → Orchestrator-Workers
    6. 有明确评估标准+迭代有价值 → Evaluator-Optimizer
    7. 开放式+步数不可预测 → Autonomous Agent
    """
    
    @staticmethod
    def recommend(task_description: str) -> Dict[str, Any]:
        """推荐最合适的 Workflow 模式"""
        task_lower = task_description.lower()
        
        # 关键词启发式
        patterns = {
            "prompt_chaining": ["step by step", "then", "first.*then", "sequence", "pipeline"],
            "routing": ["classify", "categorize", "route", "different types", "separate"],
            "parallelization": ["parallel", "simultaneously", "multiple perspectives", "vote", "review"],
            "orchestrator_workers": ["complex", "multiple files", "unpredictable", "coordinate"],
            "evaluator_optimizer": ["improve", "refine", "iterate", "feedback", "score", "evaluate"],
            "autonomous_agent": ["open-ended", "explore", "autonomous", "long-running", "swe-bench"],
        }
        
        scores = {}
        for pattern_name, keywords in patterns.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            scores[pattern_name] = score
        
        best = max(scores, key=scores.get)
        best_score = scores[best]
        
        if best_score == 0:
            return {
                "recommended": "single_llm_call",
                "reason": "Task is simple enough for a single LLM call",
                "scores": scores,
            }
        
        return {
            "recommended": best,
            "reason": f"Best match based on task keywords (score: {best_score})",
            "scores": scores,
        }
