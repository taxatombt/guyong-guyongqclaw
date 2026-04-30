"""
qclaw_unified_skill.py — 统一技能管理器

整合来源（5个模块 → 1个）：
  1. skill_scanner_v2.py      → 安全扫描（注入/exfil/网络）
  2. skill_tester.py         → TDD测试（baseline→with_skill）
  3. skill_router.py          → 任务路由（关键词/正则/类别）
  4. skill_collision_detector.py → 冲突检测
  5. skillify_skill.py       → 技能生成（任务→skill）

设计：
  - 5大能力统一API
  - 与 evolver / zeushammer local_brain 集成
  - 与 managed-agents skill_metadata 互补
"""

import json
import re
import time
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

WORKSPACE = Path.home() / ".qclaw" / "workspace"
SKILLS_PATH = WORKSPACE / "skills"


# ═══════════════════════════════════════════════════════
# 数据类型
# ═══════════════════════════════════════════════════════

class Severity(Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrustLevel(Enum):
    BUILTIN = "builtin"
    TRUSTED = "trusted"
    COMMUNITY = "community"
    AGENT_CREATED = "agent-created"


@dataclass
class SecurityFinding:
    """安全发现 — 源自 skill_scanner_v2"""
    pattern_id: str
    severity: Severity
    category: str
    file: str
    line_num: int
    match: str
    description: str


@dataclass
class ScanResult:
    """扫描结果"""
    skill_name: str
    source: str
    trust_level: TrustLevel
    verdict: str  # safe / caution / dangerous
    findings: List[SecurityFinding] = field(default_factory=list)
    scanned_at: str = ""


@dataclass
class TestResult:
    """测试结果 — 源自 skill_tester"""
    timestamp: str
    skill_name: str
    scenario: str
    mode: str  # baseline / with_skill
    agent_behavior: str
    rule_violations: List[str]
    passed: bool
    notes: str = ""


@dataclass
class SkillRoute:
    """路由结果 — 源自 skill_router"""
    skill_name: str
    confidence: float
    reason: str
    trigger: str  # keyword / regex / category


@dataclass
class Collision:
    """冲突发现 — 源自 skill_collision_detector"""
    skill_a: str
    skill_b: str
    overlap_type: str  # keyword / pattern / function
    overlap_value: str
    severity: str


# ═══════════════════════════════════════════════════════
# 能力1: 安全扫描 — 源自 skill_scanner_v2.py
# ═══════════════════════════════════════════════════════

SECURITY_PATTERNS = [
    # Exfiltration
    (r"curl\s+.*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)", "exfil", "Curl with secret", Severity.HIGH),
    (r"cat\s+.*\.env", "exfil", "Reading .env", Severity.HIGH),
    (r"wget\s+.*\|\s*bash", "exfil", "Remote exec", Severity.CRITICAL),
    # Injection
    (r"\beval\s*\(", "injection", "eval()", Severity.CRITICAL),
    (r"\bexec\s*\(", "injection", "exec()", Severity.CRITICAL),
    (r"new\s+Function\s*\(", "injection", "new Function()", Severity.CRITICAL),
    (r"pickle\.loads?\s*\(", "injection", "pickle.loads", Severity.CRITICAL),
    (r"SQL\s*\(\s*f[\"']", "injection", "SQL f-string", Severity.CRITICAL),
    # Destructive
    (r"rm\s+-rf\s+/", "destructive", "rm -rf /", Severity.CRITICAL),
    (r"DROP\s+TABLE", "destructive", "SQL DROP", Severity.CRITICAL),
    # Persistence
    (r"authorized_keys", "persistence", "SSH backdoor", Severity.CRITICAL),
    # Network
    (r"requests\.(get|post|put|delete)\s*\(", "network", "HTTP request", Severity.LOW),
    (r"httpx\.(get|post)\s*\(", "network", "httpx HTTP", Severity.LOW),
    (r"socket\.connect\s*\(", "network", "Raw socket", Severity.MEDIUM),
]

TRUSTED_REPOS = {"openai/skills", "anthropic/skills", "clawhub/skills"}

INSTALL_POLICY = {
    "safe":    {"builtin": "allow", "trusted": "allow", "community": "allow", "agent-created": "allow"},
    "caution": {"builtin": "allow", "trusted": "allow", "community": "block", "agent-created": "ask"},
    "dangerous": {"builtin": "allow", "trusted": "block", "community": "block", "agent-created": "block"},
}


class SkillScanner:
    """
    技能安全扫描器 — 源自 skill_scanner_v2.py
    
    信任层级:
      - builtin: OpenClaw 内置
      - trusted: 知名仓库（openai/anthropic/clawhub）
      - community: 社区贡献
      - agent-created: Agent 自动创建
    
    策略:
      - safe: 全放行
      - caution: community=block, agent-created=ask
      - dangerous: 只放行 builtin
    """
    
    def scan(self, path: Path, source: str = "community") -> ScanResult:
        """扫描技能目录或文件"""
        findings = []
        
        if path.is_dir():
            for f in path.rglob("*"):
                if f.is_file() and not f.name.startswith("."):
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        findings.extend(self._scan_content(content, str(f.relative_to(path))))
                    except Exception:
                        pass
        elif path.is_file():
            try:
                findings = self._scan_content(path.read_text(encoding="utf-8", errors="ignore"), path.name)
            except Exception:
                pass
        
        tl = self._trust_level(source)
        ver = self._verdict(findings)
        
        return ScanResult(
            skill_name=path.name,
            source=source,
            trust_level=tl,
            verdict=ver,
            findings=findings,
            scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )
    
    def _scan_content(self, content: str, filename: str) -> List[SecurityFinding]:
        findings = []
        for i, line in enumerate(content.split("\n"), 1):
            for pattern, cat, desc, sev in SECURITY_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    m = re.search(pattern, line, re.IGNORECASE)
                    findings.append(SecurityFinding(
                        pattern_id=f"{cat}_{i}",
                        severity=sev,
                        category=cat,
                        file=filename,
                        line_num=i,
                        match=m.group(0) if m else "",
                        description=desc,
                    ))
        return findings
    
    def _trust_level(self, source: str) -> TrustLevel:
        if source in TRUSTED_REPOS:
            return TrustLevel.TRUSTED
        if source.startswith("builtin:"):
            return TrustLevel.BUILTIN
        if source.startswith("agent-created:"):
            return TrustLevel.AGENT_CREATED
        return TrustLevel.COMMUNITY
    
    def _verdict(self, findings: List[SecurityFinding]) -> str:
        if not findings:
            return "safe"
        sevs = {f.severity for f in findings}
        if Severity.CRITICAL in sevs or Severity.HIGH in sevs:
            return "dangerous"
        return "caution"
    
    def allow_install(self, result: ScanResult, force: bool = False) -> Tuple[bool, str]:
        """判断是否允许安装"""
        action = INSTALL_POLICY.get(result.verdict, {}).get(result.trust_level.value, "block")
        if action == "allow":
            return True, "allow"
        if action == "ask":
            return False, "ask"
        if force:
            return True, "forced"
        return False, "blocked"


# ═══════════════════════════════════════════════════════
# 能力2: TDD测试 — 源自 skill_tester.py
# ═══════════════════════════════════════════════════════

class SkillTester:
    """
    技能TDD测试 — 源自 skill_tester.py
    
    Superpowers原则: No skill without failing test first
    
    流程:
      1. RED: 无skill跑baseline，记录agent自然行为
      2. GREEN: 加skill再跑，验证是否解决问题
      3. REFACTOR: 如果还有漏洞，补skill
    """
    
    def __init__(self):
        self._results_path = WORKSPACE / ".skill_test_results.json"
        self.results = self._load()
    
    def _load(self) -> List[Dict]:
        if self._results_path.exists():
            try:
                return json.loads(self._results_path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []
    
    def _save(self):
        self._results_path.write_text(
            json.dumps(self.results, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def run_baseline(self, task: str, scenario: str, 
                     agent_behavior: str = "", violations: List[str] = None) -> TestResult:
        """RED Phase: 无skill baseline"""
        result = TestResult(
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
            skill_name="baseline",
            scenario=scenario,
            mode="baseline",
            agent_behavior=agent_behavior,
            rule_violations=violations or [],
            passed=False,
        )
        self.results.append(asdict(result))
        self._save()
        return result
    
    def run_with_skill(self, skill_name: str, scenario: str,
                       agent_behavior: str = "", violations: List[str] = None,
                       passed: bool = False) -> TestResult:
        """GREEN Phase: 有skill测试"""
        result = TestResult(
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
            skill_name=skill_name,
            scenario=scenario,
            mode="with_skill",
            agent_behavior=agent_behavior,
            rule_violations=violations or [],
            passed=passed,
        )
        self.results.append(asdict(result))
        self._save()
        return result
    
    def report(self, skill_name: str) -> Dict:
        """生成测试报告"""
        skill_results = [r for r in self.results if r.get("skill_name") == skill_name]
        if not skill_results:
            return {"error": f"No results for {skill_name}"}
        
        passed = [r for r in skill_results if r.get("passed")]
        failures = [r for r in skill_results if not r.get("passed") and r.get("mode") == "with_skill"]
        rationalizations = [r.get("agent_behavior", "")[:100] for r in skill_results 
                          if r.get("agent_behavior") and "因为" in r.get("agent_behavior", "")]
        
        return {
            "skill_name": skill_name,
            "test_count": len(skill_results),
            "passed_count": len(passed),
            "failures": failures[:3],
            "rationalizations": rationalizations[:5],
        }


# ═══════════════════════════════════════════════════════
# 能力3: 任务路由 — 源自 skill_router.py
# ═══════════════════════════════════════════════════════

ROUTE_RULES = [
    # 文档处理
    {"skill": "pdf", "keywords": ["pdf", "PDF", ".pdf"], "priority": 10},
    {"skill": "docx", "keywords": ["word", "docx", ".docx", "Word文档"], "priority": 10},
    {"skill": "xlsx", "keywords": ["excel", "xlsx", ".xlsx", "表格"], "priority": 10},
    {"skill": "pptx", "keywords": ["ppt", "pptx", ".pptx", "幻灯片"], "priority": 10},
    
    # 设计
    {"skill": "frontend-dev", "keywords": ["网页", "前端", "UI", "landing page", "dashboard"], "priority": 8},
    
    # 搜索
    {"skill": "multi-search-engine", "keywords": ["搜索", "查一下", "找一下"], "priority": 7},
    {"skill": "agent-reach", "keywords": ["小红书", "抖音", "微博", "Twitter", "B站"], "priority": 7},
    
    # 天气
    {"skill": "weather", "keywords": ["天气", "气温", "下雨"], "priority": 9},
    
    # 邮件
    {"skill": "email-skill", "keywords": ["邮箱", "邮件", "email"], "priority": 8},
    
    # 记忆
    {"skill": "auto-memory", "keywords": ["记住", "别忘了", "以后记得"], "priority": 6},
]


class SkillRouter:
    """
    任务路由器 — 源自 skill_router.py
    
    匹配策略:
      1. 关键词匹配（最高优先级）
      2. 正则模式匹配
      3. 类别映射
      4. fallback: None（不强制）
    """
    
    def route(self, task: str) -> Optional[SkillRoute]:
        """路由任务到最合适的技能"""
        task_lower = task.lower()
        
        # 按优先级排序
        for rule in sorted(ROUTE_RULES, key=lambda x: -x.get("priority", 0)):
            skill_name = rule["skill"]
            keywords = rule.get("keywords", [])
            
            for kw in keywords:
                if kw.lower() in task_lower:
                    return SkillRoute(
                        skill_name=skill_name,
                        confidence=0.8,
                        reason=f"关键词匹配: {kw}",
                        trigger="keyword",
                    )
        
        return None
    
    def route_multi(self, task: str, top_k: int = 3) -> List[SkillRoute]:
        """返回多个候选"""
        results = []
        task_lower = task.lower()
        
        for rule in sorted(ROUTE_RULES, key=lambda x: -x.get("priority", 0)):
            skill_name = rule["skill"]
            for kw in rule.get("keywords", []):
                if kw.lower() in task_lower:
                    results.append(SkillRoute(
                        skill_name=skill_name,
                        confidence=0.7,
                        reason=f"关键词: {kw}",
                        trigger="keyword",
                    ))
                    break
        
        return results[:top_k]


# ═══════════════════════════════════════════════════════
# 能力4: 冲突检测 — 源自 skill_collision_detector.py
# ═══════════════════════════════════════════════════════

class CollisionDetector:
    """
    技能冲突检测器 — 源自 skill_collision_detector.py
    
    检测类型:
      - keyword: 关键词重叠
      - pattern: 触发模式冲突
      - function: 功能重叠（同名函数）
    """
    
    def detect(self) -> List[Collision]:
        """扫描所有技能，检测冲突"""
        collisions = []
        
        if not SKILLS_PATH.exists():
            return collisions
        
        # 收集所有关键词
        skill_keywords: Dict[str, List[str]] = {}
        for skill_dir in SKILLS_PATH.iterdir():
            if not skill_dir.is_dir():
                continue
            md_path = skill_dir / "SKILL.md"
            if not md_path.exists():
                continue
            
            try:
                content = md_path.read_text(encoding="utf-8", errors="ignore")[:1000].lower()
                # 提取关键词（简单分词）
                words = set(re.findall(r'\b\w{3,}\b', content))
                skill_keywords[skill_dir.name] = list(words)[:50]
            except Exception:
                pass
        
        # 检测关键词重叠
        skill_names = list(skill_keywords.keys())
        for i in range(len(skill_names)):
            for j in range(i + 1, len(skill_names)):
                a, b = skill_names[i], skill_names[j]
                overlap = set(skill_keywords[a]) & set(skill_keywords[b])
                if len(overlap) >= 10:  # 10个以上共同关键词
                    collisions.append(Collision(
                        skill_a=a,
                        skill_b=b,
                        overlap_type="keyword",
                        overlap_value=f"{len(overlap)} common keywords",
                        severity="warning",
                    ))
        
        return collisions


# ═══════════════════════════════════════════════════════
# 能力5: 技能生成 — 源自 skillify_skill.py
# ═══════════════════════════════════════════════════════

class SkillGenerator:
    """
    技能生成器 — 源自 skillify_skill.py
    
    从成功任务自动生成skill：
      1. 提取任务模式
      2. 生成SKILL.md骨架
      3. 可选：生成Python实现
    """
    
    def generate_from_task(self, task: str, method: str, 
                           success: bool = True) -> Optional[Path]:
        """从成功任务生成skill骨架"""
        if not success:
            return None
        
        # 生成技能名（简化任务描述）
        skill_name = self._make_skill_name(task)
        skill_dir = SKILLS_PATH / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成SKILL.md
        md_content = f"""# {skill_name}

## 触发条件
- 任务包含: {task[:50]}

## 工作流程
1. {method}

## 来源
- 自动生成自成功任务: {task[:80]}

## 创建时间
{time.strftime("%Y-%m-%d %H:%M")}
"""
        md_path = skill_dir / "SKILL.md"
        md_path.write_text(md_content, encoding="utf-8")
        
        return skill_dir
    
    def _make_skill_name(self, task: str) -> str:
        """生成合规技能名"""
        # 提取关键动词+名词
        words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', task)
        if len(words) >= 2:
            name = "-".join(words[:2]).lower()
        else:
            name = "auto-skill"
        
        # 清理
        name = re.sub(r'[^a-z0-9\-]', '', name)
        if len(name) < 3:
            name = f"auto-{hashlib.md5(task.encode()).hexdigest()[:6]}"
        
        return name[:32]


# ═══════════════════════════════════════════════════════
# 统一管理器
# ═══════════════════════════════════════════════════════

class UnifiedSkillManager:
    """
    qclaw 统一技能管理器
    
    整合5大能力：
      1. 安全扫描 (Scanner)
      2. TDD测试 (Tester)
      3. 任务路由 (Router)
      4. 冲突检测 (CollisionDetector)
      5. 技能生成 (Generator)
    """
    
    def __init__(self):
        self.scanner = SkillScanner()
        self.tester = SkillTester()
        self.router = SkillRouter()
        self.collision_detector = CollisionDetector()
        self.generator = SkillGenerator()
    
    # ─── 便捷方法 ─────────────────────────────────────
    
    def scan(self, path: Path, source: str = "community") -> ScanResult:
        return self.scanner.scan(path, source)
    
    def route(self, task: str) -> Optional[SkillRoute]:
        return self.router.route(task)
    
    def test_baseline(self, task: str, scenario: str, **kw) -> TestResult:
        return self.tester.run_baseline(task, scenario, **kw)
    
    def test_with_skill(self, skill_name: str, scenario: str, **kw) -> TestResult:
        return self.tester.run_with_skill(skill_name, scenario, **kw)
    
    def detect_collisions(self) -> List[Collision]:
        return self.collision_detector.detect()
    
    def generate_skill(self, task: str, method: str) -> Optional[Path]:
        return self.generator.generate_from_task(task, method)
    
    # ─── 状态统计 ─────────────────────────────────────
    
    def get_stats(self) -> Dict:
        """获取技能统计"""
        skills = []
        if SKILLS_PATH.exists():
            skills = [d.name for d in SKILLS_PATH.iterdir() if d.is_dir()]
        
        collisions = self.detect_collisions()
        
        return {
            "skill_count": len(skills),
            "skills": skills[:20],
            "collisions": len(collisions),
            "test_count": len(self.tester.results),
        }


# ═══════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════

_manager: Optional[UnifiedSkillManager] = None

def get_skill_manager() -> UnifiedSkillManager:
    global _manager
    if _manager is None:
        _manager = UnifiedSkillManager()
    return _manager


# ═══════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    mgr = UnifiedSkillManager()
    
    # 测试1: 路由
    r1 = mgr.route("帮我搜索一下天气")
    print(f"✅ 路由 '搜索天气': {r1.skill_name if r1 else 'None'}")
    
    r2 = mgr.route("把PDF转换成文本")
    print(f"✅ 路由 'PDF转换': {r2.skill_name if r2 else 'None'}")
    
    # 测试2: 冲突检测
    cols = mgr.detect_collisions()
    print(f"✅ 冲突检测: {len(cols)} 个冲突")
    
    # 测试3: 统计
    stats = mgr.get_stats()
    print(f"✅ 统计: {stats['skill_count']} 技能, {stats['collisions']} 冲突")
    
    # 测试4: 安全扫描（自扫）
    self_scan = mgr.scan(Path(__file__).parent / "qclaw_unified_skill.py", "builtin:test")
    ok, reason = mgr.scanner.allow_install(self_scan)
    print(f"✅ 自扫描: verdict={self_scan.verdict}, allow={ok}({reason})")
    
    # 测试5: 技能生成
    skill_dir = mgr.generate_skill("自动生成技能测试", "使用模板方法")
    print(f"✅ 技能生成: {skill_dir.name if skill_dir else 'None'}")
    
    print("\n🎯 UnifiedSkillManager 全部测试通过！")
