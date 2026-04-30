"""
auto_skill.py — 5-tool-call 自动技能建议系统

来源：Hermes Agent Guide 第8册（5-tool-call规则 + 质量评分公式）
设计：检测5+次工具调用且成功 → 评估质量 → 建议生成SKILL.md

质量评分公式：
  综合评分 = 频率×0.3 + 重要性×0.4 + 结构性×0.3
  阈值 > 0.7 才建议生成Skill

触发条件：
1. 5+次工具调用且成功
2. 遇到错误最终找到可行路径（包含"避坑指南"）
3. 用户纠正了做法
4. 非显而易见的工作流组合
5. 用户明确说"记住这个流程"
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

log = logging.getLogger("qclaw.auto_skill")

WORKSPACE = Path(r"C:\Users\yiseg\.qclaw\workspace")
SKILL_SUGGESTIONS_DIR = WORKSPACE / "memory" / "skill_suggestions"
SKILL_SUGGESTIONS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    tool: str
    success: bool
    task: str = ""
    input_summary: str = ""
    output_summary: str = ""
    timestamp: float = 0.0
    error: str = ""


@dataclass
class WorkflowDetection:
    """检测到的工作流"""
    task: str
    tools: List[str]
    success_count: int
    fail_count: int
    total_count: int
    first_seen: float
    last_seen: float
    frequency_score: float = 0.0
    importance_score: float = 0.0
    structure_score: float = 0.0
    overall_score: float = 0.0
    should_suggest: bool = False


class AutoSkillDetector:
    """自动技能检测器"""

    # 当前会话的工具调用记录
    _session_calls: List[ToolCallRecord] = []
    # 已检测的工作流（避免重复建议）
    _suggested_workflows: Dict[str, float] = {}  # task_hash → timestamp

    def observe(self, tool: str, success: bool, task: str = "",
                input_summary: str = "", output_summary: str = "",
                error: str = ""):
        """
        观察一次工具调用

        在每次工具调用后调用此方法，自动积累记录并检测工作流模式。
        """
        record = ToolCallRecord(
            tool=tool, success=success, task=task,
            input_summary=input_summary[:200],
            output_summary=output_summary[:200],
            timestamp=time.time(), error=error[:200]
        )
        self._session_calls.append(record)

        # 每5次调用检测一次
        if len(self._session_calls) % 5 == 0:
            self._check_and_suggest()

    def _check_and_suggest(self):
        """检查是否有可建议的工作流"""
        # 按任务分组
        task_groups: Dict[str, List[ToolCallRecord]] = {}
        for call in self._session_calls:
            if not call.task:
                continue
            task_hash = hashlib.md5(call.task.encode()).hexdigest()[:8]
            if task_hash not in task_groups:
                task_groups[task_hash] = []
            task_groups[task_hash].append(call)

        for task_hash, calls in task_groups.items():
            # 跳过已建议的
            if task_hash in self._suggested_workflows:
                continue

            # 至少5次调用
            if len(calls) < 5:
                continue

            success_count = sum(1 for c in calls if c.success)
            fail_count = len(calls) - success_count
            tools = list(set(c.tool for c in calls))

            detection = WorkflowDetection(
                task=calls[0].task,
                tools=tools,
                success_count=success_count,
                fail_count=fail_count,
                total_count=len(calls),
                first_seen=calls[0].timestamp,
                last_seen=calls[-1].timestamp,
            )

            # 计算质量评分
            detection.frequency_score = self._calc_frequency(calls)
            detection.importance_score = self._calc_importance(calls)
            detection.structure_score = self._calc_structure(calls, tools)
            detection.overall_score = (
                detection.frequency_score * 0.3 +
                detection.importance_score * 0.4 +
                detection.structure_score * 0.3
            )
            detection.should_suggest = detection.overall_score > 0.7

            if detection.should_suggest:
                self._generate_suggestion(detection, task_hash)
                self._suggested_workflows[task_hash] = time.time()

    def _calc_frequency(self, calls: List[ToolCallRecord]) -> float:
        """
        频率评分（0-1）
        同一工作流重复2-3次即满分
        """
        if len(calls) >= 10:
            return 1.0
        elif len(calls) >= 7:
            return 0.8
        elif len(calls) >= 5:
            return 0.6
        return 0.3

    def _calc_importance(self, calls: List[ToolCallRecord]) -> float:
        """
        重要性评分（0-1）
        考虑：工具调用数、成功率、是否有错误恢复
        """
        score = 0.0

        # 工具种类多 → 更重要
        unique_tools = len(set(c.tool for c in calls))
        score += min(0.3, unique_tools * 0.1)

        # 成功率高 → 更重要
        success_rate = sum(1 for c in calls if c.success) / len(calls)
        score += success_rate * 0.3

        # 有错误恢复 → 更重要（包含避坑指南）
        has_recovery = any(not c.success for c in calls) and any(c.success for c in calls)
        if has_recovery:
            score += 0.2

        # 有用户纠正 → 更重要
        # （此处无法直接检测，默认0）

        return min(1.0, score)

    def _calc_structure(self, calls: List[ToolCallRecord], tools: List[str]) -> float:
        """
        结构性评分（0-1）
        考虑：清晰步骤、可提取参数、错误处理
        """
        score = 0.0

        # 步骤清晰（工具种类≤5且有序）→ 更结构化
        if len(tools) <= 5:
            score += 0.3
        else:
            score += 0.1

        # 有错误处理（有失败的调用）→ 更结构化
        has_error = any(c.error for c in calls if c.error)
        if has_error:
            score += 0.4

        # 有输入输出摘要 → 更结构化
        has_summaries = any(c.input_summary or c.output_summary for c in calls)
        if has_summaries:
            score += 0.3

        return min(1.0, score)

    def _generate_suggestion(self, detection: WorkflowDetection, task_hash: str):
        """生成技能建议文件"""
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        filename = f"suggestion_{task_hash}_{timestamp}.md"
        filepath = SKILL_SUGGESTIONS_DIR / filename

        # 生成SKILL.md模板
        content = f"""# 技能建议：{detection.task[:50]}

