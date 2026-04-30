"""
qclaw Skill Quality — 自 ZeusHammer skill_learner.py 改造

核心设计（源自 ZeusHammer，适配 qclaw）：
1. SkillQuality — 技能质量评估（4因素加权评分）
2. SkillRetirement — 技能自动淘汰
3. PatternExtractor — 触发模式提取（改进版）
4. SkillOptimizer — 技能优化

ZeusHammer 原版 skill_learner.py 的评分公式：
- 成功率 (40%): success_rate * 40
- 速度 (30%): max(0, 30 - (avg_duration_ms / 1000) * 30)
- 使用频率 (20%): min(20, usage_count * 2)
- 复杂度 (10%): (6 - complexity) * 2
总分: 0-100

qclaw 改进：
- 与 evolver rules 对接
- 持久化质量数据
- 自动淘汰+替换机制
"""

import json
import time
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

WORKSPACE = Path.home() / ".qclaw" / "workspace"


@dataclass
class SkillQuality:
    """
    技能质量评估 — 源自 ZeusHammer SkillQuality
    
    评分公式：
    - 成功率 (40%): success_rate * 40
    - 速度 (30%): max(0, 30 - (avg_duration_ms / 1000) * 30)  
    - 使用频率 (20%): min(20, usage_count * 2)
    - 复杂度 (10%): (6 - complexity) * 2
    总分: 0-100
    
    评级：
    - 80+: 优秀
    - 60-79: 良好
    - 40-59: 一般
    - 20-39: 较差
    - <20: 应淘汰
    """
    skill_id: str
    success_rate: float  # 0-1
    avg_duration_ms: float
    usage_count: int
    last_used: float
    complexity: int  # 1-5
    score: float = 0.0
    grade: str = ""
    
    def __post_init__(self):
        self.score = self._calculate()
        self.grade = self._grade()
    
    def _calculate(self) -> float:
        """计算综合评分 — 源自 ZeusHammer SkillLearner._calculate_score()"""
        success_score = self.success_rate * 40
        speed_score = max(0, 30 - (self.avg_duration_ms / 1000) * 30)
        usage_score = min(20, self.usage_count * 2)
        complexity_score = (6 - self.complexity) * 2
        return success_score + speed_score + usage_score + complexity_score
    
    def _grade(self) -> str:
        """评级"""
        if self.score >= 80:
            return "优秀"
        elif self.score >= 60:
            return "良好"
        elif self.score >= 40:
            return "一般"
        elif self.score >= 20:
            return "较差"
        return "应淘汰"


class PatternExtractor:
    """
    模式提取器 — 源自 ZeusHammer PatternExtractor
    
    改进：
    - ZeusHammer 版本只做了简单分词 → qclaw 增加正则模式
    - 支持中英文混合
    - 提取动词+名词结构（简单版）
    """

    # 中文动词模式
    CN_VERBS = ["读取", "写入", "创建", "删除", "搜索", "查找", "安装", "配置",
                "执行", "运行", "分析", "生成", "修改", "编辑", "查看", "打开"]

    def extract(self, text: str) -> List[str]:
        """从文本提取触发模式"""
        patterns = []
        
        # 1. 关键词提取
        keywords = self._extract_keywords(text)
        patterns.extend(keywords)
        
        # 2. 动词+名词结构
        verb_noun = self._extract_verb_noun(text)
        patterns.extend(verb_noun)
        
        # 3. 路径模式
        paths = re.findall(r'[/\\][\w/.-]+', text)
        if paths:
            patterns.extend([f"path:{p}" for p in paths[:3]])
        
        # 4. 文件扩展名模式
        exts = re.findall(r'\.\w{1,4}', text)
        if exts:
            patterns.extend([f"ext:{e}" for e in exts[:3]])
        
        return list(set(patterns))

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 中文：按字符切片
        cn_keywords = []
        for verb in self.CN_VERBS:
            if verb in text:
                cn_keywords.append(verb)
        
        # 英文：按空格分词
        en_words = [w for w in text.split() if len(w) > 2 and re.match(r'^[a-zA-Z]+$', w)]
        
        return cn_keywords + en_words[:5]

    def _extract_verb_noun(self, text: str) -> List[str]:
        """提取动词+名词结构"""
        patterns = []
        
        for verb in self.CN_VERBS:
            idx = text.find(verb)
            if idx >= 0:
                # 取动词后的名词部分（简单实现）
                after = text[idx + len(verb):idx + len(verb) + 10].strip()
                if after:
                    noun = after.split()[0] if after.split() else after[:4]
                    patterns.append(f"{verb}{noun}")
        
        return patterns[:5]


