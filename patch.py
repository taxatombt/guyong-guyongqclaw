# -*- coding: utf-8 -*-
"""
patch.py — 多文件补丁系统（对齐 OpenSpace skill_engine/patch.py）

支持三种 LLM 输出格式：
  FULL  — 完整文件内容（单文件或 *** Begin Files 多文件）
  DIFF  — SEARCH/REPLACE 块（单文件）
  PATCH — *** Begin Patch 多文件格式（支持 Add/Update/Delete）

三种技能操作：
  fix_skill    — 原地修复现有技能
  derive_skill — 复制目录 → 在副本中应用修改
  create_skill — 创建全新技能目录（CAPTURED 用）

关键设计（来自 OpenSpace）：
1. 路径安全检查：防止 ../ 逃逸到技能目录外
2. .skill_id sidecar 被明确排除在 diff/snapshot 之外
3. 自动检测格式：detect_patch_type()
4. 4级模糊匹配：exact → rstrip → strip → Unicode normalize

来源：HKUDS/OpenSpace skill_engine/patch.py
"""

import difflib
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


# ═══════════════════════════════════════════════════════════════════
# FileSnapshot — Hermes 风格写前快照 + unified_diff 预览
# 借鉴：hermes_study/display/emotion_display.py
# ═══════════════════════════════════════════════════════════════════
_SNAPSHOT_CACHE: Dict[str, str] = {}


def file_snapshot(path: str) -> 'FileSnapshot':
    """写操作前快照（返回快照对象）"""
    p = Path(path)
    content = p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''
    _SNAPSHOT_CACHE[str(p.absolute())] = content
    return FileSnapshot(str(p.absolute()))


class FileSnapshot:
    """写操作前快照，支持 unified_diff 彩色预览 + 回滚"""

    def __init__(self, snap_key: str):
        self.key = snap_key

    def diff(self, new_content: str = None) -> str:
        """生成 unified_diff"""
        old = _SNAPSHOT_CACHE.get(self.key, '')
        new = new_content if new_content is not None else self._current()
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff_lines = difflib.unified_diff(old_lines, new_lines, lineterm='')
        return ''.join(diff_lines)

    def preview(self, new_content: str = None) -> str:
        """生成彩色 unified_diff 预览"""
        diff = self.diff(new_content).splitlines()
        result = []
        for line in diff[:80]:
            if line.startswith('+') and not line.startswith('+++'):
                result.append(f'\033[32m{line}\033[0m')   # 绿色
            elif line.startswith('-') and not line.startswith('---'):
                result.append(f'\033[31m{line}\033[0m')   # 红色
            elif line.startswith('@@'):
                result.append(f'\033[36m{line}\033[0m')   # 青色
            else:
                result.append(line)
        return '\n'.join(result)

    def restore(self) -> None:
        """回滚到快照"""
        Path(self.key).write_text(
            _SNAPSHOT_CACHE.get(self.key, ''), encoding='utf-8')

    def _current(self) -> str:
        p = Path(self.key)
        return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''

    def discard(self) -> None:
        _SNAPSHOT_CACHE.pop(self.key, None)


def _safe_write(path: Path, content: str) -> None:
    """安全写文件：自动快照，支持回滚"""
    file_snapshot(str(path))
    path.write_text(content, encoding='utf-8')


SKILL_FILENAME = "SKILL.md"
SKILL_ID_FILENAME = ".skill_id"


# ═══════════════════════════════════════════════════════════════════
# Patch 类型
# ═══════════════════════════════════════════════════════════════════

class PatchType(str, Enum):
    AUTO  = "auto"
    FULL  = "full"
    DIFF  = "diff"
    PATCH = "patch"


# ═══════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SkillEditResult:
    skill_dir: Path = field(default_factory=lambda: Path("."))
    content_diff: str = ""
    content_snapshot: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def ok(self) -> bool:
        return self.error is None


class PatchError(RuntimeError):
    """补丁无法应用时抛出"""
    pass


# SEARCH/REPLACE 格式的正则
PATCH_PATTERN = re.compile(
    r"<{7}\s*SEARCH\s*\n(.*?)\n\s*={7}\s*\n(.*?)\n\s*>{7}\s*REPLACE\s*",
    re.DOTALL,
)


