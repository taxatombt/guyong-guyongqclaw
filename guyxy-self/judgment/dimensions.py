"""
dimensions.py — 十维判断框架

四维基础：
- cognitive        认知心理学：偏差检测 + 元认知
- game_theory     博弈论：玩家分析 + 策略推演
- economic        经济学：机会成本 + 激励结构
- dialectical     辩证唯物主义：实事求是 + 矛盾分析

六维进阶：
- emotional       情绪智能：情绪如何影响判断
- intuitive       直觉/第六感：System 1 的运作机制
- moral           价值/道德推理：应不应该，不是值不值
- social          社会意识：群体压力 + 身份认同
- temporal        时间折扣：人类短视 vs 长期视角
- metacognitive   元认知：思考我在怎么思考

目标：模拟人类判断 → 超越人类判断
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Dimension:
    id: str
    name: str
    description: str
    questions: List[str]
    sub_questions: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "questions": self.questions,
            "sub_questions": self.sub_questions,
        }


DIMENSIONS = [

    # === 四维基础 ===

    Dimension(
        id="cognitive",
        name="认知心理学",
        description="卡尼曼 System 1/2 / 偏差检测 / 元认知",
        questions=[
            "我现在用的是直觉（System 1）还是分析（System 2）？",
            "我有没有只找支持自己的证据，忽略反面的？",
            "我现在情绪状态有没有影响判断？",
        ],
        sub_questions=[
            "这个判断依赖的事实是确定的，还是我假设的？",
            "有没有类似经历在绑架我现在的新判断？",
            "我现在是在「想清楚」还是在「说服自己」？",
        ],
    ),

    Dimension(
        id="game_theory",
        name="博弈论",
        description="玩家分析 / 策略推演 / 激励结构 / 均衡分析",
        questions=[
            "涉及哪些玩家？每个玩家的核心诉求是什么？",
            "每个玩家的底线和最优策略是什么？",
            "最终会走向什么均衡？",
        ],
        sub_questions=[
            "对方的激励结构是什么？他们真正想要什么？",
            "我展示了什么信号？对方会怎么解读？",
            "有没有隐藏的第三方会受影响？",
        ],
    ),

    Dimension(
        id="economic",
        name="经济学",
        description="机会成本 / 边际分析 / 隐性代价",
        questions=[
            "做这个选择，我放弃了什么？（机会成本）",
            "这个选择最大的隐性代价是什么？",
            "边际收益是否值得边际成本？",
        ],
        sub_questions=[
            "激励结构是什么？奖励什么、惩罚什么？",
            "这个选择是不可逆的吗？退出成本有多高？",
            "随着时间推移，这个选择的真实成本会变高还是变低？",
        ],
    ),

    Dimension(
        id="dialectical",
        name="辩证唯物主义",
        description="实事求是 / 具体问题具体分析 / 实践检验 / 对立统一",
        questions=[
            "这个判断符合实际情况吗？有没有脱离现实？",
            "主要矛盾是什么？次要矛盾是什么？",
            "对立面是什么？有没有看到另一面的合理性？",
        ],
        sub_questions=[
            "实践是检验真理的唯一标准——我的判断能被验证吗？",
            "事物在发展变化，现在的前提还成立吗？",
            "有没有从群众中来、到群众中去？别人的真实处境是什么？",
        ],
    ),

    # === 六维进阶 ===

    Dimension(
        id="emotional",
        name="情绪智能",
        description="情绪如何影响判断 / 情绪调节 / 共情能力",
        questions=[
            "我现在感受到什么情绪？这个情绪在告诉我什么？",
            "这个情绪是真相，还是对情况的即时反应？",
            "如果情绪消失了，我会怎么重新看这个问题？",
        ],
        sub_questions=[
            "我能识别对方现在的情绪状态吗？",
            "我的情绪有没有让我过度放大或缩小了某个风险？",
            "情绪在说「要」还是「不要」？这个声音可靠吗？",
        ],
    ),

    Dimension(
        id="intuitive",
        name="直觉/第六感",
        description="System 1 快速判断 / 模式识别 / 身体反应",
        questions=[
            "我的第一反应是什么？直觉给了什么信号？",
            "这个直觉基于什么经验或模式识别？",
            "身体有没有给我信号？（胃紧 / 放松 / 警觉）",
        ],
        sub_questions=[
            "这个直觉在过去准过吗？有多少次是准的？",
            "我现在是在用直觉判断，还是在用直觉验证理性分析？",
            "如果把这个问题放一晚上再想，直觉会告诉我什么？",
        ],
    ),

    Dimension(
        id="moral",
        name="价值/道德推理",
        description="应不应该 / 伦理原则 / 公正判断",
        questions=[
            "这件事应不应该做，而不是值不值做？",
            "如果所有人都这样做，世界会变成什么样？",
            "我的原则是什么？这个选择有没有违背我的原则？",
        ],
        sub_questions=[
            "谁会因为这个决策受益，谁会受损？公正吗？",
            "如果这个决定被公开，我能坦然面对吗？",
            "我在妥协什么价值？这种妥协值得吗？",
        ],
    ),

    Dimension(
        id="social",
        name="社会意识",
        description="群体压力 / 从众心理 / 身份认同 / 社会变量",
        questions=[
            "社会/群体对这个问题的普遍看法是什么？",
            "我是在独立判断，还是在被群体影响？",
            "做这个选择，会让我属于哪个群体？身份认同在绑架我吗？",
        ],
        sub_questions=[
            "如果周围人不知道我的选择，我会做出同样的决定吗？",
            "哪些人的利益被这个决策代表了？哪些被忽略了？",
            "我是在「做自己」还是「演别人期待的角色」？",
        ],
    ),

    Dimension(
        id="temporal",
        name="时间折扣",
        description="人类短视 / 长期后果 / 跨期决策",
        questions=[
            "5年后回头看，这个决策还正确吗？",
            "这个选择的影响会持续多久？是一次性的还是累积的？",
            "我在透支未来的自己吗？",
        ],
        sub_questions=[
            "如果这个问题发生在10年前，我会希望当时的自己怎么选？",
            "这个选择的收益是立即的，代价是滞后的吗？",
            "随着时间推移，这个决策的复利效果是正的还是负的？",
        ],
    ),

    Dimension(
        id="metacognitive",
        name="元认知",
        description="思考我在怎么思考 / 自我监控 / 认知校准",
        questions=[
            "我现在的思考方向对吗？还是在原地打转？",
            "我有没有遗漏一个我根本没想到的角度？",
            "我对自己判断的信心程度有多少？依据是什么？",
        ],
        sub_questions=[
            "如果有人强烈反对我的观点，最有说服力的反对意见是什么？",
            "我现在是「知道我不知道」还是「不知道我不知道」？",
            "这次思考过程中，我最大的收获是什么？",
            "我愿不愿意把自己的分析过程公开给另一个人看？",
        ],
    ),
]

# 复杂度分级配置
COMPLEXITY_RULES = {
    "simple": {
        "keywords": ["怎么做", "告诉我", "是什么", "查一下", "搜索", "下载"],
        "required_dims": ["cognitive", "economic"],
        "description": "简单查询/执行类任务",
    },
    "complex": {
        "keywords": ["纠结", "矛盾", "要不要", "两难", "选哪个", "怎么办", "建议"],
        "required_dims": ["cognitive", "game_theory", "economic", "dialectical", "emotional", "temporal"],
        "description": "需要权衡的复杂决策",
    },
    "critical": {
        "keywords": ["辞职", "离婚", "投资", "法律", "生死", "不可逆", "重大", "关键"],
        "required_dims": [d.id for d in DIMENSIONS],  # 全部十维
        "description": "重大不可逆决策",
    },
}


def classify_complexity(task: str) -> str:
    """根据任务内容判断复杂度级别"""
    task_lower = task.lower()
    
    # 从 critical 开始检查（最高优先级）
    for level in ["critical", "complex", "simple"]:
        for keyword in COMPLEXITY_RULES[level]["keywords"]:
            if keyword in task_lower:
                return level
    
    # 默认返回 simple
    return "simple"


def get_dimensions_for_complexity(level: str) -> List[Dimension]:
    """获取指定复杂度级别需要检视的维度"""
    dim_ids = COMPLEXITY_RULES[level]["required_dims"]
    return [d for d in DIMENSIONS if d.id in dim_ids]


if __name__ == "__main__":
    # 测试
    test_tasks = [
        "怎么安装 Python？",
        "我要不要辞职？",
        "这个投资决定很关键",
    ]
    
    for task in test_tasks:
        level = classify_complexity(task)
        dims = get_dimensions_for_complexity(level)
        print(f"任务: {task}")
        print(f"复杂度: {level} ({COMPLEXITY_RULES[level]['description']})")
        print(f"检视维度: {[d.name for d in dims]}")
        print()
