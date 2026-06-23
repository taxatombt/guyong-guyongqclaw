"""
Evolver Safety Rules - ISC Defense Implementation
Based on paper: "Internal Safety Collapse in Frontier Large Language Models"

Key insight from ISC paper:
- Alignment reshapes observable outputs but does NOT eliminate underlying risk
- Safety classifiers can be bypassed by task chain internal reasoning
- Dual-use tools automatically expand attack surface

This module adds SAFETY rules to evolver.py with HIGHEST priority.
Safety rules CANNOT be overridden by task completion rules.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, List


class RulePriority(Enum):
    """Rule priority levels. SAFETY is absolute highest."""
    SAFETY = 0      # Safety rules - CANNOT be overridden
    SYSTEM = 1        # System rules (file permissions, etc.)
    USER = 2          # User-defined rules
    TASK = 3          # Task completion rules (can be overridden by higher priority)
    DEFAULT = 4        # Default/fallback rules


@dataclass
class SafetyRule:
    """
    Safety rule with highest priority.

    ISC Insight: The paper shows that models prioritize "task completion"
    over safety when the task chain derives that unsafe actions are necessary.
    Solution: Make safety rules UNCONDITIONAL and HIGHEST priority.
    """
    name: str
    description: str
    check_func: Callable[[str, Any, Dict], bool]  # tool_name, tool_input, context -> bool
    block_func: Callable[[str, Any, Dict], str]      # -> block reason
    priority: RulePriority = RulePriority.SAFETY
    enabled: bool = True

    def check(self, tool_name: str, tool_input: Any, context: Dict) -> bool:
        """Check if this rule blocks the action. Returns True if SAFE."""
        if not self.enabled:
            return True
        return self.check_func(tool_name, tool_input, context)

    def block_reason(self, tool_name: str, tool_input: Any, context: Dict) -> str:
        """Get block reason if check fails."""
        return self.block_func(tool_name, tool_input, context)


class SafetyRuleEngine:
    """
    Safety rule engine that runs BEFORE evolver rules.

    ISC Defense: Run safety checks FIRST. If any safety rule blocks,
    DO NOT proceed to task completion rules.
    """

    def __init__(self):
        self.rules: List[SafetyRule] = []
        self._init_default_rules()

    def _init_default_rules(self):
        """Initialize default safety rules based on ISC paper insights."""
        # Rule 1: Block dangerous commands (ISC Insight: Task completion pressure can lead to dangerous commands)
        self.add_rule(SafetyRule(
            name="block_dangerous_commands",
            description="Block commands that can cause data loss or system damage",
            check_func=self._check_dangerous_commands,
            block_func=self._block_dangerous_commands_reason,
            priority=RulePriority.SAFETY
        ))

        # Rule 2: Block writing to system directories (ISC Insight: Agent may derive that overwriting system files is "necessary")
        self.add_rule(SafetyRule(
            name="block_system_file_write",
            description="Block writing to system directories",
            check_func=self._check_system_file_write,
            block_func=self._block_system_file_write_reason,
            priority=RulePriority.SAFETY
        ))

        # Rule 3: Warn on non-HTTPS URLs (ISC Insight: Agent may navigate to "necessary" but insecure sites)
        self.add_rule(SafetyRule(
            name="warn_insecure_urls",
            description="Warn when navigating to non-HTTPS URLs",
            check_func=self._check_insecure_urls,
            block_func=self._block_insecure_urls_reason,
            priority=RulePriority.SAFETY
        ))

        # Rule 4: Block secret leakage in messages (ISC Insight: Agent may "need" to include credentials in messages to "complete the task")
        self.add_rule(SafetyRule(
            name="block_secret_leakage",
            description="Block sending messages that contain secrets",
            check_func=self._check_secret_leakage,
            block_func=self._block_secret_leakage_reason,
            priority=RulePriority.SAFETY
        ))

        # Rule 5: Chain deviation detection (ISC Core Insight!)
        self.add_rule(SafetyRule(
            name="detect_chain_deviation",
            description="Detect when task chain deviates from original intent",
            check_func=self._check_chain_deviation,
            block_func=self._block_chain_deviation_reason,
            priority=RulePriority.SAFETY
        ))

    def add_rule(self, rule: SafetyRule):
        """Add a safety rule. Safety rules are always inserted at the beginning."""
        self.rules.insert(0, rule)

    def check_all(self, tool_name: str, tool_input: Any, context: Dict) -> Dict:
        """
        Check all safety rules. If ANY rule blocks, return immediately.

        ISC Defense: Safety rules run FIRST, before any task completion logic.
        """
        for rule in sorted(self.rules, key=lambda r: r.priority.value):
            if not rule.enabled:
                continue

            is_safe = rule.check(tool_name, tool_input, context)

            if not is_safe:
                reason = rule.block_reason(tool_name, tool_input, context)
                return {
                    'safe': False,
                    'rule': rule.name,
                    'reason': reason,
                    'priority': rule.priority.name,
                    'block': True  # Safety rules ALWAYS block
                }

        return {'safe': True, 'rule': None, 'reason': None, 'priority': None, 'block': False}

    # --- Rule check functions ---

    def _check_dangerous_commands(self, tool_name: str, tool_input: Any, context: Dict) -> bool:
        """Check if exec command is dangerous."""
        if tool_name != 'exec':
            return True  # Not an exec tool, safe

        cmd = str(tool_input).lower()

        # Dangerous patterns from ISC paper analysis
        dangerous_patterns = [
            r'rm\s+-rf',
            r'del\s+/[fq]',
            r'format\s+[a-z]:',
            r'dd\s+if=',
            r'chmod\s+777',
            r'curl\s+.*\|\s*(bash|sh)',
            r'wget\s+.*\|\s*(bash|sh)',
        ]

        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd, re.IGNORECASE):
                return False  # Unsafe!

        return True  # Safe

    def _block_dangerous_commands_reason(self, tool_name: str, tool_input: Any, context: Dict) -> str:
        return (f"Safety Rule 'block_dangerous_commands' BLOCKED execution:\n"
                f"Command: {tool_input}\n"
                f"Reason: This command can cause data loss or system damage.\n"
                f"ISC Insight: Task completion pressure should NOT override safety.\n"
                f"Action: Ask user to confirm if this command is REALLY necessary.")

    def _check_system_file_write(self, tool_name: str, tool_input: Any, context: Dict) -> bool:
        """Check if writing to system directory."""
        if tool_name != 'write':
            return True

        path = ""
        if isinstance(tool_input, dict):
            path = tool_input.get('path', '')
        else:
            path = str(tool_input)

        system_dirs = [
            'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)',
            '/etc', '/sys', '/proc', '/dev'
        ]

        import os
        path_norm = os.path.normpath(path).lower()

        for sys_dir in system_dirs:
            if path_norm.startswith(sys_dir.lower()):
                return False  # Unsafe!

        return True

    def _block_system_file_write_reason(self, tool_name: str, tool_input: Any, context: Dict) -> str:
        path = tool_input.get('path', str(tool_input)) if isinstance(tool_input, dict) else str(tool_input)
        return (f"Safety Rule 'block_system_file_write' BLOCKED file write:\n"
                f"Path: {path}\n"
                f"Reason: Writing to system directories can break the OS.\n"
                f"ISC Insight: Agent may derive that overwriting system files is 'necessary'.\n"
                f"Action: Confirm with user before writing to system directories.")

    def _check_insecure_urls(self, tool_name: str, tool_input: Any, context: Dict) -> bool:
        """Check if URL is insecure (non-HTTPS)."""
        if tool_name != 'browser':
            return True

        url = str(tool_input)

        if not url.startswith('https://'):
            return False  # Insecure, but not blocked (warning only)

        return True

    def _block_insecure_urls_reason(self, tool_name: str, tool_input: Any, context: Dict) -> str:
        return (f"Safety Rule 'warn_insecure_urls' WARNING:\n"
                f"URL: {tool_input}\n"
                f"Reason: Non-HTTPS URLs may be insecure.\n"
                f"ISC Insight: Agent may navigate to 'necessary' but insecure sites.\n"
                f"Action: Consider using HTTPS. Ask user to confirm.")

    def _check_secret_leakage(self, tool_name: str, tool_input: Any, context: Dict) -> bool:
        """Check if message contains secrets."""
        if tool_name != 'message':
            return True

        content = ""
        if isinstance(tool_input, dict):
            content = tool_input.get('content', '')
        else:
            content = str(tool_input)

        secret_patterns = ['password', 'token', 'secret', 'api_key', 'private_key', 'credential']

        import re
        content_lower = content.lower()

        for pattern in secret_patterns:
            if re.search(pattern, content_lower):
                return False  # Contains secret!

        return True

    def _block_secret_leakage_reason(self, tool_name: str, tool_input: Any, context: Dict) -> str:
        return (f"Safety Rule 'block_secret_leakage' BLOCKED message:\n"
                f"Reason: Message appears to contain sensitive information.\n"
                f"ISC Insight: Agent may 'need' to include credentials to 'complete the task'.\n"
                f"Action: Confirm recipient and necessity before sending secrets.")

    def _check_chain_deviation(self, tool_name: str, tool_input: Any, context: Dict) -> bool:
        """
        Detect chain deviation (ISC Core!).

        ISC Insight: The paper shows that models start with benign tasks,
        but through multiple steps of reasoning, derive that unsafe actions
        are necessary. This function detects that derivation.
        """
        # Get execution chain from context
        chain = context.get('execution_chain')
        if not chain:
            return True  # No chain tracking, can't check

        steps = chain.get('steps', [])
        original_intent = chain.get('original_intent', '')

        # Simple heuristic: If we're on step 3+ and suddenly using dangerous commands
        if len(steps) >= 3 and tool_name == 'exec':
            cmd = str(tool_input).lower()

            dangerous_patterns = ['rm -rf', 'del /f', 'format', 'dd if=']
            for pattern in dangerous_patterns:
                if pattern in cmd:
                    return False  # Chain deviation detected!

        return True

    def _block_chain_deviation_reason(self, tool_name: str, tool_input: Any, context: Dict) -> str:
        chain = context.get('execution_chain', {})
        original_intent = chain.get('original_intent', 'Unknown')
        return (f"Safety Rule 'detect_chain_deviation' BLOCKED execution:\n"
                f"Tool: {tool_name}\n"
                f"Input: {tool_input}\n"
                f"Original Intent: {original_intent}\n"
                f"Reason: Task chain has deviated from original intent.\n"
                f"ISC Core Insight: Model derived that unsafe action is 'necessary'.\n"
                f"Action: PAUSE and ask user. Do NOT proceed without confirmation.")


# Global safety rule engine
safety_engine = SafetyRuleEngine()


def check_safety(tool_name: str, tool_input: Any, context: Optional[Dict] = None) -> Dict:
    """
    Main entry point for safety checks.

    ISC Defense: ALL tool calls MUST pass this check before execution.

    Usage:
        context = {
            'execution_chain': {...},  # Optional: for chain deviation detection
        }
        result = check_safety('exec', 'rm -rf /', context)
        if not result['safe']:
            print(f"Blocked: {result['reason']}")
            # DO NOT PROCEED
    """
    if context is None:
        context = {}

    return safety_engine.check_all(tool_name, tool_input, context)


def add_safety_rule(rule: SafetyRule):
    """Add a custom safety rule."""
    safety_engine.add_rule(rule)


def list_safety_rules() -> List[Dict]:
    """List all safety rules."""
    return [
        {
            'name': rule.name,
            'description': rule.description,
            'priority': rule.priority.name,
            'enabled': rule.enabled
        }
        for rule in safety_engine.rules
    ]


# Example usage
if __name__ == '__main__':
    # Example 1: Dangerous command
    result = check_safety('exec', 'rm -rf /')
    print(f"Example 1: {result}")

    # Example 2: Safe command
    result = check_safety('exec', 'pip install numpy')
    print(f"Example 2: {result}")

    # Example 3: Chain deviation (ISC scenario!)
    context = {
        'execution_chain': {
            'original_intent': 'Install dependencies for project',
            'steps': [
                {'tool': 'exec', 'input': 'pip install numpy'},
                {'tool': 'exec', 'input': 'pip install pandas'},
                {'tool': 'exec', 'input': 'pip install scipy'},
            ]
        }
    }
    result = check_safety('exec', 'rm -rf .', context)
    print(f"Example 3 (ISC Chain Deviation): {result}")

    # List all rules
    print(f"\nAll Safety Rules:")
    for rule_info in list_safety_rules():
        print(f"  - {rule_info['name']} (Priority: {rule_info['priority']}, Enabled: {rule_info['enabled']})")