# ═══════════════════════════════════════════════════════════════════
# 核心操作
# ═══════════════════════════════════════════════════════════════════

def fix_skill(
    skill_dir: Path,
    content: str,
    patch_type: PatchType = PatchType.AUTO,
) -> SkillEditResult:
    """
    原地修复技能（对齐 OpenSpace patch.py）
    
    流程：
    1. 快照修改前文件
    2. 检测格式并应用补丁
    3. 标准化 frontmatter
    4. 快照修改后文件，计算 diff
    """
    if not skill_dir.is_dir():
        return SkillEditResult(error=f"Skill directory not found: {skill_dir}")
    skill_file = skill_dir / SKILL_FILENAME
    if not skill_file.exists():
        return SkillEditResult(error=f"SKILL.md not found: {skill_file}")
    
    old_files = _collect_files(skill_dir)
    
    if patch_type == PatchType.AUTO:
        patch_type = detect_patch_type(content)
    
    try:
        if patch_type == PatchType.PATCH:
            _apply_multi_file_patch(content, skill_dir)
        elif patch_type == PatchType.FULL:
            _apply_multi_file_full(content, skill_dir)
        elif patch_type == PatchType.DIFF:
            _apply_search_replace_to_file(content, skill_file)
        else:
            return SkillEditResult(error=f"Unknown patch type: {patch_type}")
    except PatchError as e:
        return SkillEditResult(error=str(e))
    except Exception as e:
        return SkillEditResult(error=f"Unexpected error: {e}")
    
    new_files = _collect_files(skill_dir)
    diff = _compute_files_diff(old_files, new_files)
    
    return SkillEditResult(
        skill_dir=skill_dir,
        content_diff=diff,
        content_snapshot=new_files,
    )


def derive_skill(
    source_dir: Path,
    target_dir: Path,
    content: str,
    patch_type: PatchType = PatchType.AUTO,
) -> SkillEditResult:
    """
    从现有技能派生（对齐 OpenSpace patch.py）
    
    1. 复制源目录
    2. 应用补丁
    3. 计算与源的 diff
    """
    if not source_dir.is_dir():
        return SkillEditResult(error=f"Source not found: {source_dir}")
    if target_dir.exists():
        return SkillEditResult(error=f"Target already exists: {target_dir}")
    
    if patch_type == PatchType.AUTO:
        patch_type = detect_patch_type(content)
    
    try:
        shutil.copytree(source_dir, target_dir)
        
        if patch_type == PatchType.PATCH:
            _apply_multi_file_patch(content, target_dir)
        elif patch_type == PatchType.FULL:
            _apply_multi_file_full(content, target_dir)
        elif patch_type == PatchType.DIFF:
            _apply_search_replace_to_file(content, target_dir / SKILL_FILENAME)
        else:
            shutil.rmtree(target_dir, ignore_errors=True)
            return SkillEditResult(error=f"Unknown patch type: {patch_type}")
    except (PatchError, Exception) as e:
        shutil.rmtree(target_dir, ignore_errors=True)
        return SkillEditResult(error=str(e))
    
    new_files = _collect_files(target_dir)
    diff = compute_skill_diff(source_dir, target_dir)
    
    return SkillEditResult(
        skill_dir=target_dir,
        content_diff=diff,
        content_snapshot=new_files,
    )


def create_skill(
    target_dir: Path,
    content: str,
    patch_type: PatchType = PatchType.AUTO,
) -> SkillEditResult:
    """
    创建全新技能（对齐 OpenSpace patch.py）
    """
    if target_dir.exists():
        return SkillEditResult(error=f"Target already exists: {target_dir}")
    
    if patch_type == PatchType.AUTO:
        patch_type = detect_patch_type(content)
    
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        
        if patch_type == PatchType.PATCH:
            _apply_multi_file_patch(content, target_dir)
        elif patch_type == PatchType.FULL:
            _apply_multi_file_full(content, target_dir)
        elif patch_type == PatchType.DIFF:
            # CAPTURED 的 DIFF → 视为单文件完整内容
            _safe_write(target_dir / SKILL_FILENAME, content)
        else:
            shutil.rmtree(target_dir, ignore_errors=True)
            return SkillEditResult(error=f"Unknown patch type: {patch_type}")
    except (PatchError, Exception) as e:
        shutil.rmtree(target_dir, ignore_errors=True)
        return SkillEditResult(error=str(e))
    
    new_files = _collect_files(target_dir)
    
    return SkillEditResult(
        skill_dir=target_dir,
        content_diff="",
        content_snapshot=new_files,
    )


