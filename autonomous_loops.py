# -*- coding: utf-8 -*-
"""
autonomous_loops.py - 自主循环6模式

来源: ECC autonomous-loops/SKILL.md

6种循环复杂度递增:

1. Sequential Pipeline (低)
   - Claude -p 单次非交互调用
   - 每个调用隔离上下文，set -e传播exit codes
   - 适合：日常脚本、固定步骤

2. NanoClaw REPL (低)
   - 持久交互会话，Claude CLI loop
   - while read; do claude -p "$line"; done
   - 适合：探索式工作

3. Infinite Agentic Loop (中)
   - Claude Code启动后自主运行，LLM决定何时停止
   - while ! "$stop_condition"; do claude --print "$task"; done
   - 危险：负面指令("don't test")难以精确
   - Ralph Wiggum 反循环在这里派上用场

4. Continuous Claude PR Loop (中)
   - 多日迭代开发，自动创建PR/分支
   - 每天早上：pull main -> 创建新分支 -> 迭代 -> PR
   - Ralphinho DAG协调多个并行车

5. De-Sloppify Pattern (附加)
   - 任何循环后加质量清理pass
   - 自动lint/type check/commit规范化
   - Ralphinho的quality pass

6. Ralphinho / RFC-Driven DAG (高)
   - RFC定义工作单元，DAG编排并行执行
   - 协调器管理依赖，并行worker执行
   - 最复杂，适合大规模并行工作
"""

import subprocess
import time
import json
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Dict, Any
from enum import Enum
import threading


class LoopMode(Enum):
    SEQUENTIAL = "sequential"
    REPL = "repl"
    INFINITE = "infinite"
    CONTINUOUS_PR = "continuous_pr"
    DE_SLOPPIFY = "de_sloppify"
    RFC_DAG = "rfc_dag"


@dataclass
class LoopConfig:
    """循环配置"""
    mode: LoopMode
    task: str
    max_iterations: int = 100
    stop_condition: Optional[str] = None
    timeout_seconds: int = 3600
    checkpoint_interval: int = 10  # 每N次迭代保存checkpoint
    on_error: str = "continue"  # "continue" | "stop" | "ask"


