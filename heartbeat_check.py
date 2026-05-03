import sys
sys.stdout.reconfigure(encoding='utf-8')

from evolver import EvolverEngine
eng = EvolverEngine()

print('=== Evolver Stats ===')
print(f'Total rules: {len(eng.rules)}')

import datetime
today = datetime.date.today().isoformat()

# Latest 10 by last_success
rules_sorted = sorted(eng.rules, key=lambda r: r.last_success or r.created_at or '', reverse=True)

print('\n--- Latest 10 rules (by last_success) ---')
for r in rules_sorted[:10]:
    ts = (r.last_success or r.created_at or '?')[:10]
    print(f'  {r.task[:40]:40s} | {r.method[:30]:30s} | sr={r.success_rate:.0%} | n={r.total_count}')

# Today new
today_rules = [r for r in eng.rules if r.created_at and r.created_at.startswith(today)]
print(f'\n--- Today new: {len(today_rules)} ---')
for r in today_rules:
    print(f'  {r.task[:40]} | {r.method[:30]}')

# Low confidence rules (total_count>=3, conf<0.6)
print('\n--- Low conf rules (>=3 attempts, conf<0.6) ---')
low = [r for r in eng.rules if r.total_count >= 3 and r.confidence < 0.6]
if low:
    for r in low[:5]:
        print(f'  {r.task[:40]} | conf={r.confidence:.2f} | rate={r.success_rate:.0%} | n={r.total_count}')
else:
    print('  None')

# Top performers
print('\n--- Top performers (conf>=0.8) ---')
top = [r for r in eng.rules if r.confidence >= 0.8]
for r in sorted(top, key=lambda x: -x.confidence)[:8]:
    print(f'  conf={r.confidence:.2f} | {r.task[:35]} | {r.method[:25]}')

# Recent failures
print('\n--- Recent failures (last_failure not null) ---')
failures = sorted([r for r in eng.rules if r.last_failure], key=lambda r: r.last_failure, reverse=True)[:5]
for r in failures:
    print(f'  {r.task[:40]} | fails={r.consecutive_failures} | last={r.last_failure[:10]} | conf={r.confidence:.2f}')