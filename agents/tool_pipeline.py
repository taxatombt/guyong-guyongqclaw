# -*- coding: utf-8 -*-
"""
agents/tool_pipeline.py — 工具执行管道

Claude Code 原则落地：
- 原则3：工具调用要有治理 — 15步执行管道
- 原则5：安全层互不绕过 — 三层防护（SpeculativeClassifier + HookPolicy + PermissionDecision）
- 原则7：产品化在于第二天 — 完整cleanup chain

结构：
- PipelineContext: 执行上下文
- ToolResult / PipelineResult: 执行结果
- HookResult: Hook执行结果（新增：FailedAbort级联）
- PromptDecision: 弹窗决策结果（新增：真正Prompt机制）
- execute_pipeline(): 主管道
- 15步执行流程

v2.0 更新（codex execpolicy 启发）：
- justification 字段：拒绝时说明"为什么这条规则存在"
- PromptDecision：真正的 ASK 弹窗机制（callback驱动）
- FailedAbort：Hook可级联中断操作
"""

from __future__ import annotations
import json
import time
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional, Callable

# ─── 枚举定义 ──────────────────────────────────────────────

class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    MODIFY = "modify"  # 修改输入后允许

class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class PipelinePhase(Enum):
    FIND_TOOL = "find_tool"
    VALIDATE = "validate"
    CLASSIFY = "classify"
    PRE_HOOK = "pre_hook"
    PERMISSION = "permission"
    EXECUTE = "execute"
    RECORD = "record"
    POST_HOOK = "post_hook"
    PROCESS = "process"
    CLEANUP = "cleanup"


# ─── Codex ExecPolicy 启发：Hook结果枚举（v2.0新增）───────────
# 对应 codex hooks/types.rs: HookResult { Success, FailedContinue, FailedAbort }

class HookResult(Enum):
    """Hook执行的三种结果（来自 codex hooks 系统）"""
    SUCCESS = "success"                           # 成功，继续下个hook
    FAILED_CONTINUE = "failed_continue"          # 失败，但继续执行其他hook和操作
    FAILED_ABORT = "failed_abort"                # ⭐ 失败，中断操作（级联中断）


@dataclass
class HookResponse:
    """
    单个Hook的执行响应
    
    v2.2 增强（参考 Codex hooks/types.rs HookPayload）：
    - hook_event: 完整事件类型（AfterAgent / AfterToolUse）
    - tool_name / tool_input: 工具上下文
    - session_id / cwd / triggered_at：完整执行上下文
    - duration_ms / output_preview：执行详情
    - mutating：是否修改状态
    """
    hook_name: str
    result: HookResult
    error: Optional[str] = None
    modified_input: Optional[dict] = None
    
    # v2.2 新增（参考 Codex HookPayload.hook_event）
    hook_event: str = ""                   # "after_agent" | "after_tool_use" | "pre_tool_use"
    tool_name: str = ""                    # 工具名
    tool_input: Optional[dict] = None      # 工具输入参数
    
    # v2.1 新增（来自 Codex HookPayload）
    session_id: str = ""                   # 会话ID
    cwd: str = ""                          # 当前工作目录
    triggered_at: str = ""                 # 触发时间（ISO格式）
    duration_ms: float = 0.0               # 执行耗时
    output_preview: str = ""               # 输出前200字符
    mutating: bool = False                 # 是否修改状态


# ─── Codex Hooks Dispatcher 启发：泛型分发 Pipeline（v2.2）──

@dataclass
class HookOutcome:
    """
    Hook 执行结果（泛型分发管道用）
    参考 Codex hooks/engine/dispatcher.rs 的 ParsedHandler<T>
    
    v2.2: 替代简单的 HookResponse，用于 HookDispatcher 泛型 pipeline
    """
    hook_name: str
    status: str = "success"          # "success" | "failed_continue" | "failed_abort" | "unsupported"
    continue_processing: bool = True  # 是否继续后续 hooks
    suppress_output: bool = False    # 是否压制输出
    stop_reason: Optional[str] = None # 中断原因
    system_message: Optional[str] = None  # 系统消息
    modified_input: Optional[dict] = None # Hook 提议的修改版本
    output_preview: str = ""          # 输出前200字符
    duration_ms: float = 0.0          # 执行耗时


@dataclass
class ConfiguredHandler:
    """
    一个已配置的 hook 处理器
    参考 Codex hooks/engine/dispatcher.rs 的 ConfiguredHandler
    
    v2.2: 支持正则 matcher + event_type 二维过滤
    """
    name: str
    event_type: str                   # "pre_tool_use" / "post_tool_use" / "after_agent"
    matcher: Optional[str] = None     # 正则表达式（None="*" 匹配所有）
    command: Optional[str] = None     # 外部命令（与 hook_fn 二选一）
    timeout: int = 30                # 超时秒数
    display_order: int = 0            # 执行顺序（数字越小越先）
    hook_fn: Optional[Callable] = None  # 函数式 hook（与 command 二选一）
    
    def matches(self, event_type: str, tool_name: str) -> bool:
        """两维过滤：event_type 完全匹配 + matcher 正则匹配"""
        if self.event_type != event_type:
            return False
        if self.matcher is None or self.matcher == "*":
            return True
        import re
        try:
            return bool(re.match(self.matcher, tool_name))
        except re.error:
            return True  # 无效正则则放行


