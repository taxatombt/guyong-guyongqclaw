"""
token_budget.py — qclaw Token Budget Controller

来源：Hermes Agent Guide 第4册（预算三维度）+ 第7册（上下文溢出5级降级）

设计：
- 三维度预算：max_turns / max_tool_calls / max_cost_usd
- 5级溢出降级策略
- 实时追踪，超预算自动触发降级
"""

import time
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class DegradationLevel(IntEnum):
    """上下文溢出5级降级（Hermes设计）"""
    NORMAL = 0       # 正常运行
    COMPACT = 1      # 压缩上下文（snip → microcompact → collapse → autocompact）
    FIFO_TRUNCATE = 2  # FIFO截断（保留工具调用，丢弃早期对话）
    REDUCE_COLD = 3    # 缩减冷记忆注入（减少从memory/加载的上下文）
    REDUCE_WARM = 4    # 缩减温记忆（保留MEMORY.md，丢弃USER.md/细节）
    ERROR = 5          # 报错终止


@dataclass
class BudgetConfig:
    """预算配置"""
    max_turns: int = 50          # 最大对话轮次
    max_tool_calls: int = 100    # 最大工具调用次数
    max_cost_usd: float = 5.0    # 最大花费（美元）
    max_context_tokens: int = 200000  # 上下文token上限
    warn_threshold: float = 0.8   # 警告阈值（80%）
    
    # 降级阈值（占上下文token上限的比例）
    compact_threshold: float = 0.85    # 85%触发compact
    fifo_threshold: float = 0.90       # 90%触发FIFO
    reduce_cold_threshold: float = 0.93  # 93%缩减冷记忆
    reduce_warm_threshold: float = 0.96  # 96%缩减温记忆


@dataclass
class UsageStats:
    """使用统计"""
    turns: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    context_tokens: int = 0
    session_start: float = field(default_factory=time.time)
    
    # 各降级触发次数
    compact_count: int = 0
    fifo_count: int = 0
    reduce_cold_count: int = 0
    reduce_warm_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "cost_usd": round(self.cost_usd, 4),
            "context_tokens": self.context_tokens,
            "session_duration_sec": round(time.time() - self.session_start, 1),
            "degradation_counts": {
                "compact": self.compact_count,
                "fifo": self.fifo_count,
                "reduce_cold": self.reduce_cold_count,
                "reduce_warm": self.reduce_warm_count,
            }
        }


class ModelFallbackChain:
    """
    模型精度降级链（Karpathy train.py精度策略的qclaw版）
    
    来源：karpathy/nanoGPT train.py
    设计：bf16 > fp16+scaler > fp32 的三段式精度策略
    qclaw版：贵模型 → 便宜模型 → 本地模型
    
    用法：
        chain = ModelFallbackChain(['gpt-4o', 'gpt-3.5-turbo', 'local'])
        model = chain.current()  # 当前模型
        if budget.is_over_warn():
            model = chain.downgrade()  # 降级
    """
    
    def __init__(self, models: list, cost_weights: Optional[list] = None):
        self.models = models
        self.cost_weights = cost_weights or [1.0 / (i + 1) for i in range(len(models))]
        self._index = 0
    
    def current(self) -> str:
        return self.models[self._index]
    
    def downgrade(self) -> str:
        if self._index < len(self.models) - 1:
            self._index += 1
        return self.current()
    
    def upgrade(self) -> str:
        if self._index > 0:
            self._index -= 1
        return self.current()
    
    def reset(self):
        self._index = 0
    
    def cost_weight(self) -> float:
        return self.cost_weights[self._index]
    
    def is_local(self) -> bool:
        return self._index == len(self.models) - 1


