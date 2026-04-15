# -*- coding: utf-8 -*-
"""
persona_extractor.py - 人格提取器

来源: 顾庸t workspace_tools/persona_extractor.py
参考: ECC persona-forge + Hermes personality system

功能:
  从对话历史中提取人格特征:
  1. 语言风格 (formal/casual/technical)
  2. 常用词汇 (高频词/口头禅)
  3. 回复模式 (详细/简洁/列表)
  4. 情感倾向 (积极/中性/谨慎)
  5. 工具偏好
  
  输出: PersonaProfile → 可用于 SOUL.md / IDENTITY.md 更新
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class PersonaProfile:
    """人格档案"""
    style: str  # formal / casual / technical / mixed
    top_words: List[Tuple[str, int]]  # (word, count)
    avg_response_length: int
    response_pattern: str  # detailed / concise / list_mixed
    sentiment_tendency: str  # positive / neutral / cautious
    tool_preferences: List[Tuple[str, int]]
    quirks: List[str]  # 特殊习惯/口头禅


class PersonaExtractor:
    """人格提取器"""
    
    # 风格关键词
    STYLE_KEYWORDS = {
        "formal": ["请", "您", "建议", "综上所述", "因此", "值得注意的是"],
        "casual": ["哈哈", "嗯", "好", "行", "OK", "ok", "哈哈", "哦"],
        "technical": ["API", "JSON", "token", "模块", "函数", "接口", "配置"],
    }
    
    # 情感关键词
    SENTIMENT_KEYWORDS = {
        "positive": ["好", "棒", "成功", "完美", "不错", "很好", "优秀", "赞"],
        "cautious": ["注意", "小心", "风险", "确认", "不确定", "可能", "需要检查"],
    }
    
    def extract(self, messages: List[Dict[str, Any]]) -> PersonaProfile:
        """
        从消息列表提取人格档案。
        只分析 assistant/ai 角色的消息。
        """
        assistant_msgs = [
            m.get("content", "") 
            for m in messages 
            if m.get("role") in ("assistant", "ai")
        ]
        
        if not assistant_msgs:
            return PersonaProfile(
                style="unknown", top_words=[], avg_response_length=0,
                response_pattern="unknown", sentiment_tendency="neutral",
                tool_preferences=[], quirks=[],
            )
        
        # 1. 语言风格
        style = self._detect_style(assistant_msgs)
        
        # 2. 常用词汇
        top_words = self._extract_top_words(assistant_msgs, top_n=20)
        
        # 3. 回复模式
        pattern = self._detect_pattern(assistant_msgs)
        
        # 4. 情感倾向
        sentiment = self._detect_sentiment(assistant_msgs)
        
        # 5. 工具偏好
        tool_prefs = self._detect_tool_prefs(messages)
        
        # 6. 特殊习惯
        quirks = self._detect_quirks(assistant_msgs)
        
        avg_len = sum(len(m) for m in assistant_msgs) // len(assistant_msgs)
        
        return PersonaProfile(
            style=style,
            top_words=top_words,
            avg_response_length=avg_len,
            response_pattern=pattern,
            sentiment_tendency=sentiment,
            tool_preferences=tool_prefs,
            quirks=quirks,
        )
    
    def _detect_style(self, messages: List[str]) -> str:
        """检测语言风格"""
        all_text = " ".join(messages).lower()
        scores = {}
        
        for style, keywords in self.STYLE_KEYWORDS.items():
            score = sum(all_text.count(kw.lower()) for kw in keywords)
            scores[style] = score
        
        total = sum(scores.values())
        if total == 0:
            return "mixed"
        
        # 找最高分风格
        best = max(scores, key=scores.get)
        
        # 如果最高分占比 < 40%，视为 mixed
        if scores[best] / total < 0.4:
            return "mixed"
        return best
    
    def _extract_top_words(self, messages: List[str], top_n: int = 20) -> List[Tuple[str, int]]:
        """提取高频词"""
        all_text = " ".join(messages)
        
        # 中文: 按字符分割高频双字词
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', all_text)
        # 英文: 按空格分割
        english_words = re.findall(r'[a-zA-Z_]{3,}', all_text)
        
        all_words = chinese_words + english_words
        
        # 过滤停用词
        stopwords = {"的是", "在了", "不是", "这个", "那个", "一个", "什么", 
                     "可以", "没有", "已经", "但是", "然后", "所以", "因为",
                     "the", "and", "for", "are", "but", "not", "with", "this"}
        
        filtered = [w for w in all_words if w.lower() not in stopwords]
        
        return Counter(filtered).most_common(top_n)
    
    def _detect_pattern(self, messages: List[str]) -> str:
        """检测回复模式"""
        has_list = sum(1 for m in messages if re.search(r'[-*•]\s', m))
        has_paragraph = sum(1 for m in messages if len(m) > 200)
        
        list_ratio = has_list / len(messages)
        para_ratio = has_paragraph / len(messages)
        
        if list_ratio > 0.6:
            return "list_dominant"
        elif para_ratio > 0.6:
            return "detailed"
        elif list_ratio > 0.3 and para_ratio > 0.3:
            return "list_mixed"
        else:
            avg = sum(len(m) for m in messages) / len(messages)
            if avg < 100:
                return "concise"
            return "moderate"
    
    def _detect_sentiment(self, messages: List[str]) -> str:
        """检测情感倾向"""
        all_text = " ".join(messages).lower()
        scores = {}
        
        for sentiment, keywords in self.SENTIMENT_KEYWORDS.items():
            scores[sentiment] = sum(all_text.count(kw) for kw in keywords)
        
        total = sum(scores.values())
        if total == 0:
            return "neutral"
        
        best = max(scores, key=scores.get)
        if scores[best] / total < 0.4:
            return "neutral"
        return best
    
    def _detect_tool_prefs(self, messages: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
        """检测工具偏好"""
        tool_counts = Counter()
        for msg in messages:
            content = msg.get("content", "")
            tool_names = re.findall(r'(exec|read|write|edit|web_search|browser|message|web_fetch)\b', content, re.IGNORECASE)
            for t in tool_names:
                tool_counts[t.lower()] += 1
        return tool_counts.most_common(10)
    
    def _detect_quirks(self, messages: List[str]) -> List[str]:
        """检测特殊习惯"""
        quirks = []
        all_text = " ".join(messages)
        
        if all_text.count("收到") > 3:
            quirks.append("Always replies '收到' first")
        if all_text.count("✅") > 3:
            quirks.append("Uses ✅ emoji frequently")
        if all_text.count("⚠️") > 2:
            quirks.append("Uses ⚠️ warning emoji")
        if re.search(r'^(NO_REPLY|HEARTBEAT_OK)', all_text, re.MULTILINE):
            quirks.append("Uses NO_REPLY/HEARTBEAT_OK")
        
        return quirks
    
    def format_profile(self, profile: PersonaProfile) -> str:
        """格式化人格档案"""
        lines = [
            "# Persona Profile",
            f"\n## Style: {profile.style}",
            f"## Response Pattern: {profile.response_pattern}",
            f"## Sentiment: {profile.sentiment_tendency}",
            f"## Avg Response Length: {profile.avg_response_length} chars",
        ]
        
        if profile.top_words:
            words_str = ", ".join(f"{w}({c})" for w, c in profile.top_words[:10])
            lines.append(f"\n## Top Words: {words_str}")
        
        if profile.tool_preferences:
            tools_str = ", ".join(f"{t}({c})" for t, c in profile.tool_preferences[:5])
            lines.append(f"\n## Tool Preferences: {tools_str}")
        
        if profile.quirks:
            lines.append(f"\n## Quirks:")
            for q in profile.quirks:
                lines.append(f"  - {q}")
        
        return "\n".join(lines)


_extractor: Optional[PersonaExtractor] = None

def get_persona_extractor() -> PersonaExtractor:
    global _extractor
    if _extractor is None:
        _extractor = PersonaExtractor()
    return _extractor
