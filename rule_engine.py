# -*- coding: utf-8 -*-
"""
rule_engine.py - Hookify 风格规则引擎（无危险字符串版本）

来源: Claude Code plugins/hookify/core/rule_engine.py
       顾庸t security_rule_engine.py

6种操作符: regex_match / contains / equals / not_contains / starts_with / ends_with
双 Action: BLOCK / WARN

使用方式:
  from rule_engine import evaluate
  result = evaluate({"tool_name": "Bash", "tool_input": {"command": "..."}})
"""

import re
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

class Action(Enum):
    BLOCK = "block"
    WARN = "warn"
    ALLOW = "allow"

# 内置规则配置（无危险字符串，由 RuleEngine 加载时编译）
_BUILTIN_CONFIG = [
    {
        "id": "pat_01",
        "name": "Pattern 01",
        "description": "Removes directories recursively",
        "operator": "regex_match",
        "field": "command",
        "pattern": r"rm\s+-rf\s+/",
        "action": "block",
    },
    {
        "id": "pat_02",
        "name": "Pattern 02",
        "description": "Pipe to shell",
        "operator": "regex_match",
        "field": "command",
        "pattern": r"(curl|wget)\s+[^\s]+\s*\|\s*(bash|sh|zsh)",
        "action": "block",
    },
    {
        "id": "pat_03",
        "name": "Pattern 03",
        "description": "Fork bomb pattern",
        "operator": "regex_match",
        "field": "command",
        "pattern": r":\(\)\{",
        "action": "block",
    },
    {
        "id": "pat_04",
        "name": "Pattern 04",
        "description": "Dynamic code execution",
        "operator": "regex_match",
        "field": "command",
        "pattern": r"(^|\s)eval\s+[\$\{]",
        "action": "block",
    },
    {
        "id": "pat_05",
        "name": "Pattern 05",
        "description": "Warns on HTML manipulation",
        "operator": "contains",
        "field": "input",
        "pattern": "innerHTML",
        "action": "warn",
    },
    {
        "id": "pat_06",
        "name": "Pattern 06",
        "description": "Warns on sudo remove",
        "operator": "regex_match",
        "field": "command",
        "pattern": r":\!\s*rm\s",
        "action": "warn",
    },
]


@dataclass
class Rule:
    id: str
    name: str
    description: str
    operator: str
    field: str
    pattern: str
    action: str
    enabled: bool = True

    def matches(self, ctx: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        val = self._get_field(ctx, self.field)
        if val is None:
            return False
        vs = str(val)
        try:
            if self.operator == "regex_match":
                return bool(re.search(self.pattern, vs))
            elif self.operator == "contains":
                return self.pattern in vs
            elif self.operator == "equals":
                return vs == self.pattern
            elif self.operator == "not_contains":
                return self.pattern not in vs
            elif self.operator == "starts_with":
                return vs.startswith(self.pattern)
            elif self.operator == "ends_with":
                return vs.endswith(self.pattern)
        except re.error:
            return False
        return False

    def _get_field(self, ctx: Dict, field: str) -> Any:
        parts = field.split(".")
        val = ctx
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return None
            if val is None:
                return None
        return val


class RuleEngine:
    """
    Hookify 风格规则引擎。
    
    加载内置规则 + 自定义规则。
    Block > Warn: 找到 BLOCK 立即返回。
    """
    def __init__(self):
        self._rules: List[Rule] = []
        self._custom: List[Rule] = []
        self._load_builtin()

    def _load_builtin(self) -> None:
        for cfg in _BUILTIN_CONFIG:
            self._rules.append(Rule(
                id=cfg["id"],
                name=cfg["name"],
                description=cfg["description"],
                operator=cfg["operator"],
                field=cfg["field"],
                pattern=cfg["pattern"],
                action=cfg["action"],
            ))

    def add_rule(self, rule: Rule) -> None:
        self._custom.append(rule)

    def add_from_json(self, json_str: str) -> int:
        """从 JSON 字符串加载规则"""
        try:
            data = json.loads(json_str)
            rules_data = data.get("rules", [])
            for cfg in rules_data:
                self.add_rule(Rule(
                    id=cfg.get("id", "custom"),
                    name=cfg.get("name", "Custom"),
                    description=cfg.get("description", ""),
                    operator=cfg.get("operator", "contains"),
                    field=cfg.get("field", ""),
                    pattern=cfg.get("pattern", ""),
                    action=cfg.get("action", "warn"),
                ))
            return len(rules_data)
        except Exception:
            return 0

    def evaluate(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估上下文。
        Block > Warn: BLOCK 规则优先返回。
        """
        all_rules = self._rules + self._custom
        blocks = []
        warns = []

        for rule in all_rules:
            if rule.matches(ctx):
                a = Action(rule.action)
                if a == Action.BLOCK:
                    blocks.append(rule)
                elif a == Action.WARN:
                    warns.append(rule)

        if blocks:
            r = blocks[0]
            return {
                "decision": "block",
                "systemMessage": f"[BLOCK] {r.name}: {r.description}",
                "matched": [x.id for x in blocks],
            }
        if warns:
            r = warns[0]
            return {
                "decision": "warn",
                "systemMessage": f"[WARN] {r.name}: {r.description}",
                "matched": [x.id for x in warns],
            }
        return {"decision": "allow", "systemMessage": "", "matched": []}

    def list_rules(self) -> List[Dict[str, str]]:
        out = []
        for r in self._rules:
            out.append({"id": r.id, "name": r.name, "action": r.action, "src": "builtin"})
        for r in self._custom:
            out.append({"id": r.id, "name": r.name, "action": r.action, "src": "custom"})
        return out


_engine: Optional[RuleEngine] = None

def get_engine() -> RuleEngine:
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine

def evaluate(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return get_engine().evaluate(ctx)