class HookDispatcher:
    """
    泛型分发器 — 所有 hook 类型共用同一 pipeline
    参考 Codex hooks/engine/dispatcher.rs 的 execute_handlers<T> 模式
    
    v2.2: 新增 hook 类型只需定义 parse 函数，无需改 dispatch 逻辑
    
    使用方式：
        dispatcher = HookDispatcher(cwd=ctx.cwd)
        dispatcher.register(ConfiguredHandler(name="security", event_type="pre_tool_use",
                                              matcher="curl.*", hook_fn=security_check))
        outcomes = await dispatcher.dispatch("pre_tool_use", "curl http://evil.com", input_json)
    """
    
    def __init__(self, cwd: str = "", session_id: str = ""):
        self.cwd = cwd
        self.session_id = session_id
        self._handlers: list[ConfiguredHandler] = []
    
    def register(self, handler: ConfiguredHandler) -> None:
        """注册一个 hook 处理器"""
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.display_order)
    
    def select_handlers(self, event_type: str, tool_name: str) -> list[ConfiguredHandler]:
        """两维过滤：event_type 完全匹配 + matcher 正则匹配"""
        return [h for h in self._handlers if h.matches(event_type, tool_name)]
    
    def preview(self, event_type: str, tool_name: str) -> list[str]:
        """dry-run：列出会触发哪些 handler（不实际执行）"""
        return [h.name for h in self.select_handlers(event_type, tool_name)]
    
    def parse_pre_tool_use(self, handler: ConfiguredHandler, 
                          stdout: str, stderr: str, exit_code: int) -> HookOutcome:
        """解析 PreToolUse hook 输出（双版本协议兼容）"""
        import json
        if not stdout.strip():
            # 非 JSON 输出 fallback
            if stderr:
                return HookOutcome(handler.name, "failed_continue", 
                                 stop_reason=stderr[:200], continue_processing=True)
            return HookOutcome(handler.name, "success", continue_processing=True)
        
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return HookOutcome(handler.name, "failed_continue",
                             stop_reason=f"invalid JSON: {stdout[:100]}", continue_processing=True)
        
        # modern: permissionDecision
        if "permissionDecision" in data or "hookSpecificOutput" in data:
            inner = data.get("hookSpecificOutput", data)
            decision = inner.get("permissionDecision", "")
            if decision == "deny":
                return HookOutcome(
                    handler.name, "failed_abort",
                    stop_reason=inner.get("permissionDecisionReason"),
                    system_message=inner.get("systemMessage"),
                    continue_processing=False,
                )
            return HookOutcome(handler.name, "success", 
                             system_message=inner.get("systemMessage"),
                             continue_processing=True)
        
        # universal: continue / suppressOutput
        if "continue" in data or "suppressOutput" in data:
            return HookOutcome(
                handler.name, "success",
                continue_processing=data.get("continue", True),
                suppress_output=data.get("suppressOutput", False),
                system_message=data.get("systemMessage"),
            )
        
        # legacy: decision: block
        if "decision" in data:
            if data["decision"] == "block":
                return HookOutcome(handler.name, "failed_abort",
                                 stop_reason=data.get("reason"), continue_processing=False)
            return HookOutcome(handler.name, "success", continue_processing=True)
        
        # unsupported 字段 → 不阻断
        return HookOutcome(handler.name, "unsupported", continue_processing=True)
    
    def parse_post_tool_use(self, handler: ConfiguredHandler,
                            stdout: str, stderr: str, exit_code: int) -> HookOutcome:
        """解析 PostToolUse hook 输出"""
        return self.parse_pre_tool_use(handler, stdout, stderr, exit_code)
    
    async def dispatch(self, event_type: str, tool_name: str,
                      input_json: str, turn_id: Optional[str] = None) -> list[HookOutcome]:
        """
        泛型分发 — 所有事件类型共用
        参考 Codex execute_handlers<T>：
        新增事件类型只需定义 parse 函数，无需改 dispatch 逻辑
        """
        handlers = self.select_handlers(event_type, tool_name)
        if not handlers:
            return []
        
        results = []
        for h in handlers:
            outcome = await self._execute_single(h, input_json, turn_id)
            results.append(outcome)
            # ⭐ FailedAbort: 立即停止后续 handlers
            if outcome.status == "failed_abort":
                break
        return results
    
    async def _execute_single(self, handler: ConfiguredHandler,
                               input_json: str, turn_id: Optional[str]) -> HookOutcome:
        """执行单个 handler 并解析输出"""
        import asyncio
        import time
        
        if handler.hook_fn:
            # 函数式 hook（同步调用）
            start = time.perf_counter()
            try:
                result = handler.hook_fn(tool_name=tool_name, input_json=input_json, 
                                       turn_id=turn_id, cwd=self.cwd)
                duration = (time.perf_counter() - start) * 1000
                # 转换函数返回为 HookOutcome
                if isinstance(result, dict):
                    parsed = self.parse_pre_tool_use(handler, json.dumps(result), "", 0)
                    parsed.duration_ms = duration
                    return parsed
                elif result and result.get("status") == "abort":
                    return HookOutcome(handler.name, "failed_abort",
                                     stop_reason=result.get("error"), duration_ms=duration)
                return HookOutcome(handler.name, "success", duration_ms=duration)
            except Exception as e:
                duration = (time.perf_counter() - start) * 1000
                return HookOutcome(handler.name, "failed_continue",
                                 stop_reason=str(e), duration_ms=duration)
        
        # 外部命令 hook（异步执行）
        import subprocess
        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_shell(
                f'{handler.command} {input_json}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=handler.timeout
            )
        except asyncio.TimeoutError:
            return HookOutcome(handler.name, "failed_continue",
                             stop_reason=f"timeout {handler.timeout}s",
                             duration_ms=(time.perf_counter() - start) * 1000)
        except Exception as e:
            return HookOutcome(handler.name, "failed_continue",
                             stop_reason=str(e),
                             duration_ms=(time.perf_counter() - start) * 1000)
        
        stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
        stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
        duration = (time.perf_counter() - start) * 1000
        
        if event_type in ("pre_tool_use",):
            return self.parse_pre_tool_use(handler, stdout, stderr, proc.returncode)
        else:
            return self.parse_post_tool_use(handler, stdout, stderr, proc.returncode)


# ─── Prompt 弹窗机制（v2.0新增）─────────────────────────────

class PromptDecision(Enum):
    """用户对ASK弹窗的决策"""
    ALLOW = "allow"      # 用户允许
    DENY = "deny"        # 用户拒绝
    CANCEL = "cancel"    # 用户取消（等同于DENY但保留reason）


@dataclass
class PromptRequest:
    """弹窗请求结构（发给用户）"""
    tool_name: str
    risk_level: RiskLevel
    justification: str          # 为什么这条规则要弹窗
    command: Optional[str] = None
    modified_input: Optional[dict] = None  # Hook提议的修改版本
    timeout_ms: int = 30000     # 默认30秒超时


# ─── 危险模式库（含 justification）───────────────────────────
# v2.0: 每个模式现在都有 justification 字段

