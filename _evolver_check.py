from evolver import EvolverEngine
eng = EvolverEngine()
print(f'总规则: {len(eng.rules)}')
# Rule 是 dataclass，用属性访问
today_new = sum(1 for r in eng.rules if hasattr(r, 'timestamp') and "2026-05-05" in str(r.timestamp))
print(f'今日新增: {today_new}')
recent = eng.rules[-5:]
print('\n最近5条:')
for r in recent:
    task = getattr(r, 'task', '?')
    method = getattr(r, 'method', '?')
    sr = getattr(r, 'success_rate', 0) or 0
    print(f"  - {task} -> {method} [{sr:.0%}]")
