"""
qclaw Local Brain — 自 ZeusHammer local_brain.py 改造

核心设计（源自 ZeusHammer，适配 qclaw）：
1. 意图理解 → evolver.best_method 代替关键词匹配
2. 技能匹配 → skill_metadata 三层披露 + 评分公式
3. 短路执行 → 命中技能直接执行，不调 LLM
4. 自动学习 → 工作记录 → 新技能

与 ZeusHammer 的关键区别：
- ZeusHammer 用关键词做意图理解 → qclaw 用 evolver 置信度
- ZeusHammer 用内存字典存技能 → qclaw 用 skill_metadata JSONL
- ZeusHammer 没有持久化 → qclaw 持久化到文件
"""

import json
import time
import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# qclaw workspace 路径
WORKSPACE = Path.home() / ".qclaw" / "workspace"

class IntentType(Enum):
    """意图类型 — 扩展自 ZeusHammer，适配 qclaw 工具体系"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    CODE_EXEC = "code_exec"
    SKILL_INSTALL = "skill_install"
    MEMORY_WRITE = "memory_write"
    MEMORY_READ = "memory_read"
    AGENT_DELEGATE = "agent_delegate"
    BROWSER = "browser"
    MESSAGE_SEND = "message_send"
    QUESTION = "question"
    TASK = "task"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """用户意图"""
    type: IntentType
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""
    language: str = "zh"


@dataclass
class Skill:
    """技能定义 — 兼容 ZeusHammer 格式 + qclaw skill_metadata"""
    id: str
    name: str
    description: str
    trigger_patterns: List[str]
    intent_type: IntentType
    actions: List[Dict]
    examples: List[str]
    usage_count: int = 0
    success_count: int = 0
    last_used: float = 0
    created_at: float = field(default_factory=time.time)
    learned_from: str = ""
    source: str = "builtin"  # builtin / learned / evolver


@dataclass
class WorkRecord:
    """工作记录"""
    id: str
    input: str
    output: str
    intent: Intent
    actions: List[Dict]
    success: bool
    duration_ms: float
    created_at: float = field(default_factory=time.time)
    converted_to_skill: bool = False


@dataclass
class ThinkResult:
    """思考结果"""
    matched_skill: Optional[Skill] = None
    needs_llm: bool = True
    confidence: float = 0.0
    evolver_method: Optional[Dict] = None  # evolver.best_method 返回
    response: str = ""


class QClawLocalBrain:
    """
    qclaw 本地大脑
    
    核心流程（源自 ZeusHammer WorkflowEngine）：
    输入 → 意图理解 → evolver经验匹配 → skill匹配 → 短路执行/LLM → 学习
    
    与 evolver 的集成：
    - evolver.best_method() 提供"有没有做过类似的事"
    - skill_metadata 提供"有没有匹配的技能"
    - 两者都没命中 → 调 LLM
    - 执行完 → evolver.record() + 自动学习
    """

    def __init__(self, evolver=None, skill_metadata=None):
        self.evolver = evolver  # evolver.EvolverEngine
        self.skill_metadata = skill_metadata
        
        # 技能库（运行时）
        self._skills: Dict[str, Skill] = {}
        
        # 工作历史（运行时，持久化到 memory/）
        self._work_history: List[WorkRecord] = []
        
        # 统计
        self._stats = {
            "total_requests": 0,
            "skill_hits": 0,       # 技能直接命中
            "evolver_hits": 0,     # evolver 经验命中
            "llm_calls": 0,        # 需要 LLM
            "skills_learned": 0,   # 自动学习的新技能
        }
        
        # 注册内置技能
        self._register_builtin_skills()
        
        # 加载已学习技能
        self._load_learned_skills()

    def _register_builtin_skills(self):
        """注册 qclaw 内置技能 — 从 ZeusHammer 改造"""
        builtin_skills = [
            Skill(
                id="builtin_file_read",
                name="读取文件",
                description="读取指定路径的文件内容",
                trigger_patterns=["读取文件", "打开文件", "查看文件", "cat", "read file", "show content"],
                intent_type=IntentType.FILE_READ,
                actions=[{"tool": "read", "params": {"path": "{path}"}}],
                examples=["读取 config.json", "查看日志文件"],
            ),
            Skill(
                id="builtin_file_write",
                name="写入文件",
                description="创建或覆盖文件内容",
                trigger_patterns=["写入文件", "创建文件", "写文件", "write file", "create file", "save"],
                intent_type=IntentType.FILE_WRITE,
                actions=[{"tool": "write", "params": {"path": "{path}", "content": "{content}"}}],
                examples=["创建 SKILL.md", "写入配置"],
            ),
            Skill(
                id="builtin_web_search",
                name="网络搜索",
                description="搜索互联网获取信息",
                trigger_patterns=["搜索", "查找", "google", "search", "query"],
                intent_type=IntentType.WEB_SEARCH,
                actions=[{"tool": "web_search", "params": {"query": "{query}"}}],
                examples=["搜索 Python 教程", "查找最新消息"],
            ),
            Skill(
                id="builtin_exec",
                name="执行命令",
                description="执行 shell 命令",
                trigger_patterns=["执行命令", "运行命令", "终端", "run", "bash", "shell", "exec"],
                intent_type=IntentType.CODE_EXEC,
                actions=[{"tool": "exec", "params": {"command": "{command}"}}],
                examples=["执行 git status", "运行测试"],
            ),
            Skill(
                id="builtin_skill_install",
                name="安装技能",
                description="安装 SkillHub 技能",
                trigger_patterns=["安装技能", "安装skill", "install skill", "添加技能"],
                intent_type=IntentType.SKILL_INSTALL,
                actions=[{"tool": "skillhub_install", "params": {"action": "install_skill", "skillName": "{name}"}}],
                examples=["安装 pdf 技能"],
            ),
            Skill(
                id="builtin_memory_write",
                name="写入记忆",
                description="写入记忆文件",
                trigger_patterns=["记住", "记下来", "写记忆", "remember", "save memory"],
                intent_type=IntentType.MEMORY_WRITE,
                actions=[{"tool": "write", "params": {"path": "{path}", "content": "{content}"}}],
                examples=["记住这个决定", "写下今天的收获"],
            ),
        ]
        
        for skill in builtin_skills:
            self._skills[skill.id] = skill

    def _load_learned_skills(self):
        """加载已学习的技能"""
        skills_file = WORKSPACE / ".learned_skills.json"
        if skills_file.exists():
            try:
                data = json.loads(skills_file.read_text(encoding="utf-8"))
                for s in data:
                    skill = Skill(
                        id=s["id"],
                        name=s["name"],
                        description=s["description"],
                        trigger_patterns=s.get("trigger_patterns", []),
                        intent_type=IntentType(s.get("intent_type", "unknown")),
                        actions=s.get("actions", []),
                        examples=s.get("examples", []),
                        usage_count=s.get("usage_count", 0),
                        success_count=s.get("success_count", 0),
                        last_used=s.get("last_used", 0),
                        created_at=s.get("created_at", time.time()),
                        learned_from=s.get("learned_from", ""),
                        source="learned",
                    )
                    self._skills[skill.id] = skill
                logger.info(f"加载了 {len(data)} 个已学习技能")
            except Exception as e:
                logger.warning(f"加载已学习技能失败: {e}")

    def _save_learned_skills(self):
        """持久化已学习的技能"""
        skills_file = WORKSPACE / ".learned_skills.json"
        learned = []
        for skill in self._skills.values():
            if skill.source == "learned":
                learned.append({
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "trigger_patterns": skill.trigger_patterns,
                    "intent_type": skill.intent_type.value,
                    "actions": skill.actions,
                    "examples": skill.examples,
                    "usage_count": skill.usage_count,
                    "success_count": skill.success_count,
                    "last_used": skill.last_used,
                    "created_at": skill.created_at,
                    "learned_from": skill.learned_from,
                })
        skills_file.write_text(json.dumps(learned, indent=2, ensure_ascii=False), encoding="utf-8")

    def think(self, user_input: str) -> ThinkResult:
        """
        本地大脑思考 — 三层匹配
        
        1. evolver 经验匹配（最快，0 API 调用）
        2. skill 触发模式匹配（次快，0 API 调用）
        3. 都没命中 → 需要 LLM
        
        源自 ZeusHammer LocalBrain.think()，但增加了 evolver 层
        """
        self._stats["total_requests"] += 1
        
        # Step 1: evolver 经验匹配
        evolver_result = None
        if self.evolver:
            try:
                evolver_result = self.evolver.best_method({"task": user_input})
                if evolver_result and evolver_result.get("confidence", 0) >= 0.7:
                    self._stats["evolver_hits"] += 1
                    return ThinkResult(
                        matched_skill=None,
                        needs_llm=False,
                        confidence=evolver_result["confidence"],
                        evolver_method=evolver_result,
                        response=f"evolver命中: {evolver_result['method']} (置信度{evolver_result['confidence']:.2f})",
                    )
            except Exception as e:
                logger.debug(f"evolver 查询失败: {e}")

        # Step 2: 理解意图 + skill 匹配
        intent = self._understand_intent(user_input)
        matched_skill = self._match_skill(intent, user_input)

        if matched_skill:
            self._stats["skill_hits"] += 1
            return ThinkResult(
                matched_skill=matched_skill,
                needs_llm=False,
                confidence=self._calculate_skill_confidence(matched_skill),
            )

        # Step 3: 需要 LLM
        self._stats["llm_calls"] += 1
        return ThinkResult(
            matched_skill=None,
            needs_llm=True,
            confidence=0.0,
            evolver_method=evolver_result,  # 可能有低置信度的 evolver 建议
        )

    def record_work(self, user_input: str, output: str, success: bool,
                    actions: List[Dict] = None, duration_ms: float = 0):
        """
        记录工作结果 → 用于自动学习
        
        源自 ZeusHammer _learn_from_work，但与 evolver.record 集成
        """
        intent = self._understand_intent(user_input)
        
        work = WorkRecord(
            id=self._generate_id(),
            input=user_input,
            output=output[:500],  # 截断
            intent=intent,
            actions=actions or [],
            success=success,
            duration_ms=duration_ms,
        )
        
        self._work_history.append(work)
        
        # 自动学习新技能
        if success and duration_ms > 1000 and actions:
            self._try_learn_skill(work)
        
        # 持久化
        self._save_work_record(work)
        
        return work

    def _try_learn_skill(self, work: WorkRecord):
        """
        尝试从工作记录学习新技能
        
        源自 ZeusHammer local_brain._learn_from_work()
        学习条件：成功 + 耗时>1s + 有动作 + 无已有类似技能
        """
        if work.converted_to_skill:
            return
        
        # 检查是否已有类似技能
        existing = self._match_skill(work.intent, work.input)
        if existing:
            return
        
        # 创建新技能
        skill = Skill(
            id=f"learned_{work.id}",
            name=self._extract_name(work.input),
            description=f"从工作学习: {work.input[:80]}...",
            trigger_patterns=self._extract_patterns(work.input),
            intent_type=work.intent.type,
            actions=work.actions,
            examples=[work.input],
            learned_from=work.id,
            source="learned",
        )
        
        self._skills[skill.id] = skill
        work.converted_to_skill = True
        self._stats["skills_learned"] += 1
        
        logger.info(f"学习新技能: {skill.name}")
        self._save_learned_skills()

    def _understand_intent(self, user_input: str) -> Intent:
        """
        理解用户意图 — 源自 ZeusHammer，扩展 qclaw 特有意图
        
        改进：优先级更合理，增加 qclaw 工具类型
        """
        text = user_input.lower()
        entities = {}

        # 路径检测
        paths = re.findall(r'[/\\][\w/.-]+', user_input)
        if paths:
            entities["paths"] = paths

        # 代码检测
        if any(kw in text for kw in ["function", "def ", "class ", "import ", "const ", "let ", "var "]):
            entities["has_code"] = True

        # 意图分类（优先级从高到低）
        # qclaw 特有：技能安装
        if any(p in text for p in ["安装技能", "安装skill", "install skill", "添加技能"]):
            intent_type = IntentType.SKILL_INSTALL
        # qclaw 特有：记忆写入
        elif any(p in text for p in ["记住", "记下来", "写记忆", "remember", "save memory"]):
            intent_type = IntentType.MEMORY_WRITE
        # qclaw 特有：代理委派
        elif any(p in text for p in ["子代理", "subagent", "委派", "delegate"]):
            intent_type = IntentType.AGENT_DELEGATE
        # 搜索
        elif any(p in text for p in ["搜索", "查找", "google", "search", "query", "问", "打听"]):
            intent_type = IntentType.WEB_SEARCH
        # 文件读取
        elif any(p in text for p in ["读取", "打开", "查看", "cat", "read", "show", "open"]):
            intent_type = IntentType.FILE_READ
        # 文件写入
        elif any(p in text for p in ["写入", "创建", "save", "write", "create"]):
            intent_type = IntentType.FILE_WRITE
        # 文件编辑
        elif any(p in text for p in ["编辑", "修改", "edit", "change"]):
            intent_type = IntentType.FILE_EDIT
        # 命令执行
        elif any(p in text for p in ["执行", "运行", "命令", "run", "bash", "shell", "exec"]):
            intent_type = IntentType.CODE_EXEC
        # 浏览器
        elif any(p in text for p in ["浏览", "打开网页", "browse", "navigate", "截图"]):
            intent_type = IntentType.BROWSER
        # 问题
        elif any(p in text for p in ["什么", "如何", "为什么", "why", "how", "what", "?"]):
            intent_type = IntentType.QUESTION
        else:
            intent_type = IntentType.UNKNOWN

        # 置信度
        confidence = 0.5
        if entities.get("paths"):
            confidence += 0.15
        if entities.get("has_code"):
            confidence += 0.15

        language = "zh" if any('\u4e00' <= c <= '\u9fff' for c in user_input) else "en"

        return Intent(
            type=intent_type,
            confidence=min(confidence, 1.0),
            entities=entities,
            raw_input=user_input,
            language=language,
        )

    def _match_skill(self, intent: Intent, user_input: str) -> Optional[Skill]:
        """
        技能匹配 — 源自 ZeusHammer _match_skill()
        
        评分公式（源自 ZeusHammer，微调权重）：
        - 意图类型匹配: 0.4
        - 触发模式匹配: 0.3
        - 使用频率加成: 0.1
        - 成功率加成:   0.2
        阈值: >= 0.5
        """
        user_lower = user_input.lower()
        best_match = None
        best_score = 0.0

        for skill_id, skill in self._skills.items():
            score = 0.0

            # 1. 意图类型匹配
            if skill.intent_type == intent.type:
                score += 0.4

            # 2. 触发模式匹配
            for pattern in skill.trigger_patterns:
                pattern_lower = pattern.lower()
                if pattern_lower in user_lower:
                    score += 0.3
                elif pattern_lower.split()[0] in user_lower if pattern_lower.split() else False:
                    score += 0.1

            # 3. 使用频率加成
            if skill.usage_count > 10:
                score += 0.1
            elif skill.usage_count > 0:
                score += 0.05 * min(skill.usage_count / 10, 1)

            # 4. 成功率加成
            if skill.usage_count > 0:
                success_rate = skill.success_count / skill.usage_count
                score += success_rate * 0.2

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = skill

        return best_match

    def _calculate_skill_confidence(self, skill: Skill) -> float:
        """计算技能置信度"""
        if skill.usage_count == 0:
            return 0.5
        success_rate = skill.success_count / skill.usage_count
        freq_bonus = min(skill.usage_count / 50, 0.2)
        return min(success_rate + freq_bonus, 1.0)

    def _extract_name(self, input_text: str) -> str:
        """提取技能名称"""
        return input_text[:25].strip().replace(" ", "_")

    def _extract_patterns(self, input_text: str) -> List[str]:
        """提取触发模式 — 源自 ZeusHammer"""
        patterns = [input_text]
        keywords = [w for w in input_text.split() if len(w) > 2]
        patterns.extend(keywords[:5])
        return patterns

    def _generate_id(self) -> str:
        """生成 ID"""
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:12]

    def _save_work_record(self, work: WorkRecord):
        """保存工作记录到 memory/"""
        log_file = WORKSPACE / "memory" / "work_history.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        record = {
            "id": work.id,
            "input": work.input[:200],
            "success": work.success,
            "duration_ms": work.duration_ms,
            "intent_type": work.intent.type.value,
            "converted_to_skill": work.converted_to_skill,
            "timestamp": work.created_at,
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_stats(self) -> Dict:
        """获取统计 — 源自 ZeusHammer WorkflowEngine.get_stats()"""
        total = self._stats["total_requests"]
        if total == 0:
            return {**self._stats, "hit_rate": 0.0}
        
        skill_hit_rate = self._stats["skill_hits"] / total
        evolver_hit_rate = self._stats["evolver_hits"] / total
        
        return {
            **self._stats,
            "skill_hit_rate": f"{skill_hit_rate:.1%}",
            "evolver_hit_rate": f"{evolver_hit_rate:.1%}",
            "total_hit_rate": f"{skill_hit_rate + evolver_hit_rate:.1%}",
            "total_skills": len(self._skills),
            "learned_skills": sum(1 for s in self._skills.values() if s.source == "learned"),
        }


# ===== 自测 =====
if __name__ == "__main__":
    brain = QClawLocalBrain()
    
    # 测试1: 意图理解
    intent = brain._understand_intent("帮我搜索最新的 AI 新闻")
    assert intent.type == IntentType.WEB_SEARCH, f"Expected WEB_SEARCH, got {intent.type}"
    print(f"✅ 意图理解: {intent.type.value} (置信度={intent.confidence:.2f})")
    
    # 测试2: 技能匹配
    result = brain.think("搜索 Python 教程")
    assert result.matched_skill is not None, "Should match builtin_web_search"
    print(f"✅ 技能匹配: {result.matched_skill.name} (置信度={result.confidence:.2f})")
    
    # 测试3: 未匹配 → 需要 LLM
    result2 = brain.think("帮我分析一下这段代码的架构问题")
    assert result2.needs_llm, "Should need LLM"
    print(f"✅ LLM 需要: needs_llm={result2.needs_llm}")
    
    # 测试4: 工作记录 + 自动学习
    work = brain.record_work(
        "分析代码架构并生成报告",
        "架构分析完成：采用微服务架构...",
        success=True,
        actions=[{"tool": "read", "params": {}}, {"tool": "write", "params": {}}],
        duration_ms=3500,
    )
    print(f"✅ 工作记录: {work.id}, 转化为技能={work.converted_to_skill}")
    
    # 测试5: 统计
    stats = brain.get_stats()
    print(f"✅ 统计: {json.dumps(stats, ensure_ascii=False, indent=2)}")
    
    print("\n🎯 QClawLocalBrain 全部测试通过！")