DANGEROUS_PATTERNS = [
    # 数据销毁
    (r"rm\s+-rf\s+/",        RiskLevel.CRITICAL, "递归删除根目录",           "安全策略：禁止递归删除根目录，可能导致系统完全不可用"),
    (r"rm\s+-rf\s+/\w+",     RiskLevel.HIGH,     "递归删除系统目录",         "安全策略：禁止递归删除系统目录，可能破坏系统文件"),
    (r"del\s+/[sfq]\s+",     RiskLevel.HIGH,     "Windows强制删除",          "安全策略：Windows强制删除可能永久丢失数据"),
    (r"Format-Volume",        RiskLevel.CRITICAL, "格式化卷",                "安全策略：格式化将清除磁盘所有数据"),
    # 网络危险
    (r"curl.*--insecure.*\|.*bash", RiskLevel.CRITICAL, "下载并执行脚本",  "安全策略：下载并执行未知脚本是典型入侵路径"),
    (r"wget.*\|.*bash",       RiskLevel.CRITICAL, "下载并执行脚本",          "安全策略：wget+bash等同于直接执行任意代码"),
    (r"nc\s+-e\s+",           RiskLevel.CRITICAL, "反向shell",              "安全策略：反向shell建立远程控制通道"),
    (r"rm\s+/.*ssh/.*",       RiskLevel.HIGH,     "删除SSH配置",             "安全策略：删除SSH配置会锁定远程访问"),
    # 权限提升
    (r"sudo\s+.*--no-check",  RiskLevel.MEDIUM,   "无密码sudo",              "安全策略：无密码sudo绕过了权限验证"),
    (r"chmod\s+777",          RiskLevel.HIGH,     "完全权限设置",            "安全策略：777权限使文件对所有人可读可写可执行"),
    (r"chmod\s+4755",         RiskLevel.HIGH,     "SUID位设置",              "安全策略：SUID位允许以root身份执行"),
    # 持久化
    (r"crontab\s+.*-e",       RiskLevel.MEDIUM,   "修改定时任务",            "安全策略：定时任务可建立持久化执行"),
    (r"systemctl\s+enable",   RiskLevel.MEDIUM,   "启用服务",                "安全策略：新建服务建立持久化"),
    (r"launchctl\s+load",     RiskLevel.MEDIUM,   "加载launchd",             "安全策略：launchd建立macOS持久化"),
    # Git危险
    (r"git\s+push\s+--force", RiskLevel.MEDIUM,   "强制推送",               "操作风险：强制推送会覆盖远程历史"),
    (r"git\s+push\s+--all",   RiskLevel.LOW,      "推送所有分支",           "操作风险：推送所有分支可能包含未审查代码"),
    (r"git\s+filter-branch",  RiskLevel.MEDIUM,   "分支过滤",               "操作风险：filter-branch会修改本地历史"),
    # 进程终止
    (r"kill\s+-9\s+1\b",     RiskLevel.CRITICAL,  "杀死init进程",           "安全策略：杀死PID 1会导致系统关机"),
    (r"taskkill.*/F",         RiskLevel.MEDIUM,   "强制终止进程",            "操作风险：强制终止进程可能丢失未保存数据"),
    # 文件覆盖
    (r">\s*/etc/",            RiskLevel.HIGH,     "覆盖系统文件",           "安全策略：覆盖系统文件可能破坏系统完整性"),
    (r">\s*/boot/",           RiskLevel.HIGH,     "覆盖启动文件",           "安全策略：覆盖boot文件可能导致系统无法启动"),
    (r"\|\s*tee\s+.*/etc/",   RiskLevel.HIGH,     "写系统文件",             "安全策略：tee写入系统文件绕过了编辑器保护"),
    # 权限修改
    (r"chown\s+",             RiskLevel.MEDIUM,   "修改文件所有者",         "操作风险：修改所有权可能影响其他用户访问"),
    (r"chmod\s+[02]",        RiskLevel.MEDIUM,   "移除所有权限",           "操作风险：移除执行权限可能导致程序无法运行"),
]


# Read-only 安全命令
SAFE_COMMANDS = {
    "ls", "pwd", "git", "cat", "grep", "find", "head", "tail", "wc",
    "stat", "file", "which", "whereis", "type", "echo", "date", "whoami",
    "uname", "id", "ps", "netstat", "ss", "df", "du", "free", "top",
    "git status", "git log", "git diff", "git show", "git branch",
    "git remote", "git config --list", "git stash list",
}

SAFE_PREFIXES = (
    "ls ", "git status", "git log", "git diff", "git show", "git branch",
    "git remote", "git config", "git stash", "git reflog",
    "cat ", "head ", "tail ", "wc ", "grep ", "find . -name",
    "pwd", "echo ", "date ", "whoami ", "uname ", "id ",
    "ps ", "df ", "du ", "free ", "stat ", "file ",
    "node -e \"console.log", "python -c \"import",
    "npm list", "pip list", "pip show",
)


# ─── 数据模型 ──────────────────────────────────────────────

@dataclass
class PipelineContext:
    """工具执行上下文"""
    tool_name: str
    tool_input: dict[str, Any]
    user_id: str = "default"
    session_id: str = ""
    
    # 工具查找
    tool_object: Optional[Any] = None
    parsed_mcp: Optional[dict] = None
    validated_input: Optional[dict] = None
    risk_level: RiskLevel = RiskLevel.SAFE
    
    # v2.0: justification — 拒绝/弹窗时的理由
    justification: Optional[str] = None
    
    # Hook 层
    pre_hook_results: list[HookResponse] = field(default_factory=list)
    permission_override: Optional[PermissionBehavior] = None
    modified_input: Optional[dict] = None
    
    # v2.0: Prompt 机制
    prompt_callback: Optional[Callable[[PromptRequest], PromptDecision]] = None
    
    # v2.0: FailedAbort 级联中断
    abort_requested: bool = False
    abort_reason: Optional[str] = None
    
    # 执行结果
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    # 日志
    steps_executed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    # v2.0: Prompt 机制
    prompt_decision: Optional[PromptDecision] = None
    
    # 外部依赖
    tool_registry: Optional[Callable] = None
    hook_registry: Optional[Callable] = None
    permission_rules: Optional[Callable] = None
    analytics_callback: Optional[Callable] = None


