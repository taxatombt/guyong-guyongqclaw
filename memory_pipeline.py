"""
memory_pipeline.py — Codex Phase2 风格两阶段记忆整合
借鉴：OpenAI/codex-rs 两阶段记忆管道
实现：
  Phase1 extract  → memory_buffer/（积累碎片）
  Phase2 consolidate → memory_summary.md / MEMORY.md / skills/
"""
import pathlib, json, sys, datetime, hashlib, uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8')
WS = pathlib.Path(r'C:\Users\yiseg\.qclaw\workspace')
BUFFER = WS / 'memory_buffer'
SUMMARY = WS / 'memory_summary.md'
CONSOLIDATION_PROMPT = WS / 'consolidation_prompt.md'

# === 配置 ===
MIN_PENDING = 3          # 至少N条pending才触发整合
MIN_INTERVAL_HOURS = 6   # 两次整合最小间隔
QUALITY_RULES = [
    "稳定用户偏好 > 程序性知识",
    "减少未来用户steering > 减少agent搜索努力",
    "决策触发点（context where user chose X）",
    "失败护盾：symptom → cause → fix + verification",
    "Repo orientation：入口/配置/命令",
    "工具quirks和可靠shortcuts",
    "验证性reproduction plans",
]
FORGET_RULES = [
    "泛泛建议（be careful）",
    "存secrets/credentials",
    "复制大段原始输出",
    "探索性讨论变永久记忆",
    "无意义更新（no-op allowed）",
]


# ═══════════════════════════════════════════════════════════════════════
# render_workspace_tree — Codex realtime_context.py 风格的目录树渲染
# 来源：codex-rs_core_src_realtime_context.rs render_tree()
# 功能：新会话开始时注入工作区上下文，帮助 agent 理解项目结构
# ═══════════════════════════════════════════════════════════════════════

def render_workspace_tree(root: pathlib.Path, max_depth: int = 3, max_entries: int = 50) -> str:
    """
    渲染工作区的目录树，用于新会话时的上下文注入。

    Codex 设计（realtime_context.rs）：
    - 排除 __pycache__/.git/node_modules 等噪音目录
    - 深度限制 + 总条目限制
    - 每层缩进2空格
    """
    SKIP_NAMES = {
        '__pycache__', '.git', '.venv', 'node_modules', '.mypy_cache',
        '.pytest_cache', '.ruff_cache', 'target', 'dist', 'build', '.next',
        '.cache', '.tox', '.eggs', '*.egg-info', '.DS_Store', '.idea',
        '.vscode', 'vendor', '__pypackages__', '.env', '.venv',
    }

    def should_skip(name: str) -> bool:
        return name in SKIP_NAMES or name.startswith('.')

    def collect_entries(path: pathlib.Path, depth: int) -> list:
        if depth > max_depth:
            return []
        entries = []
        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return []
        for item in items:
            if should_skip(item.name):
                continue
            if len(entries) >= max_entries:
                entries.append(('truncated', depth, f'... more in {item.parent.name}/'))
                return entries
            if item.is_dir():
                entries.append(('dir', depth, item.name))
                if depth < max_depth:
                    entries.extend(collect_entries(item, depth + 1))
            else:
                entries.append(('file', depth, item.name))
        return entries

    lines = []
    lines.append(f'@ {root.name}/')
    for etype, depth, name in collect_entries(root, 0):
        indent = '  ' * (depth + 1)
        if etype == 'dir':
            lines.append(f'{indent}@ {name}/')
        elif etype == 'file':
            lines.append(f'{indent}* {name}')
        elif etype == 'truncated':
            lines.append(f'{indent}... {name}')
    return '\n'.join(lines)


@dataclass
class MemoryFragment:
    """Phase1 提取的记忆碎片"""
    id: str
    timestamp: str
    task: str          # 任务类型
    method: str        # 使用的方法
    success: bool
    tool_calls: int    # tool调用次数（复杂度指标）
    context: str       # 决策触发点描述
    lesson: str        # 核心教训（1-2句）
    quality_score: float = 0.0  # 0-1，越高越值得保留


@dataclass
class ConsolidationResult:
    """Phase2 整合结果（Codex 风格 selection diff）"""
    added: list[str]    # 新增的片段ID（本次有，上次没有）
    retained: list[str] # 保留的片段ID（上次和本次都有）
    removed: list[str]  # 遗忘的片段ID（上次有，本次没有）
    summary_md: str     # memory_summary.md 内容
    memory_md_additions: str  # MEMORY.md 新增内容
    phase2_inputs: list = field(default_factory=list)  # 本次选择的全部碎片（for next diff）


