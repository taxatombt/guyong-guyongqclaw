# -*- coding: utf-8 -*-
"""
OpenViking Context Manager - qclaw landing version (enhanced)
Based on volcengine/OpenViking (24K stars) core design
Added: Experience 3-section format, Working Memory 7-section, Directory-first Retrieval
"""
import os, json, re, uuid, math
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

# ======================== Core Types ========================

class ContextType(Enum):
    RESOURCE = "resource"
    MEMORY = "memory"
    SKILL = "skill"

    @classmethod
    def from_path(cls, path):
        if "/resources/" in path: return cls.RESOURCE
        if "/memories/" in path: return cls.MEMORY
        if "/skills/" in path: return cls.SKILL
        return cls.RESOURCE

@dataclass
class ContextLayer:
    name: str; file_suffix: str; token_budget: int; purpose: str

LAYERS = {
    "L0": ContextLayer("L0", ".abstract.md", 100, "One-sentence overview, fast relevance check"),
    "L1": ContextLayer("L1", ".overview.md", 2000, "Directory summary + 7-section Working Memory"),
    "L2": ContextLayer("L2", "", 0, "Full content, on-demand loading"),
}

class MemoryUpdateStrategy(Enum):
    MERGE = "merge"
    APPEND = "append"
    NO_UPDATE = "no_update"
    REPLACE = "replace"

@dataclass
class MemoryCategory:
    name: str; scope: str; path_template: str
    update_strategy: MemoryUpdateStrategy; description: str
    examples: list = field(default_factory=list)

MEMORY_TAXONOMY = {
    "profile":     MemoryCategory("profile",     "user", "profile.md",              MemoryUpdateStrategy.MERGE,  "User identity, role, communication style"),
    "preferences": MemoryCategory("preferences", "user", "preferences/{topic}.md",  MemoryUpdateStrategy.MERGE,  "User preferences by topic"),
    "entities":    MemoryCategory("entities",    "user", "entities/{name}.md",     MemoryUpdateStrategy.APPEND,  "Entity memories: people, projects"),
    "events":      MemoryCategory("events",     "user", "events/{id}.md",        MemoryUpdateStrategy.APPEND,  "Event records: decisions, milestones"),
    "cases":       MemoryCategory("cases",      "agent", "cases/{id}.md",         MemoryUpdateStrategy.NO_UPDATE, "Agent learned cases"),
    "patterns":    MemoryCategory("patterns",   "agent", "patterns/{name}.md",    MemoryUpdateStrategy.MERGE,  "Agent learned patterns"),
    "tools":       MemoryCategory("tools",      "agent", "tools/{name}.md",       MemoryUpdateStrategy.MERGE,  "Tool usage knowledge"),
    "skills":      MemoryCategory("skills",    "agent", "skills/{name}.md",      MemoryUpdateStrategy.MERGE,  "Skill execution knowledge"),
    "experiences": MemoryCategory("experiences","agent", "experiences/{name}.md", MemoryUpdateStrategy.REPLACE, "Executable agent experiences (3-section)"),
    "trajectories":MemoryCategory("trajectories","agent","trajectories/{id}.md",  MemoryUpdateStrategy.APPEND,  "LLM call trajectory history"),
}

# ======================== VikingURI ========================

@dataclass
class VikingURI:
    scope: str; path: str; uri: str
    SCOPES = {"resources", "user", "agent", "session"}

    @classmethod
    def parse(cls, uri):
        if not uri.startswith("viking://"):
            raise ValueError(f"Invalid Viking URI: {uri}")
        parts = uri[9:].lstrip("/").split("/", 1)
        scope, path = (parts[0], parts[1] if len(parts) > 1 else "")
        if scope not in cls.SCOPES:
            raise ValueError(f"Unknown scope: {scope}")
        return cls(scope=scope, path=path, uri=uri)

    @classmethod
    def build(cls, scope, path):
        if scope not in cls.SCOPES:
            raise ValueError(f"Unknown scope: {scope}")
        return cls(scope=scope, path=path, uri=f"viking://{scope}/{path}")

    @property
    def parent(self):
        pp = "/".join(self.path.split("/")[:-1])
        return VikingURI(self.scope, pp, f"viking://{self.scope}/{pp}") if pp else None

    @property
    def name(self):
        return self.path.split("/")[-1] if self.path else "root"

    def join(self, sub):
        j = f"{self.path}/{sub}" if self.path else sub
        return VikingURI(self.scope, j, f"viking://{self.scope}/{j}")

    @property
    def workspace_path(self):
        m = {"resources": "resources", "user": "memory/user", "agent": "agent", "session": "sessions/active"}
        b = m.get(self.scope, self.scope)
        return Path(f"{b}/{self.path}" if self.path else b)

    def __str__(self): return self.uri
    def __repr__(self): return f"VikingURI({self.uri!r})"
    def __hash__(self): return hash(self.uri)
    def __eq__(self, o): return isinstance(o, VikingURI) and self.uri == o.uri

