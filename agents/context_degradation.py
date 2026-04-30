"""
context_degradation.py — 5级上下文溢出降级执行器

来源：Hermes Agent Guide 第7册（5级降级）+ Karpathy nanoGPT（精度三段式）
依赖：agents/token_budget.py（DegradationLevel）

降级策略：
1. NORMAL — 正常运行
2. COMPACT — 压缩上下文（调用compactor）
3. FIFO_TRUNCATE — 截断早期对话，保留工具调用
4. REDUCE_COLD — 减少从memory/加载的冷记忆
5. REDUCE_WARM — 只保留MEMORY.md核心，丢USER.md和细节
6. ERROR — 报错终止
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from agents.token_budget import DegradationLevel, get_budget

log = logging.getLogger("qclaw.degradation")

WORKSPACE = Path(os.environ.get("QCLAW_WORKSPACE", r"C:\Users\yiseg\.qclaw\workspace"))
MEMORY_DIR = WORKSPACE / "memory"
DEGRADATION_LOG = MEMORY_DIR / "degradation_log.jsonl"


class ContextDegradationExecutor:
    """执行上下文溢出降级策略"""

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def execute(self, level: DegradationLevel, context_tokens: int = 0) -> Dict[str, Any]:
        """根据降级级别执行对应策略"""
        result = {
            "level": level.name,
            "level_int": int(level),
            "context_tokens": context_tokens,
            "timestamp": time.time(),
            "actions_taken": [],
        }

        if level >= DegradationLevel.ERROR:
            result["actions_taken"].append("ERROR: 上下文溢出，需要开新会话")
            result["message"] = "⚠️ 上下文已满，请开新会话继续"
            self._log(result)
            return result

        if level >= DegradationLevel.COMPACT:
            actions = self._do_compact()
            result["actions_taken"].extend(actions)

        if level >= DegradationLevel.FIFO_TRUNCATE:
            actions = self._do_fifo_truncate()
            result["actions_taken"].extend(actions)

        if level >= DegradationLevel.REDUCE_COLD:
            actions = self._do_reduce_cold()
            result["actions_taken"].extend(actions)

        if level >= DegradationLevel.REDUCE_WARM:
            actions = self._do_reduce_warm()
            result["actions_taken"].extend(actions)

        self._log(result)
        return result

    def _do_compact(self) -> List[str]:
        """
        Level 1: 压缩上下文
        策略：建议系统执行compaction（OpenClaw的LCM系统会自动处理）
        这里只记录建议，不直接操作上下文
        """
        log.info("[degradation] COMPACT: 建议执行上下文压缩")
        return ["COMPACT: 建议系统执行compaction"]

    def _do_fifo_truncate(self) -> List[str]:
        """
        Level 2: FIFO截断
        策略：丢弃早期对话轮次，保留工具调用结果
        （OpenClaw的compaction模式=safeguard已实现类似功能）
        """
        log.info("[degradation] FIFO_TRUNCATE: 早期对话可被截断")
        return ["FIFO_TRUNCATE: 早期对话优先截断，保留工具调用结果"]

    def _do_reduce_cold(self) -> List[str]:
        """
        Level 3: 缩减冷记忆注入
        策略：减少从memory/文件加载到上下文的内容量
        具体做法：只加载最近3天的memory文件（而非7天），限制每文件只取前20行
        """
        actions = []
        # 统计memory/目录下的文件数和总大小
        total_files = 0
        total_size = 0
        if MEMORY_DIR.exists():
            for f in MEMORY_DIR.glob("*.md"):
                if f.name.startswith("202"):
                    total_files += 1
                    total_size += f.stat().st_size

        actions.append(f"REDUCE_COLD: 限制memory/注入量（{total_files}个文件，{total_size//1024}KB）")
        actions.append("REDUCE_COLD: 只加载最近3天memory，每文件限前20行")
        log.info(f"[degradation] REDUCE_COLD: {total_files} files, {total_size//1024}KB")
        return actions

    def _do_reduce_warm(self) -> List[str]:
        """
        Level 4: 缩减温记忆
        策略：只保留MEMORY.md核心（索引），USER.md降级为冷记忆
        """
        actions = []
        memory_md = WORKSPACE / "MEMORY.md"
        if memory_md.exists():
            size = memory_md.stat().st_size
            actions.append(f"REDUCE_WARM: MEMORY.md保留（{size}B），USER.md降级为冷记忆")
        log.info("[degradation] REDUCE_WARM: 只保留MEMORY.md核心索引")
        return actions

    def _log(self, result: Dict):
        """记录降级事件到日志"""
        try:
            with open(DEGRADATION_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning(f"[degradation] log write failed: {e}")

    def get_recent_degradations(self, limit: int = 10) -> List[Dict]:
        """读取最近的降级事件"""
        if not DEGRADATION_LOG.exists():
            return []
        try:
            with open(DEGRADATION_LOG, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            return [json.loads(l) for l in lines[-limit:]]
        except Exception:
            return []


# 全局单例
_executor: Optional[ContextDegradationExecutor] = None

def get_degradation_executor() -> ContextDegradationExecutor:
    global _executor
    if _executor is None:
        _executor = ContextDegradationExecutor()
    return _executor

def check_and_degrade(context_tokens: int) -> Optional[Dict]:
    """
    检查上下文大小，执行必要降级。
    在每次工具调用后或每次对话轮次开始时调用。

    Returns:
        降级结果dict，或None（不需要降级）
    """
    budget = get_budget()
    level = budget.check_context(context_tokens)
    if level > DegradationLevel.NORMAL:
        executor = get_degradation_executor()
        return executor.execute(level, context_tokens)
    return None
