# -*- coding: utf-8 -*-
"""
skill_evolution/registry.py — qclaw 技能注册表（适配 OpenSpace）

功能：
- 发现 qclaw 的 skill 目录中的技能
- 维护 skill_id → 技能记录的映射
- 支持 .skill_id sidecar 持久化
- 生成 skill_id（对齐 OpenSpace）

来源：HKUDS/OpenSpace skill_engine/registry.py
"""

import json
import re
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .types import (
    EvolutionType, SkillOrigin, SkillCategory,
    SkillLineage, SkillMetrics, SkillRecord
)


WORKSPACE = Path(__file__).parent.parent  # qclaw workspace
SKILLS_DIR = WORKSPACE / "skills"         # qclaw skill 目录
DB_FILE = WORKSPACE / ".skill_evolution_db.json"


# ═══════════════════════════════════════════════════════════════════
# 技能注册表
# ═══════════════════════════════════════════════════════════════════

class SkillRegistry:
    """
    qclaw 的技能注册表（适配 OpenSpace registry.py）
    
    核心功能：
    - 从 qclaw skill 目录发现技能
    - 管理 skill_id 和技能记录
    - 维护 Version DAG（通过 lineage）
    - 与 qclaw 的 evolver.py 联动
    """
    
    def __init__(self):
        self.db = self._load_db()
        self._discover_all()
    
    def _load_db(self) -> Dict[str, Any]:
        if DB_FILE.exists():
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"skills": {}, "lineages": {}}
    
    def _save_db(self):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)
    
    def _discover_all(self):
        """发现所有 qclaw skill 目录中的技能"""
        # qclaw skill 目录
        qclaw_skills = Path("C:/Users/yiseg/.qclaw/skills")
        if qclaw_skills.exists():
            self._scan_skill_dir(qclaw_skills, origin=SkillOrigin.IMPORTED)
        
        # openclaw workspace skills
        workspace_skills = Path("C:/Users/yiseg/.openclaw/workspace/skills")
        if workspace_skills.exists():
            self._scan_skill_dir(workspace_skills, origin=SkillOrigin.IMPORTED)
    
    def _scan_skill_dir(self, skills_root: Path, origin: SkillOrigin):
        """扫描技能目录，发现所有 SKILL.md"""
        if not skills_root.exists():
            return
        
        for skill_dir in skills_root.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith("."):
                continue  # 跳过隐藏目录
            
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            
            skill_id = self._read_skill_id(skill_dir)
            if not skill_id:
                skill_id = self._generate_skill_id(skill_dir.name, origin)
                self._write_skill_id(skill_dir, skill_id)
            
            if skill_id not in self.db["skills"]:
                skill = self._create_skill_record(
                    skill_id, skill_dir, origin,
                    description=self._read_description(skill_file)
                )
                self.db["skills"][skill_id] = skill.to_dict()
    
    def _read_skill_id(self, skill_dir: Path) -> Optional[str]:
        """读取 .skill_id sidecar"""
        id_file = skill_dir / ".skill_id"
        if id_file.exists():
            try:
                content = id_file.read_text(encoding="utf-8").strip()
                return content if content else None
            except OSError:
                pass
        return None
    
    def _write_skill_id(self, skill_dir: Path, skill_id: str):
        """写入 .skill_id sidecar"""
        try:
            (skill_dir / ".skill_id").write_text(skill_id + "\n", encoding="utf-8")
        except OSError:
            pass
    
    def _generate_skill_id(
        self,
        name: str,
        origin: SkillOrigin,
        fix_version: int = 0,
        content_hash: str = "",
        parent_skill_id: str = ""
    ) -> str:
        """
        生成 skill_id（对齐 OpenSpace registry.py）

        格式：
        - 导入：{name}__imp_{uuid8}
        - CAPTURED/DERIVED：{name}__v0_{uuid8}
        - FIX：{name}__v{fix_version}_{parent_hash8}
          （保持父节点 hash，只改变 v{n}）
        """
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)[:50]

        if origin == SkillOrigin.IMPORTED:
            suffix = uuid.uuid4().hex[:8]
            return f"{safe_name}__imp_{suffix}"

        # CAPTURED / DERIVED：新建 uuid
        if origin in (SkillOrigin.CAPTURED, SkillOrigin.DERIVED):
            suffix = uuid.uuid4().hex[:8]
            return f"{safe_name}__v0_{suffix}"

        # FIX：复用父节点 hash（核心区别）
        if origin == SkillOrigin.FIXED:
            # 从父 skill_id 提取 hash
            if parent_skill_id:
                parts = parent_skill_id.split("__")
                if len(parts) >= 2:
                    parent_hash = parts[-1]  # e.g. "v0_59f433fe" → "59f433fe"
                    if "_" in parent_hash:
                        parent_hash = parent_hash.split("_")[-1]
                else:
                    parent_hash = uuid.uuid4().hex[:8]
            else:
                parent_hash = uuid.uuid4().hex[:8]
            fix_str = f"v{fix_version}"
            return f"{safe_name}__{fix_str}_{parent_hash}"

        # fallback
        suffix = uuid.uuid4().hex[:8]
        return f"{safe_name}__imp_{suffix}"
    
    def _read_description(self, skill_file: Path) -> str:
        """从 SKILL.md 读取 description"""
        try:
            content = skill_file.read_text(encoding="utf-8")
            # 尝试从 frontmatter 读取
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                for line in fm_match.group(1).split("\n"):
                    if line.startswith("description:"):
                        return line.split(":", 1)[1].strip().strip('"').strip("'")
            # 否则用文件名
            return skill_file.parent.name
        except OSError:
            return skill_file.parent.name
    
    def _create_skill_record(
        self,
        skill_id: str,
        skill_dir: Path,
        origin: SkillOrigin,
        description: str = ""
    ) -> SkillRecord:
        """从目录创建技能记录"""
        skill_file = skill_dir / "SKILL.md"
        
        lineage = SkillLineage(
            origin=origin,
            generation=0,
            parent_skill_ids=[],
            source_task_id=f"discovered:{skill_dir.name}",
            change_summary=f"Discovered from {skill_dir.parent.name}",
        )
        
        metrics = SkillMetrics(
            total_selections=0,
            applied_count=0,
            completions=0,
        )
        
        return SkillRecord(
            skill_id=skill_id,
            name=skill_dir.name,
            description=description,
            path=str(skill_file),
            category=SkillCategory.WORKFLOW,
            lineage=lineage,
            metrics=metrics,
            is_active=True,
            version="v1.0",
            fix_version=0,
        )
    
    # ═══════════════════════════════════════════════════════════════
    # 查询接口
    # ═══════════════════════════════════════════════════════════════
    
    def get_skill(self, skill_id: str) -> Optional[SkillRecord]:
        """获取技能记录"""
        data = self.db["skills"].get(skill_id)
        if data:
            return SkillRecord.from_dict(data)
        return None
    
    def get_all_skills(self, active_only: bool = True) -> List[SkillRecord]:
        """获取所有技能"""
        skills = []
        for skill_id, data in self.db["skills"].items():
            if active_only and not data.get("is_active"):
                continue
            skills.append(SkillRecord.from_dict(data))
        return skills
    
    def list_skills(self, active_only: bool = True) -> List[Dict]:
        """列出技能（简洁格式）"""
        skills = []
        for skill_id, data in self.db["skills"].items():
            if active_only and not data.get("is_active"):
                continue
            lineage = data.get("lineage", {})
            metrics = data.get("metrics", {})
            skills.append({
                "skill_id": skill_id,
                "name": data.get("name", ""),
                "category": data.get("category", ""),
                "origin": lineage.get("origin", ""),
                "generation": lineage.get("generation", 0),
                "fix_version": data.get("fix_version", 0),
                "confidence": metrics.get("confidence", 0.0),
                "effective_rate": metrics.get("effective_rate", 0.0),
                "is_active": data.get("is_active", True),
            })
        skills.sort(key=lambda x: x["confidence"], reverse=True)
        return skills
    
    def get_dag(self) -> Dict[str, Any]:
        """获取 Version DAG"""
        nodes = []
        edges = []
        
        for skill_id, data in self.db["skills"].items():
            lineage = data.get("lineage", {})
            nodes.append({
                "id": skill_id,
                "name": data.get("name", ""),
                "generation": lineage.get("generation", 0),
                "origin": lineage.get("origin", ""),
                "is_active": data.get("is_active", True),
                "confidence": data.get("metrics", {}).get("confidence", 0.0),
            })
            for parent_id in lineage.get("parent_skill_ids", []):
                edges.append({"source": parent_id, "target": skill_id})
        
        return {"nodes": nodes, "links": edges}
    
    def update_metrics(self, skill_id: str, **kwargs):
        """更新技能指标"""
        if skill_id not in self.db["skills"]:
            return
        
        metrics = self.db["skills"][skill_id].get("metrics", {})
        for key, value in kwargs.items():
            if key in metrics or key in ["total_selections", "applied_count", "completions", "fallbacks", "confidence"]:
                metrics[key] = value
        
        # 重新计算比率
        if "total_selections" in kwargs or "applied_count" in kwargs:
            ts = metrics.get("total_selections", 0)
            ac = metrics.get("applied_count", 0)
            comp = metrics.get("completions", 0)
            fb = metrics.get("fallbacks", 0)
            if ts > 0:
                metrics["applied_rate"] = round(ac / ts, 3)
                metrics["effective_rate"] = round(comp / ts, 3)
            if ac > 0:
                metrics["completion_rate"] = round(comp / ac, 3)
                metrics["fallback_rate"] = round(fb / ac, 3)
        
        metrics["last_used"] = datetime.now().isoformat()
        self._save_db()
    
    def add_lineage(
        self,
        skill_id: str,
        lineage: SkillLineage,
        fix_version: int = 0
    ):
        """添加谱系记录"""
        if skill_id in self.db["skills"]:
            self.db["skills"][skill_id]["lineage"] = lineage.to_dict()
            self.db["skills"][skill_id]["fix_version"] = fix_version
        self.db["lineages"][skill_id] = lineage.to_dict()
        self._save_db()
    
    def register_skill(
        self,
        name: str,
        origin: SkillOrigin,
        description: str = "",
        lineage: Optional[SkillLineage] = None,
        metrics: Optional[SkillMetrics] = None,
    ) -> str:
        """注册新技能"""
        content_hash = hashlib.md5(description.encode()).hexdigest()
        skill_id = self._generate_skill_id(name, origin, 0, content_hash)
        
        record = SkillRecord(
            skill_id=skill_id,
            name=name,
            description=description,
            lineage=lineage or SkillLineage(origin=origin),
            metrics=metrics or SkillMetrics(),
        )
        
        self.db["skills"][skill_id] = record.to_dict()
        if lineage:
            self.db["lineages"][skill_id] = lineage.to_dict()
        self._save_db()
        
        return skill_id
    
    def deactivate_skill(self, skill_id: str):
        """标记技能为非活跃"""
        if skill_id in self.db["skills"]:
            self.db["skills"][skill_id]["is_active"] = False
            self.db["skills"][skill_id]["updated_at"] = datetime.now().isoformat()
            self._save_db()
    
    def stats(self) -> Dict[str, int]:
        """统计信息"""
        all_skills = self.db["skills"]
        return {
            "total": len(all_skills),
            "active": sum(1 for s in all_skills.values() if s.get("is_active")),
            "by_origin": self._count_by_origin(),
            "by_category": self._count_by_category(),
        }
    
    def _count_by_origin(self) -> Dict[str, int]:
        counts = {}
        for data in self.db["skills"].values():
            origin = data.get("lineage", {}).get("origin", "imported")
            counts[origin] = counts.get(origin, 0) + 1
        return counts
    
    def _count_by_category(self) -> Dict[str, int]:
        counts = {}
        for data in self.db["skills"].values():
            cat = data.get("category", "workflow")
            counts[cat] = counts.get(cat, 0) + 1
        return counts


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="qclaw Skill Registry")
    parser.add_argument("--list", "-l", action="store_true", help="List all skills")
    parser.add_argument("--stats", "-s", action="store_true", help="Show statistics")
    parser.add_argument("--dag", action="store_true", help="Show Version DAG")
    parser.add_argument("--search", metavar="NAME", help="Search skills by name")
    args = parser.parse_args()
    
    registry = SkillRegistry()
    
    if args.stats:
        stats = registry.stats()
        print(f"\n=== Skill Stats ===")
        print(f"  Total: {stats['total']}")
        print(f"  Active: {stats['active']}")
        print(f"  By origin: {stats['by_origin']}")
        print(f"  By category: {stats['by_category']}")
    
    elif args.search:
        results = [s for s in registry.list_skills() if args.search.lower() in s["name"].lower()]
        print(f"\n=== Search: {args.search} ({len(results)} results) ===")
        for s in results:
            print(f"  [{s['skill_id']}] {s['name']} ({s['category']}) conf={s['confidence']}")
    
    elif args.dag:
        dag = registry.get_dag()
        print(f"\n=== Version DAG ===")
        print(f"  Nodes: {len(dag['nodes'])}, Links: {len(dag['links'])}")
        for n in dag["nodes"]:
            a = "[A]" if n["is_active"] else "[X]"
            print(f"  {a} {n['id']} gen={n['generation']} {n['origin']}")
        for l in dag["links"]:
            print(f"  {l['source']} -> {l['target']}")
    
    else:
        skills = registry.list_skills()
        print(f"\n=== Skills ({len(skills)}) ===")
        for s in skills:
            conf = s.get("confidence", 0)
            conf_str = f"{conf:.2f}" if conf else "-"
            print(f"  [{s['skill_id']}] {s['name']} ({s['category']}) conf={conf_str}")