@dataclass
class Phase2SelectionDiff:
    """
    Codex Phase2 Selection Diff（两阶段记忆整合的核心算法）

    来源：codex-rs runtime_memories.rs get_phase2_input_selection()

    Selection Diff = 本次选择 - 上次选择
    - added: 本次新选入的（新鲜度高）
    - retained: 既在上次又在本次的（高频使用）
    - removed: 本次不再选的（可能是已遗忘或过时）

    记忆淘汰策略（Codex）：
    1. usage_count > 0 的行：即使超过 max_unused_days 也保留
    2. selected_for_phase2 = 1 的行：本次参与了整合
    3. 超过 max_unused_days 且 usage_count = 0 的行 → 删除
    """
    current: list          # 本次选择的碎片
    previous: list         # 上次选择的碎片
    retained: list         # 交集（added = current - previous）
    removed: list          # diff（previous - current）

    @property
    def added(self) -> list:
        """本次新增（current 中不属于 previous 的）"""
        prev_ids = {self._id(m) for m in self.previous}
        return [m for m in self.current if self._id(m) not in prev_ids]

    @property
    def has_changed(self) -> bool:
        """是否有变化（任何 added 或 removed）"""
        return len(self.added) > 0 or len(self.removed) > 0

    def _id(self, item) -> str:
        """从碎片中提取 ID"""
        if isinstance(item, dict):
            return item.get('id', item.get('thread_id', ''))
        if hasattr(item, 'id'):
            return item.id
        return str(item)


def compute_selection_diff(
    current: list,
    previous: list,
    max_unused_days: int = 30,
) -> Phase2SelectionDiff:
    """
    计算 Codex 风格的 selection diff。

    淘汰策略（与 Codex 一致）：
    1. 本次选择（current）：按 usage_count + last_usage 排序
    2. 上次选择（previous）：selected_for_phase2 = 1 的行
    3. removed = previous - current（本次不再选 = 被遗忘）
    """
    current_ids = {Phase2SelectionDiff._id(None, c) for c in current}
    prev_ids = {Phase2SelectionDiff._id(None, p) for p in previous}

    retained_ids = current_ids & prev_ids
    removed_ids = prev_ids - current_ids

    retained = [m for m in current if Phase2SelectionDiff._id(None, m) in retained_ids]
    removed = [m for m in previous if Phase2SelectionDiff._id(None, m) in removed_ids]

    return Phase2SelectionDiff(
        current=current,
        previous=previous,
        retained=retained,
        removed=removed,
    )
    skills_created: list[dict]  # [{"name": str, "trigger": str, "desc": str}]


# ============================================================
# Phase1: Extract — 每次任务后调用
# ============================================================
def extract(task: str, method: str, success: bool,
            tool_calls: int, context: str, lesson: str) -> str:
    """
    Phase1：记录一个记忆碎片到 buffer。
    调用方式：evolver.record() 后自动调用，或手动调用。
    返回：fragment_id
    """
    BUFFER.mkdir(exist_ok=True)

    # 计算质量分数
    score = _quality_score(task, method, success, tool_calls, context, lesson)

    frag = MemoryFragment(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'),
        task=task,
        method=method,
        success=success,
        tool_calls=tool_calls,
        context=context,
        lesson=lesson,
        quality_score=score,
    )

    path = BUFFER / f'{frag.id}.json'
    path.write_text(json.dumps(asdict(frag), ensure_ascii=False, indent=2),
                    encoding='utf-8')

    # 检查是否需要触发 Phase2
    if _should_consolidate():
        print(f"[Phase1] 触发 Phase2 整合（{pending_count()} 条待整合）")
        # 非阻塞，交给下次心跳或手动触发

    return frag.id


def pending_count() -> int:
    """buffer中待整合的碎片数"""
    if not BUFFER.exists():
        return 0
    return len([f for f in BUFFER.iterdir() if f.suffix == '.json'])


def last_consolidation() -> Optional[datetime.datetime]:
    """上次整合时间"""
    marker = BUFFER / '_last_consolidation.txt'
    if marker.exists():
        try:
            return datetime.datetime.fromisoformat(marker.read_text(encoding='utf-8').strip())
        except:
            pass
    return None


