# -*- coding: utf-8 -*-
"""
self_model_insights_bridge.py - insights 量化数据 → self_model 叙事结论

来源: Hermes InsightsEngine + guyong-juhuo 第8系统
       顾庸t self_model_insights_bridge.py

核心理念: 只有量化了自己，才能知道自己变了多少。

SelfModelAnalyzer 从 session 元数据推断:
  - 时间模式: 工作日型 / 夜猫型
  - engagement 深度: 浅/中/深
  - 变化趋势: 上升/下降/稳定
  - 工具偏好: 哪些工具用得最多

写入 memory/evolver_global/self_model_updates/YYYY-W{week}.json
周内多跑自动合并去重。
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
STORAGE_DIR = WORKSPACE / "memory" / "evolver_global" / "self_model_updates"


@dataclass
class SessionMeta:
    """单次 session 元数据"""
    session_id: str
    started_at: str
    duration_minutes: float
    message_count: int
    tool_calls: int
    tools_used: List[str] = field(default_factory=list)
    turns: int = 0
    tokens_used: int = 0


@dataclass
class SelfModelUpdate:
    """单条 self_model 更新"""
    timestamp: str
    week: str
    insight_type: str
    insight_value: str
    confidence: float
    evidence: List[str] = field(default_factory=list)


class SelfModelAnalyzer:
    """
    从 session 洞察推断 self_model 叙事结论。
    
    流程:
    1. 收集 session 元数据
    2. 量化分析 (时间模式/工具偏好/engagement)
    3. 生成 self_model 叙事结论
    4. 与历史对比，生成变化趋势
    5. 写入周文件 (自动合并去重)
    """
    
    def __init__(self):
        self._storage_dir = STORAGE_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _week_id(self, dt: Optional[datetime] = None) -> str:
        if dt is None:
            dt = datetime.now(timezone.utc)
        return f"{dt.year}-W{dt.isocalendar()[1]:02d}"
    
    def _load_history(self, week: str) -> List[SelfModelUpdate]:
        """加载历史更新"""
        path = self._storage_dir / f"{week}.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [SelfModelUpdate(**u) for u in data.get("updates", [])]
        except Exception:
            return []
    
    def _save_updates(self, week: str, updates: List[SelfModelUpdate]) -> None:
        """保存更新 (自动去重)"""
        # 去重: 同类型同值只保留最新的
        seen = {}
        for u in sorted(updates, key=lambda x: x.timestamp, reverse=True):
            key = (u.insight_type, u.insight_value)
            if key not in seen:
                seen[key] = u
        unique = list(seen.values())
        
        path = self._storage_dir / f"{week}.json"
        data = {
            "week": week,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updates": [u.__dict__ for u in unique],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def analyze_time_pattern(self, sessions: List[SessionMeta]) -> str:
        """
        从 session 开始时间推断时间模式。
        返回: 'morning_person' / 'night_owl' / 'flexible'
        """
        if not sessions:
            return "unknown"
        
        hour_counts = Counter()
        for s in sessions:
            try:
                dt = datetime.fromisoformat(s.started_at.replace("Z", "+00:00"))
                hour_counts[dt.hour] += 1
            except Exception:
                pass
        
        if not hour_counts:
            return "flexible"
        
        morning = sum(hour_counts.get(h, 0) for h in range(6, 12))
        afternoon = sum(hour_counts.get(h, 0) for h in range(12, 18))
        evening = sum(hour_counts.get(h, 0) for h in range(18, 24))
        
        total = len(sessions)
        if morning / total > 0.6:
            return "morning_person"
        elif evening / total > 0.5:
            return "night_owl"
        return "flexible"
    
    def analyze_engagement(self, sessions: List[SessionMeta]) -> str:
        """
        从消息数/工具调用分析 engagement 深度。
        返回: 'shallow' / 'medium' / 'deep'
        """
        if not sessions:
            return "unknown"
        
        avg_messages = sum(s.message_count for s in sessions) / len(sessions)
        avg_tools = sum(s.tool_calls for s in sessions) / len(sessions)
        avg_turns = sum(s.turns for s in sessions) / len(sessions)
        
        score = (avg_messages * 0.3 + avg_tools * 0.4 + avg_turns * 0.3)
        
        if score < 5:
            return "shallow"
        elif score < 20:
            return "medium"
        return "deep"
    
    def analyze_tool_preference(self, sessions: List[SessionMeta]) -> Dict[str, int]:
        """统计工具使用偏好"""
        all_tools = []
        for s in sessions:
            all_tools.extend(s.tools_used)
        return dict(Counter(all_tools).most_common(10))
    
    def generate_updates(self, sessions: List[SessionMeta]) -> List[SelfModelUpdate]:
        """从 session 列表生成 self_model 更新"""
        if not sessions:
            return []
        
        now = datetime.now(timezone.utc).isoformat()
        week = self._week_id()
        updates = []
        
        # 时间模式
        time_pattern = self.analyze_time_pattern(sessions)
        updates.append(SelfModelUpdate(
            timestamp=now, week=week,
            insight_type="time_pattern",
            insight_value=time_pattern,
            confidence=0.8,
            evidence=["Based on session start times"],
        ))
        
        # Engagement
        engagement = self.analyze_engagement(sessions)
        updates.append(SelfModelUpdate(
            timestamp=now, week=week,
            insight_type="engagement_depth",
            insight_value=engagement,
            confidence=0.7,
            evidence=[f"Avg messages: {sum(s.message_count for s in sessions)/len(sessions):.1f}"],
        ))
        
        # 工具偏好 top3
        tools = self.analyze_tool_preference(sessions)
        if tools:
            top3 = ", ".join(f"{k}({v})" for k, v in list(tools.items())[:3])
            updates.append(SelfModelUpdate(
                timestamp=now, week=week,
                insight_type="tool_preference",
                insight_value=top3,
                confidence=0.9,
                evidence=[f"Top tools: {top3}"],
            ))
        
        return updates
    
    def run(self, sessions: List[SessionMeta]) -> List[SelfModelUpdate]:
        """
        主入口: 收集 → 分析 → 写入。
        返回生成的更新列表。
        """
        updates = self.generate_updates(sessions)
        if not updates:
            return []
        
        week = updates[0].week
        
        # 合并历史
        history = self._load_history(week)
        existing = {(u.insight_type, u.insight_value) for u in history}
        
        # 只添加新更新
        new_updates = [u for u in updates if (u.insight_type, u.insight_value) not in existing]
        
        all_updates = history + new_updates
        self._save_updates(week, all_updates)
        
        return new_updates
    
    def read_current(self) -> List[SelfModelUpdate]:
        """读取本周 self_model 当前状态"""
        week = self._week_id()
        return self._load_history(week)


_analyzer: Optional[SelfModelAnalyzer] = None

def get_analyzer() -> SelfModelAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SelfModelAnalyzer()
    return _analyzer
