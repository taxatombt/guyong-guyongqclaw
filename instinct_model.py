# -*- coding: utf-8 -*-
"""
instinct_model.py — ECC instinct 格式解析器 + 项目级隔离

参考：ECC continuous-learning-v2 instinct-cli.py（1700行，MIT License）
适配：qclaw evolver.py v2.2

与 evolver.py 的关系：
- evolver.py 负责规则引擎（Rule/task/method）
- instinct_model.py 负责原子行为模型（Instinct/trigger/action）
- 两者互补：Rule = "最佳方法"，Instinct = "为什么这样做"

ECC instinct 格式：
---
id: prefer-functional-style
trigger: "when writing new functions"
confidence: 0.7
domain: "code-style"
source: "session-observation"
scope: project
project_id: "a1b2c3d4e5f6"
---
# Prefer Functional Style

## Action
Use functional patterns over classes when appropriate.

## Evidence
- Observed 5 instances of functional pattern preference
- User corrected class-based approach to functional on 2025-01-15
"""

import json
import re
import hashlib
import os
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime, timezone

WORKSPACE = Path(__file__).parent

# ═══════════════════════════════════════════════════════
# 路径配置
# ═══════════════════════════════════════════════════════

HOMUNCULUS_DIR = WORKSPACE / ".homunculus"
INSTINCTS_DIR = HOMUNCULUS_DIR / "instincts"
PROJECTS_DIR = HOMUNCULUS_DIR / "projects"
REGISTRY_FILE = HOMUNCULUS_DIR / "projects.json"

GLOBAL_PERSONAL_DIR = INSTINCTS_DIR / "personal"
GLOBAL_INHERITED_DIR = INSTINCTS_DIR / "inherited"
GLOBAL_EVOLVED_DIR = HOMUNCULUS_DIR / "evolved"

PROMOTE_MIN_PROJECTS = 2
PROMOTE_CONFIDENCE_THRESHOLD = 0.8
ALLOWED_EXTENSIONS = (".yaml", ".yml", ".md")


# ═══════════════════════════════════════════════════════
# Instinct 数据类
# ═══════════════════════════════════════════════════════

