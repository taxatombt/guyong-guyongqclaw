#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qclaw_cleanup.py - QClaw 定时清理脚本（纯 Python，无 LLM 调用）
直接替换 Cron 任务中的 agentTurn，避免占用 API 配额
"""
import os
import json
import glob
import shutil
import datetime

WORKSPACE = r"C:\Users\yiseg\.qclaw\workspace"
SESSION_DIR = os.path.expanduser(r"~/.qclaw/sessions")
DOWNLOAD_DIR = os.path.join(WORKSPACE, "_download")
MEMORY_DIR = os.path.join(WORKSPACE, "memory")

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def get_age_hours(path):
    """返回文件年龄（小时）"""
    mtime = os.path.getmtime(path)
    age_s = datetime.datetime.now().timestamp() - mtime
    return age_s / 3600

def cleanup_tmp_files():
    """清理临时文件"""
    deleted = []
    patterns = ["_tmp*", "*.tmp", "check_*.py", "_check_*.py", "_find_*.py", "_read_*.py"]
    for pattern in patterns:
        for f in glob.glob(os.path.join(WORKSPACE, pattern)):
            age = get_age_hours(f)
            # Python 脚本超过 1 小时删除，*.tmp 文件超过 1 小时删除
            is_tmp = pattern.startswith("_tmp") or pattern == "*.tmp"
            threshold = 1 if is_tmp else 1
            if age > threshold:
                try:
                    os.remove(f)
                    deleted.append(f"{os.path.basename(f)} ({age:.1f}h)")
                except Exception as e:
                    log(f"  删除失败 {f}: {e}")
    return deleted

def cleanup_downloads():
    """清理下载缓存"""
    deleted = []
    if not os.path.exists(DOWNLOAD_DIR):
        return deleted
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        age = get_age_hours(f)
        if age > 24:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                elif os.path.isdir(f):
                    shutil.rmtree(f)
                deleted.append(f"{os.path.basename(f)} ({age:.1f}h)")
            except Exception as e:
                log(f"  删除失败 {f}: {e}")
    return deleted

def cleanup_memory():
    """清理过期的 memory 日期文件"""
    deleted = []
    if not os.path.exists(MEMORY_DIR):
        return deleted
    now = datetime.datetime.now()
    for f in glob.glob(os.path.join(MEMORY_DIR, "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md")):
        try:
            age_days = (now - datetime.datetime.fromtimestamp(os.path.getmtime(f))).days
            size = os.path.getsize(f)
            # 超过 7 天且内容少于 500 字
            if age_days > 7 and size < 500:
                os.remove(f)
                deleted.append(f"{os.path.basename(f)} ({age_days}d, {size}b)")
        except Exception as e:
            log(f"  删除失败 {f}: {e}")
    return deleted

def cleanup_sessions():
    """清理旧的会话缓存文件"""
    deleted = []
    if not os.path.exists(SESSION_DIR):
        return deleted
    for f in glob.glob(os.path.join(SESSION_DIR, "*.jsonl")):
        age_days = get_age_hours(f) / 24
        if age_days > 7:
            try:
                os.remove(f)
                deleted.append(f"{os.path.basename(f)} ({age_days:.1f}d)")
            except Exception as e:
                log(f"  删除失败 {f}: {e}")
    return deleted

def main():
    log("QClaw 定时清理开始...")
    
    r1 = cleanup_tmp_files()
    r2 = cleanup_downloads()
    r3 = cleanup_memory()
    r4 = cleanup_sessions()
    
    all_deleted = r1 + r2 + r3 + r4
    
    if all_deleted:
        log(f"已清理 {len(all_deleted)} 个文件/目录:")
        for d in all_deleted:
            log(f"  - {d}")
    else:
        log("无需清理")
    
    # 更新 heartbeat state
    state_path = os.path.join(WORKSPACE, "memory", "heartbeat-state.json")
    today = datetime.date.today().isoformat()
    state = {}
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except:
            pass
    state["lastCleanup"] = today
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    log("清理完成")

if __name__ == "__main__":
    main()