# ======================== Experience (3-Section Format) ========================

@dataclass
class Experience:
    """
    Executable, machine-readable agent experience.
    Situation -> Approach -> Reflect (mutually exclusive).
    Reference: openviking/prompts/templates/memory/experiences.yaml
    """
    name: str
    situation: Dict[str, Any]
    approach: List[str]
    reflect: List[str]
    supersedes: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self):
        lines = [
            f"# Experience: {self.name}",
            "",
            "## Situation",
            "Entry conditions (when to trigger this experience):",
        ]
        for k, v in self.situation.items():
            lines.append(f"  - {k}: {v}")
        lines += ["", "## Approach", "Command-style execution steps:"]
        for step in self.approach:
            lines.append(f"  - {step}")
        lines += ["", "## Reflect", "Negative constraints (what NOT to do):"]
        for item in self.reflect:
            lines.append(f"  - {item}")
        if self.supersedes:
            lines += ["", "## Supersedes", "Automatically deprecates:"]
            for uri in self.supersedes:
                lines.append(f"  - {uri}")
        lines += ["", f"_Created: {self.created_at}_"]
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, md_text, name):
        situation, approach, reflect = {}, [], []
        current = None
        for line in md_text.splitlines():
            line = line.strip()
            if line.startswith("## Situation"):
                current = "situation"; continue
            if line.startswith("## Approach"):
                current = "approach"; continue
            if line.startswith("## Reflect"):
                current = "reflect"; continue
            if line.startswith("## Supersedes"):
                current = "supersedes"; continue
            if line.startswith("# "):
                continue
            if current == "situation" and line.startswith("- "):
                parts = line[2:].split(": ", 1)
                if len(parts) == 2:
                    situation[parts[0].strip()] = parts[1].strip()
            elif current == "approach" and line.startswith("- "):
                approach.append(line[2:].strip())
            elif current == "reflect" and line.startswith("- "):
                reflect.append(line[2:].strip())
        return cls(name=name, situation=situation, approach=approach, reflect=reflect)

    def to_viking_uri(self, workspace):
        return VikingURI.build("agent", f"memories/experiences/{self.name}.md")

    def save(self, workspace):
        target = workspace.agent_memories_dir / "experiences" / f"{self.name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_markdown(), encoding="utf-8")
        for old_uri in self.supersedes:
            try:
                old_path = workspace._uri_to_path(old_uri)
                if old_path.exists():
                    content = old_path.read_text(encoding="utf-8")
                    if "DEPRECATED" not in content:
                        content += "\n\n**DEPRECATED** - superseded by newer version.\n"
                        old_path.write_text(content, encoding="utf-8")
            except Exception:
                pass
        return target

# ======================== Working Memory (7-Section) ========================

WORKING_MEMORY_SECTIONS = [
    "Session Title",
    "Current State",
    "Task & Goals",
    "Key Facts & Decisions",
    "Files & Context",
    "Errors & Corrections",
    "Open Issues",
]

@dataclass
class WorkingMemory:
    session_id: str
    sections: Dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self):
        lines = [f"# Working Memory: {self.session_id}", ""]
        for sec in WORKING_MEMORY_SECTIONS:
            lines.append(f"## {sec}")
            lines.append(self.sections.get(sec, "(empty)"))
            lines.append("")
        lines.append(f"_Updated: {self.updated_at}_")
        return "\n".join(lines)

    def update_section(self, section_name, content, mode="update"):
        if mode == "keep":
            old = self.sections.get(section_name, "")
            if old and old != "(empty)":
                return
        self.sections[section_name] = content
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @classmethod
    def from_markdown(cls, md_text, session_id):
        wm = cls(session_id=session_id)
        current = None
        buf = []
        for line in md_text.splitlines():
            matched = False
            for sec in WORKING_MEMORY_SECTIONS:
                if line.strip() == f"## {sec}":
                    if current:
                        wm.sections[current] = "\n".join(buf).strip() or "(empty)"
                    current = sec; buf = []; matched = True; break
            if not matched and current:
                buf.append(line)
        if current:
            wm.sections[current] = "\n".join(buf).strip() or "(empty)"
        return wm

    def save(self, workspace):
        target = workspace.agent_memories_dir / "working_memory" / f"{self.session_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_markdown(), encoding="utf-8")
        self._save_l0_l1(workspace)
        return target

    def _save_l0_l1(self, workspace):
        base = workspace.agent_memories_dir / "working_memory"
        abstract = f"Session {self.session_id}: {self.sections.get('Session Title', 'no title')}"
        (base / f"{self.session_id}.abstract.md").write_text(abstract, encoding="utf-8")
        overview = self.to_markdown()
        (base / f"{self.session_id}.overview.md").write_text(overview, encoding="utf-8")

