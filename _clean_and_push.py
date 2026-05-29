#!/usr/bin/env python3
"""清除 token 并提交干净版本后推送"""
import subprocess, os, re

os.chdir(r'C:\Users\yiseg\.qclaw\workspace')

def run(cmd, check=True, capture=True):
    print(f"\n$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, encoding='utf-8', errors='replace')
    if r.stdout: print(r.stdout[-800:])
    if r.stderr: print("(stderr)", r.stderr[-400:])
    if check and r.returncode != 0:
        raise SystemExit(f"exit {r.returncode}")
    return r

# 1. 清除 memory/2026-05-23.md 中的 token 模式
print("=== 清除 token 模式 ===")
fp = r'C:\Users\yiseg\.qclaw\workspace\memory\2026-05-23.md'
with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换所有 ghp_ 模式为安全文本
count = 0
def replace_token(m):
    global count
    count += 1
    return f'[GITHUB_TOKEN_REDACTED_{count}]'
content = re.sub(r'ghp_[A-Za-z0-9_]{10,60}', replace_token, content)
content = content.replace('ghp_REDACTED', '[GITHUB_TOKEN_REDACTED]')
content = content.replace('REDACTED', 'REDACTED')

with open(fp, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ 已清除 token 模式（{count} 处替换）")

# 2. 验证无 token
print("\n=== 验证无 token ===")
r = run('git diff -- memory/2026-05-23.md', check=False)
if 'ghp_' in r.stdout or 'REDACTED' in r.stdout:
    print("❌ 仍有 token 模式")
else:
    print("✅ 无 token 模式")

# 3. add + commit
print("\n=== 提交 ===")
run('git add -A')
r = run('git commit -m "backup: 2026-05-29 workspace (token cleaned)"', check=False)
if r.returncode != 0:
    print("commit 失败，可能无变化")
    run('git status --short')

# 4. 推送
print("\n=== 推送 ===")
r = run('git push origin master', check=False)
if r.returncode == 0:
    print("\n✅ 推送成功！")
else:
    print(f"\n❌ 推送失败 (exit {r.returncode})")
    print("如果仍被拒，需要：git reset --soft HEAD~1 && 修改 remote URL 去掉 token")