class TokenBudgetController:
    """
    Token预算控制器
    
    用法：
        budget = TokenBudgetController()
        
        # 每轮开始
        budget.on_turn_start()
        
        # 每次工具调用
        budget.on_tool_call()
        
        # 每次token更新
        level = budget.check_context(estimated_tokens)
        if level >= DegradationLevel.COMPACT:
            # 触发压缩
            pass
        
        # 花费追踪
        budget.add_cost(0.02)
        
        # 模型降级
        model = budget.recommend_model()
        
        # 查询
        print(budget.status())
    """
    
    def __init__(self, config: Optional[BudgetConfig] = None, fallback_models: Optional[list] = None):
        self.config = config or BudgetConfig()
        self.stats = UsageStats()
        self._degradation_level = DegradationLevel.NORMAL
        self._cost_per_tool_call = 0.0  # 动态估算
        self._total_tool_cost = 0.0
        self._tool_call_count_for_avg = 0
        self.fallback = ModelFallbackChain(fallback_models or ['gpt-4o', 'gpt-3.5-turbo', 'local'])
    
    # === 事件钩子 ===
    
    def on_turn_start(self) -> bool:
        """轮次开始，返回True如果允许继续"""
        self.stats.turns += 1
        return self.stats.turns <= self.config.max_turns
    
    def on_tool_call(self, estimated_cost_usd: float = 0.0) -> bool:
        """
        工具调用，返回True如果允许继续
        
        Args:
            estimated_cost_usd: 预估此次调用花费
        """
        if self.stats.tool_calls >= self.config.max_tool_calls:
            return False
        if self.stats.cost_usd + estimated_cost_usd > self.config.max_cost_usd:
            return False
        
        self.stats.tool_calls += 1
        if estimated_cost_usd > 0:
            self.add_cost(estimated_cost_usd)
        return True
    
    def add_cost(self, cost_usd: float):
        """追加花费"""
        self.stats.cost_usd += cost_usd
        # 动态更新平均每次工具调用花费
        if cost_usd > 0:
            self._total_tool_cost += cost_usd
            self._tool_call_count_for_avg += 1
            self._cost_per_tool_call = self._total_tool_cost / self._tool_call_count_for_avg
    
    # === 降级检测 ===
    
    def check_context(self, current_tokens: int) -> DegradationLevel:
        """
        检查上下文大小，返回当前应处的降级级别
        
        这实现了Hermes的5级降级策略：
        NORMAL → COMPACT → FIFO_TRUNCATE → REDUCE_COLD → REDUCE_WARM → ERROR
        """
        self.stats.context_tokens = current_tokens
        max_t = self.config.max_context_tokens
        ratio = current_tokens / max_t if max_t > 0 else 0
        
        if ratio >= 1.0:
            level = DegradationLevel.ERROR
        elif ratio >= self.config.reduce_warm_threshold:
            level = DegradationLevel.REDUCE_WARM
            self.stats.reduce_warm_count += 1
        elif ratio >= self.config.reduce_cold_threshold:
            level = DegradationLevel.REDUCE_COLD
            self.stats.reduce_cold_count += 1
        elif ratio >= self.config.fifo_threshold:
            level = DegradationLevel.FIFO_TRUNCATE
            self.stats.fifo_count += 1
        elif ratio >= self.config.compact_threshold:
            level = DegradationLevel.COMPACT
            self.stats.compact_count += 1
        else:
            level = DegradationLevel.NORMAL
        
        # 只在级别升高时更新（不降级）
        if level > self._degradation_level:
            self._degradation_level = level
        
        return self._degradation_level
    
    def get_degradation_action(self, level: DegradationLevel) -> str:
        """返回降级级别对应的行动建议"""
        actions = {
            DegradationLevel.NORMAL: "正常运行",
            DegradationLevel.COMPACT: "压缩上下文（snip → microcompact → collapse → autocompact）",
            DegradationLevel.FIFO_TRUNCATE: "FIFO截断：保留工具调用结果，丢弃早期对话",
            DegradationLevel.REDUCE_COLD: "缩减冷记忆：减少从memory/加载的历史上下文",
            DegradationLevel.REDUCE_WARM: "缩减温记忆：保留MEMORY.md核心，丢弃USER.md和细节",
            DegradationLevel.ERROR: "上下文溢出：必须终止或重置",
        }
        return actions.get(level, "未知")
    
    # === 预算查询 ===
    
    def remaining_turns(self) -> int:
        return max(0, self.config.max_turns - self.stats.turns)
    
    def remaining_tool_calls(self) -> int:
        return max(0, self.config.max_tool_calls - self.stats.tool_calls)
    
    def remaining_budget_usd(self) -> float:
        return max(0.0, self.config.max_cost_usd - self.stats.cost_usd)
    
    def usage_ratio(self) -> dict:
        """各维度使用率"""
        return {
            "turns": self.stats.turns / self.config.max_turns,
            "tool_calls": self.stats.tool_calls / self.config.max_tool_calls,
            "cost": self.stats.cost_usd / self.config.max_cost_usd if self.config.max_cost_usd > 0 else 0,
            "context": self.stats.context_tokens / self.config.max_context_tokens if self.config.max_context_tokens > 0 else 0,
        }
    
    def is_over_warn(self) -> bool:
        """是否超过警告阈值"""
        ratios = self.usage_ratio()
        return any(r >= self.config.warn_threshold for r in ratios.values())
    
    def status(self) -> dict:
        """完整状态报告"""
        ratios = self.usage_ratio()
        return {
            "usage": self.stats.to_dict(),
            "remaining": {
                "turns": self.remaining_turns(),
                "tool_calls": self.remaining_tool_calls(),
                "budget_usd": round(self.remaining_budget_usd(), 4),
            },
            "ratios": {k: round(v, 3) for k, v in ratios.items()},
            "degradation": {
                "current_level": self._degradation_level.name,
                "action": self.get_degradation_action(self._degradation_level),
            },
            "over_warn": self.is_over_warn(),
            "avg_cost_per_tool": round(self._cost_per_tool_call, 4),
        }
    
    def summary(self) -> str:
        """人类可读摘要"""
        s = self.status()
        lines = [
            f"🔄 TokenBudget: Turn {s['usage']['turns']}/{self.config.max_turns} | "
            f"Tools {s['usage']['tool_calls']}/{self.config.max_tool_calls} | "
            f"${s['usage']['cost_usd']:.4f}/${self.config.max_cost_usd}",
            f"📊 Context: {s['usage']['context_tokens']} tokens "
            f"({s['ratios']['context']:.1%}) | "
            f"Degradation: {s['degradation']['current_level']}",
        ]
        if self.is_over_warn():
            lines.append("⚠️ 超过警告阈值！")
        return "\n".join(lines)
    
    # === 序列化 ===
    
    def save(self, path: str):
        """保存状态到JSON"""
        data = {
            "config": {
                "max_turns": self.config.max_turns,
                "max_tool_calls": self.config.max_tool_calls,
                "max_cost_usd": self.config.max_cost_usd,
                "max_context_tokens": self.config.max_context_tokens,
                "warn_threshold": self.config.warn_threshold,
            },
            "stats": self.stats.to_dict(),
            "degradation_level": int(self._degradation_level),
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, path: str) -> 'TokenBudgetController':
        """从JSON恢复状态"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        config = BudgetConfig(**data.get("config", {}))
        ctrl = cls(config)
        
        stats_data = data.get("stats", {})
        ctrl.stats.turns = stats_data.get("turns", 0)
        ctrl.stats.tool_calls = stats_data.get("tool_calls", 0)
        ctrl.stats.cost_usd = stats_data.get("cost_usd", 0.0)
        ctrl.stats.context_tokens = stats_data.get("context_tokens", 0)
        
        ctrl._degradation_level = DegradationLevel(data.get("degradation_level", 0))
        return ctrl


# === 快捷函数 ===

_default_controller: Optional[TokenBudgetController] = None


def get_budget(config: Optional[BudgetConfig] = None) -> TokenBudgetController:
    """获取全局预算控制器（单例）"""
    global _default_controller
    if _default_controller is None:
        _default_controller = TokenBudgetController(config)
    return _default_controller


def reset_budget(config: Optional[BudgetConfig] = None):
    """重置全局预算控制器"""
    global _default_controller
    _default_controller = TokenBudgetController(config)


if __name__ == "__main__":
    # 自测
    ctrl = TokenBudgetController()
    
    # 模拟10轮对话
    for i in range(10):
        ctrl.on_turn_start()
        ctrl.on_tool_call(0.01)
        level = ctrl.check_context(50000 + i * 15000)
        if level > DegradationLevel.NORMAL:
            print(f"  Turn {i+1}: {ctrl.get_degradation_action(level)}")
    
    print("\n" + ctrl.summary())
    print("\nFull status:")
    print(json.dumps(ctrl.status(), ensure_ascii=False, indent=2))
    
    # 保存/加载测试
    ctrl.save("test_budget.json")
    loaded = TokenBudgetController.load("test_budget.json")
    assert loaded.stats.turns == ctrl.stats.turns
    assert loaded.stats.tool_calls == ctrl.stats.tool_calls
    print("\n✅ Save/Load test passed")
    
    # 清理
    import os
    os.remove("test_budget.json")
    print("✅ All tests passed")