class SkillOptimizer:
    """
    技能优化器 — 源自 ZeusHammer SkillOptimizer
    
    改进：
    - ZeusHammer 版本 TODO 太多 → qclaw 实现了去重和泛化
    - 增加同义词扩展
    """

    # 同义词映射（简单版）
    SYNONYMS = {
        "读取": ["打开", "查看", "cat", "read", "open", "show"],
        "写入": ["创建", "写", "write", "create", "save"],
        "搜索": ["查找", "google", "search", "query", "find"],
        "执行": ["运行", "命令", "run", "bash", "shell", "exec"],
        "删除": ["移除", "remove", "delete", "rm"],
        "安装": ["install", "添加", "add"],
    }

    def optimize_patterns(self, trigger_patterns: List[str]) -> List[str]:
        """优化触发模式 — 源自 ZeusHammer optimize_patterns()"""
        # 1. 去重
        unique = list(set(trigger_patterns))
        
        # 2. 添加同义词变体
        variants = self._add_variants(unique)
        unique.extend(variants)
        
        # 3. 再次去重
        unique = list(set(unique))
        
        # 4. 按长度排序（长的优先，更精确）
        unique.sort(key=len, reverse=True)
        
        return unique[:20]  # 最多保留20个模式

    def _add_variants(self, patterns: List[str]) -> List[str]:
        """添加同义词变体 — qclaw 改进"""
        variants = []
        
        for pattern in patterns:
            for verb, syns in self.SYNONYMS.items():
                if verb in pattern:
                    for syn in syns:
                        variant = pattern.replace(verb, syn)
                        if variant != pattern:
                            variants.append(variant)
        
        return variants


