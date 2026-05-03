#!/usr/bin/env python3
"""
skill_collision_detector.py — 顾庸t Skill 触发条件碰撞检测工具
来源：Superpowers CSO description 规范 + tool-runtime-pipeline 设计
日期：2026-04-05

功能：
- 扫描所有 skill 的 description（触发条件）
- 检测是否有交叉触发风险
- 两种碰撞类型：
  1. INCLUDE — A 的触发条件语义上包含 B 的（A 会同时触发 B）
  2. OVERLAP — A 和 B 触发条件部分重叠（不确定谁优先）

Exit Code：
  0 = 无碰撞
  1 = 碰撞发现
  2 = 错误

用法：
  python3 skill_collision_detector.py --skills-dir skills/
  python3 skill_collision_detector.py --skills-dir skills/ --verbose
  python3 skill_collision_detector.py --skills-dir skills/ --json --report-path collisions.json
"""

import argparse
import os
import re
import sys
import json
from pathlib import Path
from collections import defaultdict


# ===== Description 解析 =====

def extract_frontmatter(text: str) -> str | None:
    """提取 YAML frontmatter"""
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return None
    end = stripped.find("---", 3)
    if end == -1:
        return None
    return stripped[3:end]


def parse_frontmatter(fm_text: str) -> dict:
    """解析 frontmatter"""
    try:
        import yaml
        return yaml.safe_load(fm_text) or {}
    except Exception:
        return {}


def extract_description(skill_md_path: str) -> tuple[str, str]:
    """
    提取 skill 的 name 和 description。
    Returns: (name, description)
    """
    content = Path(skill_md_path).read_text(encoding="utf-8", errors="ignore")

    fm_text = extract_frontmatter(content)
    if fm_text is None:
        return "", ""

    fm = parse_frontmatter(fm_text)
    name = fm.get("name", "")
    description = fm.get("description", "")

    if not name:
        name = Path(skill_md_path).parent.name

    return name.strip(), description.strip()


# ===== 关键词提取 =====

def extract_keywords(description: str) -> set[str]:
    """
    从 description 提取触发关键词。
    过滤掉停用词，保留有意义的触发条件词。
    """
    # 停用词（常见但无区分力）
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
        "at", "by", "from", "or", "and", "but", "if", "when", "then", "that",
        "this", "these", "those", "it", "its", "your", "you", "i", "we", "they",
        "all", "any", "some", "no", "not", "only", "just", "also", "very",
        "before", "after", "during", "before", "after", "under", "over", "between",
        "through", "about", "into", "like", "than", "more", "most", "less",
        "least", "such", "each", "every", "both", "few", "many", "much", "other",
        "another", "same", "different", "various", "specific", "particular",
        "certain", "general", "simple", "basic", "specific", "particular",
        "appropriate", "relevant", "useful", "helpful", "needed", "required",
        "want", "need", "like", "use", "used", "using", "make", "want", "help",
    }

    # 清理 description
    desc = description.lower()
    # 移除 "use when" 前缀（CSO 规范要求以这个开头）
    desc = re.sub(r'^use when\s*', '', desc)
    # 提取词
    words = re.findall(r'\b[a-z]{3,}\b', desc)
    # 过滤停用词和太常见的词
    keywords = {w for w in words if w not in stop_words and len(w) > 2}

    return keywords


# ===== 碰撞检测 =====

def detect_collisions(skills: list[dict]) -> list[dict]:
    """
    检测 skill 触发条件之间的碰撞。
    两种碰撞类型：
    - INCLUDE: A 的关键词集合包含 B 的（语义上 A 覆盖 B）
    - OVERLAP: A 和 B 有交集但互不包含
    """
    collisions = []

    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            skill_a = skills[i]
            skill_b = skills[j]

            keywords_a = skill_a["keywords"]
            keywords_b = skill_b["keywords"]

            # 空关键词跳过
            if not keywords_a or not keywords_b:
                continue

            # 计算交集
            intersection = keywords_a & keywords_b
            union = keywords_a | keywords_b

            # Jaccard 相似度
            jaccard = len(intersection) / len(union) if union else 0

            # 包含检测：A 的关键词是否包含 B
            # 弱包含：intersection / keywords_b > 0.6（60% 关键词重叠）
            overlap_ratio_a_to_b = len(intersection) / len(keywords_b) if keywords_b else 0
            overlap_ratio_b_to_a = len(intersection) / len(keywords_a) if keywords_a else 0

            if overlap_ratio_b_to_a >= 0.7 and len(keywords_a) >= len(keywords_b):
                # A 包含 B（且 A 关键词更多或相等）
                collision_type = "INCLUDE_A_OVER_B"
                collisions.append({
                    "type": collision_type,
                    "skill_a": skill_a["name"],
                    "skill_b": skill_b["name"],
                    "shared_keywords": sorted(intersection),
                    "overlap_ratio": round(overlap_ratio_b_to_a, 2),
                    "description_a": skill_a["description"],
                    "description_b": skill_b["description"],
                    "path_a": skill_a["path"],
                    "path_b": skill_b["path"],
                    "severity": "HIGH" if overlap_ratio_b_to_a >= 0.85 else "MEDIUM",
                })
            elif overlap_ratio_a_to_b >= 0.7 and len(keywords_b) >= len(keywords_a):
                # B 包含 A
                collision_type = "INCLUDE_B_OVER_A"
                collisions.append({
                    "type": collision_type,
                    "skill_a": skill_a["name"],
                    "skill_b": skill_b["name"],
                    "shared_keywords": sorted(intersection),
                    "overlap_ratio": round(overlap_ratio_a_to_b, 2),
                    "description_a": skill_a["description"],
                    "description_b": skill_b["description"],
                    "path_a": skill_a["path"],
                    "path_b": skill_b["path"],
                    "severity": "HIGH" if overlap_ratio_a_to_b >= 0.85 else "MEDIUM",
                })
            elif jaccard >= 0.3:
                # 部分重叠
                collisions.append({
                    "type": "OVERLAP",
                    "skill_a": skill_a["name"],
                    "skill_b": skill_b["name"],
                    "shared_keywords": sorted(intersection),
                    "overlap_ratio": round(jaccard, 2),
                    "description_a": skill_a["description"],
                    "description_b": skill_b["description"],
                    "path_a": skill_a["path"],
                    "path_b": skill_b["path"],
                    "severity": "LOW",
                })

    # 按严重程度和重叠比例排序
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    collisions.sort(key=lambda x: (severity_order.get(x["severity"], 3), -x["overlap_ratio"]))

    return collisions


