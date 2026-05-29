import subprocess, os
os.chdir(r'C:\Users\yiseg\.qclaw\workspace')

print("=== git push ===")
r = subprocess.run(
    ['git', 'push', 'origin', 'master'],
    capture_output=True, text=True, timeout=60,
    encoding='utf-8', errors='replace'
)
print("stdout:", r.stdout[-500:] if r.stdout else "(empty)")
print("stderr:", r.stderr[-500:] if r.stderr else "(empty)")
print("returncode:", r.returncode)
print("===")