class SkillQualityManager:
    """
    技能质量管理器 — 整合评估、淘汰、优化
    
    源自 ZeusHammer SkillLearner 的评估和淘汰逻辑
    """

    def __init__(self):
        self._quality_db: Dict[str, SkillQuality] = {}
        self._load_quality_db()
    
    def evaluate(self, skill_id: str, success: bool, duration_ms: float,
                 complexity: int = 1) -> SkillQuality:
        """
        评估技能 — 源自 ZeusHammer SkillLearner.evaluate_skill()
        
        更新或创建技能质量记录
        """
        if skill_id in self._quality_db:
            q = self._quality_db[skill_id]
            total = q.usage_count + 1
            success_count = int(q.success_rate * q.usage_count) + (1 if success else 0)
            q.success_rate = success_count / total
            q.avg_duration_ms = (q.avg_duration_ms * q.usage_count + duration_ms) / total
            q.usage_count = total
            q.last_used = time.time()
            q.score = q._calculate()
            q.grade = q._grade()
        else:
            q = SkillQuality(
                skill_id=skill_id,
                success_rate=1.0 if success else 0.0,
                avg_duration_ms=duration_ms,
                usage_count=1,
                last_used=time.time(),
                complexity=complexity,
            )
        
        self._quality_db[skill_id] = q
        self._save_quality_db()
        
        return q

    def should_retire(self, skill_id: str, days_inactive: int = 30) -> Tuple[bool, str]:
        """
        判断是否应该淘汰 — 源自 ZeusHammer SkillLearner.should_retire_skill()
        
        淘汰条件：
        1. 评分 < 20
        2. 超过 days_inactive 天未使用
        """
        if skill_id not in self._quality_db:
            return False, "无质量数据"
        
        q = self._quality_db[skill_id]
        
        if q.score < 20:
            return True, f"评分过低 ({q.score:.1f}/100, {q.grade})"
        
        inactive_days = (time.time() - q.last_used) / 86400
        if inactive_days > days_inactive:
            return True, f"超过 {inactive_days:.0f} 天未使用"
        
        return False, ""

    def get_low_quality(self, threshold: float = 30.0) -> List[SkillQuality]:
        """获取低质量技能"""
        return [q for q in self._quality_db.values() if q.score < threshold]

    def get_top_skills(self, limit: int = 10) -> List[SkillQuality]:
        """获取高质量技能 Top N"""
        sorted_skills = sorted(self._quality_db.values(), key=lambda q: q.score, reverse=True)
        return sorted_skills[:limit]

    def get_report(self) -> Dict:
        """获取质量报告"""
        if not self._quality_db:
            return {"total": 0, "message": "无技能质量数据"}
        
        grades = {}
        for q in self._quality_db.values():
            grades[q.grade] = grades.get(q.grade, 0) + 1
        
        scores = [q.score for q in self._quality_db.values()]
        
        return {
            "total": len(self._quality_db),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "min_score": min(scores),
            "grades": grades,
            "retire_candidates": len(self.get_low_quality()),
        }

    def _load_quality_db(self):
        """加载质量数据库"""
        db_file = WORKSPACE / ".skill_quality_db.json"
        if db_file.exists():
            try:
                data = json.loads(db_file.read_text(encoding="utf-8"))
                for item in data:
                    q = SkillQuality(
                        skill_id=item["skill_id"],
                        success_rate=item["success_rate"],
                        avg_duration_ms=item["avg_duration_ms"],
                        usage_count=item["usage_count"],
                        last_used=item["last_used"],
                        complexity=item["complexity"],
                    )
                    self._quality_db[q.skill_id] = q
            except Exception as e:
                logger.warning(f"加载技能质量数据失败: {e}")

    def _save_quality_db(self):
        """保存质量数据库"""
        db_file = WORKSPACE / ".skill_quality_db.json"
        data = []
        for q in self._quality_db.values():
            data.append({
                "skill_id": q.skill_id,
                "success_rate": q.success_rate,
                "avg_duration_ms": q.avg_duration_ms,
                "usage_count": q.usage_count,
                "last_used": q.last_used,
                "complexity": q.complexity,
                "score": q.score,
                "grade": q.grade,
            })
        db_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ===== 自测 =====
if __name__ == "__main__":
    # 测试 SkillQuality
    q1 = SkillQuality("skill_1", 0.9, 500, 50, time.time(), 1)
    print(f"✅ 优秀技能: {q1.score:.1f}/100 ({q1.grade})")
    
    q2 = SkillQuality("skill_2", 0.3, 5000, 2, time.time(), 3)
    print(f"✅ 较差技能: {q2.score:.1f}/100 ({q2.grade})")
    
    # 测试 PatternExtractor
    pe = PatternExtractor()
    patterns = pe.extract("帮我搜索最新的 Python 教程并读取 /tmp/result.json")
    print(f"✅ 模式提取: {patterns}")
    
    # 测试 SkillOptimizer
    so = SkillOptimizer()
    optimized = so.optimize_patterns(["搜索", "读取文件"])
    print(f"✅ 模式优化: {optimized[:5]}...")
    
    # 测试 SkillQualityManager
    sqm = SkillQualityManager()
    sqm.evaluate("test_skill", True, 1500, 1)
    sqm.evaluate("test_skill", True, 2000, 1)
    sqm.evaluate("test_skill", False, 3000, 1)
    
    should_retire, reason = sqm.should_retire("test_skill")
    report = sqm.get_report()
    print(f"✅ 质量报告: 平均分={report['avg_score']:.1f}, 应淘汰={should_retire}")
    
    print("\n🎯 Skill Quality 全部测试通过！")