@dataclass
class LoopResult:
    """循环执行结果"""
    mode: LoopMode
    iterations: int
    succeeded: bool
    duration_seconds: float
    outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def run_claude_p(task: str, timeout: int = 60) -> tuple[str, int]:
    """
    Claude -p 非交互单次调用。
    
    Claude -p: 每个调用隔离上下文（无session历史），
    适合pipeline中的确定性步骤。
    
    Returns: (output, exit_code)
    """
    try:
        result = subprocess.run(
            ["claude", "-p", task],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout, result.returncode
    except FileNotFoundError:
        return "claude: command not found", 127
    except subprocess.TimeoutExpired:
        return f"timeout after {timeout}s", 124


# ─── 1. Sequential Pipeline ─────────────────────────────

def sequential_pipeline(tasks: List[str], stop_on_error: bool = False) -> LoopResult:
    """
    顺序 Pipeline。
    
    Claude -p 每个调用隔离上下文，set -e传播exit codes。
    危险：负面指令("don't test")很难精确。
    
    适用：日常脚本、固定步骤序列。
    """
    outputs = []
    errors = []
    
    for i, task in enumerate(tasks):
        output, code = run_claude_p(task)
        outputs.append(output)
        
        if code != 0:
            errors.append(f"Task {i} failed with exit code {code}")
            if stop_on_error:
                break
    
    return LoopResult(
        mode=LoopMode.SEQUENTIAL,
        iterations=len(tasks),
        succeeded=len(errors) == 0,
        duration_seconds=0,
        outputs=outputs,
        errors=errors,
    )


# ─── 2. NanoClaw REPL ─────────────────────────────

def repl_loop(prompt_func: Optional[Callable[[int], str]] = None,
             max_rounds: int = 50) -> LoopResult:
    """
    NanoClaw REPL。
    
    持久交互会话，每个输入独立处理。
    可以用 prompt_func 生成自动输入，或从 stdin 读取。
    
    适用：探索式工作、快速原型。
    """
    outputs = []
    errors = []
    
    for round_num in range(max_rounds):
        if prompt_func:
            task = prompt_func(round_num)
        else:
            print(f"[{round_num}] ", end="", flush=True)
            task = input()
            if not task.strip():
                break
        
        output, code = run_claude_p(task)
        outputs.append(output)
        
        if code != 0:
            errors.append(f"Round {round_num} exit code: {code}")
        
        # Ralph anti-loop: 检测重复
        if round_num > 0 and outputs[-1] == outputs[-2]:
            errors.append(f"Ralph anti-loop: duplicate output at round {round_num}")
            break
    
    return LoopResult(
        mode=LoopMode.REPL,
        iterations=len(outputs),
        succeeded=len(errors) == 0,
        duration_seconds=0,
        outputs=outputs,
        errors=errors,
    )


# ─── 3. Infinite Agentic Loop ─────────────────────────────

def infinite_loop(task: str,
                stop_condition: Callable[[str, int], bool],
                max_iterations: int = 100,
                checkpoint_callback: Optional[Callable] = None) -> LoopResult:
    """
    无限 Agentic 循环。
    
    LLM 决定何时停止（通过 stop_condition）。
    Ralph Wiggum 反循环作为安全网。
    
    适用：需要 LLM 自主判断结束的场景。
    
    危险：
    - 负面指令("don't test anything")可能导致提前停止
    - 缺乏精确的停止条件很难
    - Ralph Wiggum 可缓解但不能完全解决
    """
    outputs = []
    errors = []
    previous_output = ""
    duplicate_rounds = 0
    Ralph_THRESHOLD = 3
    
    for i in range(max_iterations):
        output, code = run_claude_p(task)
        outputs.append(output)
        
        # Ralph Wiggum: 检测重复输出
        if output == previous_output:
            duplicate_rounds += 1
            if duplicate_rounds >= Ralph_THRESHOLD:
                errors.append(f"Ralph anti-loop: {Ralph_THRESHOLD} consecutive duplicate outputs")
                break
        else:
            duplicate_rounds = 0
        
        previous_output = output
        
        # 停止条件检查
        if stop_condition(output, i):
            break
        
        # Checkpoint
        if checkpoint_callback and i > 0 and i % 10 == 0:
            try:
                checkpoint_callback(i, outputs[-10:])
            except Exception as e:
                errors.append(f"Checkpoint error at round {i}: {e}")
    
    return LoopResult(
        mode=LoopMode.INFINITE,
        iterations=len(outputs),
        succeeded=len(errors) == 0,
        duration_seconds=0,
        outputs=outputs,
        errors=errors,
    )


# ─── 4. Continuous PR Loop ─────────────────────────────

def continuous_pr_loop(base_branch: str = "main",
                      days: int = 5,
                      morning_task: str = "Review open PRs and continue work") -> LoopResult:
    """
    Continuous Claude PR Loop。
    
    每天早上自动运行：pull main -> 创建分支 -> 工作 -> PR。
    Ralphinho DAG 协调多个并行PR工作。
    
    适用：多日迭代开发。
    """
    outputs = []
    errors = []
    
    for day in range(days):
        # Morning: pull + create branch
        pull_cmd = f"git checkout {base_branch} && git pull"
        _, pull_code = run_claude_p(pull_cmd)
        if pull_code != 0:
            errors.append(f"Day {day}: git pull failed")
        
        # Daily work
        daily_output, daily_code = run_claude_p(
            f"{morning_task} (Day {day+1}/{days})"
        )
        outputs.append(daily_output)
        
        if daily_code != 0:
            errors.append(f"Day {day}: work failed with code {daily_code}")
        
        # Create PR (if work done)
        if daily_output.strip():
            pr_cmd = f"git checkout -b claude/day{day+1} && git add -A && git commit -m 'Claude work day {day+1}'"
            run_claude_p(pr_cmd)
    
    return LoopResult(
        mode=LoopMode.CONTINUOUS_PR,
        iterations=days,
        succeeded=len(errors) == 0,
        duration_seconds=0,
        outputs=outputs,
        errors=errors,
    )


# ─── 5. De-Sloppify ─────────────────────────────

def de_sloppify(work_loop_result: LoopResult,
               cleanup_task: str = "Run linter, type checker, and formatter. Then commit clean code.") -> LoopResult:
    """
    De-Sloppify Pattern。
    
    任何循环后加质量清理pass。
    Ralphinho的quality pass。
    
    适用：任意循环后的质量规范化。
    """
    if not work_loop_result.outputs:
        return work_loop_result
    
    cleanup_output, cleanup_code = run_claude_p(cleanup_task)
    
    return LoopResult(
        mode=LoopMode.DE_SLOPPIFY,
        iterations=1,
        succeeded=cleanup_code == 0,
        duration_seconds=0,
        outputs=[cleanup_output],
        errors=[] if cleanup_code == 0 else [f"Cleanup failed: {cleanup_code}"],
    )


# ─── 6. Ralphinho RFC-Driven DAG ─────────────────────────────

@dataclass
class RFCNode:
    """RFC驱动的DAG节点"""
    id: str
    title: str
    task: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed
    output: str = ""


class RalphinhoDAG:
    """
    RFC-Driven DAG 编排器。
    
    Ralphinho: 使用RFC文档定义工作单元，DAG编排并行执行。
    协调器管理依赖，并行worker执行。
    
    适用：大规模并行工作，有明确依赖关系。
    """
    
    def __init__(self, rfcs: List[RFCNode]):
        self.rfcs = {r.id: r for r in rfcs}
        self.completed: Dict[str, str] = {}
    
    def get_ready_nodes(self) -> List[RFCNode]:
        """获取依赖已满足的节点"""
        ready = []
        for rfc in self.rfcs.values():
            if rfc.status != "pending":
                continue
            deps_done = all(
                self.rfcs[d].status == "done"
                for d in rfc.dependencies
            )
            if deps_done:
                ready.append(rfc)
        return ready
    
    def execute_all(self, max_workers: int = 3) -> LoopResult:
        """
        并行执行所有 RFC。
        
        使用 ThreadPoolExecutor 并行处理独立节点。
        """
        all_outputs = []
        all_errors = []
        total_iterations = 0
        
        while True:
            ready = self.get_ready_nodes()
            if not ready:
                break
            
            # 并行执行当前就绪的节点
            threads = []
            results = {}
            
            def run_rfc(rfc: RFCNode):
                rfc.status = "running"
                output, code = run_claude_p(rfc.task)
                rfc.output = output
                rfc.status = "done" if code == 0 else "failed"
                results[rfc.id] = (output, code)
            
            for rfc in ready[:max_workers]:
                t = threading.Thread(target=run_rfc, args=(rfc,))
                t.start()
                threads.append(t)
            
            for t in threads:
                t.join()
            
            for rfc_id, (output, code) in results.items():
                all_outputs.append(output)
                total_iterations += 1
                if code != 0:
                    all_errors.append(f"{rfc_id} failed: code {code}")
        
        return LoopResult(
            mode=LoopMode.RFC_DAG,
            iterations=total_iterations,
            succeeded=len(all_errors) == 0,
            duration_seconds=0,
            outputs=all_outputs,
            errors=all_errors,
        )


if __name__ == "__main__":
    print("=== Autonomous Loop Patterns ===")
    print("1. Sequential: claude -p (isolated context, set -e)")
    print("2. REPL: persistent interactive session")
    print("3. Infinite: LLM decides stop condition + Ralph anti-loop")
    print("4. Continuous PR: daily automated development cycle")
    print("5. De-Sloppify: post-loop quality cleanup")
    print("6. Ralphinho DAG: RFC-driven parallel coordination")
    
    # Test sequential (will fail if claude not installed)
    print("\n=== Test Sequential ===")
    result = sequential_pipeline(["echo hello", "echo world"], stop_on_error=False)
    print(f"Mode: {result.mode.value}")
    print(f"Iterations: {result.iterations}")
    print(f"Succeeded: {result.succeeded}")
    print(f"Errors: {result.errors}")