def _should_consolidate() -> bool:
    if pending_count() < MIN_PENDING:
        return False
    last = last_consolidation()
    if last is None:
        return True
    elapsed = datetime.datetime.now() - last
    return elapsed.total_seconds() >= MIN_INTERVAL_HOURS * 3600


def _quality_score(task: str, method: str, success: bool,
                   tool_calls: int, context: str, lesson: str) -> float:
    """
    0-1 质量分数。越高越值得保留。
    规则：
      - 成功任务 + 有明确context + 有lesson > 泛泛记录
      - tool_calls高（复杂任务成功）加分
      - 空lesson或通用描述减分
    """
    score = 0.3 if success else 0.1
    if context and len(context) > 10:
        score += 0.2
    if lesson and len(lesson) > 5:
        score += 0.2
    if tool_calls > 5:
        score += 0.15
    if tool_calls > 10:
        score += 0.15
    # 惩罚泛泛描述
    generic = ['待观察', '继续使用', '正常', 'ok', 'done']
    if any(g in lesson.lower() for g in generic):
        score -= 0.2
    return max(0.0, min(1.0, score))


# ============================================================
# Phase2: Consolidate — 整合碎片生成三文件
# ============================================================
def consolidate() -> ConsolidationResult:
    """
    Phase2：独立整合流程。
    1. 读取所有 pending fragments
    2. 按质量过滤
    3. 生成 memory_summary.md / MEMORY.md 更新 / skills/
    4. 清理已整合的碎片（遗忘机制）
    """
    if not BUFFER.exists():
        return ConsolidationResult(added=[], retained=[], removed=[],
                                   summary_md='', memory_md_additions='',
                                   skills_created=[])

    fragments = []
    for f in BUFFER.iterdir():
        if f.suffix != '.json' or f.name == '_last_consolidation.txt':
            continue
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            fragments.append(MemoryFragment(**data))
        except:
            pass

    if not fragments:
        return ConsolidationResult(added=[], retained=[], removed=[],
                                   summary_md='', memory_md_additions='',
                                   skills_created=[])

    # 按质量分数排序
    fragments.sort(key=lambda x: x.quality_score, reverse=True)

    # === 生成 memory_summary.md ===
    summary_md = _build_summary(fragments)

    # === 生成 MEMORY.md 更新片段 ===
    memory_additions = _build_memory_additions(fragments)

    # === 生成 skills（高质量碎片） ===
    skills_created = _build_skills(fragments)

    # === 遗忘机制：移除低质量碎片 ===
    # 保留 top 70% 或 quality > 0.5
    threshold_idx = max(1, int(len(fragments) * 0.7))
    kept = [f for f in fragments if f.quality_score >= 0.5 or
            fragments.index(f) < threshold_idx]
    removed_ids = [f.id for f in fragments if f not in kept]

    # 写入文件
    SUMMARY.write_text(summary_md, encoding='utf-8')
    _update_memory_md(memory_additions)

    # 删除已整合的碎片（保留高质量的近期样本）
    for f in fragments:
        if f not in kept:
            fp = BUFFER / f'{f.id}.json'
            if fp.exists():
                fp.unlink()

    # 标记整合时间
    marker = BUFFER / '_last_consolidation.txt'
    marker.write_text(datetime.datetime.now().isoformat(), encoding='utf-8')

    print(f"[Phase2] 整合完成：{len(kept)}条保留，{len(removed_ids)}条遗忘，"
          f"生成{len(skills_created)}个skill")

    return ConsolidationResult(
        added=[f.id for f in kept],
        retained=[f.id for f in kept if f.quality_score >= 0.5],
        removed=removed_ids,
        summary_md=summary_md,
        memory_md_additions=memory_additions,
        skills_created=skills_created,
    )


