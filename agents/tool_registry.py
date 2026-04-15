# -*- coding: utf-8 -*-
"""
tool_registry.py — qclaw 工具注册表

将 qclaw 的工具（exec/read/write/glob/grep 等）映射为 tool_pipeline 的 Tool 对象。
Claude Code 原则6（模型感知）：MCP instructions / Skill 列表注入。

工具分类：
  - read_only: 只读工具（Explore/Verify/Plan 可用）
  - read_write: 读写工具（General 可用）
  - dangerous: 高危工具（需要特殊权限）
  - system: 系统工具（仅内部使用）

使用方式：
    from agents.tool_registry import get_tool_registry, lookup_tool

    registry = get_tool_registry()
    tool = registry.get("exec")
    print(tool.name, tool.category, tool.zod_schema)

    # 注入到 pipeline
    result = execute_tool_with_registry("exec", {"command": "ls"}, registry)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum, auto

from .tool_pipeline import (
    execute_pipeline,
    PipelineContext,
    RiskLevel,
    DANGEROUS_PATTERNS,
)


# ─────────────────────────────────────────────────────────────────
# 工具分类
# ─────────────────────────────────────────────────────────────────

class ToolCategory(Enum):
    READ_ONLY = auto()      # 只读工具
    READ_WRITE = auto()     # 读写工具
    DANGEROUS = auto()      # 高危工具
    SYSTEM = auto()         # 系统工具
    MESSAGE = auto()        # 消息发送
    COMPUTATION = auto()    # 计算工具


# ─────────────────────────────────────────────────────────────────
# Tool 对象
# ─────────────────────────────────────────────────────────────────

@dataclass
class Tool:
    name: str
    category: ToolCategory
    readonly: bool
    risk_level: RiskLevel

    # Zod schema（用于 validate_input 步骤）
    zod_schema: str = ""
    description: str = ""
    example_input: dict = field(default_factory=dict)

    # 权限要求
    requires_confirmation: bool = False
    confirmation_prompt: str = ""

    # 特殊行为标记
    can_stream: bool = False           # Claude Code: StreamingToolExecutor
    dangerous_pattern: Optional[str] = None  # 匹配此 regex → 直接拒绝

    def matches_dangerous_pattern(self, raw_input: Any) -> bool:
        """检查输入是否匹配危险模式"""
        if not self.dangerous_pattern:
            return False
        if isinstance(raw_input, dict):
            text = str(raw_input)
        else:
            text = str(raw_input)
        return bool(re.search(self.dangerous_pattern, text))


# ─────────────────────────────────────────────────────────────────
# qclaw 工具注册表
# ─────────────────────────────────────────────────────────────────

def _build_qclaw_registry() -> dict[str, Tool]:
    """构建 qclaw 工具注册表"""

    tools = {

        # ── 只读工具 ─────────────────────────────────────────
        "exec": Tool(
            name="exec",
            category=ToolCategory.READ_WRITE,
            readonly=False,
            risk_level=RiskLevel.HIGH,
            description="执行 Shell 命令",
            zod_schema='{"command": "string", "workdir?": "string", "timeout?": "number"}',
            example_input={"command": "git status", "timeout": 10},
            dangerous_pattern=r"rm\s+-rf\s+/|>\s*/etc/|curl\s+.*\|\s*bash|nc\s+-e\s+",
        ),

        "read": Tool(
            name="read",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="读取文件内容",
            zod_schema='{"path": "string", "offset?": "number", "limit?": "number"}',
            example_input={"path": "MEMORY.md", "limit": 100},
        ),

        "glob": Tool(
            name="glob",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="文件名模式匹配",
            zod_schema='{"pattern": "string", "workdir?": "string"}',
            example_input={"pattern": "**/*.py"},
        ),

        "grep": Tool(
            name="grep",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="正则搜索文件内容",
            zod_schema='{"pattern": "string", "path?": "string", "mode?": "string"}',
            example_input={"pattern": "TODO.*fixme", "mode": "regex"},
        ),

        "web_search": Tool(
            name="web_search",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="网页搜索",
            zod_schema='{"query": "string", "count?": "number"}',
            example_input={"query": "Python async best practices"},
        ),

        "web_fetch": Tool(
            name="web_fetch",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="获取网页内容",
            zod_schema='{"url": "string", "maxChars?": "number"}',
            example_input={"url": "https://example.com", "maxChars": 5000},
        ),

        # ── 会话/记忆工具 ───────────────────────────────────
        "sessions_list": Tool(
            name="sessions_list",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="列出活跃会话",
            zod_schema='{"limit?": "number", "activeMinutes?": "number"}',
        ),

        "sessions_history": Tool(
            name="sessions_history",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="获取会话历史",
            zod_schema='{"sessionKey": "string", "limit?": "number"}',
        ),

        "memory_search": Tool(
            name="memory_search",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="语义搜索记忆文件",
            zod_schema='{"query": "string", "maxResults?": "number"}',
        ),

        "memory_get": Tool(
            name="memory_get",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="读取记忆文件片段",
            zod_schema='{"path": "string", "from?": "number", "lines?": "number"}',
        ),

        "lcm_grep": Tool(
            name="lcm_grep",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="搜索压缩对话历史",
            zod_schema='{"pattern": "string", "scope?": "string"}',
        ),

        "lcm_expand": Tool(
            name="lcm_expand",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="展开压缩对话摘要",
            zod_schema='{"summaryIds?": "string[]", "query?": "string"}',
        ),

        "session_status": Tool(
            name="session_status",
            category=ToolCategory.READ_ONLY,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="查看会话状态",
            zod_schema='{}',
        ),

        # ── 写操作工具 ───────────────────────────────────────
        "write": Tool(
            name="write",
            category=ToolCategory.READ_WRITE,
            readonly=False,
            risk_level=RiskLevel.MEDIUM,
            description="写入文件（覆盖）",
            zod_schema='{"path": "string", "content": "string"}',
            dangerous_pattern=r"~/.ssh/|/etc/passwd",
        ),

        "edit": Tool(
            name="edit",
            category=ToolCategory.READ_WRITE,
            readonly=False,
            risk_level=RiskLevel.MEDIUM,
            description="精确编辑文件（oldText匹配替换）",
            zod_schema='{"path": "string", "oldText": "string", "newText": "string"}',
        ),

        # ── Agent/子任务工具 ─────────────────────────────────
        "sessions_spawn": Tool(
            name="sessions_spawn",
            category=ToolCategory.DANGEROUS,
            readonly=False,
            risk_level=RiskLevel.HIGH,
            description="派生子Agent会话",
            zod_schema='{"task": "string", "mode?": "string", "runtime?": "string"}',
            requires_confirmation=True,
            confirmation_prompt="派生新子Agent会话？",
        ),

        "sessions_send": Tool(
            name="sessions_send",
            category=ToolCategory.MESSAGE,
            readonly=False,
            risk_level=RiskLevel.MEDIUM,
            description="向其他会话发送消息",
            zod_schema='{"sessionKey": "string", "message": "string"}',
        ),

        "subagents": Tool(
            name="subagents",
            category=ToolCategory.READ_WRITE,
            readonly=False,
            risk_level=RiskLevel.MEDIUM,
            description="管理子Agent（列表/终止/转向）",
            zod_schema='{"action": "string", "target?": "string"}',
        ),

        # ── 消息工具 ─────────────────────────────────────────
        "message": Tool(
            name="message",
            category=ToolCategory.MESSAGE,
            readonly=False,
            risk_level=RiskLevel.HIGH,
            description="发送消息（可跨平台）",
            zod_schema='{"action": "string", "channel?": "string", "target?": "string", "message": "string"}',
            requires_confirmation=True,
            confirmation_prompt="向外发送消息？",
        ),

        "tts": Tool(
            name="tts",
            category=ToolCategory.COMPUTATION,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="文字转语音",
            zod_schema='{"text": "string"}',
        ),

        # ── 浏览器工具 ───────────────────────────────────────
        "browser": Tool(
            name="browser",
            category=ToolCategory.READ_WRITE,
            readonly=False,
            risk_level=RiskLevel.MEDIUM,
            description="控制浏览器",
            zod_schema='{"action": "string", "url?": "string"}',
            dangerous_pattern=r"--headless|--no-sandbox",
        ),

        "canvas": Tool(
            name="canvas",
            category=ToolCategory.COMPUTATION,
            readonly=True,
            risk_level=RiskLevel.SAFE,
            description="控制画布（Present/ Eval）",
            zod_schema='{"action": "string"}',
        ),

        # ── Skill/插件工具 ───────────────────────────────────
        "skillhub_install": Tool(
            name="skillhub_install",
            category=ToolCategory.DANGEROUS,
            readonly=False,
            risk_level=RiskLevel.HIGH,
            description="安装 SkillHub 技能",
            zod_schema='{"action": "string", "skillName?": "string"}',
            requires_confirmation=True,
            confirmation_prompt="安装新的技能包？",
        ),

        # ── MCP 工具（动态发现）────────────────────────────────
        # 注意：MCP 工具由 parse_mcp 步骤动态发现，此处仅为占位

    }
    return tools


# ─────────────────────────────────────────────────────────────────
# 注册表
# ─────────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    qclaw 工具注册表。

    支持：
    - 工具查询：get / lookup
    - 分类过滤：by_category / read_only / dangerous
    - 权限检查：can_use / requires_confirmation
    - 动态注册：register / register_mcp
    - 模型感知：get_skill_list() → 注入到 system prompt
    """

    def __init__(self):
        self._tools: dict[str, Tool] = _build_qclaw_registry()
        self._mcp_tools: dict[str, Tool] = {}

    # ── 查询 ──────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name) or self._mcp_tools.get(name)

    def lookup(self, name: str) -> Tool:
        """lookup：找不到则返回默认 Tool（风险最高）"""
        t = self.get(name)
        if t is None:
            return Tool(
                name=name,
                category=ToolCategory.READ_WRITE,
                readonly=False,
                risk_level=RiskLevel.HIGH,
                description=f"未知工具: {name}",
                requires_confirmation=True,
            )
        return t

    def all(self) -> dict[str, Tool]:
        return {**self._tools, **self._mcp_tools}

    # ── 过滤 ──────────────────────────────────────────────────

    def by_category(self, cat: ToolCategory) -> list[Tool]:
        return [t for t in self.all().values() if t.category == cat]

    def read_only(self) -> list[Tool]:
        return [t for t in self.all().values() if t.category == ToolCategory.READ_ONLY]

    def dangerous(self) -> list[Tool]:
        return [t for t in self.all().values() if t.category == ToolCategory.DANGEROUS]

    def requires_confirmation(self) -> list[Tool]:
        return [t for t in self.all().values() if t.requires_confirmation]

    # ── 权限检查 ───────────────────────────────────────────────

    def can_use(self, tool_name: str, role: str, readonly: bool = False) -> bool:
        """检查某角色是否可以使用某工具"""
        t = self.get(tool_name)
        if t is None:
            return False
        if readonly and not t.readonly:
            return False
        return True

    # ── 动态注册 ──────────────────────────────────────────────

    def register(self, tool: Tool) -> None:
        """注册或覆盖工具"""
        self._tools[tool.name] = tool

    def register_mcp(self, server_name: str, tool_name: str, schema: str = "") -> Tool:
        """注册 MCP 工具"""
        t = Tool(
            name=tool_name,
            category=ToolCategory.READ_ONLY,  # MCP 工具默认只读
            readonly=True,
            risk_level=RiskLevel.SAFE,
            zod_schema=schema,
            description=f"MCP [{server_name}]: {tool_name}",
        )
        self._mcp_tools[tool_name] = t
        return t

    # ── 模型感知（原则6）──────────────────────────────────────

    def get_skill_list(self) -> str:
        """生成 Skill 列表字符串，注入到 system prompt"""
        lines = ["## 可用工具列表（Tool Registry）"]
        for cat_name, cat in [
            ("只读工具（安全）", ToolCategory.READ_ONLY),
            ("读写工具", ToolCategory.READ_WRITE),
            ("消息工具", ToolCategory.MESSAGE),
            ("计算工具", ToolCategory.COMPUTATION),
            ("高危工具（需确认）", ToolCategory.DANGEROUS),
        ]:
            tools = self.by_category(cat)
            if tools:
                lines.append(f"\n### {cat_name}")
                for t in tools:
                    confirm = " [⚠️需确认]" if t.requires_confirmation else ""
                    lines.append(f"- `{t.name}`: {t.description}{confirm}")
        return "\n".join(lines)

    def get_mcp_skill_list(self) -> str:
        """生成 MCP 工具列表"""
        if not self._mcp_tools:
            return "（无 MCP 工具）"
        lines = ["## MCP 工具"]
        for t in self._mcp_tools.values():
            lines.append(f"- `{t.name}`: {t.description}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_tool_registry() -> None:
    """重置注册表（测试用）"""
    global _registry
    _registry = None


# ─────────────────────────────────────────────────────────────────
# 便捷包装
# ─────────────────────────────────────────────────────────────────

def execute_tool_with_registry(
    tool_name: str,
    tool_input: dict,
    registry: Optional[ToolRegistry] = None,
    **kwargs,
):
    """
    用工具注册表执行工具。
    内部调用 tool_pipeline.execute_pipeline。
    """
    if registry is None:
        registry = get_tool_registry()

    tool = registry.lookup(tool_name)

    # 危险模式检查
    if tool.matches_dangerous_pattern(tool_input):
        from .tool_pipeline import PipelineResult
        return PipelineResult(
            success=False,
            rejected=True,
            risk_level=RiskLevel.CRITICAL,
            steps=[],
            warnings=[f"Dangerous pattern matched for {tool_name}: {tool.dangerous_pattern}"],
            error="输入匹配危险模式，已拒绝执行",
        )

    ctx = PipelineContext(tool_name=tool_name, tool_input=tool_input, **kwargs)
    return execute_pipeline(ctx)
