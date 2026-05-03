import sys
sys.path.insert(0, 'C:/Users/yiseg/.qclaw/workspace')
from evolver import EvolverEngine

eng = EvolverEngine()
stats = eng.get_stats()
print(f"规则总数: {len(eng.rules)}")
print(f"总调用: {stats.get('total_calls', stats.get('calls', 'N/A'))}")

# Check recent evolution candidates
candidates = [r for r in eng.rules if r.success_count >= 3 and r.confidence >= 0.7]
print(f"\n高置信度规则 ({len(candidates)} 条):")
for r in sorted(candidates, key=lambda x: -x.confidence)[:5]:
    print(f"  {r.task[:40]:40s} -> {r.method[:30]:30s} (conf={r.confidence:.0%}, calls={r.total_calls})")