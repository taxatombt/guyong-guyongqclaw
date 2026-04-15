# -*- coding: utf-8 -*-
"""
skill_router.py - Skill 路由（pre-task 强制检查）

来源: 顾庸t workspace_tools/skill_router.py
参考: Claude Code skill injection + ECC skill-ranking

核心功能:
  1. 任务来了 → 先分析任务特征
  2. 匹配最合适的 Skill
  3. 返回 Skill 名称 + 触发原因
  4. 如果没有匹配 → 返回 None（不强制）

路由策略:
  - 关键词匹配（最高优先级）
  - 正则模式匹配
  - 语义类别映射
  - fallback: 通用路由
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")


@dataclass
class SkillRoute:
    """路由结果"""
    skill_name: str
    confidence: float  # 0.0 ~ 1.0
    reason: str
    trigger: str  # keyword / regex / category


@dataclass
class RouteRule:
    """路由规则"""
    skill_name: str
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    priority: int = 0  # 越高越优先


# ─── 内置路由表 ─────────────────────────────────────

BUILTIN_RULES: List[RouteRule] = [
    # 文档处理
    RouteRule("pdf", keywords=["pdf", "PDF", ".pdf"], priority=10),
    RouteRule("docx", keywords=["word", "docx", ".docx", "Word文档"], priority=10),
    RouteRule("pptx", keywords=["ppt", "pptx", ".pptx", "幻灯片", "演示"], priority=10),
    RouteRule("xlsx", keywords=["excel", "xlsx", ".xlsx", "表格", "spreadsheet"], priority=10),
    
    # 设计
    RouteRule("frontend-design", keywords=["网页", "前端", "UI", "界面", "landing page", 
              "dashboard", "website", "HTML", "CSS"], priority=8),
    RouteRule("canvas-design", keywords=["海报", "设计", "poster", "art", "banner"], priority=8),
    
    # 搜索
    RouteRule("multi-search-engine", keywords=["搜索", "查一下", "找一下", "搜搜"], priority=7),
    RouteRule("agent-reach", keywords=["小红书", "抖音", "微博", "推特", "Twitter",
              "B站", "bilibili", "Reddit", "LinkedIn"], priority=7),
    
    # 天气
    RouteRule("weather-advisor", keywords=["天气", "气温", "下雨", "穿什么", "出行"], priority=9),
    
    # 新闻
    RouteRule("news-summary", keywords=["新闻", "头条", "热点", "时政"], priority=7),
    RouteRule("tech-news-digest", keywords=["科技新闻", "tech news", "AI新闻"], priority=7),
    
    # 邮件
    RouteRule("email-skill", keywords=["邮箱", "邮件", "email", "发邮件"], priority=8),
    
    # 文档平台
    RouteRule("tencent-docs", keywords=["腾讯文档", "docs.qq", "在线文档"], priority=8),
    RouteRule("kdocs", keywords=["金山文档", "WPS", "kdocs", "365.kdocs"], priority=8),
    
    # 金融
    RouteRule("neodata-financial-search", keywords=["股票", "基金", "行情", "K线",
              "财报", "A股"], priority=8),
    
    # 知识库
    RouteRule("ima-skill", keywords=["知识库", "笔记", "备忘", "记一下", "收藏"], priority=7),
    
    # 开发
    RouteRule("qclaw-env", keywords=["安装", "配置", "环境", "install", "setup"], priority=6),
    RouteRule("qclaw-cron-skill", keywords=["定时", "提醒", "闹钟", "每天", "周期",
              "cron", "remind", "timer"], priority=8),
    
    # 内容创作
    RouteRule("content-factory", keywords=["文案", "内容创作", "copywriting", "写文案"], priority=7),
    
    # 会议
    RouteRule("tencent-meeting-mcp", keywords=["腾讯会议", "会议", "meeting"], priority=7),
    
    # 腾讯问卷
    RouteRule("tencent-survey", keywords=["问卷", "调查", "投票", "wj.qq"], priority=7),
    
    # 桌面整理
    RouteRule("file-skill", keywords=["桌面整理", "文件整理", "清理桌面", "排列桌面"], priority=8),
]


class SkillRouter:
    """Skill 路由器"""
    
    def __init__(self, custom_rules: Optional[List[RouteRule]] = None):
        self._rules = list(BUILTIN_RULES)
        if custom_rules:
            self._rules.extend(custom_rules)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        self._regex_cache: Dict[str, re.Pattern] = {}
    
    def _get_regex(self, pattern: str) -> re.Pattern:
        if pattern not in self._regex_cache:
            self._regex_cache[pattern] = re.compile(pattern, re.IGNORECASE)
        return self._regex_cache[pattern]
    
    def route(self, task_description: str) -> List[SkillRoute]:
        """
        路由任务描述到最合适的 Skill。
        返回: 按置信度排序的 SkillRoute 列表
        """
        query = task_description.lower()
        results: List[SkillRoute] = []
        
        for rule in self._rules:
            score = 0.0
            trigger = ""
            
            # 关键词匹配
            for kw in rule.keywords:
                if kw.lower() in query:
                    score += 0.3
                    trigger = f"keyword: {kw}"
            
            # 正则匹配
            for pat in rule.patterns:
                if self._get_regex(pat).search(query):
                    score += 0.25
                    trigger = f"regex: {pat}"
            
            # 类别匹配（需要在 description 中出现类别相关词）
            for cat in rule.categories:
                if cat.lower() in query:
                    score += 0.2
                    trigger = f"category: {cat}"
            
            if score > 0:
                confidence = min(1.0, score)
                results.append(SkillRoute(
                    skill_name=rule.skill_name,
                    confidence=confidence,
                    reason=f"Matched {trigger}",
                    trigger=trigger,
                ))
        
        # 去重（同 skill 保留最高分）
        best = {}
        for r in results:
            if r.skill_name not in best or r.confidence > best[r.skill_name].confidence:
                best[r.skill_name] = r
        
        return sorted(best.values(), key=lambda x: x.confidence, reverse=True)
    
    def best_match(self, task_description: str, threshold: float = 0.3) -> Optional[SkillRoute]:
        """返回最佳匹配（超过阈值）"""
        routes = self.route(task_description)
        if routes and routes[0].confidence >= threshold:
            return routes[0]
        return None
    
    def add_rule(self, rule: RouteRule) -> None:
        """添加自定义规则"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
    
    def list_rules(self) -> List[str]:
        """列出所有已注册的 skill 名称"""
        seen = set()
        result = []
        for r in self._rules:
            if r.skill_name not in seen:
                seen.add(r.skill_name)
                result.append(r.skill_name)
        return result


_router: Optional[SkillRouter] = None

def get_router() -> SkillRouter:
    global _router
    if _router is None:
        _router = SkillRouter()
    return _router
