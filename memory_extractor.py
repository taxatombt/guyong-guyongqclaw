# -*- coding: utf-8 -*-
"""
memory_extractor.py - 4类记忆提取

来源: 顾庸t workspace_tools/memory_extractor.py
参考: Claude Code agentMemory.ts + Hermes memory_tool.py

4类提取:
  1. Decision    — 决策记录（选择了什么，为什么）
  2. Learning    — 学习记录（学到了什么）
  3. Pending     — 待处理（还没做的事）
  4. KeyFiles    — 关键文件（修改了哪些文件）

从对话历史中自动提取，写入 memory/日期.md
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
MEMORY_DIR = WORKSPACE / "memory"


@dataclass
class MemoryItem:
    """提取的记忆条目"""
    category: str  # decision / learning / pending / key_file
    content: str
    timestamp: str = ""
    confidence: float = 0.5
    context: str = ""


# 提取模式
EXTRACTION_PATTERNS = {
    "decision": [
        (r"(决定|选择|采用|确认)\s*[：:]\s*(.+)", 0.7),
        (r"(用|使用|选用)\s*(.+?)\s*(而|来|去)\s*(.+)", 0.5),
        (r"(不用|放弃|排除)\s*(.+?)\s*(因为|由于)\s*(.+)", 0.6),
    ],
    "learning": [
        (r"(学到|发现|意识到|注意到|发现)\s*[：:]\s*(.+)", 0.7),
        (r"(关键|核心|重要)\s*(认知|发现|洞察)\s*[：:]\s*(.+)", 0.8),
        (r"(\S+)\s*(的原理|的工作方式|是如何)\s*(.+)", 0.5),
    ],
    "pending": [
        (r"(待做|待办|TODO|还没|需要)\s*[：:]\s*(.+)", 0.7),
        (r"(下一步|接下来)\s*(要|需要|应该)\s*(.+)", 0.5),
        (r"(\[ \])\s*(.+)", 0.6),
    ],
    "key_file": [
        (r"(新建|创建|修改|更新)\s*[：:]\s*(\S+\.py)", 0.7),
        (r"(落地|完成|写入)\s*[：:]\s*(\S+\.\w+)", 0.6),
        (r"(file|path|文件)\s*[：:]\s*(\S+)", 0.4),
    ],
}


class MemoryExtractor:
    """4类记忆提取器"""
    
    def extract(self, text: str) -> List[MemoryItem]:
        """
        从文本中提取记忆条目。
        返回: 去重后的 MemoryItem 列表
        """
        items = []
        now = datetime.now(timezone.utc).isoformat()
        
        for category, patterns in EXTRACTION_PATTERNS.items():
            for pattern, confidence in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if isinstance(match, tuple):
                        content = " ".join(str(m) for m in match if m)
                    else:
                        content = str(match)
                    
                    if len(content.strip()) < 5:
                        continue
                    
                    items.append(MemoryItem(
                        category=category,
                        content=content.strip(),
                        timestamp=now,
                        confidence=confidence,
                    ))
        
        # 去重: 同类别同内容只保留最高置信度
        seen = {}
        for item in items:
            key = (item.category, item.content[:50])
            if key not in seen or item.confidence > seen[key].confidence:
                seen[key] = item
        
        return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)
    
    def extract_from_messages(self, messages: List[Dict[str, Any]]) -> List[MemoryItem]:
        """从消息列表中提取"""
        all_text = ""
        for msg in messages:
            content = msg.get("content", "")
            if content:
                all_text += f"\n{content}"
        return self.extract(all_text)
    
    def format_for_daily(self, items: List[MemoryItem]) -> str:
        """格式化为 daily note 格式"""
        if not items:
            return ""
        
        lines = []
        by_category: Dict[str, List[MemoryItem]] = {}
        for item in items:
            by_category.setdefault(item.category, []).append(item)
        
        category_labels = {
            "decision": "决策",
            "learning": "学习",
            "pending": "待办",
            "key_file": "关键文件",
        }
        
        for cat, cat_items in by_category.items():
            label = category_labels.get(cat, cat)
            lines.append(f"\n### {label}")
            for item in cat_items:
                ts = f" ({item.timestamp[:16]})" if item.timestamp else ""
                lines.append(f"- [{cat}] {item.content}{ts}")
        
        return "\n".join(lines)


_extractor: Optional[MemoryExtractor] = None

def get_extractor() -> MemoryExtractor:
    global _extractor
    if _extractor is None:
        _extractor = MemoryExtractor()
    return _extractor
