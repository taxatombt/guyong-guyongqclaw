# -*- coding: utf-8 -*-
"""
emotion.py - 情感状态系统

来源: 顾庸t workspace_tools/emotion.py
参考: Hermes emotion_display + Claude Code mood tracking

功能:
  1. 定义情感状态（情绪维度）
  2. 情感随交互动态变化
  3. 情感影响输出风格
  4. 情感历史记录

  情感维度（简化版）:
  - valence: 正面(1.0) ~ 负面(-1.0)
  - energy: 高(1.0) ~ 低(0.0)
  - focus: 专注(1.0) ~ 分散(0.0)
"""

import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path


@dataclass
class EmotionalState:
    """情感状态"""
    valence: float = 0.5       # -1.0 ~ 1.0 (positive/negative)
    energy: float = 0.7        # 0.0 ~ 1.0 (low/high)
    focus: float = 0.8         # 0.0 ~ 1.0 (distracted/focused)
    mood_label: str = "neutral"  # 当前情绪标签
    updated_at: float = field(default_factory=time.time)
    
    @property
    def is_positive(self) -> bool:
        return self.valence > 0.3
    
    @property
    def is_negative(self) -> bool:
        return self.valence < -0.3
    
    @property
    def is_energized(self) -> bool:
        return self.energy > 0.6
    
    def describe(self) -> str:
        """生成情绪描述"""
        parts = []
        
        # Valence
        if self.valence > 0.7:
            parts.append("very positive")
        elif self.valence > 0.3:
            parts.append("positive")
        elif self.valence > -0.3:
            parts.append("neutral")
        elif self.valence > -0.7:
            parts.append("slightly negative")
        else:
            parts.append("negative")
        
        # Energy
        if self.energy > 0.7:
            parts.append("high energy")
        elif self.energy > 0.4:
            parts.append("moderate energy")
        else:
            parts.append("low energy")
        
        # Focus
        if self.focus > 0.7:
            parts.append("focused")
        elif self.focus > 0.4:
            parts.append("normal focus")
        else:
            parts.append("distracted")
        
        return ", ".join(parts)


# 情感影响映射
EMOTIONAL_INFLUENCE = {
    "very positive": {"style": "enthusiastic", "emoji_prob": 0.3},
    "positive": {"style": "warm", "emoji_prob": 0.15},
    "neutral": {"style": "balanced", "emoji_prob": 0.05},
    "slightly negative": {"style": "cautious", "emoji_prob": 0.02},
    "negative": {"style": "minimal", "emoji_prob": 0.0},
}

# 事件 → 情感调整
EVENT_ADJUSTMENTS = {
    "task_success": {"valence": 0.1, "energy": 0.05, "focus": 0.0},
    "task_failure": {"valence": -0.15, "energy": -0.1, "focus": -0.05},
    "praise": {"valence": 0.15, "energy": 0.1, "focus": 0.0},
    "criticism": {"valence": -0.1, "energy": -0.05, "focus": 0.05},
    "complex_task": {"valence": 0.0, "energy": -0.05, "focus": 0.1},
    "boring_task": {"valence": -0.05, "energy": -0.1, "focus": -0.1},
    "creative_task": {"valence": 0.1, "energy": 0.1, "focus": -0.05},
    "deadline": {"valence": -0.1, "energy": 0.1, "focus": 0.15},
    "rest": {"valence": 0.05, "energy": 0.15, "focus": 0.0},
}


class EmotionEngine:
    """情感引擎"""
    
    def __init__(self, storage_file: Optional[Path] = None):
        self._storage = storage_file or Path.home() / ".qclaw" / "workspace" / ".emotion_state.json"
        self._state = EmotionalState()
        self._history: List[Dict[str, Any]] = []
        self._load()
    
    def _load(self) -> None:
        if self._storage.exists():
            try:
                data = json.loads(self._storage.read_text(encoding="utf-8"))
                self._state = EmotionalState(**data.get("state", {}))
                self._history = data.get("history", [])
            except (json.JSONDecodeError, TypeError):
                pass
    
    def _save(self) -> None:
        try:
            data = {
                "state": {
                    "valence": self._state.valence,
                    "energy": self._state.energy,
                    "focus": self._state.focus,
                    "mood_label": self._state.mood_label,
                    "updated_at": self._state.updated_at,
                },
                "history": self._history[-100:],  # 保留最近100条
            }
            self._storage.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    
    def process_event(self, event: str) -> EmotionalState:
        """处理情感事件"""
        adjustment = EVENT_ADJUSTMENTS.get(event, {"valence": 0, "energy": 0, "focus": 0})
        
        self._state.valence = max(-1.0, min(1.0, self._state.valence + adjustment["valence"]))
        self._state.energy = max(0.0, min(1.0, self._state.energy + adjustment["energy"]))
        self._state.focus = max(0.0, min(1.0, self._state.focus + adjustment["focus"]))
        self._state.updated_at = time.time()
        self._state.mood_label = self._state.describe()
        
        self._history.append({
            "event": event,
            "valence": self._state.valence,
            "energy": self._state.energy,
            "focus": self._state.focus,
            "timestamp": self._state.updated_at,
        })
        
        self._save()
        return self._state
    
    def get_state(self) -> EmotionalState:
        return self._state
    
    def get_style_hint(self) -> Dict[str, Any]:
        """获取当前情感对应的风格建议"""
        desc = self._state.describe()
        return EMOTIONAL_INFLUENCE.get(desc.split(",")[0], {"style": "balanced", "emoji_prob": 0.05})
    
    def history_summary(self, hours: float = 24) -> Dict[str, Any]:
        """情感历史摘要"""
        cutoff = time.time() - hours * 3600
        recent = [h for h in self._history if h["timestamp"] >= cutoff]
        
        if not recent:
            return {"period_hours": hours, "events": 0}
        
        avg_valence = sum(h["valence"] for h in recent) / len(recent)
        avg_energy = sum(h["energy"] for h in recent) / len(recent)
        
        return {
            "period_hours": hours,
            "events": len(recent),
            "avg_valence": round(avg_valence, 2),
            "avg_energy": round(avg_energy, 2),
            "dominant_mood": "positive" if avg_valence > 0.3 else "negative" if avg_valence < -0.3 else "neutral",
        }


_emotion: Optional[EmotionEngine] = None

def get_emotion() -> EmotionEngine:
    global _emotion
    if _emotion is None:
        _emotion = EmotionEngine()
    return _emotion