# ===== 报告生成 =====

def format_report(skills: list[dict], collisions: list[dict], verbose: bool = False) -> str:
    """生成人类可读的报告"""

    high = [c for c in collisions if c["severity"] == "HIGH"]
    medium = [c for c in collisions if c["severity"] == "MEDIUM"]
    low = [c for c in collisions if c["severity"] == "LOW"]

    lines = [
        f"\n{'=' * 70}",
        f"  SKILL COLLISION DETECTOR REPORT",
        f"{'=' * 70}",
        f"\n  Skills scanned:      {len(skills)}",
        f"  Total collisions:    {len(collisions)}",
        f"    HIGH severity:     {len(high)}",
        f"    MEDIUM severity:   {len(medium)}",
        f"    LOW severity:      {len(low)}",
    ]

    if not collisions:
        lines.append(f"\n✅ NO SIGNIFICANT COLLISIONS DETECTED")
        lines.append(f"{'=' * 70}\n")
        return "\n".join(lines)

    if high:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"\n  🚨 HIGH SEVERITY — One skill likely supersedes another:")
        for c in high:
            if c["type"] == "INCLUDE_A_OVER_B":
                lines.append(f"\n  [{c['skill_a']}] supersedes [{c['skill_b']}]")
            else:
                lines.append(f"\n  [{c['skill_b']}] supersedes [{c['skill_a']}]")
            lines.append(f"  Overlap: {c['overlap_ratio']:.0%} keywords shared")
            lines.append(f"  Shared: {', '.join(c['shared_keywords'][:8])}")
            lines.append(f"  A: \"{c['description_a'][:80]}\"")
            lines.append(f"  B: \"{c['description_b'][:80]}\"")

    if medium:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"\n  ⚠️  MEDIUM SEVERITY — Significant overlap, priority unclear:")
        for c in medium:
            lines.append(f"\n  [{c['skill_a']}] ↔ [{c['skill_b']}]")
            lines.append(f"  Overlap: {c['overlap_ratio']:.0%}")
            lines.append(f"  Shared: {', '.join(c['shared_keywords'][:6])}")

    if low and verbose:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"\n  ℹ️  LOW SEVERITY — Minor overlap:")
        for c in low[:5]:
            lines.append(f"\n  [{c['skill_a']}] ↔ [{c['skill_b']}] ({c['overlap_ratio']:.0%})")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"\n  RECOMMENDATIONS:")
    if high:
        lines.append(f"  HIGH: Merge the narrower skill into the broader one,")
        lines.append(f"        or clarify the narrower skill's description to be more specific.")
    if medium:
        lines.append(f"  MEDIUM: Add context qualifiers to descriptions to differentiate.")
        lines.append(f"          e.g., '...when [specific context X]' vs '...when [context Y]'")
    if low:
        lines.append(f"  LOW: Generally acceptable, monitor for unexpected triggers.")

    lines.append(f"\n{'=' * 70}\n")
    return "\n".join(lines)


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description="Skill Collision Detector — find overlapping skill trigger conditions.\n"
                    "Exit 0: no collisions. Exit 1: collisions found. Exit 2: error."
    )
    parser.add_argument("--skills-dir", type=str, required=True,
                       help="Skills 根目录")
    parser.add_argument("--verbose", action="store_true", help="显示低严重度碰撞")
    parser.add_argument("--json", action="store_true", help="JSON 输出格式")
    parser.add_argument("--report-path", type=str, default="",
                       help="保存报告到文件")

    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.is_dir():
        print(f"❌ ERROR: {skills_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    # 扫描所有 SKILL.md
    skills = []
    for skill_path in skills_dir.rglob("SKILL.md"):
        name, description = extract_description(str(skill_path))
        if not name:
            continue
        keywords = extract_keywords(description) if description else set()
        skills.append({
            "name": name,
            "description": description,
            "keywords": keywords,
            "path": str(skill_path.relative_to(skills_dir.parent)),
        })

    if not skills:
        print(f"⚠️  No skills found in {skills_dir}")
        sys.exit(0)

    # 检测碰撞
    collisions = detect_collisions(skills)

    # 输出
    if args.json:
        output = {
            "skills_scanned": len(skills),
            "collisions": collisions,
            "high_count": len([c for c in collisions if c["severity"] == "HIGH"]),
            "medium_count": len([c for c in collisions if c["severity"] == "MEDIUM"]),
            "low_count": len([c for c in collisions if c["severity"] == "LOW"]),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        report = format_report(skills, collisions, args.verbose)
        print(report)

    # 保存报告
    if args.report_path:
        output_data = {
            "skills_scanned": len(skills),
            "collisions": collisions,
            "skills": [{"name": s["name"], "path": s["path"], "keywords": sorted(s["keywords"])} for s in skills],
        }
        Path(args.report_path).write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[saved] {args.report_path}", file=sys.stderr)

    sys.exit(1 if collisions else 0)


if __name__ == "__main__":
    main()