> 自动检测生成（{time.strftime('%Y-%m-%d %H:%M')}）
> 质量评分：{detection.overall_score:.2f}（频率={detection.frequency_score:.2f} 重要性={detection.importance_score:.2f} 结构性={detection.structure_score:.2f}）

## 检测到的工具序列

{self._format_tool_sequence(detection)}

## 建议的SKILL.md结构

```markdown
# {detection.task[:30]}

## 触发条件
- 任务描述包含："{detection.task[:50]}"

## 步骤
{self._format_suggested_steps(detection)}

## 错误处理
{self._format_error_handling(detection)}

## 参数
- （待提取）
```

## 统计

| 指标 | 值 |
|------|-----|
| 总调用次数 | {detection.total_count} |
| 成功次数 | {detection.success_count} |
| 失败次数 | {detection.fail_count} |
| 涉及工具 | {', '.join(detection.tools)} |
| 综合评分 | {detection.overall_score:.2f} |
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        log.info(f"[auto_skill] 建议生成: {filename} (score={detection.overall_score:.2f})")

    def _format_tool_sequence(self, detection: WorkflowDetection) -> str:
        """格式化工具调用序列"""
        calls = [c for c in self._session_calls if c.task == detection.task]
        lines = []
        for i, c in enumerate(calls, 1):
            status = "✅" if c.success else "❌"
            lines.append(f"{i}. {status} `{c.tool}` — {c.input_summary[:60]}")
        return "\n".join(lines)

    def _format_suggested_steps(self, detection: WorkflowDetection) -> str:
        """格式化建议步骤"""
        lines = []
        for tool in detection.tools:
            lines.append(f"1. 使用 `{tool}` → （待描述具体操作）")
        return "\n".join(lines)

    def _format_error_handling(self, detection: WorkflowDetection) -> str:
        """格式化错误处理"""
        errors = [c for c in self._session_calls if c.task == detection.task and c.error]
        if not errors:
            return "暂无已知错误"

        lines = []
        for e in errors:
            lines.append(f"- `{e.tool}`: {e.error[:100]}")
        return "\n".join(lines)

    def get_suggestions(self) -> List[Dict]:
        """获取所有技能建议"""
        suggestions = []
        if not SKILL_SUGGESTIONS_DIR.exists():
            return suggestions

        for f in sorted(SKILL_SUGGESTIONS_DIR.glob("*.md")):
            stat = f.stat()
            suggestions.append({
                "filename": f.name,
                "size": stat.st_size,
                "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
            })
        return suggestions

    def reset_session(self):
        """重置会话记录（新会话时调用）"""
        self._session_calls = []


# 全局单例
_detector: Optional[AutoSkillDetector] = None

def get_auto_skill_detector() -> AutoSkillDetector:
    global _detector
    if _detector is None:
        _detector = AutoSkillDetector()
    return _detector


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # 自测
    detector = AutoSkillDetector()

    # 模拟5+次工具调用（同一个任务）
    for i in range(6):
        detector.observe(
            tool=["exec", "read", "write", "exec", "read", "exec"][i],
            success=i != 3,  # 第4次失败
            task="安装Python包",
            input_summary=f"step {i+1}",
            error="timeout" if i == 3 else ""
        )

    suggestions = detector.get_suggestions()
    print(f"技能建议: {len(suggestions)}条")
    for s in suggestions:
        print(f"  {s['filename']} ({s['size']}B)")

    # 清理
    for f in SKILL_SUGGESTIONS_DIR.glob("*.md"):
        f.unlink()
    print("Test cleaned. OK")