# ═══════════════════════════════════════════════════════════════════
# 格式检测
# ═══════════════════════════════════════════════════════════════════

_FILE_HEADER_RE = re.compile(r"^\*\*\*\s*File:\s*(.+)$", re.MULTILINE)


def detect_patch_type(content: str) -> PatchType:
    """
    自动检测补丁格式（对齐 OpenSpace）
    
    检测顺序（按特异性）：
    1. *** Begin Patch     → PATCH（多文件 diff）
    2. *** Begin Files     → FULL（多文件完整内容）
    3. *** File: 行标记    → FULL（多文件，无信封）
    4. <<<<<<< SEARCH      → DIFF（单文件 SEARCH/REPLACE）
    5. 默认                → FULL（单文件完整内容）
    """
    if "*** Begin Patch" in content:
        return PatchType.PATCH
    if "*** Begin Files" in content:
        return PatchType.FULL
    
    file_header_hits = _FILE_HEADER_RE.findall(content)
    if file_header_hits:
        return PatchType.FULL
    
    if "<<<<<<< SEARCH" in content:
        return PatchType.DIFF
    
    return PatchType.FULL


# ═══════════════════════════════════════════════════════════════════
# FULL 格式
# ═══════════════════════════════════════════════════════════════════

def parse_multi_file_full(content: str) -> Dict[str, str]:
    """
    解析 *** Begin Files 格式
    
    格式：
      *** Begin Files
      *** File: SKILL.md
      (完整内容)
      *** File: examples/helper.sh
      (完整内容)
      *** End Files
    
    回退：无标记 → {SKILL.md: content}
    """
    stripped = content.strip()
    if stripped.startswith("*** Begin Files"):
        stripped = stripped[len("*** Begin Files"):].strip()
    
    end_idx = stripped.rfind("*** End Files")
    if end_idx != -1:
        stripped = stripped[:end_idx].strip()
    
    headers = list(_FILE_HEADER_RE.finditer(stripped))
    if not headers:
        return {SKILL_FILENAME: content}
    
    files: Dict[str, str] = {}
    for i, match in enumerate(headers):
        file_path = match.group(1).strip()
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(stripped)
        file_content = stripped[start:end].strip("\n")
        if file_content and not file_content.endswith("\n"):
            file_content += "\n"
        files[file_path] = file_content
    
    return files


def _apply_multi_file_full(content: str, skill_dir: Path) -> None:
    """应用多文件 FULL 格式"""
    files = parse_multi_file_full(content)
    
    for rel_path, file_content in files.items():
        target = (skill_dir / rel_path).resolve()
        if not str(target).startswith(str(skill_dir.resolve())):
            raise PatchError(f"Path escapes skill directory: {rel_path}")
        
        target.parent.mkdir(parents=True, exist_ok=True)
        _safe_write(target, file_content)


# ═══════════════════════════════════════════════════════════════════
# PATCH 格式
# ═══════════════════════════════════════════════════════════════════

_PATCH_BLOCK_RE = re.compile(
    r"^\*\*\*\s*(Begin Patch|End Patch|Add File:|Update File:|Delete File:|"
    r"Move to:)\s*(.*)$",
    re.MULTILINE,
)


