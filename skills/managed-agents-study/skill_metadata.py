# -*- coding: utf-8 -*-
"""
skill_metadata.py — 技能元数据层 + 渐进式披露（Anthropic Managed Agents 落地）

对应 CMA 的 Skills 渐进式披露机制：
- 三层加载：Metadata → SKILL.md → 附加资源
- 上下文消耗从 16k → 500 token（按需触发）

核心设计：
- SkillFrontmatter：YAML frontmatter 解析（name/desc/version/tags/tier）
- SkillRegistry：扫描 + 索引所有技能的元数据层
- ProgressiveLoader：按需加载，不一次全部注入上下文
- Token 估算：每层加载前估算 token 消耗

与 CMA 对照：
  CMA: Skills = 模块化知识胶囊，discover → understand → load-on-demand
  qclaw: SkillFrontmatter(Tier0) → SKILL.md(Tier1) → resources(Tier2)
"""

from __future__ import annotations

import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum

log = logging.getLogger("qclaw.skill_metadata")

# ─── 技能目录 ─────────────────────────────────────────────

SKILLS_DIR = Path(r"C:\Users\yiseg\.qclaw\workspace\skills")
BUNDLED_SKILLS_DIR = Path(r"E:\qclaw\resources\openclaw\config\skills")
MANAGED_SKILLS_DIR = Path(r"C:\Users\yiseg\.qclaw\skills")


# ─── 渐进式披露层级 ───────────────────────────────────────

class DisclosureTier(Enum):
    """渐进式披露三层"""
    METADATA = 0      # ~100 token：name + description + tags
    SKILL_MD = 1      # ~1-5k token：完整 SKILL.md 内容
    RESOURCES = 2     # 按需：脚本/文档/代码文件


# ─── Frontmatter 解析 ─────────────────────────────────────

@dataclass
class SkillFrontmatter:
    """
    YAML frontmatter 数据结构（Tier 0: Metadata）
    
    从 SKILL.md 的 --- 之间的 YAML 解析而来。
    这是渐进式披露的第一层：启动时扫描所有技能的 frontmatter，
    只注入 name + description，不加载完整内容。
    """
    name: str = ""
    description: str = ""
    version: str = "0.0.0"
    tags: List[str] = field(default_factory=list)
    tier: str = "standard"         # standard / advanced / expert
    requires: List[str] = field(default_factory=list)  # 依赖的其他技能
    token_estimate: Dict[str, int] = field(default_factory=dict)  # 各层 token 估算
    
    # 内部字段
    _skill_dir: Path = field(default_factory=lambda: Path("."), repr=False)
    _raw_frontmatter: str = ""

    def estimate_tokens(self, tier: DisclosureTier = DisclosureTier.METADATA) -> int:
        """估算指定层的 token 消耗"""
        if self.token_estimate:
            tier_name = tier.name.lower()
            return self.token_estimate.get(tier_name, 0)
        # 默认估算
        if tier == DisclosureTier.METADATA:
            return 100
        elif tier == DisclosureTier.SKILL_MD:
            return 3000
        else:
            return 5000

    def to_index_entry(self) -> str:
        """生成索引条目（Tier 0 输出格式）"""
        tags_str = ", ".join(self.tags[:5]) if self.tags else "none"
        return f"- {self.name}: {self.description[:80]} [{tags_str}]"