# ======================== WorkingMemoryManager ========================

class WorkingMemoryManager:
    def __init__(self, workspace):
        self.workspace = workspace
        self.current = None

    def start_session(self, session_id=None):
        sid = session_id or str(uuid.uuid4())[:8]
        self.current = WorkingMemory(session_id=sid)
        return self.current

    def update(self, section, content, mode="update"):
        if not self.current:
            self.start_session()
        self.current.update_section(section, content, mode)

    def commit(self):
        if not self.current:
            raise ValueError("No active session. Call start_session() first.")
        return self.current.save(self.workspace)

    def load(self, session_id):
        target = self.workspace.agent_memories_dir / "working_memory" / f"{session_id}.md"
        if not target.exists():
            return None
        text = target.read_text(encoding="utf-8")
        self.current = WorkingMemory.from_markdown(text, session_id)
        return self.current

# ======================== OpenVikingWorkspace ========================

class OpenVikingWorkspace:
    def __init__(self, workspace_root):
        self.root = Path(workspace_root)
        self.resources_dir = self.root / "resources"
        self.user_memories_dir = self.root / "memory" / "user"
        self.agent_memories_dir = self.root / "agent" / "memories"
        self.skills_dir = self.root / "skills"
        for d in [self.resources_dir, self.user_memories_dir, self.agent_memories_dir, self.skills_dir]:
            d.mkdir(parents=True, exist_ok=True)
        (self.agent_memories_dir / "experiences").mkdir(parents=True, exist_ok=True)
        (self.agent_memories_dir / "working_memory").mkdir(parents=True, exist_ok=True)

    def _uri_to_path(self, uri_str):
        try:
            uri = VikingURI.parse(uri_str)
            return uri.workspace_path
        except Exception:
            return Path(uri_str.replace("viking://", "").replace("/", os.sep))

    def tree(self, max_depth=2):
        lines = ["viking://"]
        scope_dirs = {"resources": self.resources_dir, "user": self.user_memories_dir, "agent": self.agent_memories_dir}
        for scope, d in scope_dirs.items():
            lines.append(f"|-- {scope}/")
            if d.exists() and max_depth > 0:
                self._tree_items(d, lines, "|   ", max_depth)
        return "\n".join(lines)

    def _tree_items(self, path, lines, prefix, depth):
        try:
            items = sorted(path.iterdir())
        except Exception:
            return
        items = items[:20]
        for i, item in enumerate(items):
            last = (i == len(items) - 1 or i == 19)
            conn = "`--" if last else "|--"
            if item.is_dir():
                lines.append(f"{prefix}{conn} {item.name}/")
                if depth > 1:
                    self._tree_items(item, lines, prefix + ("    " if last else "|   "), depth - 1)
            else:
                lines.append(f"{prefix}{conn} {item.name}")

    def add_memory(self, category, path, data):
        cat = MEMORY_TAXONOMY.get(category)
        if cat is None:
            raise ValueError(f"Unknown category: {category}")
        base = self.user_memories_dir if cat.scope == "user" else self.agent_memories_dir
        target = base / path
        target.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        header = f"# {data.get('title', cat.description)}\n\n_recorded: {ts}_\n\n"
        content = header + json.dumps(data, ensure_ascii=False, indent=2)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        self._generate_l0_l1(target, data)
        return target

    def _generate_l0_l1(self, target, data):
        abstract = f"{data.get('title', target.stem)}: {str(data)[:100]}"
        l0_path = target.parent / f"{target.stem}.abstract.md"
        l0_path.write_text(abstract, encoding="utf-8")
        overview_lines = [
            f"# Overview: {target.stem}",
            "",
            "## Summary",
            f"{data.get('title', target.stem)} - {str(data)[:500]}",
            "",
            "## Working Memory Sections",
        ]
        for sec in WORKING_MEMORY_SECTIONS:
            overview_lines.append(f"- {sec}: (to be filled by LLM)")
        overview_lines += ["", f"_Generated: {datetime.now(timezone.utc).isoformat()}_"]
        l1_path = target.parent / f"{target.stem}.overview.md"
        l1_path.write_text("\n".join(overview_lines), encoding="utf-8")

    def find(self, query, scope=None, use_dir_first=True):
        search_dirs = []
        if scope in (None, "resources") and self.resources_dir.exists():
            search_dirs.append((self.resources_dir, "resources"))
        if scope in (None, "user") and self.user_memories_dir.exists():
            search_dirs.append((self.user_memories_dir, "user"))
        if scope in (None, "agent") and self.agent_memories_dir.exists():
            search_dirs.append((self.agent_memories_dir, "agent"))

        if use_dir_first:
            return self._dir_first_search(query.lower(), search_dirs)
        return self._flat_search(query.lower(), search_dirs)

    def _flat_search(self, query, search_dirs):
        results = []
        for base_dir, s in search_dirs:
            for fpath in base_dir.rglob("*"):
                if not fpath.is_file() or fpath.name.startswith("."):
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8").lower()
                    if query in fpath.name.lower() or query in text:
                        results.append({
                            "uri": f"viking://{s}/{fpath.relative_to(base_dir)}",
                            "preview": text[:200],
                            "score": text.count(query),
                        })
                except Exception:
                    pass
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:20]

    def _dir_first_search(self, query, search_dirs):
        """
        Directory-first retrieval (simplified).
        Step 1: Score all files
        Step 2: Aggregate by directory, dir_score = max(child_score) * 1.2
        Step 3: Return directory-first results
        """
        file_scores = {}
        dir_scores = {}

        for base_dir, s in search_dirs:
            for fpath in base_dir.rglob("*"):
                if not fpath.is_file() or fpath.name.startswith("."):
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8")
                    text_l = text.lower()
                    score = text_l.count(query) if query else 1
                    if score == 0:
                        continue
                    rel = str(fpath.relative_to(base_dir))
                    uri = f"viking://{s}/{rel}"
                    file_scores[uri] = {"path": fpath, "score": score, "preview": text[:200]}
                    dir_path = str(fpath.parent.relative_to(base_dir))
                    key = f"viking://{s}/{dir_path}" if dir_path != "." else f"viking://{s}"
                    if key not in dir_scores or score > dir_scores[key]:
                        dir_scores[key] = score
                except Exception:
                    pass

        results = []
        seen = set()
        # Sort directories by score first
        for dk, dscore in sorted(dir_scores.items(), key=lambda x: x[1], reverse=True):
            boosted = dscore * 1.2
            if dk not in seen:
                results.append({"uri": dk, "preview": "(directory)", "score": int(boosted), "is_dir": True})
                seen.add(dk)
            # Add child files of this directory
            for uri, info in sorted(file_scores.items(), key=lambda x: x[1]["score"], reverse=True):
                if uri.startswith(dk) and uri not in seen:
                    results.append({"uri": uri, "preview": info["preview"], "score": info["score"], "is_dir": False})
                    seen.add(uri)

        return results[:20]

    def find_experience(self, situation_query):
        exp_dir = self.agent_memories_dir / "experiences"
        if not exp_dir.exists():
            return None
        best, best_score = None, -1
        for fpath in exp_dir.glob("*.md"):
            try:
                text = fpath.read_text(encoding="utf-8")
                score = sum(1 for v in situation_query.values() if str(v).lower() in text.lower())
                if score > best_score:
                    best_score = score
                    best = Experience.from_markdown(text, fpath.stem)
            except Exception:
                pass
        return best if best_score > 0 else None

    def stats(self):
        def count(d):
            if not d.exists(): return 0, 0
            files = [f for f in d.rglob("*") if f.is_file() and not f.name.startswith(".")]
            return len(files), sum(f.stat().st_size for f in files)
        rc, rs = count(self.resources_dir)
        um, us = count(self.user_memories_dir)
        am, a_s = count(self.agent_memories_dir)
        sm, ss = count(self.skills_dir)
        return {"resources": rc, "user_memories": um, "agent_memories": am, "skills": sm,
                "total": rc+um+am+sm, "size_kb": (rs+us+a_s+ss)//1024}

    def summary(self):
        s = self.stats()
        return f"Workspace: {s['total']} files, {s['size_kb']}KB | R:{s['resources']} UM:{s['user_memories']} AM:{s['agent_memories']} S:{s['skills']}"

# ======================== SessionContextAdapter (Enhanced) ========================

class SessionContextAdapter:
    """
    Bridge OpenViking context management with qclaw session system.
    Enhanced: Two-Phase Commit pattern.
    """

    def __init__(self, workspace):
        self.workspace = workspace
        self.session_id = str(uuid.uuid4())[:8]
        self.message_buffer = []
        self.pending_dir = workspace.root / ".openviking_pending" / self.session_id
        self.wm_manager = WorkingMemoryManager(workspace)

    def add_message(self, role, content):
        self.message_buffer.append({
            "role": role, "content": content,
            "ts": datetime.now(timezone.utc).isoformat()
        })

    def commit(self):
        if not self.message_buffer:
            return {"extracted": 0}
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        msg_file = self.pending_dir / "messages.json"
        with open(msg_file, "w", encoding="utf-8") as f:
            json.dump(self.message_buffer, f, ensure_ascii=False, indent=2)
        result = self._phase2_extract()
        self.message_buffer.clear()
        return result

    def _phase2_extract(self):
        if not self.pending_dir.exists():
            return {"extracted": 0, "status": "no_pending"}
        try:
            msg_file = self.pending_dir / "messages.json"
            if not msg_file.exists():
                return {"extracted": 0, "status": "no_messages"}
            messages = json.loads(msg_file.read_text(encoding="utf-8"))
            full_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
        except Exception:
            return {"extracted": 0, "status": "error"}

        extracted = []
        checks = {
            "profile":     ["name", "call me", "I am"],
            "preferences": ["prefer", "like", "habit", "always"],
            "entities":    ["project", "person", "organization"],
            "events":      ["decided", "completed", "deployed", "milestone"],
            "cases":       ["case", "example", "learned"],
            "patterns":    ["pattern", "approach", "method"],
            "tools":       ["tool", "call", "parameter"],
            "skills":      ["skill", "capability"],
            "experiences": ["experience", "learned", "mistake", "lesson"],
        }
        for cat, keywords in checks.items():
            matched = any(kw.lower() in full_text.lower() for kw in keywords)
            if matched:
                data = {"title": f"session_{self.session_id}", "content": full_text[:500]}
                try:
                    target = self.workspace.add_memory(cat, f"session_{self.session_id}.md", data)
                    extracted.append({"category": cat, "path": str(target)})
                except Exception:
                    pass

        done_file = self.pending_dir / ".done"
        done_file.write_text(json.dumps({"extracted": len(extracted), "status": "done", "time": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
        return {
            "session_id": self.session_id,
            "extracted": len(extracted),
            "categories": [e["category"] for e in extracted],
            "status": "done"
        }

    def poll_pending(self):
        done = self.pending_dir / ".done"
        failed = self.pending_dir / ".failed.json"
        if done.exists():
            return json.loads(done.read_text(encoding="utf-8"))
        if failed.exists():
            return json.loads(failed.read_text(encoding="utf-8"))
        return {"status": "pending", "session_id": self.session_id}

    def compress_and_archive(self, keep_recent=10):
        if len(self.message_buffer) <= keep_recent:
            return "no compression needed"
        archive = self.message_buffer[:-keep_recent]
        self.message_buffer = self.message_buffer[-keep_recent:]
        traj_dir = self.workspace.agent_memories_dir / "trajectories"
        traj_dir.mkdir(parents=True, exist_ok=True)
        traj_file = traj_dir / f"session_{self.session_id}.md"
        content = "\n".join(f"[{m['role']}]: {m['content']}" for m in archive)
        traj_file.write_text(f"# Trajectory: {self.session_id}\n\n{content}", encoding="utf-8")
        return f"archived {len(archive)} messages, keeping {keep_recent} recent"

# ======================== Export ========================
__all__ = [
    "ContextType", "ContextLayer", "LAYERS",
    "MemoryUpdateStrategy", "MemoryCategory", "MEMORY_TAXONOMY",
    "VikingURI",
    "Experience",
    "WorkingMemory", "WorkingMemoryManager", "WORKING_MEMORY_SECTIONS",
    "OpenVikingWorkspace",
    "SessionContextAdapter",
]