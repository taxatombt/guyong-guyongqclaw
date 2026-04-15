#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
context-cleanup.py - 上下文清理脚本
定时清理会话上下文，释放 token 预算
"""
import os
import json
import datetime

WORKSPACE = r"C:\Users\yiseg\.qclaw\workspace"

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

def main():
    log("Context cleanup starting...")
    
    # 1. 检查 heartbeat-state.json
    state_path = os.path.join(WORKSPACE, "memory", "heartbeat-state.json")
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        log(f"lastMemoryMaint: {state.get('lastMemoryMaint', 'unknown')}")
    
    # 2. 存储今天的记忆
    mem_path = os.path.join(WORKSPACE, f"memory/{today}.md")
    if os.path.exists(mem_path):
        size = os.path.getsize(mem_path)
        log(f"Today memory: {size} bytes")
    
    # 3. 检查 KNOWLEDGE.md
    kw_path = os.path.join(WORKSPACE, "KNOWLEDGE.md")
    if os.path.exists(kw_path):
        size = os.path.getsize(kw_path)
        log(f"KNOWLEDGE.md: {size} bytes")
    
    log("Context cleanup done. Run 'openclaw sessions compact' for actual LCM compaction.")

if __name__ == "__main__":
    main()
