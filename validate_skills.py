# -*- coding: utf-8 -*-
"""
validate_skills.py - Skill 验证框架

来源: 顾庸t workspace_tools/validate_skills.py
参考: ECC skill-tester + Claude Code skillify TDD

功能:
  1. 检查 SKILL.md 格式合规
  2. 验证引用文件是否存在
  3. 验证脚本可执行
  4. 检查触发条件覆盖
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from enum import Enum


class CheckResult(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class ValidationCheck:
    """验证检查项"""
    name: str
    result: CheckResult
    message: str
    file_path: Optional[str] = None


@dataclass
class SkillValidation:
    """Skill 验证结果"""
    skill_name: str
    skill_path: Path
    checks: List[ValidationCheck] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        return all(c.result != CheckResult.FAIL for c in self.checks)
    
    @property
    def score(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.result == CheckResult.PASS)
        return f"{passed}/{total}"


class SkillValidator:
    """Skill 验证器"""
    
    def validate(self, skill_path: Path) -> SkillValidation:
        """验证一个 Skill"""
        skill_name = skill_path.name
        checks = []
        
        # 1. SKILL.md 存在
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            checks.append(ValidationCheck(
                "SKILL.md exists", CheckResult.PASS, "Found"
            ))
            
            # 2. SKILL.md 格式
            format_checks = self._validate_skill_md(skill_md, skill_path)
            checks.extend(format_checks)
        else:
            checks.append(ValidationCheck(
                "SKILL.md exists", CheckResult.FAIL, "Not found"
            ))
        
        # 3. 目录结构
        struct_checks = self._validate_structure(skill_path)
        checks.extend(struct_checks)
        
        # 4. 脚本可执行
        script_checks = self._validate_scripts(skill_path)
        checks.extend(script_checks)
        
        return SkillValidation(
            skill_name=skill_name,
            skill_path=skill_path,
            checks=checks,
        )
    
    def _validate_skill_md(self, skill_md: Path, skill_path: Path) -> List[ValidationCheck]:
        """验证 SKILL.md 内容"""
        checks = []
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return [ValidationCheck("SKILL.md readable", CheckResult.FAIL, str(e))]
        
        # 标题
        if re.search(r'^#\s+', content, re.MULTILINE):
            checks.append(ValidationCheck("Has title", CheckResult.PASS, "H1 found"))
        else:
            checks.append(ValidationCheck("Has title", CheckResult.WARN, "No H1 header"))
        
        # 描述
        if len(content) > 50:
            checks.append(ValidationCheck("Has content", CheckResult.PASS, f"{len(content)} chars"))
        else:
            checks.append(ValidationCheck("Has content", CheckResult.WARN, "Very short (<50 chars)"))
        
        # 代码块
        code_blocks = re.findall(r'```', content)
        if code_blocks:
            checks.append(ValidationCheck(
                "Code blocks", CheckResult.PASS, 
                f"{len(code_blocks)//2} blocks"
            ))
        
        # 引用文件检查
        refs = re.findall(r'(?:path|file|script)[:\s]+(\S+\.\w+)', content, re.IGNORECASE)
        broken_refs = []
        for ref in refs:
            # 尝试相对路径
            ref_path = skill_path / ref
            if not ref_path.exists():
                broken_refs.append(ref)
        
        if broken_refs:
            checks.append(ValidationCheck(
                "File references",
                CheckResult.WARN if len(broken_refs) <= 2 else CheckResult.FAIL,
                f"Broken refs: {', '.join(broken_refs[:5])}",
            ))
        else:
            checks.append(ValidationCheck(
                "File references", CheckResult.PASS, 
                f"{len(refs)} refs, all exist" if refs else "No external refs"
            ))
        
        return checks
    
    def _validate_structure(self, skill_path: Path) -> List[ValidationCheck]:
        """验证目录结构"""
        checks = []
        entries = list(skill_path.iterdir()) if skill_path.exists() else []
        
        if len(entries) > 50:
            checks.append(ValidationCheck(
                "Structure size", CheckResult.WARN, 
                f"{len(entries)} entries (consider organizing)"
            ))
        
        # 检查没有 .pyc 或 __pycache__
        pyc_files = [e for e in entries if e.suffix == '.pyc']
        if pyc_files:
            checks.append(ValidationCheck(
                "Clean build artifacts", CheckResult.WARN,
                f"{len(pyc_files)} .pyc files found"
            ))
        else:
            checks.append(ValidationCheck(
                "Clean build artifacts", CheckResult.PASS, "No .pyc files"
            ))
        
        return checks
    
    def _validate_scripts(self, skill_path: Path) -> List[ValidationCheck]:
        """验证脚本可执行"""
        checks = []
        py_files = [e for e in skill_path.iterdir() if e.suffix == '.py'] if skill_path.exists() else []
        
        for pf in py_files:
            try:
                # 只检查语法，不执行
                with open(pf, encoding="utf-8", errors="replace") as f:
                    compile(f.read(), str(pf), "exec")
                checks.append(ValidationCheck(
                    f"Script: {pf.name}", CheckResult.PASS, "Syntax OK"
                ))
            except SyntaxError as e:
                checks.append(ValidationCheck(
                    f"Script: {pf.name}", CheckResult.FAIL, f"Syntax error: {e}"
                ))
        
        return checks
    
    def format_report(self, validation: SkillValidation) -> str:
        """格式化报告"""
        status = "PASSED" if validation.passed else "FAILED"
        lines = [
            f"# Skill Validation: {validation.skill_name} [{status}]",
            f"Score: {validation.score}",
            f"Path: {validation.skill_path}",
            "",
        ]
        
        for c in validation.checks:
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(c.result.value, "?")
            lines.append(f"  {icon} {c.name}: {c.message}")
        
        return "\n".join(lines)


_validator: Optional[SkillValidator] = None

def get_skill_validator() -> SkillValidator:
    global _validator
    if _validator is None:
        _validator = SkillValidator()
    return _validator
