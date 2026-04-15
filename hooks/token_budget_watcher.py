#!/usr/bin/env python3
# token_budget_watcher.py
# Token 预算监控 Hook
# 70% 警告，90% 触发自动压缩

import os, json

tool_input_str = os.environ.get("TOOL_INPUT", "{}")
try:
    tool_input = json.loads(tool_input_str)
except:
    tool_input = {}

tokens = tool_input.get("tokens", 0)
budget = tool_input.get("budget", 100000)
ratio = tokens / budget if budget > 0 else 0

if ratio >= 0.9:
    print("deny: Token budget exceeded 90%, triggering autocompact")
elif ratio >= 0.7:
    print("modify: {\"action\": \"compact\", \"ratio\": \"" + str(round(ratio, 2)) + "\"}")
else:
    print("allow")