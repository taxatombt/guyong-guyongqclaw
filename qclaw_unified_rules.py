# -*- coding: utf-8 -*-
"""
qclaw_unified_rules.py — 三个规则系统统一查询接口

整合三个互补的规则系统：
1. evolver.py — 经验记录（what method worked），110条规则，置信度排序
2. instinct_model.py — 行为原因（why I do this），原子行为级，项目隔离
3. rule_engine.py — 安全规则（what's blocked/warned），6种操作符，双Action

设计原则：
- 三系统互补不重叠，不合并
- 统一查询入口，按需路由
- 单一 API：query(task) → 综合结果
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

log = logging.getLogger("qclaw.unified_rules")


# ─── 统一结果格式 ─────────────────────────────────────────

@dataclass
class RuleResult:
    """统一规则查询结果"""
    source: str = ""          # "evolver" / "instinct" / "rule_engine"
    action: str = ""          # "use_method" / "follow_instinct" / "block" / "warn" / "allow"
    confidence: float = 0.0   # 0.0-1.0
    content: str = ""         # 具体建议/规则内容
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedQueryResult:
    """综合查询结果"""
    task: str = ""
    evolver: Optional[RuleResult] = None
    instinct: Optional[RuleResult] = None
    security: Optional[RuleResult] = None
    recommendation: str = ""  # 综合推荐

    def to_summary(self) -> str:
        """生成可读摘要"""
        lines = [f"📋 规则查询: {self.task}"]
        if self.evolver:
            lines.append(f"  📊 经验: {self.evolver.content} (置信度{self.evolver.confidence:.0%})")
        if self.instinct:
            lines.append(f"  🧠 本能: {self.instinct.content} (置信度{self.instinct.confidence:.0%})")
        if self.security:
            icon = "🚫" if self.security.action == "block" else "⚠️"
            lines.append(f"  {icon} 安全: {self.security.content}")
        if self.recommendation:
            lines.append(f"  ➡️ 推荐: {self.recommendation}")
        return "\n".join(lines)


# ─── 统一查询引擎 ─────────────────────────────────────────

class UnifiedRuleEngine:
    """
    三个规则系统的统一查询入口
    
    查询优先级：
    1. 安全规则（最高） — 如果 block，直接返回
    2. 经验记录（次高） — 有高置信度方法就用
    3. 行为本能（补充） — 解释为什么要这样做
    """

    def __init__(self, workspace_dir: str = ""):
        self._workspace = workspace_dir
        self._evolver = None
        self._instinct_model = None
        self._rule_engine = None
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化（避免导入循环）"""
        if self._initialized:
            return
        
        import sys
        from pathlib import Path
        ws = self._workspace or str(Path.home() / ".qclaw" / "workspace")
        if ws not in sys.path:
            sys.path.insert(0, ws)

        # 1. Evolver
        try:
            from evolver import EvolverEngine
            self._evolver = EvolverEngine()
        except Exception as e:
            log.warning(f"Evolver init failed: {e}")

        # 2. Instinct Model
        try:
            from instinct_model import InstinctStore
            self._instinct_model = InstinctStore()
        except Exception as e:
            log.debug(f"InstinctModel not available: {e}")

        # 3. Rule Engine
        try:
            from rule_engine import RuleEngine
            self._rule_engine = RuleEngine()
        except Exception as e:
            log.debug(f"RuleEngine not available: {e}")

        self._initialized = True

    def query(self, task: str, tool_name: str = "",
              tool_input: Dict[str, Any] = None) -> UnifiedQueryResult:
        """
        统一查询：给定任务/工具调用，返回综合规则结果
        
        Args:
            task: 任务描述
            tool_name: 工具名（可选，安全规则需要）
            tool_input: 工具输入（可选，安全规则需要）
        """
        self._ensure_initialized()
        result = UnifiedQueryResult(task=task)

        # 1. 安全规则（最高优先级）
        if self._rule_engine and tool_name:
            try:
                context = {"tool_name": tool_name, "tool_input": tool_input or {}}
                sec_result = self._rule_engine.evaluate(context)
                if sec_result and sec_result.get("action") != "allow":
                    result.security = RuleResult(
                        source="rule_engine",
                        action=sec_result.get("action", "warn"),
                        confidence=1.0,
                        content=sec_result.get("name", "Security rule triggered"),
                        metadata=sec_result,
                    )
                    if result.security.action == "block":
                        result.recommendation = f"🚫 被安全规则阻止: {result.security.content}"
                        return result  # 直接返回，不查其他
            except Exception as e:
                log.debug(f"Rule engine query failed: {e}")

        # 2. 经验记录
        if self._evolver:
            try:
                best = self._evolver.best_method({"task": task})
                if best and best.get("confidence", 0) >= 0.5:
                    result.evolver = RuleResult(
                        source="evolver",
                        action="use_method",
                        confidence=best.get("confidence", 0),
                        content=f"使用: {best.get('method', 'unknown')} (成功率{best.get('success_rate', 0):.0%})",
                        metadata=best,
                    )
            except Exception as e:
                log.debug(f"Evolver query failed: {e}")

        # 3. 行为本能
        if self._instinct_model:
            try:
                instincts = self._instinct_model.search(task)
                if instincts:
                    top = instincts[0] if isinstance(instincts, list) else instincts
                    result.instinct = RuleResult(
                        source="instinct_model",
                        action="follow_instinct",
                        confidence=getattr(top, "confidence", 0.5),
                        content=getattr(top, "action", str(top)),
                        metadata={"instinct": str(top)},
                    )
            except Exception as e:
                log.debug(f"Instinct query failed: {e}")

        # 4. 综合推荐
        result.recommendation = self._build_recommendation(result)
        return result

    def _build_recommendation(self, result: UnifiedQueryResult) -> str:
        """根据查询结果生成综合推荐"""
        if result.security and result.security.action == "block":
            return f"🚫 被安全规则阻止: {result.security.content}"
        
        parts = []
        if result.evolver:
            parts.append(f"经验推荐: {result.evolver.content}")
        if result.instinct:
            parts.append(f"本能倾向: {result.instinct.content}")
        if result.security and result.security.action == "warn":
            parts.append(f"⚠️ 安全警告: {result.security.content}")
        
        if not parts:
            return "无相关规则，自由决策"
        return " | ".join(parts)

    def stats(self) -> Dict[str, Any]:
        """统计三个系统的规则数量"""
        self._ensure_initialized()
        return {
            "evolver_rules": len(self._evolver.rules) if self._evolver else 0,
            "instincts": 0,  # TODO: instinct_store.count()
            "security_rules": len(self._rule_engine._rules) if self._rule_engine else 0,
        }


# ─── 便捷函数 ─────────────────────────────────────────────

_engine: Optional[UnifiedRuleEngine] = None

def get_unified_engine(workspace_dir: str = "") -> UnifiedRuleEngine:
    """获取全局统一规则引擎"""
    global _engine
    if _engine is None:
        _engine = UnifiedRuleEngine(workspace_dir)
    return _engine

def query_rules(task: str, tool_name: str = "",
                tool_input: Dict[str, Any] = None) -> UnifiedQueryResult:
    """快捷查询"""
    return get_unified_engine().query(task, tool_name, tool_input)
