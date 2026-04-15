"""
router.py — 判断路由系统

根据任务复杂度，路由到不同的判断流程
"""

from typing import Dict, List, Optional
from judgment.dimensions import (
    Dimension,
    DIMENSIONS,
    classify_complexity,
    get_dimensions_for_complexity,
)


class JudgmentRouter:
    """判断路由器"""
    
    def __init__(self):
        self.dimensions = {d.id: d for d in DIMENSIONS}
    
    def analyze(self, task: str, agent_profile: Optional[Dict] = None) -> Dict:
        """
        分析任务，返回判断框架
        
        Args:
            task: 任务描述
            agent_profile: Agent 配置（可选）
            
        Returns:
            包含复杂度、检视维度、追问问题的字典
        """
        # 1. 判断复杂度
        complexity = classify_complexity(task)
        
        # 2. 获取需要检视的维度
        must_check = get_dimensions_for_complexity(complexity)
        must_check_ids = [d.id for d in must_check]
        
        # 3. 计算跳过的维度
        all_dim_ids = [d.id for d in DIMENSIONS]
        skipped = [d_id for d_id in all_dim_ids if d_id not in must_check_ids]
        
        # 4. 确定重要维度（根据 profile 调整）
        important = []
        if agent_profile:
            # 根据 profile 类型调整
            profile_type = agent_profile.get("type", "balanced")
            if profile_type == "rational":
                important = ["cognitive", "economic", "dialectical"]
            elif profile_type == "emotional":
                important = ["emotional", "intuitive", "social"]
            elif profile_type == "intuitive":
                important = ["intuitive", "cognitive", "temporal"]
        
        # 5. 生成追问问题
        questions = {}
        for dim in must_check:
            questions[dim.id] = {
                "name": dim.name,
                "description": dim.description,
                "questions": dim.questions[:2],  # 每个维度最多2个核心问题
            }
        
        return {
            "task": task,
            "complexity": complexity,
            "must_check": must_check_ids,
            "important": important,
            "skipped": skipped,
            "questions": questions,
            "meta": {
                "total_dims": len(DIMENSIONS),
                "checked": len(must_check),
                "skipped_count": len(skipped),
            },
        }
    
    def format_output(self, result: Dict) -> str:
        """格式化输出"""
        lines = []
        lines.append("=" * 50)
        lines.append(f"任务: {result['task']}")
        lines.append(f"复杂度: {result['complexity']}")
        lines.append("=" * 50)
        lines.append("")
        
        # 检视维度
        lines.append("【必须检视的维度】")
        for dim_id in result["must_check"]:
            dim = self.dimensions.get(dim_id)
            if dim:
                lines.append(f"  • {dim.name} - {dim.description}")
        lines.append("")
        
        # 跳过的维度
        if result["skipped"]:
            lines.append("【跳过的维度】")
            for dim_id in result["skipped"]:
                dim = self.dimensions.get(dim_id)
                if dim:
                    lines.append(f"  • {dim.name}")
            lines.append("")
        
        # 追问问题
        lines.append("【追问问题】")
        for dim_id, q_data in result["questions"].items():
            lines.append(f"\n【{q_data['name']}】")
            for q in q_data["questions"]:
                lines.append(f"  Q: {q}")
        
        return "\n".join(lines)


def check10d(task: str, agent_profile: Optional[Dict] = None, complexity: str = "auto") -> Dict:
    """
    十维判断入口函数
    
    Args:
        task: 任务描述
        agent_profile: Agent 配置
        complexity: 复杂度级别（auto/simple/complex/critical）
        
    Returns:
        判断结果字典
    """
    router = JudgmentRouter()
    
    # 如果指定了复杂度，临时修改任务文本以匹配
    if complexity != "auto":
        # 在任务前加上复杂度标记（用于 classify_complexity）
        task = f"[{complexity}] {task}"
    
    result = router.analyze(task, agent_profile)
    return result


def format_structured(result: Dict) -> str:
    """格式化结构化输出"""
    router = JudgmentRouter()
    return router.format_output(result)


if __name__ == "__main__":
    # 测试
    test_cases = [
        "怎么安装 Python？",
        "我要不要辞职？",
        "这个投资决定很关键",
    ]
    
    for task in test_cases:
        print("\n" + "=" * 60)
        result = check10d(task)
        print(format_structured(result))
