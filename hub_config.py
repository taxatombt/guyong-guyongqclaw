# -*- coding: utf-8 -*-
"""
hub_config.py - Hub 配置管理

来源: 顾庸t workspace_tools/hub_config.py
参考: Claude Code settings + Hermes config

功能:
  1. 集中管理所有子系统的配置
  2. 配置热加载（不重启生效）
  3. 配置验证（类型/范围/依赖）
  4. 配置导出/导入
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pathlib import Path

WORKSPACE = Path("C:/Users/yiseg/.qclaw/workspace")
CONFIG_FILE = WORKSPACE / ".hub_config.json"

# 默认配置
DEFAULT_CONFIG = {
    "evolver": {
        "max_rules": 100,
        "confidence_threshold": 0.6,
        "auto_record": True,
    },
    "memory": {
        "max_daily_entries": 200,
        "cleanup_days": 90,
        "search_depth": 30,
    },
    "budget": {
        "default_token_limit": 4000,
        "search_token_limit": 6000,
        "exec_token_limit": 2000,
    },
    "heartbeat": {
        "active_hours_start": 8,
        "active_hours_end": 22,
        "rotation_items": [
            "memory_maintenance",
            "evolver_check",
            "todo_check",
            "system_status",
        ],
    },
    "security": {
        "max_dangerous_level": "high",
        "auto_block_critical": True,
        "log_all_scans": True,
    },
    "tasks": {
        "max_concurrent": 3,
        "default_complexity": 1,
        "auto_lifecycle": True,
    },
}


class HubConfig:
    """Hub 配置管理器"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self._file = config_file or CONFIG_FILE
        self._config: Dict[str, Any] = {}
        self._load()
    
    def _load(self) -> None:
        """加载配置"""
        if self._file.exists():
            try:
                with open(self._file, encoding="utf-8") as f:
                    user_config = json.load(f)
                # 合并: default + user overrides
                self._config = self._deep_merge(DEFAULT_CONFIG, user_config)
            except (json.JSONDecodeError, TypeError):
                self._config = dict(DEFAULT_CONFIG)
        else:
            self._config = dict(DEFAULT_CONFIG)
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并配置"""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值。
        支持 dot-notation: hub_config.get("evolver.max_rules")
        """
        parts = key.split(".")
        current = self._config
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return default
            if current is None:
                return default
        return current
    
    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        parts = key.split(".")
        current = self._config
        
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
        self._save()
    
    def save(self) -> None:
        """保存配置"""
        self._save()
    
    def _save(self) -> None:
        """写入配置文件"""
        try:
            self._file.write_text(
                json.dumps(self._config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
    
    def reload(self) -> None:
        """热加载配置"""
        self._load()
    
    def export(self) -> str:
        """导出为 JSON"""
        return json.dumps(self._config, ensure_ascii=False, indent=2)
    
    def validate(self) -> Tuple[bool, List[str]]:
        """验证配置"""
        errors = []
        
        # 验证 heartbeat 小时
        start = self.get("heartbeat.active_hours_start")
        end = self.get("heartbeat.active_hours_end")
        if not isinstance(start, int) or not isinstance(end, int):
            errors.append("heartbeat.active_hours must be int")
        elif start >= end:
            errors.append("heartbeat.active_hours_start must be < end")
        
        # 验证 budget 限制
        for budget_key in ["default_token_limit", "search_token_limit", "exec_token_limit"]:
            val = self.get(f"budget.{budget_key}")
            if not isinstance(val, (int, float)) or val <= 0:
                errors.append(f"budget.{budget_key} must be positive number")
        
        return len(errors) == 0, errors
    
    def list_sections(self) -> Dict[str, List[str]]:
        """列出所有配置节和键"""
        result = {}
        for section, values in self._config.items():
            if isinstance(values, dict):
                result[section] = list(values.keys())
            else:
                result[section] = []
        return result
    
    def diff_default(self) -> Dict[str, Any]:
        """显示与默认配置的差异"""
        return self._diff_dicts(DEFAULT_CONFIG, self._config)
    
    def _diff_dicts(self, a: Dict, b: Dict) -> Dict[str, Any]:
        """比较两个字典的差异"""
        diffs = {}
        all_keys = set(list(a.keys()) + list(b.keys()))
        for key in all_keys:
            if key not in a:
                diffs[key] = {"status": "added", "value": b[key]}
            elif key not in b:
                diffs[key] = {"status": "removed", "value": a[key]}
            elif a[key] != b[key]:
                if isinstance(a[key], dict) and isinstance(b[key], dict):
                    sub_diff = self._diff_dicts(a[key], b[key])
                    if sub_diff:
                        diffs[key] = sub_diff
                else:
                    diffs[key] = {"status": "changed", "default": a[key], "current": b[key]}
        return diffs


_config: Optional[HubConfig] = None

def get_hub_config() -> HubConfig:
    global _config
    if _config is None:
        _config = HubConfig()
    return _config
