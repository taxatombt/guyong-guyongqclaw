"""
Safety Monitor - ISC (Internal Safety Collapse) Defense Implementation
Based on paper: "Internal Safety Collapse in Frontier Large Language Models"
arXiv:2603.23509

Key insight: Alignment != Safety. External detectors cannot block internal
risk accumulation in long-horizon task chains.

This module implements:
1. Execution Chain Monitoring - check if tool output deviates from original intent
2. Dual-Use Tool Detection - flag risky tool usage patterns
3. Task Completion Pressure Relief - interrupt when task chain derives dangerous operations
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    safe: bool
    risk_level: RiskLevel
    reason: str
    suggestion: Optional[str] = None
    block: bool = False


@dataclass
class ExecutionStep:
    """Record of a single execution step in a task chain."""
    step_id: int
    tool_name: str
    tool_input: Any
    tool_output: Any
    timestamp: float
    safety_result: Optional[SafetyCheckResult] = None


class ExecutionChain:
    """Tracks the execution chain for a task to detect ISC."""

    def __init__(self, task_id: str, original_intent: str):
        self.task_id = task_id
        self.original_intent = original_intent
        self.steps: List[ExecutionStep] = []
        self.deviation_detected = False
        self.deviation_reason = ""

    def add_step(self, step: ExecutionStep):
        """Add a step and check for deviation."""
        self.steps.append(step)
        result = monitor.check_chain_deviation(self, step)
        step.safety_result = result

        if not result.safe:
            self.deviation_detected = True
            self.deviation_reason = result.reason

        return result


class SafetyMonitor:
    """
    Main safety monitor implementing ISC defenses.

    Key principle from ISC paper:
    - Traditional safety filters check INPUT (user prompt)
    - ISC happens in the TASK CHAIN (model's own reasoning)
    - Need to monitor the ENTIRE execution chain
    """

    # Dangerous command patterns (for exec tool)
    DANGEROUS_COMMANDS = [
        r'rm\s+-rf',           # rm -rf
        r'del\s+/[fq]',        # del /f /q
        r'format\s+[a-z]:',    # format C:
        r'DD\s+if=',            # dd if= (dangerous disk write)
        r'mkfs\.',              # mkfs.*
        r':\(\)\s*\{.*\}',     # fork bomb
        r'chmod\s+777',        # chmod 777
        r'curl\s+.*\|\s*(bash|sh)',  # curl ... | bash
        r'wget\s+.*\|\s*(bash|sh)',  # wget ... | bash
    ]

    # Dual-use tool risk patterns
    DUAL_USE_PATTERNS = {
        'exec': {
            'normal': ['pip install', 'npm install', 'python', 'node'],
            'risky': ['rm', 'del', 'format', 'dd', 'chmod 777', 'curl | bash'],
        },
        'write': {
            'normal': ['report', 'config', 'README', '.md'],
            'risky': ['.sh$', '.bat$', '.ps1$', 'malicious', 'exploit'],
        },
        'browser': {
            'normal': ['docs.', 'github.com', 'stackoverflow.com'],
            'risky': ['bit.ly', 'tinyurl', 'phishing', 'malware'],
        },
        'message': {
            'normal': ['notification', 'update', 'report'],
            'risky': ['password', 'token', 'secret', 'API key'],
        },
    }

    def __init__(self):
        self.chains: Dict[str, ExecutionChain] = {}
        self.risk_threshold = RiskLevel.MEDIUM

    def create_chain(self, task_id: str, original_intent: str) -> ExecutionChain:
        """Create a new execution chain for a task."""
        chain = ExecutionChain(task_id, original_intent)
        self.chains[task_id] = chain
        logger.info(f"Created execution chain {task_id} for intent: {original_intent[:50]}...")
        return chain

    def check_tool_input(self, tool_name: str, tool_input: Any) -> SafetyCheckResult:
        """
        Pre-execution check: Check if tool input is dangerous.

        ISC Insight: The task chain may derive that dangerous input is
        "necessary to complete the task". We need to flag this BEFORE execution.
        """
        if tool_name == 'exec':
            return self._check_exec_input(tool_input)
        elif tool_name == 'write':
            return self._check_write_input(tool_input)
        elif tool_name == 'browser':
            return self._check_browser_input(tool_input)
        elif tool_name == 'message':
            return self._check_message_input(tool_input)

        return SafetyCheckResult(True, RiskLevel.SAFE, "Tool not flagged for ISC risk")

    def check_tool_output(self, tool_name: str, tool_output: Any, context: str) -> SafetyCheckResult:
        """
        Post-execution check: Check if output indicates safety collapse.

        ISC Insight: The model may have generated harmful content as part
        of "completing the task". Check if output contains unsafe content.
        """
        if tool_name == 'exec':
            return self._check_exec_output(tool_output)
        elif tool_name == 'write':
            return self._check_write_output(tool_output)
        elif tool_name == 'browser':
            return self._check_browser_output(tool_output)

        return SafetyCheckResult(True, RiskLevel.SAFE, "Output check passed")

    def check_chain_deviation(self, chain: ExecutionChain, current_step: ExecutionStep) -> SafetyCheckResult:
        """
        Check if current step deviates from original task intent.

        ISC Insight: This is the KEY defense. The model starts with a benign
        task, but through multiple steps of reasoning, derives that it needs
        to do something dangerous. We detect this derivation.
        """
        # Simple heuristic: if we're on step 3+ and suddenly using dangerous
        # commands, that's suspicious
        if len(chain.steps) >= 3 and current_step.tool_name == 'exec':
            cmd = str(current_step.tool_input).lower()
            for pattern in self.DANGEROUS_COMMANDS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return SafetyCheckResult(
                        False,
                        RiskLevel.HIGH,
                        f"Chain deviation detected: Dangerous command '{cmd[:50]}...' "
                        f"appears at step {len(chain.steps)} of task chain. "
                        f"Original intent: {chain.original_intent[:100]}",
                        suggestion="Ask user: Is this dangerous operation necessary for the task?",
                        block=True
                    )

        return SafetyCheckResult(True, RiskLevel.SAFE, "No chain deviation detected")

    def _check_exec_input(self, cmd: str) -> SafetyCheckResult:
        """Check if exec command is dangerous."""
        if not isinstance(cmd, str):
            cmd = str(cmd)

        cmd_lower = cmd.lower()

        # Check dangerous patterns
        for pattern in self.DANGEROUS_COMMANDS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return SafetyCheckResult(
                    False,
                    RiskLevel.CRITICAL,
                    f"Dangerous command pattern detected: {pattern}",
                    suggestion="This command can cause data loss or system damage. Confirm with user.",
                    block=True
                )

        return SafetyCheckResult(True, RiskLevel.SAFE, "Command appears safe")

    def _check_write_input(self, file_info: Any) -> SafetyCheckResult:
        """Check if file write is dangerous."""
        # file_info might be a dict with 'path' and 'content'
        if isinstance(file_info, dict):
            path = file_info.get('path', '')
            content = file_info.get('content', '')

            # Check if writing to system directory
            system_dirs = ['C:\\Windows', 'C:\\Program Files', '/etc', '/sys', '/proc']
            for sys_dir in system_dirs:
                if sys_dir.lower() in path.lower():
                    return SafetyCheckResult(
                        False,
                        RiskLevel.HIGH,
                        f"Writing to system directory: {path}",
                        suggestion="Writing to system directories can break the OS. Confirm with user.",
                        block=True
                    )

            # Check if content looks like malware
            malware_patterns = ['rm -rf', 'format ', 'DD if=', 'chmod 777', 'curl | bash']
            for pattern in malware_patterns:
                if pattern in content:
                    return SafetyCheckResult(
                        False,
                        RiskLevel.HIGH,
                        f"File content contains potentially dangerous command: {pattern}",
                        suggestion="File appears to contain malware. Confirm with user.",
                        block=True
                    )

        return SafetyCheckResult(True, RiskLevel.SAFE, "File write appears safe")

    def _check_browser_input(self, url: str) -> SafetyCheckResult:
        """Check if URL is dangerous."""
        if not isinstance(url, str):
            url = str(url)

        # Simple check: warn about non-HTTPS URLs
        if not url.startswith('https://'):
            return SafetyCheckResult(
                False,
                RiskLevel.LOW,
                f"Non-HTTPS URL: {url}",
                suggestion="Non-HTTPS URLs may be insecure. Consider using HTTPS.",
                block=False
            )

        # Check for suspicious domains
        suspicious_patterns = ['bit.ly', 'tinyurl', 'goo.gl', 'phishing', 'malware']
        for pattern in suspicious_patterns:
            if pattern in url.lower():
                return SafetyCheckResult(
                    False,
                    RiskLevel.MEDIUM,
                    f"Suspicious URL pattern detected: {pattern}",
                    suggestion="This URL looks suspicious. Confirm with user.",
                    block=True
                )

        return SafetyCheckResult(True, RiskLevel.SAFE, "URL appears safe")

    def _check_message_input(self, message_info: Any) -> SafetyCheckResult:
        """Check if message sending is dangerous (e.g., leaking secrets)."""
        if isinstance(message_info, dict):
            content = message_info.get('content', '')
            to = message_info.get('to', '')

            # Check if message contains secrets
            secret_patterns = ['password', 'token', 'secret', 'API key', 'private key']
            for pattern in secret_patterns:
                if pattern.lower() in content.lower():
                    return SafetyCheckResult(
                        False,
                        RiskLevel.HIGH,
                        f"Message may contain sensitive information: {pattern}",
                        suggestion="Message appears to contain sensitive info. Confirm recipient.",
                        block=True
                    )

        return SafetyCheckResult(True, RiskLevel.SAFE, "Message appears safe")

    def _check_exec_output(self, output: Any) -> SafetyCheckResult:
        """Check if exec output indicates security issue."""
        output_str = str(output).lower()

        # Check for signs of security breach
        breach_indicators = ['permission denied', 'access denied', 'unauthorized', 'error']
        for indicator in breach_indicators:
            if indicator in output_str:
                return SafetyCheckResult(
                    False,
                    RiskLevel.LOW,
                    f"Command output indicates possible issue: {indicator}",
                    suggestion="Check command output for security issues.",
                    block=False
                )

        return SafetyCheckResult(True, RiskLevel.SAFE, "Output appears safe")

    def _check_write_output(self, output: Any) -> SafetyCheckResult:
        """Check if file write output indicates issue."""
        return SafetyCheckResult(True, RiskLevel.SAFE, "Write output check passed")

    def _check_browser_output(self, output: Any) -> SafetyCheckResult:
        """Check if browser output indicates issue."""
        return SafetyCheckResult(True, RiskLevel.SAFE, "Browser output check passed")


# Global monitor instance
monitor = SafetyMonitor()


def check_tool_call(tool_name: str, tool_input: Any, task_id: Optional[str] = None,
                    original_intent: Optional[str] = None) -> SafetyCheckResult:
    """
    Main entry point for tool call safety check.

    ISC Defense: Check BEFORE tool execution.

    Usage:
        result = check_tool_call('exec', 'rm -rf /', task_id='task_123', original_intent='clean up temp files')
        if not result.safe:
            # Ask user for confirmation
            print(f"Safety check failed: {result.reason}")
            if result.block:
                return None  # Block the call
    """
    # Get or create chain
    chain = None
    if task_id:
        if task_id not in monitor.chains:
            monitor.create_chain(task_id, original_intent or 'Unknown')
        chain = monitor.chains[task_id]

    # Pre-execution check
    result = monitor.check_tool_input(tool_name, tool_input)

    # If part of a chain, check chain deviation
    if chain and len(chain.steps) > 0:
        step = ExecutionStep(
            step_id=len(chain.steps),
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=None,
            timestamp=0  # Would use time.time() in real implementation
        )
        chain_result = monitor.check_chain_deviation(chain, step)
        if not chain_result.safe:
            result = chain_result  # Chain deviation is more serious

    return result


def check_tool_result(tool_name: str, tool_output: Any, task_id: Optional[str] = None) -> SafetyCheckResult:
    """
    Check tool execution result for safety issues.

    ISC Defense: Check AFTER tool execution.
    """
    chain = monitor.chains.get(task_id) if task_id else None
    context = chain.original_intent if chain else ""

    return monitor.check_tool_output(tool_name, tool_output, context)


# Example usage
if __name__ == '__main__':
    # Example 1: Dangerous command
    result = check_tool_call('exec', 'rm -rf /', task_id='task_1', original_intent='Clean up temp files')
    print(f"Example 1: {result.safe}, {result.reason}")

    # Example 2: Safe command
    result = check_tool_call('exec', 'pip install numpy', task_id='task_2', original_intent='Install dependencies')
    print(f"Example 2: {result.safe}, {result.reason}")

    # Example 3: Writing malware
    result = check_tool_call('write', {'path': '/tmp/test.sh', 'content': 'rm -rf /'}, task_id='task_3', original_intent='Create test script')
    print(f"Example 3: {result.safe}, {result.reason}")

    # Example 4: Chain deviation
    task_id = 'task_4'
    monitor.create_chain(task_id, 'Install dependencies for project')
    # Step 1: Normal
    result1 = check_tool_call('exec', 'pip install numpy', task_id=task_id)
    print(f"Example 4 Step 1: {result1.safe}")
    # Step 2: Normal
    result2 = check_tool_call('exec', 'pip install pandas', task_id=task_id)
    print(f"Example 4 Step 2: {result2.safe}")
    # Step 3: Suddenly dangerous (ISC scenario!)
    result3 = check_tool_call('exec', 'rm -rf .', task_id=task_id)
    print(f"Example 4 Step 3: {result3.safe}, {result3.reason}")
