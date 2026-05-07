from evolver import EvolverEngine

e = EvolverEngine()
print(f'Rules: {len(e.rules)} | Failing: {sum(1 for r in e.rules if getattr(r, "success_rate", 1) < 0.5)}')
print(f'High confidence (>=0.7): {sum(1 for r in e.rules if getattr(r, "confidence", 0) >= 0.7)}')
print()
top = sorted(e.rules, key=lambda r: getattr(r, "confidence", 0), reverse=True)[:5]
print('Top confidence:')
for r in top:
    print(f'  {getattr(r, "task", "?")} -> {getattr(r, "method", "?")} [{getattr(r, "confidence", 0)*100:.0f}%]')