def _apply_multi_file_patch(patch_text: str, skill_dir: Path) -> None:
    """
    解析并应用 *** Begin Patch 块
    
    格式：
      *** Begin Patch
      *** Add File: <path>
      +new line 1
      +new line 2
      *** Update File: <path>
      @@ context
      -old line
      +new line
      *** Delete File: <path>
      *** End Patch
    """
    lines = patch_text.strip().split("\n")
    i = 0
    resolved_dir = skill_dir.resolve()
    
    changes: List[Tuple[str, Path, str]] = []  # (op, path, content)
    
    while i < len(lines):
        line = lines[i].strip()
        
        if line == "*** Begin Patch":
            i += 1
            continue
        
        if line == "*** End Patch":
            break
        
        if line.startswith("*** Add File:"):
            file_path = line.split(":", 1)[1].strip()
            if not file_path:
                i += 1
                continue
            
            content_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("***"):
                if lines[i].startswith("+"):
                    content_lines.append(lines[i][1:])
                i += 1
            content = "\n".join(content_lines)
            if content and not content.endswith("\n"):
                content += "\n"
            changes.append(("add", file_path, content))
            continue
        
        elif line.startswith("*** Update File:"):
            file_path = line.split(":", 1)[1].strip()
            if not file_path:
                i += 1
                continue
            
            # 收集 @@ 上下文块
            old_lines = []
            new_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("***"):
                cl = lines[i]
                if cl.startswith("@@"):
                    i += 1
                    continue
                if cl.startswith("-"):
                    old_lines.append(cl[1:])
                elif cl.startswith("+"):
                    new_lines.append(cl[1:])
                elif cl.startswith(" ") or not cl.startswith(("+", "-")):
                    old_lines.append(cl[1:] if cl.startswith(" ") else cl)
                    new_lines.append(cl[1:] if cl.startswith(" ") else cl)
                i += 1
            
            # 读取原文件并应用修改
            target_path = skill_dir / file_path
            if not target_path.exists():
                raise PatchError(f"Cannot update non-existent file: {file_path}")
            
            original = target_path.read_text(encoding="utf-8")
            updated = _apply_search_only(original, old_lines, new_lines)
            changes.append(("update", file_path, updated))
            continue
        
        elif line.startswith("*** Delete File:"):
            file_path = line.split(":", 1)[1].strip()
            changes.append(("delete", file_path, ""))
            i += 1
            continue
        
        else:
            i += 1
    
    # 应用所有变更
    for op, file_path, new_content in changes:
        target = (skill_dir / file_path).resolve()
        if not str(target).startswith(str(resolved_dir)):
            raise PatchError(f"Path escapes skill directory: {file_path}")
        
        if op == "add":
            target.parent.mkdir(parents=True, exist_ok=True)
            _safe_write(target, new_content)
        elif op == "update":
            _safe_write(target, new_content)
        elif op == "delete":
            if target.exists():
                target.unlink()


def _apply_search_only(
    original: str,
    search_lines: List[str],
    replace_lines: List[str],
) -> str:
    """
    简单替换：在 original 中找到 search_lines，替换为 replace_lines
    
    使用 4 级模糊匹配（对齐 OpenSpace seek_sequence）：
    1. 精确匹配
    2. rstrip 后匹配
    3. strip 后匹配
    4. Unicode normalize + strip
    """
    if not search_lines:
        # 追加模式
        return original.rstrip("\n") + "\n" + "\n".join(replace_lines) + "\n"
    
    orig_lines = original.split("\n")
    
    # 级别 1: 精确匹配
    idx = _seek_lines(orig_lines, search_lines, exact=True)
    
    # 级别 2: rstrip 匹配
    if idx == -1:
        idx = _seek_lines(orig_lines, search_lines, exact=False, strip_level=1)
    
    # 级别 3: strip 匹配
    if idx == -1:
        idx = _seek_lines(orig_lines, search_lines, exact=False, strip_level=2)
    
    if idx == -1:
        # 找不到，报错
        first = search_lines[0].strip() if search_lines else ""
        raise PatchError(
            f"Cannot find SEARCH block in file:\n"
            f"Looking for: {first!r}\n"
            f"Hint: Check for whitespace differences"
        )
    
    # 应用替换
    result = orig_lines[:idx] + replace_lines + orig_lines[idx + len(search_lines):]
    return "\n".join(result) + ("\n" if original.endswith("\n") else "")


_UNICODE_REPL: Dict[str, str] = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2026": "...",
    "\u00a0": " ",
}

_UNICODE_PAT = re.compile("|".join(re.escape(k) for k in _UNICODE_REPL))


def _normalize_unicode(s: str) -> str:
    return _UNICODE_PAT.sub(lambda m: _UNICODE_REPL[m.group()], s)


