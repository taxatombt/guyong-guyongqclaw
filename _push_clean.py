#!/usr/bin/env python3
"""清理 token 并推送"""
import subprocess, os, re

os.chdir(r'C:\Users\yiseg\.qclaw\workspace')

def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f"$ {cmd}")
    if r.stdout: print(r.stdout[:500])
    if r.stderr: print("(stderr)", r.stderr[:500])
    if check and r.returncode != 0:
        raise SystemExit(f"exit {r.returncode}")
    return r

# 1. 确认没有 token
print("=== 扫描 token ===")
r = run('git diff --cached --name-only', check=False)
files = [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
# 也检查未暂存文件
r2 = run('git diff --name-only', check=False)
files += [f.strip() for f in r2.stdout.strip().splitlines() if f.strip()]
files = list(set(files))
print(f"暂存+未暂存共 {len(files)} 个文件")

token_found = False
for f in files:
    if not os.path.exists(f): continue
    with open(f, 'r', encoding='utf-8', errors='replace') as fp:
        content = fp.read()
    if re.search(r'ghp_[A-Za-z0-9]{20,}', content):
        print(f"  ❌ {f} 含 token")
        token_found = True

if token_found:
    print("中止：有 token 未清除")
    raise SystemExit(1)
print("✅ 无 token")

# 2. 重新 add + commit
print("\n=== 重新提交 ===")
run('git add -A')
run('git commit -m "backup: 2026-05-29 workspace snapshot (token cleaned)"')

# 3. 推送
print("\n=== 推送 ===")
r = run('git push origin master', check=False)
if r.returncode == 0:
    print("\n✅ 推送成功")
else:
    print(f"\n❌ 推送失败 (exit {r.returncode})")
    # 如果还是被拒，需要更深入处理
    print("可能需要：git reset --soft HEAD~1 然后修改 remote URL 去掉 token")
