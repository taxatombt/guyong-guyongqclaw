# -*- coding: utf-8 -*-
"""
qclaw_handover.py - HANDOVER DOCUMENT 格式

来源: 顾庸t compact.py + Codex compact 模板 + Claude Code iterative summary

核心理念: 压缩不是摘要，是交接。
输出从"摘要"改为"HANDOVER DOCUMENT"格式。

关键洞察(顾庸t):
  'another language model' 比 'context summary' 心理距离更对
  交接 > 总结：关键是防重复、能续上

格式4字段:
  RESOLVED     — 已完成的事（关注结果非过程）
  PENDING      — 待处理（避免重复回答）
  KEY DECISIONS — 关键判断+文件路径，非泛泛描述
  SYSTEM       — 工具/文件/压缩轮次
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import time

# HANDOVER 核心常量
HANDOVER_PREAMBLE = (
    "You are another language model, continuing a prior session.\n"
    "Below is a structured handover - NOT a verbose recap.\n\n"
)

DIRECT_RESUME_INSTRUCTION = (
    "- Do NOT say 'Based on the summary...'\n"
    "- Do NOT recap. Resume action immediately.\n"
    "- If uncertain, state your assumption and proceed.\n"
    "- If tasks were left incomplete, continue them.\n"
    "- If questions were asked but not answered, answer them now.\n"
)


@dataclass
class HandoverDocument:
    """HANDOVER DOCUMENT 结构"""
    resolved: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    key_decisions: List[Dict[str, str]] = field(default_factory=list)
    system_tools: List[str] = field(default_factory=list)
    system_files: List[str] = field(default_factory=list)
    compression_round: int = 0

    def to_markdown(self) -> str:
        """渲染为 markdown"""
        resolved_text = "\n".join("- " + r for r in self.resolved[:5])
        pending_text = "\n".join("- " + p for p in self.pending[:5])

        decisions_lines = []
        for d in self.key_decisions[:5]:
            line = "- **" + d.get("decision", "")[:100] + "**"
            if d.get("file"):
                line += " [`" + d["file"] + "`]"
            if d.get("reason"):
                line += " - " + d["reason"]
            decisions_lines.append(line)
        key_decisions_text = "\n".join(decisions_lines)

        tools_str = ", ".join(self.system_tools) or "none"
        files_str = ", ".join(self.system_files) or "none"

        return (
            "## RESOLVED\n(Completed tasks - focus on RESULTS)\n"
            + (resolved_text or "- ") + "\n\n"
            + "## PENDING\n(Tasks not completed - AVOID repeating)\n"
            + (pending_text or "- ") + "\n\n"
            + "## KEY DECISIONS\n(Specific decisions + file paths)\n"
            + (key_decisions_text or "- ") + "\n\n"
            + "## SYSTEM\n(Tool/File/Compression state)\n"
            + "- Compression round: " + str(self.compression_round) + "\n"
            + "- Active tools: " + tools_str + "\n"
            + "- Files in play: " + files_str + "\n"
        )


@dataclass
class HandoverExtractor:
    """从对话历史提取 HANDOVER DOCUMENT 内容"""

    def extract(self, messages: List[Dict[str, Any]]) -> HandoverDocument:
        """从消息历史提取 HANDOVER 字段"""
        doc = HandoverDocument()
        seen_files = set()
        used_tools = set()
        completed_tasks = []
        pending_tasks = []
        decisions = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content:
                continue

            if role == "assistant":
                text = str(content)
                # 检测文件创建
                for line in text.split("\n"):
                    for prefix in ["Created ", "Created: ", "Wrote ", "Saved "]:
                        if prefix in line:
                            file_part = line.split(prefix)[-1].strip().split()[0]
                            if "." in file_part:
                                seen_files.add(file_part)
                # 检测决策
                for kw in ["decide", "decision", "chose", "chosen"]:
                    if kw.lower() in text.lower() and len(text) < 500:
                        decisions.append({"decision": text[:200], "file": "", "reason": ""})
                        break

            elif role == "tool":
                tool_name = msg.get("name", "")
                if tool_name:
                    used_tools.add(tool_name)
                # 文件创建检测
                text = str(content)
                for kw in ["Created file:", "Wrote", "Saved", "Created: "]:
                    if kw in text:
                        for line in text.split("\n"):
                            if kw in line:
                                idx = line.index(kw) + len(kw)
                                file_name = line[idx:].strip().split()[0]
                                if "." in file_name:
                                    seen_files.add(file_name)

        doc.resolved = completed_tasks if completed_tasks else []
        doc.pending = pending_tasks if pending_tasks else []
        doc.key_decisions = decisions[:10]
        doc.system_tools = sorted(list(used_tools))
        doc.system_files = sorted(list(seen_files))
        return doc

    def build_handover_prompt(self, messages: List[Dict[str, Any]],
                              round_num: int = 1) -> str:
        """构建 HANDOVER DOCUMENT 字符串"""
        doc = self.extract(messages)
        doc.compression_round = round_num
        return HANDOVER_PREAMBLE + DIRECT_RESUME_INSTRUCTION + doc.to_markdown()


# Singleton
_handover_extractor: Optional[HandoverExtractor] = None

def get_handover_extractor() -> HandoverExtractor:
    global _handover_extractor
    if _handover_extractor is None:
        _handover_extractor = HandoverExtractor()
    return _handover_extractor


def format_handover(messages: List[Dict[str, Any]], round_num: int = 1) -> str:
    """快速接口"""
    return get_handover_extractor().build_handover_prompt(messages, round_num)


if __name__ == "__main__":
    test_messages = [
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Build a REST API in Python using FastAPI"},
        {"role": "assistant", "content": "Creating FastAPI app structure."},
        {"role": "tool", "name": "write", "content": "Created file: api/main.py with FastAPI app"},
        {"role": "tool", "name": "write", "content": "Created file: api/models.py"},
        {"role": "assistant", "content": "Next I'll add JWT authentication."},
        {"role": "user", "content": "Add JWT auth"},
        {"role": "tool", "name": "write", "content": "Updated: api/auth.py with JWT implementation"},
        {"role": "assistant", "content": "I decided to use PyJWT (not python-jose) for simplicity."},
        {"role": "tool", "name": "write", "content": "Updated: api/main.py with auth endpoints"},
    ]

    extractor = get_handover_extractor()
    doc = extractor.extract(test_messages)

    print("=== HANDOVER Extraction ===")
    print("Tools:", doc.system_tools)
    print("Files:", doc.system_files)
    print("Decisions:", len(doc.key_decisions))

    handover = extractor.build_handover_prompt(test_messages, round_num=1)
    print("\n=== HANDOVER DOCUMENT ===")
    print(handover)