def _seek_lines(
    lines: List[str],
    pattern: List[str],
    exact: bool = True,
    strip_level: int = 0,
) -> int:
    """在 lines 中查找 pattern 的起始位置
    
    strip_level:
      0 = 精确匹配（默认）
      1 = rstrip 后匹配
      2 = strip 后匹配
    """
    if not pattern:
        return -1
    
    n = len(lines)
    p = len(pattern)
    
    for i in range(n - p + 1):
        match = True
        for j in range(p):
            a = lines[i + j]
            b = pattern[j]
            
            if exact:
                if a != b:
                    match = False
                    break
            elif strip_level == 1:
                if a.rstrip() != b.rstrip():
                    match = False
                    break
            elif strip_level == 2:
                a_norm = _normalize_unicode(a.strip())
                b_norm = _normalize_unicode(b.strip())
                if a_norm != b_norm:
                    match = False
                    break
        
        if match:
            return i
    
    return -1


# ═══════════════════════════════════════════════════════════════════
# DIFF 格式（SEARCH/REPLACE）
# ═══════════════════════════════════════════════════════════════════

def apply_search_replace(
    patch_text: str,
    original: str,
    strict: bool = True,
) -> Tuple[str, int, Optional[str]]:
    """
    应用 SEARCH/REPLACE 块到单文件内容
    
    Returns: (new_text, num_applied, error_message)
    """
    new_text = original
    num_applied = 0
    
    blocks = list(PATCH_PATTERN.finditer(patch_text))
    if not blocks:
        return new_text, 0, None
    
    for block in blocks:
        search = _strip_trailing_ws(block.group(1))
        replace = _strip_trailing_ws(block.group(2))
        
        if not search.strip():
            # 空 SEARCH → 追加
            new_text = new_text.rstrip("\n") + "\n" + replace + "\n"
            num_applied += 1
            continue
        
        # 4级模糊匹配
        matched, pos = _fuzzy_find_match(new_text, search)
        
        if pos != -1:
            new_text = new_text[:pos] + replace + new_text[pos + len(matched):]
            num_applied += 1
            continue
        
        if strict:
            first_line = search.splitlines()[0].strip() if search.splitlines() else ""
            return new_text, num_applied, (
                f"SEARCH text not found\nLooking for: {first_line!r}\n"
                "Hint: Check whitespace / Unicode characters"
            )
    
    return new_text, num_applied, None


def _fuzzy_find_match(text: str, search: str) -> Tuple[str, int]:
    """
    4级模糊查找（对齐 OpenSpace fuzzy_match）
    
    Returns: (matched_text, position)
    """
    lines = text.split("\n")
    pattern_lines = search.split("\n")
    
    # 级别 1: 精确
    idx = _seek_lines(lines, pattern_lines, exact=True)
    if idx != -1:
        return search, sum(len(l) + 1 for l in lines[:idx])
    
    # 级别 2: rstrip
    idx = _seek_lines(lines, pattern_lines, exact=False, strip_level=1)
    if idx != -1:
        return search, sum(len(l) + 1 for l in lines[:idx])
    
    # 级别 3: strip
    idx = _seek_lines(lines, pattern_lines, exact=False, strip_level=2)
    if idx != -1:
        return search, sum(len(l) + 1 for l in lines[:idx])
    
    return "", -1


def _apply_search_replace_to_file(patch_text: str, skill_file: Path) -> None:
    """将 SEARCH/REPLACE 块应用到文件"""
    original = skill_file.read_text(encoding="utf-8")
    updated, num_applied, error = apply_search_replace(patch_text, original)
    if error:
        raise PatchError(error)
    if num_applied == 0:
        raise PatchError("No SEARCH/REPLACE blocks found")
    _safe_write(skill_file, updated)
    # ↑ 用 search_replace 返回的 updated，已在 apply_search_replace 中处理


def _strip_trailing_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


# ═══════════════════════════════════════════════════════════════════
# Diff 和 Snapshot 工具
# ═══════════════════════════════════════════════════════════════════

def compute_unified_diff(
    original: str,
    updated: str,
    filename: str = SKILL_FILENAME,
    context: int = 3,
) -> str:
    """计算 unified diff（git diff 格式）"""
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=context,
    )
    return "".join(diff_lines)


