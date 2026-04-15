#!/usr/bin/env python3
# dangerous_cmd_checker.py
# 危险命令拦截 Hook

import os, sys, re, json

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/\.",
    r"rm\s+-rf\s+/tmp",
    r"rm\s+-rf\s+/var",
    r"rm\s+-rf\s+/home",
    r"del\s+/f\s+/s\s+/q",
    r"\bformat\b",
    r"\bmkfs\b",
    r"curl\s+\|\s*sh",
    r"wget\s+\|\s*sh",
    r":\(\)\s*:\s*\|",  # fork bomb
    r">\s*/dev/sd[a-z]",
    r"dd\s+if=",
]

tool_input_str = os.environ.get("TOOL_INPUT", "{}")
try:
    tool_input = json.loads(tool_input_str)
except:
    tool_input = {}

# 尝试获取命令
cmd = tool_input.get("cmd", "") or tool_input.get("command", "") or str(tool_input)

for pat in DANGEROUS_PATTERNS:
    if re.search(pat, cmd, re.IGNORECASE):
        print(f"deny: Dangerous pattern matched: {pat}")
        sys.exit(0)

print("allow")