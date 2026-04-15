#!/usr/bin/env python3
# log_notify.py
# 审计日志 Hook

import os, json
from datetime import datetime

hook_name = os.environ.get("HOOK_NAME", "")
tool_name = os.environ.get("TOOL_NAME", "")
tool_input = os.environ.get("TOOL_INPUT", "")
mode = os.environ.get("RUNTIME_MODE", "manual")

home = os.path.expanduser("~")
log_dir = os.path.join(home, ".qclaw", "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"tool_log_{datetime.now().strftime('%Y%m%d')}.log")

with open(log_file, "a", encoding="utf-8") as f:
    f.write(f"[{datetime.now().isoformat()}] [{mode}] {tool_name}: {tool_input[:300]}\n")

print("allow")