def compute_skill_diff(old_dir: Path, new_dir: Path) -> str:
    """比较两个技能目录，返回合并的 diff"""
    old_files = _collect_files(old_dir) if old_dir.is_dir() else {}
    new_files = _collect_files(new_dir) if new_dir.is_dir() else {}
    return _compute_files_diff(old_files, new_files)


def collect_skill_snapshot(skill_dir: Path) -> Dict[str, str]:
    """收集技能目录中所有文本文件（排除 .skill_id）"""
    return _collect_files(skill_dir)


def _compute_files_diff(
    old_files: Dict[str, str],
    new_files: Dict[str, str],
) -> str:
    """从两个 snapshot 字典计算合并的 unified diff"""
    all_names = sorted(set(old_files) | set(new_files))
    parts = []
    for name in all_names:
        d = compute_unified_diff(
            old_files.get(name, ""),
            new_files.get(name, ""),
            filename=name,
        )
        if d:
            parts.append(d)
    return "\n".join(parts)


def _collect_files(directory: Path) -> Dict[str, str]:
    """
    收集目录中所有文本文件（递归）
    
    关键：排除 .skill_id sidecar 文件！
    这保证了 .skill_id 不进入 diff/snapshot
    """
    files: Dict[str, str] = {}
    if not directory.is_dir():
        return files
    
    for p in sorted(directory.rglob("*")):
        if p.is_file() and p.name != SKILL_ID_FILENAME:
            rel = str(p.relative_to(directory))
            try:
                files[rel] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                pass
    
    return files


# ═══════════════════════════════════════════════════════════════════
# Skill Quality Checker — gstack Superpowers TDD for Skills
# ═══════════════════════════════════════════════════════════════════

def check_skill_quality(skill_dir) -> dict:
    """
    检查 SKILL.md 是否符合 Superpowers 标准。
    返回：{score, issues, rationalizations, checklist}
    """
    import re

    skill_file = Path(skill_dir) / 'SKILL.md'
    if not skill_file.exists():
        return {'score': 0, 'issues': ['SKILL.md not found'], 'rationalizations': [], 'checklist': {}}

    content = skill_file.read_text(encoding='utf-8')

    issues = []
    rationalizations = []
    checklist = {}

    # 1. Description = 触发条件
    has_trigger = bool(re.search(r'(触发|When|Use case|适用场景)', content, re.I))
    has_workflow_dump = bool(re.search(r'步骤\d+[:：]', content))
    checklist['描述=触发条件'] = has_trigger and not has_workflow_dump
    if not has_trigger:
        issues.append('缺少触发条件描述')
    if has_workflow_dump:
        issues.append('Description 堆砌步骤，应描述触发条件')

    # 2. What it does > How to do it
    has_what = bool(re.search(r'(功能|做什么|What it does)', content))
    checklist['What>How'] = has_what

    # 3. 有 Examples
    has_examples = bool(re.search(r'(示例|Example|用法示例)', content, re.I))
    checklist['有示例'] = has_examples
    if not has_examples:
        issues.append('缺少用法示例')

    # 4. 无 secrets
    has_secrets = bool(re.search(r'(api_key|password|token|secret)', content, re.I))
    checklist['无secrets'] = not has_secrets
    if has_secrets:
        issues.append('不应包含 credentials')

    # 5. Rationalization 检测
    patterns = [
        (r'not.*necessary', '认为 skill 不必要'),
        (r'already.*know', '已经知道怎么做'),
        (r'don\'t need', '认为不需要'),
    ]
    for pat, desc in patterns:
        if re.search(pat, content, re.I):
            rationalizations.append(f'可能的借口模式: {desc}')

    score = sum(checklist.values()) * 25
    return {
        'score': score,
        'issues': issues,
        'rationalizations': rationalizations,
        'checklist': checklist,
    }


def quality_report(skills_dir=None) -> None:
    """输出所有 skill 的质量报告"""
    if skills_dir is None:
        skills_dir = Path(__file__).parent / 'skills'

    print('=== Skill Quality Report ===')
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        result = check_skill_quality(d)
        star = '★' * (result['score'] // 25)
        status = 'OK' if result['score'] >= 75 else ('WARN' if result['score'] >= 50 else 'BAD')
        print(f'  [{status}] {d.name}: {result["score"]}% {star}')
        for issue in result['issues']:
            print(f'       !! {issue}')