@dataclass
class PipelineResult:
    """
    工具执行结果
    
    v2.0 新增字段：
    - justification: 为什么这条规则存在（供用户/审核用）
    - hook_responses: 所有Hook的执行结果
    - prompt_decision: ASK时的用户决策
    """
    success: bool
    output: Any = None
    error: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.SAFE
    permission_behavior: PermissionBehavior = PermissionBehavior.ALLOW
    duration_ms: float = 0.0
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    modified_input: Optional[dict] = None
    rejected: bool = False
    rejected_reason: Optional[str] = None
    
    # v2.0 新增
    justification: Optional[str] = None       # ⭐ 为什么这条规则存在
    hook_responses: list[HookResponse] = field(default_factory=list)
    prompt_decision: Optional[PromptDecision] = None  # ASK时的用户决策


# 向后兼容别名
ToolResult = PipelineResult


# ─── PipelineStep ─────────────────────────────────────────

@dataclass
class PipelineStep:
    name: str
    fn: Callable
    required: bool = True
    phase: PipelinePhase = PipelinePhase.EXECUTE
    description: str = ""

    def __call__(self, ctx: PipelineContext) -> bool:
        return self.fn(ctx)


# ─── 第1步：找工具 ─────────────────────────────────────────

def _find_tool(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("find_tool")
    
    name = ctx.tool_name
    BUILTIN_TOOLS = {
        "exec": "ExecTool", "read": "ReadTool", "write": "WriteTool",
        "edit": "EditTool", "glob": "GlobTool", "grep": "GrepTool",
        "sessions_list": "SessionsListTool", "sessions_history": "SessionsHistoryTool",
        "sessions_send": "SessionsSendTool", "sessions_spawn": "SessionsSpawnTool",
        "subagents": "SubagentsTool", "memory_search": "MemorySearchTool",
        "memory_get": "MemoryGetTool", "lcm_grep": "LcmGrepTool",
        "lcm_expand": "LcmExpandTool", "lcm_expand_query": "LcmExpandQueryTool",
        "message": "MessageTool", "tts": "TtsTool",
        "web_search": "WebSearchTool", "web_fetch": "WebFetchTool",
        "session_status": "SessionStatusTool",
    }
    
    if name in BUILTIN_TOOLS:
        ctx.tool_object = {"type": BUILTIN_TOOLS[name], "builtin": True}
        return True
    
    if ctx.tool_registry:
        try:
            tool = ctx.tool_registry(name)
            if tool:
                ctx.tool_object = tool
                return True
        except Exception:
            pass
    
    ctx.error = f"Tool not found: {name}"
    ctx.warnings.append(f"Unknown tool: {name}")
    return False


# ─── 第2步：解析MCP元数据 ─────────────────────────────────

def _parse_mcp(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("parse_mcp")
    tool_name = ctx.tool_name
    if "::" in tool_name:
        server, local_name = tool_name.split("::", 1)
        ctx.parsed_mcp = {"server": server, "local_name": local_name, "is_mcp": True}
        ctx.warnings.append(f"MCP tool from server: {server}")
        return True
    ctx.parsed_mcp = {"is_mcp": False}
    return True


# ─── 第3步：Zod Schema校验（含 justification捕获）───────────

def _validate_input(ctx: PipelineContext) -> bool:
    """
    步骤3: 对工具输入做第一道校验
    
    v2.0: 检测危险模式时，同时捕获 justification（为什么这条规则存在）
    v2.3: 对记忆文件执行安全扫描（memory_guard 12威胁+隐形字符）
    """
    ctx.steps_executed.append("validate_input")
    
    inp = ctx.tool_input
    if not isinstance(inp, dict):
        ctx.error = f"Invalid input type: {type(inp)}"
        return False
    
    if "command" in inp:
        cmd = str(inp["command"])
        # v2.0: 捕获 matched pattern 的 justification
        for pattern, level, desc, justification in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                ctx.risk_level = level
                ctx.justification = justification  # ⭐ 捕获理由
                ctx.warnings.append(f"Dangerous pattern: {desc} — {justification}")
    
    if "exec" == ctx.tool_name and "command" in inp:
        cmd = str(inp["command"]).strip()
        is_safe = cmd in SAFE_COMMANDS or any(cmd.startswith(p) for p in SAFE_PREFIXES)
        if not is_safe and ctx.risk_level in (RiskLevel.SAFE, RiskLevel.LOW):
            ctx.risk_level = RiskLevel.MEDIUM
            ctx.warnings.append(f"Non-read-only command: {cmd[:50]}")
    
    ctx.validated_input = inp
    return True
def _speculative_classify(ctx: PipelineContext) -> bool:
    """
    步骤4: 在权限决策之前启动预测性风险分类
    
    v2.0: 危险模式匹配时同步更新 justification
    """
    ctx.steps_executed.append("speculative_classify")
    
    if ctx.tool_name != "exec":
        ctx.steps_executed.append("speculative_classify.skip_non_bash")
        return True
    

# --- Step 5: PreToolUse Hooks (FailedAbort cascade) ---

def _run_pre_hooks(ctx: PipelineContext) -> bool:
    """Step 5: Run all registered pre-hooks (v2.0 FailedAbort cascade)"""
    ctx.steps_executed.append("pre_hooks")
    if not ctx.hook_registry:
        ctx.steps_executed.append("pre_hooks.skip_no_registry")
        return True
    pre_hooks = ctx.hook_registry("pre_tool_use", ctx.tool_name)
    if not pre_hooks:
        ctx.steps_executed.append("pre_hooks.skip_no_match")
        return True
    input_json = json.dumps({"tool": ctx.tool_name, "input": ctx.tool_input})
    for hook_fn in pre_hooks:
        try:
            start = time.perf_counter()
            result = hook_fn(ctx.tool_name, ctx.tool_input, ctx)
            duration = (time.perf_counter() - start) * 1000
            if isinstance(result, dict):
                hr = _parse_hook_result(hook_fn.__name__, result)
                hr.duration_ms = duration
                ctx.pre_hook_results.append(hr)
                if hr.result == HookResult.FAILED_ABORT:
                    ctx.abort_requested = True
                    ctx.error = f"ABORT: {hook_fn.__name__}: {hr.error or 'unknown'}"
                    ctx.steps_executed.append("pre_hooks.abort")
                    return False
            else:
                ctx.steps_executed.append(f"pre_hooks.{hook_fn.__name__}.unknown_result")
        except Exception as e:
            ctx.pre_hook_results.append(HookResponse(
                hook_name=hook_fn.__name__,
                result=HookResult.FAILED_CONTINUE,
                error=str(e),
            ))
            ctx.warnings.append(f"Hook {hook_fn.__name__} failed: {e}")
    ctx.steps_executed.append("pre_hooks.complete")
    return True

    cmd = ctx.validated_input.get("command", "")
    
    risk_scores = {RiskLevel.SAFE: 0, RiskLevel.LOW: 1, RiskLevel.MEDIUM: 3,
                   RiskLevel.HIGH: 6, RiskLevel.CRITICAL: 10}
    
    for pattern, level, desc, justification in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            score = risk_scores.get(level, 0)
            if score >= 10:
                ctx.risk_level = RiskLevel.CRITICAL
                ctx.justification = justification  # ⭐ 同步更新
                ctx.warnings.append(f"SPECULATIVE CRITICAL: {desc}")
            elif score >= 6:
                ctx.risk_level = RiskLevel.HIGH
                ctx.justification = justification
                ctx.warnings.append(f"SPECULATIVE HIGH: {desc}")
    
    return True


# ─── 第5步：PreToolUse Hooks（含 FailedAbort级联）──────────

    ctx.steps_executed.append("pre_hooks")
    
    # ⭐ v2.3: 内置安全扫描（对 Write/Edit/MultiEdit 工具）
    
    if not ctx.hook_registry:
        ctx.steps_executed.append("pre_hooks.skip_no_registry")
        return True
    
    try:
        hooks = ctx.hook_registry("PreToolUse", ctx.tool_name)
        for hook_fn in hooks:
            # 跳过已中断的hook
            if ctx.abort_requested:
                ctx.warnings.append(f"PreHook skipped due to prior abort: {ctx.abort_reason}")
                break
            
            try:
                result = hook_fn(ctx.tool_name, ctx.validated_input, ctx)
                hr = _parse_hook_result(hook_fn.__name__, result)
                ctx.pre_hook_results.append(hr)
                
                # ⭐ FailedAbort: 立即中断
                if hr.result == HookResult.FAILED_ABORT:
                    ctx.abort_requested = True
                    ctx.abort_reason = hr.error or f"Hook {hook_fn.__name__} requested abort"
                    ctx.warnings.append(f"⭐ ABORT requested by hook: {hook_fn.__name__}")
                    break  # 不再执行后续hook
                
                if hr.result == HookResult.SUCCESS and hr.modified_input:
                    ctx.modified_input = hr.modified_input
                    ctx.warnings.append(f"Input modified by hook: {hook_fn.__name__}")
                
                if result and result.get("permissionBehavior"):
                    ctx.permission_override = PermissionBehavior(result["permissionBehavior"])
                    
            except Exception as e:
                ctx.warnings.append(f"PreHook error {hook_fn.__name__}: {e}")
                # FAILED_CONTINUE: 记录错误但继续
                
    except Exception as e:
        ctx.warnings.append(f"Hook registry error: {e}")
    
    return True


def _parse_hook_result(hook_name: str, result: dict) -> HookResponse:
    """解析Hook返回结果为 HookResponse"""
    if not result:
        return HookResponse(hook_name=hook_name, result=HookResult.SUCCESS)
    
    status = result.get("status", "success")
    if status == "abort":
        hr = HookResult.FAILED_ABORT
    elif status == "failed_continue":
        hr = HookResult.FAILED_CONTINUE
    else:
        hr = HookResult.SUCCESS
    
    return HookResponse(
        hook_name=hook_name,
        result=hr,
        error=result.get("error"),
        modified_input=result.get("updatedInput"),
    )


# ─── 第6步：解析Hook权限结果 ──────────────────────────────

def _resolve_hook_permission(ctx: PipelineContext) -> bool:
    """步骤6: Claude Code 原则5 — Hook allow 不能绕过 settings deny"""
    ctx.steps_executed.append("resolve_hook_permission")
    
    override = ctx.permission_override
    if not override:
        ctx.steps_executed.append("resolve_hook_permission.no_override")
        return True
    
    if override == PermissionBehavior.DENY:
        ctx.permission_override = PermissionBehavior.DENY
        ctx.warnings.append("Hook denied this operation")
        return True
    
    if override == PermissionBehavior.ALLOW and ctx.permission_rules:
        try:
            settings_result = ctx.permission_rules(ctx.tool_name, ctx.validated_input)
            if settings_result == "deny":
                ctx.permission_override = PermissionBehavior.DENY
                ctx.warnings.append("Settings deny overrides hook allow")
                return True
            elif settings_result == "ask":
                ctx.permission_override = PermissionBehavior.ASK
                ctx.warnings.append("Settings ask requires confirmation despite hook allow")
        except Exception:
            pass
    
    return True


# ─── 第7步：权限决策（含 Prompt 真正实现）──────────────────

def _permission_decision(ctx: PipelineContext) -> bool:
    """
    步骤7: 综合Hook结果、规则配置、用户交互，做出最终决策
    
    v2.0: 真正实现 ASK 弹窗机制（通过 prompt_callback）
    - FailedAbort 优先：Hook已请求中断，直接拒绝
    - DENY → 直接拒绝（带 justification）
    - ASK → 调用 prompt_callback，等待用户决策
    - CRITICAL/HIGH → 自动拒绝（带 justification）
    """
    ctx.steps_executed.append("permission_decision")
    
    # ⭐ FailedAbort 优先处理
    if ctx.abort_requested:
        ctx.result = None
        ctx.error = f"ABORT: {ctx.abort_reason}"
        if ctx.justification:
            ctx.error += f"\n安全理由：{ctx.justification}"
        return False
    
    if ctx.permission_override == PermissionBehavior.DENY:
        ctx.result = None
        ctx.error = f"Permission denied by hook"
        if ctx.justification:
            ctx.error += f"\n安全理由：{ctx.justification}"
        return False
    
    # ⭐ ASK: 真正的 Prompt 机制
    if ctx.permission_override == PermissionBehavior.ASK:
        if ctx.prompt_callback:
            req = PromptRequest(
                tool_name=ctx.tool_name,
                risk_level=ctx.risk_level,
                justification=ctx.justification or "此操作需要确认",
                command=ctx.validated_input.get("command"),
                modified_input=ctx.modified_input,
            )
            decision = ctx.prompt_callback(req)
            ctx.prompt_decision = decision
            
            if decision == PromptDecision.DENY or decision == PromptDecision.CANCEL:
                ctx.result = None
                ctx.error = f"User cancelled: {ctx.tool_name}"
                return False
            # ALLOW: 继续执行
            ctx.steps_executed.append("permission_decision.user_allowed")
        else:
            # 没有callback，默认拒绝
            ctx.warnings.append("ASK decision but no prompt_callback — defaulting to deny")
            ctx.result = None
            ctx.error = "ASK requires confirmation but no prompt_callback provided"
            return False
    
    # 风险级别自动拒绝
    if ctx.risk_level == RiskLevel.CRITICAL:
        ctx.result = None
        reason = ctx.justification or "CRITICAL risk: operation blocked"
        ctx.error = reason
        return False
    
    if ctx.risk_level == RiskLevel.HIGH and not ctx.permission_override:
        ctx.warnings.append("HIGH risk: operation allowed but flagged")
    
    return True


# ─── 第8步：修正输入 ───────────────────────────────────────

def _fix_input(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("fix_input")
    if ctx.modified_input:
        ctx.tool_input = ctx.modified_input
    else:
        ctx.tool_input = ctx.validated_input
    return True


# ─── 第9步：执行工具 ───────────────────────────────────────

def _execute_tool(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("execute_tool")
    start = time.time()
    
    try:
        tool_name = ctx.tool_name
        
        if tool_name == "exec":
            from agents.exec_adapter import exec_command
            result = exec_command(
                command=ctx.tool_input.get("command", ""),
                workdir=ctx.tool_input.get("workdir"),
                timeout=ctx.tool_input.get("timeout", 30),
            )
            ctx.result = result
        
        elif tool_name == "read":
            from agents.exec_adapter import read_file
            result = read_file(
                path=ctx.tool_input.get("path", ""),
                offset=ctx.tool_input.get("offset"),
                limit=ctx.tool_input.get("limit"),
            )
            ctx.result = result
        
        elif tool_name == "sessions_list":
            ctx.result = {"error": "Not implemented in pipeline"}
        
        elif tool_name == "memory_search":
            ctx.result = {"error": "Not implemented in pipeline"}
        
        else:
            ctx.result = {"error": f"Tool {tool_name} not implemented in pipeline"}
        
        ctx.duration_ms = (time.time() - start) * 1000
        
    except Exception as e:
        ctx.error = str(e)
        ctx.duration_ms = (time.time() - start) * 1000
        return False
    
    return True


# ─── 第10步：记录遥测 ─────────────────────────────────────

def _record_analytics(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("record_analytics")
    if ctx.analytics_callback:
        try:
            ctx.analytics_callback({
                "tool": ctx.tool_name,
                "duration_ms": ctx.duration_ms,
                "risk_level": ctx.risk_level.value,
                "success": ctx.error is None,
                "steps": ctx.steps_executed,
            })
        except Exception as e:
            ctx.warnings.append(f"Analytics error: {e}")
    return True


# ─── 第11步：PostToolUse Hooks ─────────────────────────────

def _run_post_hooks(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("post_hooks")
    
    # ⭐ 成功时才运行 post-hook（失败走 failure_hooks）
    if ctx.error:
        return True
    
    if not ctx.hook_registry:
        return True
    
    try:
        hooks = ctx.hook_registry("PostToolUse", ctx.tool_name)
        for hook_fn in hooks:
            try:
                result = hook_fn(ctx.tool_name, ctx.result, ctx)
                hr = _parse_hook_result(hook_fn.__name__, result)
                ctx.pre_hook_results.append(hr)  # 复用同一字段
                
                # ⭐ FailedAbort 在 post-hook 中同样有效
                if hr.result == HookResult.FAILED_ABORT:
                    ctx.abort_requested = True
                    ctx.abort_reason = hr.error or f"PostHook {hook_fn.__name__} aborted"
                    ctx.warnings.append(f"⭐ PostHook ABORT: {hook_fn.__name__}")
                    break
            except Exception as e:
                ctx.warnings.append(f"PostHook error: {e}")
    except Exception:
        pass
    
    return True


# ─── 第12步：处理结果 ──────────────────────────────────────

def _process_result(ctx: PipelineContext) -> bool:
    ctx.steps_executed.append("process_result")
    if ctx.error:
        return False
    return True


# ─── 第13步：PostToolUseFailure Hooks ─────────────────────

def _run_failure_hooks(ctx: PipelineContext) -> bool:
    """步骤13: 如果失败了，跑失败hook（不处理ABORT，只处理普通错误）"""
    ctx.steps_executed.append("failure_hooks")
    
    if not ctx.error:
        return True
    
    # 注意：ABORT 不走 failure_hooks，因为 ABORT 不是普通"错误"
    # 而是操作被主动中断
    
    if not ctx.hook_registry:
        return True
    
    try:
        hooks = ctx.hook_registry("PostToolUseFailure", ctx.tool_name)
        for hook_fn in hooks:
            try:
                hook_fn(ctx.tool_name, ctx.error, ctx)
            except Exception:
                pass
    except Exception:
        pass
    
    return True


# ─── 主管道 ───────────────────────────────────────────────

def execute_pipeline(ctx: PipelineContext) -> ToolResult:
    """
    执行完整的15步工具管道。
    
    返回 ToolResult，包含所有执行细节。
    v2.0: justification 字段说明规则原因，HookResponse 记录所有hook结果
    """
    steps = [
        ("find_tool", _find_tool),
        ("parse_mcp", _parse_mcp),
        ("validate_input", _validate_input),
        ("speculative_classify", _speculative_classify),
        ("run_pre_hooks", _run_pre_hooks),
        ("resolve_hook_permission", _resolve_hook_permission),
        ("permission_decision", _permission_decision),
        ("fix_input", _fix_input),
        ("execute_tool", _execute_tool),
        ("record_analytics", _record_analytics),
        ("run_post_hooks", _run_post_hooks),
        ("process_result", _process_result),
        ("run_failure_hooks", _run_failure_hooks),
    ]
    
    for step_name, step_fn in steps:
        ok = step_fn(ctx)
        if not ok and ctx.error:
            break
    
    return ToolResult(
        success=ctx.error is None,
        output=ctx.result,
        error=ctx.error,
        risk_level=ctx.risk_level,
        duration_ms=ctx.duration_ms,
        steps=ctx.steps_executed,
        warnings=ctx.warnings,
        modified_input=ctx.modified_input,
        rejected=ctx.error is not None,
        rejected_reason=ctx.error,
        justification=ctx.justification,         # ⭐ v2.0
        hook_responses=ctx.pre_hook_results,      # ⭐ v2.0
        prompt_decision=ctx.prompt_decision,      # ⭐ v2.0
    )


# ─── 便捷函数 ──────────────────────────────────────────────

def execute_tool(
    tool_name: str,
    tool_input: dict,
    tool_registry: Callable = None,
    hook_registry: Callable = None,
    permission_rules: Callable = None,
    analytics_callback: Callable = None,
    prompt_callback: Callable = None,           # ⭐ v2.0
) -> ToolResult:
    """
    一行执行工具（带完整治理管道）。
    
    v2.0 新增参数:
    - prompt_callback: ASK决策时的回调，签名为 (PromptRequest) -> PromptDecision
    """
    ctx = PipelineContext(
        tool_name=tool_name,
        tool_input=tool_input,
        tool_registry=tool_registry,
        hook_registry=hook_registry,
        permission_rules=permission_rules,
        analytics_callback=analytics_callback,
        prompt_callback=prompt_callback,
    )
    return execute_pipeline(ctx)


# ─── Anthropic Managed Agents 接口层（v3.0）────────────────────────
#
# 来源：Anthropic 工程博客《Scaling Managed Agents: Decoupling the brain from the hands》(2026-04-08)
# 核心设计：
# - execute(name, input) → string: 大脑调用双手的统一接口
# - Hand: 可失败、可重启、无状态的"双手"
# - SessionVault: 会话持久化，getEvents() 按位置切片
# - 安全边界：凭证不进沙箱，通过 Vault 代理


class Hand:
    """
    "双手" — 一个可失败、可重启、无状态的执行环境。
    
    Anthropic 设计：
    - "The container became cattle. If the container died, the harness caught
       the failure as a tool-call error and passed it back to Claude."
    - "execute(name, input) → string: a name and input go in, and a string is returned."
    - "The harness doesn't know whether the sandbox is a container, a phone,
       or a Pokémon emulator."
    
    用法：
        hand = Hand(name="sandbox", executor=my_exec_fn)
        result = hand.execute("git", {"command": "status"})  # → str
        if hand.failed:
            hand.restart()  # 牲口模式：重启而非修复
    """
    
    def __init__(
        self,
        name: str,
        executor: Optional[Callable[[str, dict], str]] = None,
        provision_fn: Optional[Callable[[], bool]] = None,
        max_retries: int = 1,
        vault: Optional["CredentialVault"] = None,
    ):
        self.name = name
        self._executor = executor
        self._provision_fn = provision_fn
        self.max_retries = max_retries
        self.vault = vault
        self.failed = False
        self.error: Optional[str] = None
        self._call_count = 0
    
    def execute(self, tool_name: str, tool_input: dict) -> str:
        """
        执行工具调用，返回字符串。
        
        Anthropic 接口：execute(name, input) → string
        如果双手失败，捕获错误并返回错误字符串（不是异常）。
        大脑决定是否重试。
        """
        self._call_count += 1
        
        for attempt in range(self.max_retries + 1):
            try:
                if self._executor:
                    result = self._executor(tool_name, tool_input)
                else:
                    # 默认：走 tool_pipeline 的 execute_tool
                    r = execute_tool(tool_name, tool_input)
                    if r.success:
                        result = r.output or ""
                    else:
                        result = f"ERROR: {r.error}"
                        if r.justification:
                            result += f" (justification: {r.justification})"
                
                self.failed = False
                self.error = None
                return str(result)
                
            except Exception as e:
                self.failed = True
                self.error = str(e)
                if attempt < self.max_retries:
                    self.restart()  # 牲口模式：重启而非修复
                else:
                    return f"ERROR: Hand '{self.name}' failed after {attempt+1} attempts: {e}"
        
        return f"ERROR: Hand '{self.name}' unrecoverable"
    
    def restart(self) -> bool:
        """
        重启双手（牲口模式：重启而非修复）。
        
        Anthropic 设计："a new container could be reinitialized with a standard
        recipe: provision({resources}). We no longer had to nurse failed containers
        back to health."
        """
        self.failed = False
        self.error = None
        if self._provision_fn:
            return self._provision_fn()
        return True  # 无 provision 函数则默认成功
    
    def provision(self, resources: dict = None) -> bool:
        """初始化资源（provision({resources})）"""
        if self._provision_fn:
            return self._provision_fn()
        return True


class SessionVault:
    """
    会话持久化 — 仅追加的事件日志，活在大脑之外。
    
    Anthropic 设计：
    - "The session provides this same benefit, serving as a context object that
       lives outside Claude's context window."
    - "getEvents() allows the brain to interrogate context by selecting positional
       slices of the event stream."
    - "The harness writes to the session with emitEvent(id, event) in order to keep
       a durable record of events."
    
    用法：
        vault = SessionVault(session_id="abc123")
        vault.emit_event({"type": "tool_call", "tool": "exec", "input": {...}})
        events = vault.get_events(start=0, limit=10)
        last = vault.get_events_before(event_idx=5, count=3)
    """
    
    def __init__(self, session_id: str, storage_dir: str = None):
        self.session_id = session_id
        self._events: list = []
        self._storage_dir = storage_dir
        if storage_dir:
            self._load_from_disk()
    
    def emit_event(self, event: dict) -> int:
        """
        记录事件（仅追加）。
        Anthropic: emitEvent(id, event)
        """
        event["_idx"] = len(self._events)
        event["_session_id"] = self.session_id
        if "_timestamp" not in event:
            event["_timestamp"] = time.time()
        self._events.append(event)
        if self._storage_dir:
            self._flush_to_disk()
        return len(self._events) - 1
    
    def get_events(self, start: int = 0, limit: int = None) -> list:
        """
        按位置切片读取事件。
        Anthropic: getEvents() — 允许大脑选择位置切片
        """
        if limit is None:
            return self._events[start:]
        return self._events[start:start + limit]
    
    def get_events_before(self, event_idx: int, count: int = 5) -> list:
        """
        回溯某事件之前的上下文。
        Anthropic: "rewinding a few events before a specific moment to see the lead up"
        """
        start = max(0, event_idx - count)
        return self._events[start:event_idx]
    
    def get_events_after(self, event_idx: int, count: int = 10) -> list:
        """
        从某事件之后继续读取。
        Anthropic: "picking up from wherever it last stopped reading"
        """
        return self._events[event_idx + 1:event_idx + 1 + count]
    
    def wake(self) -> list:
        """
        唤醒/恢复：获取全部事件。
        Anthropic: "wake(sessionId), use getSession(id) to get back the event log,
        and resume from the last event."
        """
        return self._events
    
    @property
    def last_event_idx(self) -> int:
        return len(self._events) - 1 if self._events else -1
    
    @property
    def event_count(self) -> int:
        return len(self._events)
    
    def _flush_to_disk(self):
        """持久化到磁盘"""
        import os, json
        os.makedirs(self._storage_dir, exist_ok=True)
        path = os.path.join(self._storage_dir, f"{self.session_id}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self._events[-1], ensure_ascii=False) + "\n")
    
    def _load_from_disk(self):
        """从磁盘加载"""
        import os, json
        path = os.path.join(self._storage_dir, f"{self.session_id}.jsonl")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self._events = [json.loads(line) for line in f if line.strip()]


class CredentialVault:
    """
    凭证保管库 — 认证信息在沙箱外，token 绝不进沙箱。
    
    Anthropic 设计：
    - "Auth can be bundled with a resource or held in a vault outside the sandbox."
    - "The harness is never made aware of any credentials."
    - "Claude calls MCP tools via a dedicated proxy; this proxy takes in a token
       associated with the session."
    
    用法：
        vault = CredentialVault()
        vault.store("github_token", "ghp_xxx", session_id="abc123")
        # 在 Hand 内部调用时，自动注入凭证
        token = vault.get("github_token", session_id="abc123")
    """
    
    def __init__(self):
        self._credentials: dict = {}  # {key: {token: str, sessions: set}}
    
    def store(self, key: str, token: str, session_id: str = None):
        """存储凭证，关联到会话"""
        if key not in self._credentials:
            self._credentials[key] = {"token": token, "sessions": set()}
        else:
            self._credentials[key]["token"] = token
        if session_id:
            self._credentials[key]["sessions"].add(session_id)
    
    def get(self, key: str, session_id: str = None) -> Optional[str]:
        """
        获取凭证。
        安全边界：只有知道 session_id 才能获取。
        """
        if key not in self._credentials:
            return None
        entry = self._credentials[key]
        if session_id and session_id not in entry["sessions"]:
            return None  # 会话无权访问此凭证
        return entry["token"]
    
    def proxy_call(self, key: str, session_id: str, call_fn: Callable, **kwargs) -> str:
        """
        代理调用：自动注入凭证，调用外部服务。
        Anthropic: "this proxy takes in a token associated with the session.
        The proxy can then fetch the corresponding credentials from the vault
        and make the call to the external service."
        """
        token = self.get(key, session_id)
        if token is None:
            return f"ERROR: No credential '{key}' for session '{session_id}'"
        try:
            return str(call_fn(token=token, **kwargs))
        except Exception as e:
            return f"ERROR: Proxy call failed: {e}"
    
    def revoke(self, key: str):
        """撤销凭证"""
        if key in self._credentials:
            del self._credentials[key]


# ─── 顶层便捷函数：Anthropic execute(name, input) → string ─────

def execute(name: str, input: dict) -> str:
    """
    Anthropic Managed Agents 风格的统一执行接口。
    
    execute(name, input) → string
    
    大脑通过这个接口调用双手。双手失败返回错误字符串，
    大脑决定是否重试。不抛异常。
    
    示例：
        result = execute("exec", {"command": "git status"})
        if result.startswith("ERROR"):
            # 大脑决定重试或换策略
            result = execute("exec", {"command": "git status"})
    """
    hand = Hand(name=name)
    return hand.execute(name, input)


# ─── 测试 ─────────────────────────────────────────────────

def main():
    # 测试1: 安全命令
    r = execute_tool("exec", {"command": "git status"})
    print(f"[SAFE] {r.success} — {r.risk_level.value} — {r.duration_ms:.1f}ms")
    print(f"  steps: {' → '.join(r.steps)}")
    if r.warnings:
        print(f"  warnings: {r.warnings}")
    
    # 测试2: 危险命令（含 justification）
    r = execute_tool("exec", {"command": "rm -rf /tmp/test"})
    print(f"\n[DANGEROUS] {r.success} — {r.risk_level.value}")
    if r.justification:
        print(f"  justification: {r.justification}")  # ⭐ v2.0
    if r.error:
        print(f"  error: {r.error}")
    
    # 测试3: FailedAbort hook
    def abort_hook(name, inp, ctx):
        return {"status": "abort", "error": "Security hook: simulated abort"}
    
    def always_ask_hook(name, inp, ctx):
        return {"status": "success", "permissionBehavior": "ask"}
    
    r = execute_tool("exec", {"command": "curl http://example.com"},
                     hook_registry=lambda e, t: [abort_hook])
    print(f"\n[ABORT] {r.success} — rejected={r.rejected}")
    print(f"  abort in hooks: {any(h.result == HookResult.FAILED_ABORT for h in r.hook_responses)}")
    if r.error:
        print(f"  error: {r.error}")
    
    # 测试4: ASK with prompt_callback
    def prompt_handler(req: PromptRequest) -> PromptDecision:
        print(f"  [PROMPT] {req.tool_name}: {req.justification}")
        return PromptDecision.ALLOW  # 模拟用户允许
    
    r = execute_tool("exec", {"command": "curl http://example.com"},
                     hook_registry=lambda e, t: [always_ask_hook],
                     prompt_callback=prompt_handler)
    print(f"\n[ASK] {r.success} — prompt_decision={r.prompt_decision}")


if __name__ == "__main__":
    main()