def parse_frontmatter(skill_md_path: Path) -> SkillFrontmatter:
    """
    解析 SKILL.md 的 YAML frontmatter
    
    支持格式：
    ---
    name: my-skill
    description: ...
    version: 1.0.0
    tags: [a, b, c]
    ---
    
    # Skill content follows...
    """
    content = ""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning(f"Cannot read {skill_md_path}: {e}")
        return SkillFrontmatter(_skill_dir=skill_md_path.parent)

    # 提取 frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match:
        # 无 frontmatter，从文件名推断
        name = skill_md_path.parent.name or skill_md_path.stem
        return SkillFrontmatter(
            name=name,
            description="(no frontmatter)",
            _skill_dir=skill_md_path.parent,
        )

    fm_text = fm_match.group(1)
    fm = SkillFrontmatter(
        _skill_dir=skill_md_path.parent,
        _raw_frontmatter=fm_text,
    )

    # 简易 YAML 解析（不引入 pyyaml 依赖）
    for line in fm_text.split("\n"):
        line = line.strip()
        if line.startswith("name:"):
            fm.name = line.split(":", 1)[1].strip().strip("'\"")
        elif line.startswith("description:"):
            desc = line.split(":", 1)[1].strip().strip("'\"")
            # 处理多行 description 的第一行
            if desc.startswith(">"):
                desc = desc[1:].strip()
            fm.description = desc[:200]
        elif line.startswith("version:"):
            fm.version = line.split(":", 1)[1].strip().strip("'\"")
        elif line.startswith("tags:"):
            tags_str = line.split(":", 1)[1].strip()
            if tags_str.startswith("["):
                fm.tags = [t.strip().strip("'\"") for t in tags_str.strip("[]").split(",")]
        elif line.startswith("tier:"):
            fm.tier = line.split(":", 1)[1].strip().strip("'\"")

    # 估算 token
    fm.token_estimate = {
        "metadata": 100,
        "skill_md": max(500, len(content) // 4),   # 粗略估算
        "resources": fm.token_estimate.get("resources", 5000),
    }

    return fm


# ─── 技能注册表 ───────────────────────────────────────────

class SkillRegistry:
    """
    技能注册表：扫描 + 索引所有技能的元数据层
    
    启动时只扫描 frontmatter（Tier 0），不加载完整 SKILL.md。
    按需加载时才读取 Tier 1/2 内容。
    """

    def __init__(self, skills_dirs: List[Path] = None):
        self.skills_dirs = skills_dirs or [SKILLS_DIR, BUNDLED_SKILLS_DIR, MANAGED_SKILLS_DIR]
        self._index: Dict[str, SkillFrontmatter] = {}  # name → frontmatter
        self._loaded_tier: Dict[str, DisclosureTier] = {}  # name → 已加载到的层级

    def scan(self) -> int:
        """
        扫描所有技能目录，构建 Tier 0 索引
        
        Returns: 发现的技能数量
        """
        self._index.clear()
        for skills_dir in self.skills_dirs:
            if not skills_dir.exists():
                continue
            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    fm = parse_frontmatter(skill_md)
                    if fm.name:
                        self._index[fm.name] = fm
                        self._loaded_tier[fm.name] = DisclosureTier.METADATA
        return len(self._index)

    def list_skills(self, tag: str = None) -> List[SkillFrontmatter]:
        """列出所有已索引的技能（Tier 0）"""
        skills = list(self._index.values())
        if tag:
            skills = [s for s in skills if tag in s.tags]
        return skills

    def get_metadata(self, name: str) -> Optional[SkillFrontmatter]:
        """获取技能的 Tier 0 元数据"""
        return self._index.get(name)

    def load_skill_md(self, name: str) -> Optional[str]:
        """
        加载技能的 Tier 1 内容（完整 SKILL.md）
        
        对应 CMA 的 "understand" 阶段。
        """
        fm = self._index.get(name)
        if not fm:
            return None
        skill_md = fm._skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        self._loaded_tier[name] = DisclosureTier.SKILL_MD
        return skill_md.read_text(encoding="utf-8")

    def load_resource(self, name: str, resource_path: str) -> Optional[str]:
        """
        加载技能的 Tier 2 资源文件
        
        对应 CMA 的 "load-on-demand" 阶段。
        """
        fm = self._index.get(name)
        if not fm:
            return None
        resource = fm._skill_dir / resource_path
        if not resource.exists():
            return None
        # 安全检查：防止路径遍历
        try:
            resource.resolve().relative_to(fm._skill_dir.resolve())
        except ValueError:
            log.warning(f"Path traversal blocked: {resource_path}")
            return None
        self._loaded_tier[name] = DisclosureTier.RESOURCES
        return resource.read_text(encoding="utf-8")

    def generate_index_text(self) -> str:
        """
        生成 Tier 0 索引文本（注入 system prompt 用）
        
        格式：每个技能一行，包含 name + description + tags
        总 token 消耗 ≈ 技能数 × 100
        """
        lines = ["# Available Skills (metadata only, load on demand)", ""]
        for fm in sorted(self._index.values(), key=lambda f: f.name):
            lines.append(fm.to_index_entry())
        lines.append("")
        lines.append(f"Total: {len(self._index)} skills. Use load_skill_md(name) for details.")
        return "\n".join(lines)

    def token_budget_for_tier(self, tier: DisclosureTier) -> int:
        """估算加载所有技能到指定层的总 token 消耗"""
        return sum(fm.estimate_tokens(tier) for fm in self._index.values())


# ─── 便捷函数 ─────────────────────────────────────────────

_registry: Optional[SkillRegistry] = None

def get_registry() -> SkillRegistry:
    """获取全局 SkillRegistry 实例"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.scan()
    return _registry