def _build_summary(fragments: list[MemoryFragment]) -> str:
    """生成 memory_summary.md 高密度导航"""
    lines = [
        "# Memory Summary",
        "",
        f"_自动生成：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## 核心信息",
    ]

    # 按task分组，输出top记忆
    by_task: dict[str, list[MemoryFragment]] = {}
    for frag in fragments:
        by_task.setdefault(frag.task, []).append(frag)

    for task, frags in sorted(by_task.items(),
                              key=lambda x: -sum(f.quality_score for f in x[1])):
        top = sorted(frags, key=lambda x: -x.quality_score)[:3]
        lines.append(f"\n### {task}（{len(frags)}条）")
        for f in top:
            status = "✅" if f.success else "❌"
            lines.append(f"- {status} {f.lesson} [→ {f.method}]")

    lines += [
        "",
        "## 快速参考",
        "```",
        "# 查看待整合记忆",
        "python memory_pipeline.py status",
        "",
        "# 手动触发整合",
        "python memory_pipeline.py consolidate",
        "",
        "# 记录新记忆",
        "python memory_pipeline.py extract <task> <method> <yes|no> <tool_calls> <context> <lesson>",
        "```",
        "",
        "## 质量规则",
        "记住 > 稳定偏好、决策触发点、失败护盾",
        "忘记 > 泛泛建议、secrets、探索性讨论",
    ]
    return '\n'.join(lines)


def _build_memory_additions(fragments: list[MemoryFragment]) -> str:
    """生成 MEMORY.md 新增内容块"""
    lines = [f"\n## 记忆整合 {datetime.datetime.now().strftime('%Y-%m-%d')}"]
    for f in fragments:
        if f.quality_score < 0.4:
            continue
        lines.append(f"\n### {f.task}：{f.context[:60]}")
        lines.append(f"- 方法：{f.method}")
        lines.append(f"- 教训：{f.lesson}")
        if not f.success:
            lines.append(f"- ⚠️ 失败，需要改进")
    return '\n'.join(lines)


def _build_skills(fragments: list[MemoryFragment]) -> list[dict]:
    """从高质量碎片生成 skills/"""
    skills_dir = WS / 'skills'
    created = []

    for f in fragments:
        if f.quality_score < 0.6 or not f.context:
            continue

        # 生成 skill 名称
        safe_name = ''.join(c if c.isalnum() else '-' for c in f.task)[:40]
        skill_dir = skills_dir / safe_name
        skill_dir.mkdir(exist_ok=True)

        # SKILL.md 内容
        content = f"""# {f.task}

**触发条件：** {f.context}

**使用方法：** {f.method}

**核心教训：** {f.lesson}

**质量评分：** {f.quality_score:.2f}（{f.tool_calls}次tool调用）

---
_自动生成：{datetime.datetime.now().strftime('%Y-%m-%d')}_
"""
        (skill_dir / 'SKILL.md').write_text(content, encoding='utf-8')
        created.append({'name': safe_name, 'trigger': f.context})

    return created


def _update_memory_md(additions: str):
    """追加到 MEMORY.md"""
    if not additions.strip():
        return
    mem = WS / 'MEMORY.md'
    content = mem.read_text(encoding='utf-8')
    mem.write_text(content.rstrip() + '\n' + additions + '\n',
                   encoding='utf-8')


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    import sys as _sys
    cmd = _sys.argv[1] if len(_sys.argv) > 1 else 'status'

    if cmd == 'status':
        print(f"待整合：{pending_count()} 条")
        last = last_consolidation()
        print(f"上次整合：{last.strftime('%Y-%m-%d %H:%M') if last else '从未'}")
        print(f"摘要文件：{'存在' if SUMMARY.exists() else '不存在'}")

    elif cmd == 'consolidate':
        result = consolidate()
        print(f"整合完成：{len(result.retained)}保留，{len(result.removed)}遗忘，"
              f"{len(result.skills_created)}个skill")

    elif cmd == 'extract':
        # python memory_pipeline.py extract <task> <method> <success> <tool_calls> <context> <lesson>
        if len(_sys.argv) < 7:
            print("用法: extract <task> <method> <yes|no> <tool_calls> <context> <lesson>")
        else:
            fid = extract(_sys.argv[2], _sys.argv[3], _sys.argv[4].lower() == 'yes',
                          int(_sys.argv[5]), _sys.argv[6], _sys.argv[7])
            print(f"碎片已记录: {fid}（当前 {pending_count()} 条待整合）")

    elif cmd == 'test':
        # 测试：注入假碎片并整合
        for i in range(4):
            extract(f'test-task-{i}', 'test-method', i % 2 == 0,
                    10 + i, f'测试上下文 {i}', f'这是第{i}条测试教训')
        result = consolidate()
        print("测试完成")

    else:
        print(f"未知命令: {cmd}")
        print("可用: status | consolidate | extract | test")
