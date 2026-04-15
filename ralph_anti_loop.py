# -*- coding: utf-8 -*-
"""
ralph_anti_loop.py — LLM 循环检测与打断

来源: 顾庸t workspace_tools/ralph_loop.py + Claude Code plugins/ralph-wiggum/
用途: 检测 LLM 重复输出，强制打断循环

不修改任何现有系统代码，纯新建模块。
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime


@dataclass
class LoopState:
    """循环检测状态"""
    active: bool = False
    prompt: str = ""
    promise: str = ""
    iteration: int = 0
    max_iterations: int = 100
    started_at: str = ""
    last_outputs: List[str] = field(default_factory=list)
    duplicate_count: int = 0


class RalphAntiLoop:
    """
    LLM 循环检测器
    
    参考 Claude Code Ralph Wiggum 反循环机制:
    - 检测重复输出（SAME PROMPT → 计数递增）
    - Completion promise 机制
    - 最大迭代次数限制
    
    参考 顾庸t ralph_loop.py:
    - Start/Check/Cancel 三操作
    - <promise>COMPLETE</promise> 检测
    - Exit code: 0=allow, 1=needs_more, 2=block
    """
    
    def __init__(self, max_iterations: int = 100, 
                 duplicate_threshold: int = 3,
                 similarity_threshold: float = 0.85):
        self.max_iterations = max_iterations
        self.duplicate_threshold = duplicate_threshold
        self.similarity_threshold = similarity_threshold
        self._state = LoopState()
        self._hash_history: List[str] = []
    
    def start(self, prompt: str, promise: str = "COMPLETE") -> dict:
        """启动循环监控"""
        if self._state.active:
            return {
                "success": False,
                "error": f"Loop already active at iteration {self._state.iteration}/{self._state.max_iterations}. Cancel first."
            }
        
        self._state = LoopState(
            active=True,
            prompt=prompt,
            promise=promise,
            iteration=0,
            max_iterations=self.max_iterations,
            started_at=datetime.now().isoformat(),
        )
        self._hash_history = []
        
        return {
            "success": True,
            "message": f"Loop monitor started. Max {self.max_iterations} iterations.",
            "promise": promise,
        }
    
    def check_output(self, output: str) -> dict:
        """
        检查一次输出
        
        Returns:
            {
                "action": "continue" | "complete" | "block",
                "reason": str,
                "iteration": int,
                "is_duplicate": bool,
                "is_complete": bool
            }
        """
        if not self._state.active:
            return {"action": "continue", "reason": "No active loop", "iteration": 0,
                    "is_duplicate": False, "is_complete": False}
        
        self._state.iteration += 1
        self._state.last_outputs.append(output[-500:])  # 只保留最后500字符
        
        # 1. 检查 completion promise
        is_complete = self._check_promise(output)
        if is_complete:
            self._state.active = False
            return {
                "action": "complete",
                "reason": f"Completion promise '{self._state.promise}' detected",
                "iteration": self._state.iteration,
                "is_duplicate": False,
                "is_complete": True,
            }
        
        # 2. 检查最大迭代
        if self._state.iteration >= self._state.max_iterations:
            self._state.active = False
            return {
                "action": "block",
                "reason": f"Max iterations ({self._state.max_iterations}) reached",
                "iteration": self._state.iteration,
                "is_duplicate": False,
                "is_complete": False,
            }
        
        # 3. 检查重复输出
        output_hash = hashlib.md5(output.encode()).hexdigest()
        is_duplicate = self._check_duplicate(output_hash)
        self._hash_history.append(output_hash)
        
        if is_duplicate:
            self._state.duplicate_count += 1
            if self._state.duplicate_count >= self.duplicate_threshold:
                self._state.active = False
                return {
                    "action": "block",
                    "reason": f"Duplicate output detected {self._state.duplicate_count} times. Loop detected.",
                    "iteration": self._state.iteration,
                    "is_duplicate": True,
                    "is_complete": False,
                }
        
        # 4. 检查相似度（不精确重复但高度相似）
        if len(self._hash_history) >= 2:
            similarity = self._compute_similarity(
                self._state.last_outputs[-1],
                self._state.last_outputs[-2] if len(self._state.last_outputs) >= 2 else ""
            )
            if similarity > self.similarity_threshold:
                self._state.duplicate_count += 1
        
        return {
            "action": "continue",
            "reason": "",
            "iteration": self._state.iteration,
            "is_duplicate": is_duplicate,
            "is_complete": False,
        }
    
    def cancel(self) -> dict:
        """取消循环监控"""
        if not self._state.active:
            return {"success": False, "error": "No active loop to cancel."}
        
        iteration = self._state.iteration
        self._state.active = False
        return {
            "success": True,
            "message": f"Loop cancelled (was at iteration {iteration}).",
        }
    
    @property
    def status(self) -> dict:
        """获取当前状态"""
        return {
            "active": self._state.active,
            "iteration": self._state.iteration,
            "max_iterations": self._state.max_iterations,
            "duplicate_count": self._state.duplicate_count,
            "promise": self._state.promise,
        }
    
    def _check_promise(self, output: str) -> bool:
        """检查 completion promise"""
        if not self._state.promise:
            return False
        promise = self._state.promise.strip().lower()
        # 支持多种格式
        patterns = [
            f"<promise>{promise}</promise>",
            f"[{promise}]",
            f"**{promise}**",
            promise,  # 直接出现
        ]
        output_lower = output.lower()
        return any(p.lower() in output_lower for p in patterns)
    
    def _check_duplicate(self, output_hash: str) -> bool:
        """检查是否是精确重复"""
        return output_hash in self._hash_history
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        """简单的文本相似度（Jaccard on words）"""
        if not text1 or not text2:
            return 0.0
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)


if __name__ == "__main__":
    # 测试
    ralph = RalphAntiLoop(max_iterations=10, duplicate_threshold=3)
    
    # 启动
    result = ralph.start("Build a REST API", "COMPLETE")
    print(f"Start: {result}")
    
    # 模拟输出
    outputs = [
        "Step 1: Created the endpoint",
        "Step 2: Added validation",
        "Step 2: Added validation",  # 重复
        "Step 2: Added validation",  # 再次重复
        "Step 2: Added validation",  # 第3次 → 应该触发
    ]
    
    for output in outputs:
        result = ralph.check_output(output)
        print(f"  Iteration {result['iteration']}: {result['action']} (dup={result['is_duplicate']})")
        if result['action'] != 'continue':
            print(f"    Reason: {result['reason']}")
            break
    
    # 测试 completion promise
    ralph2 = RalphAntiLoop(max_iterations=10)
    ralph2.start("Deploy the app", "COMPLETE")
    result = ralph2.check_output("Deployment finished <promise>COMPLETE</promise>")
    print(f"\nPromise test: {result['action']} (complete={result['is_complete']})")