@dataclass
class Instinct:
    """ECC instinct 格式的内存表示"""
    id: str
    trigger: str
    confidence: float
    domain: str = "general"
    source: str = "session-observation"
    scope: str = "project"  # "project" or "global"
    project_id: str = ""
    project_name: str = ""
    source_repo: str = ""
    created: str = ""
    content: str = ""

    def __post_init__(self):
        if not self.created:
            self.created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def to_yaml_frontmatter(self) -> str:
        """转化为 YAML frontmatter 字符串"""
        lines = ["---"]
        lines.append(f"id: {self.id}")
        lines.append(f"trigger: \"{self.trigger.replace('\\', '\\\\').replace('"', '\\"')}\"")
        lines.append(f"confidence: {self.confidence}")
        lines.append(f"domain: {self.domain}")
        lines.append(f"source: {self.source}")
        lines.append(f"scope: {self.scope}")
        if self.project_id:
            lines.append(f"project_id: {self.project_id}")
        if self.project_name:
            lines.append(f"project_name: {self.project_name}")
        if self.source_repo:
            lines.append(f"source_repo: {self.source_repo}")
        lines.append(f"created: {self.created}")
        lines.append("---")
        return "\n".join(lines)

    def to_yaml_file(self) -> str:
        """完整的 YAML 文件内容"""
        return self.to_yaml_frontmatter() + "\n\n" + self.content

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Instinct":
        """从字典创建 Instinct"""
        known = {f.name for f in Instinct.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return Instinct(**filtered)


# ═══════════════════════════════════════════════════════
# Instinct 解析器（来自 ECC instinct-cli.py）
# ═══════════════════════════════════════════════════════

def parse_instinct_file(content: str) -> list[Instinct]:
    """解析 YAML instinct 文件，支持 --- frontmatter 分隔"""
    instincts = []
    current = {}
    in_frontmatter = False
    content_lines = []

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "---":
            if in_frontmatter:
                in_frontmatter = False
                if current:
                    current["content"] = "\n".join(content_lines).strip()
                    try:
                        instincts.append(Instinct.from_dict(current))
                    except Exception:
                        pass
                current = {}
                content_lines = []
            else:
                in_frontmatter = True
        elif in_frontmatter:
            if ": " in line:
                key, value = line.split(": ", 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                if key == "confidence":
                    try:
                        current[key] = float(value)
                    except ValueError:
                        current[key] = 0.5
                elif value:
                    current[key] = value
        else:
            content_lines.append(line)

    if current:
        current["content"] = "\n".join(content_lines).strip()
        try:
            instincts.append(Instinct.from_dict(current))
        except Exception:
            pass

    return [i for i in instincts if i.id]


# ═══════════════════════════════════════════════════════
# 项目检测（来自 ECC detect-project 逻辑）
# ═══════════════════════════════════════════════════════

def detect_project() -> dict:
    """
    检测当前项目上下文，返回项目信息字典。
    优先级：CLAUDE_PROJECT_DIR > git remote > workspace hash
    """
    project_root = None

    # 1. CLAUDE_PROJECT_DIR 环境变量
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir and os.path.isdir(env_dir):
        project_root = env_dir

    # 2. git repo root
    if not project_root:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                project_root = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if project_root:
        project_root = project_root.rstrip("/")

    # 全局 fallback
    if not project_root:
        return {
            "id": "global",
            "name": "global",
            "root": "",
            "project_dir": HOMUNCULUS_DIR,
            "instincts_personal": GLOBAL_PERSONAL_DIR,
            "instincts_inherited": GLOBAL_INHERITED_DIR,
            "evolved_dir": GLOBAL_EVOLVED_DIR,
        }

    project_name = os.path.basename(project_root)

    # git remote URL → hash 作为项目ID（跨机器一致）
    remote_url = ""
    try:
        result = subprocess.run(
            ["git", "-C", project_root, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            remote_url = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    hash_source = remote_url if remote_url else str(project_root)
    project_id = hashlib.sha256(hash_source.encode()).hexdigest()[:12]

    project_dir = PROJECTS_DIR / project_id

    # 确保目录存在
    for d in [
        project_dir / "instincts" / "personal",
        project_dir / "instincts" / "inherited",
        project_dir / "evolved" / "skills",
        project_dir / "evolved" / "commands",
        project_dir / "evolved" / "agents",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # 更新 registry
    _update_registry(project_id, project_name, project_root, remote_url)

    return {
        "id": project_id,
        "name": project_name,
        "root": project_root,
        "remote": remote_url,
        "project_dir": project_dir,
        "instincts_personal": project_dir / "instincts" / "personal",
        "instincts_inherited": project_dir / "instincts" / "inherited",
        "evolved_dir": project_dir / "evolved",
    }


def _update_registry(pid: str, pname: str, proot: str, premote: str):
    """更新 projects.json 注册表"""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        registry = {}

    registry[pid] = {
        "name": pname,
        "root": proot,
        "remote": premote,
        "last_seen": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def load_registry() -> dict:
    """加载 projects 注册表"""
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ═══════════════════════════════════════════════════════
# Instinct 加载器
# ═══════════════════════════════════════════════════════

def _load_from_dir(directory: Path, source_type: str, scope_label: str) -> list[Instinct]:
    """从目录加载所有 instinct 文件"""
    instincts = []
    if not directory.exists():
        return instincts
    for file in sorted(directory.iterdir()):
        if not (file.is_file() and file.suffix.lower() in ALLOWED_EXTENSIONS):
            continue
        try:
            content = file.read_text(encoding="utf-8")
            for inst in parse_instinct_file(content):
                inst.source = source_type
                inst.scope = scope_label
                instincts.append(inst)
        except Exception as e:
            print(f"[instinct_model] 解析失败 {file}: {e}", file=sys.stderr)
    return instincts


def load_all_instincts(project: Optional[dict] = None) -> list[Instinct]:
    """
    加载所有 instincts：项目级 + 全局。
    项目级优先于全局（同名时）。
    """
    if project is None:
        project = detect_project()

    instincts = []

    # 1. 项目级 instincts
    if project["id"] != "global":
        instincts.extend(_load_from_dir(project["instincts_personal"], "personal", "project"))
        instincts.extend(_load_from_dir(project["instincts_inherited"], "inherited", "project"))

    # 2. 全局 instincts（同名不覆盖项目级）
    global_instincts = []
    global_instincts.extend(_load_from_dir(GLOBAL_PERSONAL_DIR, "personal", "global"))
    global_instincts.extend(_load_from_dir(GLOBAL_INHERITED_DIR, "inherited", "global"))

    project_ids = {i.id for i in instincts}
    for gi in global_instincts:
        if gi.id not in project_ids:
            instincts.append(gi)

    return instincts


def load_project_instincts(project: Optional[dict] = None) -> list[Instinct]:
    """仅加载项目级 instincts（不含全局）"""
    if project is None:
        project = detect_project()
    if project["id"] == "global":
        instincts = _load_from_dir(GLOBAL_PERSONAL_DIR, "personal", "global")
        instincts.extend(_load_from_dir(GLOBAL_INHERITED_DIR, "inherited", "global"))
        return instincts
    instincts = _load_from_dir(project["instincts_personal"], "personal", "project")
    instincts.extend(_load_from_dir(project["instincts_inherited"], "inherited", "project"))
    return instincts


# ═══════════════════════════════════════════════════════
# Instinct 存储
# ═══════════════════════════════════════════════════════

def save_instinct(instinct: Instinct, overwrite: bool = False) -> Path:
    """保存 instinct 到对应目录"""
    # 确保所有父目录存在
    HOMUNCULUS_DIR.mkdir(parents=True, exist_ok=True)
    INSTINCTS_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_PERSONAL_DIR.mkdir(parents=True, exist_ok=True)

    if instinct.scope == "global":
        output_dir = GLOBAL_PERSONAL_DIR
    else:
        project = detect_project()
        if instinct.project_id:
            output_dir = PROJECTS_DIR / instinct.project_id / "instincts" / "personal"
        else:
            output_dir = project["instincts_personal"]
        output_dir.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", instinct.id)
    output_file = output_dir / f"{safe_id}.yaml"

    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Instinct '{instinct.id}' 已存在，使用 overwrite=True 覆盖")

    output_file.write_text(instinct.to_yaml_file(), encoding="utf-8")
    return output_file


# ═══════════════════════════════════════════════════════
# Instinct 创建辅助
# ═══════════════════════════════════════════════════════

DOMAIN_SUGGESTIONS = [
    "code-style", "testing", "git", "debugging", "workflow",
    "security", "performance", "architecture", "documentation", "general"
]


def create_instinct(
    id: str,
    trigger: str,
    action: str,
    confidence: float = 0.5,
    domain: str = "general",
    source: str = "session-observation",
    evidence: Optional[list[str]] = None,
    scope: Optional[str] = None,
) -> Instinct:
    """
    创建 instinct 的辅助函数。

    示例：
    ```python
    inst = create_instinct(
        id="grep-before-edit",
        trigger="when editing an existing file",
        action="Use Grep to search before Edit to understand context",
        confidence=0.7,
        domain="workflow",
        evidence=["User corrected: jumped straight to Edit"],
    )
    save_instinct(inst)
    ```
    """
    project = detect_project()

    # 构建 content
    content_parts = [f"# {id.replace('-', ' ').title()}"]
    content_parts.append("")
    content_parts.append("## Action")
    content_parts.append(action)
    if evidence:
        content_parts.append("")
        content_parts.append("## Evidence")
        for e in evidence:
            content_parts.append(f"- {e}")

    inst = Instinct(
        id=id,
        trigger=trigger,
        confidence=min(max(confidence, 0.3), 0.9),
        domain=domain,
        source=source,
        scope=scope or ("project" if project["id"] != "global" else "global"),
        project_id=project.get("id", ""),
        project_name=project.get("name", ""),
        content="\n".join(content_parts),
    )
    return inst


# ═══════════════════════════════════════════════════════
# promote 系统（ECC 核心机制）
# ═══════════════════════════════════════════════════════

def find_cross_project_instincts() -> dict:
    """找到出现在多个项目中的 instinct（promote 候选）"""
    registry = load_registry()
    cross_project = {}

    for pid in registry.keys():
        personal_dir = PROJECTS_DIR / pid / "instincts" / "personal"
        inherited_dir = PROJECTS_DIR / pid / "instincts" / "inherited"

        seen_in_project = set()
        for instinct_list in [
            _load_from_dir(personal_dir, "personal", "project"),
            _load_from_dir(inherited_dir, "inherited", "project"),
        ]:
            for inst in instinct_list:
                if inst.id not in seen_in_project:
                    seen_in_project.add(inst.id)
                    if inst.id not in cross_project:
                        cross_project[inst.id] = []
                    cross_project[inst.id].append((pid, registry[pid].get("name", pid), inst))

    # 只保留出现在 2+ 项目中的
    return {
        iid: entries
        for iid, entries in cross_project.items()
        if len(entries) >= PROMOTE_MIN_PROJECTS
    }


def get_promotion_candidates() -> list[dict]:
    """获取符合 promote 条件的 instinct"""
    cross = find_cross_project_instincts()
    global_personal = _load_from_dir(GLOBAL_PERSONAL_DIR, "personal", "global")
    global_inherited = _load_from_dir(GLOBAL_INHERITED_DIR, "inherited", "global")
    global_ids = {i.id for i in global_personal + global_inherited}

    candidates = []
    for iid, entries in cross.items():
        if iid in global_ids:
            continue
        avg_conf = sum(e[2].confidence for e in entries) / len(entries)
        if avg_conf >= PROMOTE_CONFIDENCE_THRESHOLD:
            candidates.append({
                "id": iid,
                "projects": [(pid, pinfo.get("name", pid)) for pid, pinfo, _ in entries],
                "avg_confidence": avg_conf,
                "sample": entries[0][2],
            })

    return sorted(candidates, key=lambda x: -x["avg_confidence"])


def promote_instinct(instinct_id: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    将 instinct 从项目级 promote 到全局。

    返回：(success, message)
    """
    project = detect_project()
    project_instincts = load_project_instincts(project)
    target = next((i for i in project_instincts if i.id == instinct_id), None)

    if not target:
        return False, f"Instinct '{instinct_id}' 在当前项目不存在"

    # 检查是否已是全局
    global_instincts = _load_from_dir(GLOBAL_PERSONAL_DIR, "personal", "global")
    global_instincts += _load_from_dir(GLOBAL_INHERITED_DIR, "inherited", "global")
    if any(i.id == instinct_id for i in global_instincts):
        return False, f"Instinct '{instinct_id}' 已是全局 scope"

    if dry_run:
        return True, f"[DRY RUN] 会将 '{instinct_id}' promote 到全局"

    # 写入全局目录
    GLOBAL_PERSONAL_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", instinct_id)
    output_file = GLOBAL_PERSONAL_DIR / f"{safe_id}.yaml"

    promoted = Instinct(
        id=target.id,
        trigger=target.trigger,
        confidence=target.confidence,
        domain=target.domain,
        source="promoted",
        scope="global",
        project_id="",
        project_name="",
        content=target.content,
    )
    output_file.write_text(promoted.to_yaml_file(), encoding="utf-8")
    return True, f"已 promote '{instinct_id}' 到全局 scope → {output_file}"


# ═══════════════════════════════════════════════════════
# import / export
# ═══════════════════════════════════════════════════════

def export_instincts(
    output_path: Path,
    domain: Optional[str] = None,
    min_confidence: Optional[float] = None,
    scope: Optional[str] = None,  # "project" | "global" | None (all)
) -> int:
    """导出 instincts 到文件"""
    project = detect_project()

    if scope == "project":
        instincts = load_project_instincts(project)
    elif scope == "global":
        instincts = _load_from_dir(GLOBAL_PERSONAL_DIR, "personal", "global")
        instincts += _load_from_dir(GLOBAL_INHERITED_DIR, "inherited", "global")
    else:
        instincts = load_all_instincts(project)

    if domain:
        instincts = [i for i in instincts if i.domain == domain]
    if min_confidence is not None:
        instincts = [i for i in instincts if i.confidence >= min_confidence]

    if not instincts:
        return 0

    lines = [
        f"# Instincts Export",
        f"# Date: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"# Total: {len(instincts)}",
        f"# Scope: {scope or 'all'}",
        "",
    ]
    for inst in instincts:
        lines.append(inst.to_yaml_file())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(instincts)


def import_instincts(source_path: Path, overwrite: bool = False) -> tuple[int, int, int]:
    """
    从文件导入 instincts。
    返回：(added, updated, skipped)
    """
    content = source_path.read_text(encoding="utf-8")
    new_instincts = parse_instinct_file(content)
    if not new_instincts:
        return 0, 0, 0

    project = detect_project()
    existing = load_project_instincts(project)
    existing_ids = {i.id for i in existing}

    # 去重：同 ID 取最高 confidence
    best = {}
    for inst in new_instincts:
        if inst.id not in best or inst.confidence > best[inst.id].confidence:
            best[inst.id] = inst

    added = updated = skipped = 0
    for inst in best.values():
        if inst.id in existing_ids:
            exist = next(i for i in existing if i.id == inst.id)
            if inst.confidence > exist.confidence:
                save_instinct(inst, overwrite=True)
                updated += 1
            else:
                skipped += 1
        else:
            save_instinct(inst)
            added += 1

    return added, updated, skipped


# ═══════════════════════════════════════════════════════
# 状态显示
# ═══════════════════════════════════════════════════════

def status_text() -> str:
    """生成 instinct 状态报告"""
    project = detect_project()
    instincts = load_all_instincts(project)

    project_instincts = [i for i in instincts if i.scope == "project"]
    global_instincts = [i for i in instincts if i.scope == "global"]

    SEP = "=" * 50
    lines = [SEP,
             f"  INSTINCT STATUS — {len(instincts)} total",
             SEP,
             f"  Project: {project['name']} ({project['id']})",
             f"  Project instincts: {len(project_instincts)}",
             f"  Global instincts:  {len(global_instincts)}",
             ""]

    if project_instincts:
        lines.append("## PROJECT-SCOPED")
        lines.append("")
        _print_by_domain(lines, project_instincts)

    if global_instincts:
        lines.append("## GLOBAL (all projects)")
        lines.append("")
        _print_by_domain(lines, global_instincts)

    # promote 候选
    candidates = get_promotion_candidates()
    if candidates:
        lines.append("-" * 50)
        lines.append(f"  Promote candidates: {len(candidates)}")
        for c in candidates[:5]:
            proj_names = ", ".join(p[1] for p in c["projects"][:3])
            lines.append(f"  * {c['id']} (avg {c['avg_confidence']:.0%}) in: {proj_names}")

    lines.append(SEP)
    return "\n".join(lines)


def _print_by_domain(lines: list, instincts: list[Instinct]):
    from collections import defaultdict
    by_domain = defaultdict(list)
    for inst in instincts:
        by_domain[inst.domain].append(inst)

    for domain in sorted(by_domain.keys()):
        domain_instincts = sorted(by_domain[domain], key=lambda x: -x.confidence)
        lines.append(f"  ### {domain.upper()} ({len(domain_instincts)})")
        lines.append("")
        for inst in domain_instincts:
            filled = int(inst.confidence * 10)
            empty = 10 - filled
            conf_bar = "#" * filled + "-" * empty
            lines.append(f"    [{conf_bar}] {int(inst.confidence*100):3d}%  {inst.id} [{inst.scope}]")
            lines.append(f"      trigger: {inst.trigger}")
        lines.append("")


# ═══════════════════════════════════════════════════════
# evolver.py 集成接口
# ═══════════════════════════════════════════════════════

def instinct_from_rule(rule_dict: dict) -> Instinct:
    """
    将 evolver.py 的 Rule dict 转换为 Instinct。
    用于：Rule → Instinct 双向迁移。
    """
    task = rule_dict.get("task", "unknown-task")
    method = rule_dict.get("method", "default-method")
    confidence = rule_dict.get("confidence", 0.5)

    instinct_id = f"rule-{task}-{method}".replace(" ", "-").lower()[:60]
    instinct_id = re.sub(r"[^a-z0-9_-]", "", instinct_id)

    inst = create_instinct(
        id=instinct_id,
        trigger=f"when task involves: {task}",
        action=f"Use method: {method}",
        confidence=confidence,
        domain="workflow",
        evidence=[
            f"Observed in evolver_db: task={task}, method={method}",
            f"confidence={confidence}",
        ],
        scope="global",
    )
    return inst


# ═══════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ECC instinct CLI for qclaw")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show instinct status")
    sub.add_parser("promote-candidates", help="Show promote candidates")

    args = parser.parse_args()

    if args.cmd == "status":
        print(status_text())
    elif args.cmd == "promote-candidates":
        for c in get_promotion_candidates():
            print(f"  {c['id']} ({c['avg_confidence']:.0%}) in: {[p[1] for p in c['projects']]}")
    else:
        parser.print_help()
