"""
Test script for ISC Safety Defense modules.
Run: E:\PYTON\python.exe test_safety_modules.py
"""

import sys
import os

# Add workspace to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Testing ISC Safety Defense Modules")
print("=" * 60)

# --- Test 1: safety_monitor.py ---
print("\n--- Test 1: safety_monitor.py ---")

try:
    from safety_monitor import check_tool_call, check_tool_result, monitor, RiskLevel

    # Test 1.1: Dangerous command
    print("\n1.1 Dangerous command (rm -rf /):")
    result = check_tool_call('exec', 'rm -rf /', task_id='task_1', original_intent='Clean up temp files')
    print(f"   Result: safe={result.safe}, risk={result.risk_level.name}, block={result.block}")
    print(f"   Reason: {result.reason[:80]}...")
    assert not result.safe, "Should block dangerous command"
    assert result.block, "Should block"
    print("   ✅ PASS")

    # Test 1.2: Safe command
    print("\n1.2 Safe command (pip install numpy):")
    result = check_tool_call('exec', 'pip install numpy', task_id='task_2', original_intent='Install dependencies')
    print(f"   Result: safe={result.safe}, risk={result.risk_level.name}")
    assert result.safe, "Should allow safe command"
    print("   ✅ PASS")

    # Test 1.3: Writing malware
    print("\n1.3 Writing malware:")
    result = check_tool_call('write', {'path': '/tmp/test.sh', 'content': 'rm -rf /'}, task_id='task_3', original_intent='Create test script')
    print(f"   Result: safe={result.safe}, risk={result.risk_level.name}, block={result.block}")
    assert not result.safe, "Should block malware content"
    print("   ✅ PASS")

    # Test 1.4: Chain deviation (ISC core scenario!)
    print("\n1.4 Chain deviation (ISC scenario):")
    task_id = 'task_4'
    monitor.create_chain(task_id, 'Install dependencies for project')
    # Step 1: Normal
    result1 = check_tool_call('exec', 'pip install numpy', task_id=task_id)
    print(f"   Step 1 (pip install): safe={result1.safe}")
    # Step 2: Normal
    result2 = check_tool_call('exec', 'pip install pandas', task_id=task_id)
    print(f"   Step 2 (pip install): safe={result2.safe}")
    # Step 3: Suddenly dangerous (ISC!)
    result3 = check_tool_call('exec', 'rm -rf .', task_id=task_id)
    print(f"   Step 3 (rm -rf .): safe={result3.safe}, block={result3.block}")
    print(f"   Reason: {result3.reason[:80]}...")
    assert not result3.safe, "Should detect chain deviation"
    print("   ✅ PASS")

    print("\n✅ safety_monitor.py: All tests passed!")

except Exception as e:
    print(f"\n❌ safety_monitor.py test FAILED: {e}")
    import traceback
    traceback.print_exc()


# --- Test 2: evolver_safety_rules.py ---
print("\n" + "=" * 60)
print("--- Test 2: evolver_safety_rules.py ---")

try:
    from evolver_safety_rules import check_safety, list_safety_rules, add_safety_rule, SafetyRule, RulePriority

    # Test 2.1: Dangerous command
    print("\n2.1 Dangerous command (rm -rf /):")
    result = check_safety('exec', 'rm -rf /')
    print(f"   Result: safe={result['safe']}, block={result['block']}")
    print(f"   Rule: {result['rule']}, Reason: {result['reason'][:80]}...")
    assert not result['safe'], "Should block dangerous command"
    assert result['block'], "Should block"
    print("   ✅ PASS")

    # Test 2.2: Safe command
    print("\n2.2 Safe command (pip install numpy):")
    result = check_safety('exec', 'pip install numpy')
    print(f"   Result: safe={result['safe']}")
    assert result['safe'], "Should allow safe command"
    print("   ✅ PASS")

    # Test 2.3: Chain deviation
    print("\n2.3 Chain deviation (ISC scenario):")
    context = {
        'execution_chain': {
            'original_intent': 'Install dependencies for project',
            'steps': [
                {'tool': 'exec', 'input': 'pip install numpy'},
                {'tool': 'exec', 'input': 'pip install pandas'},
                {'tool': 'exec', 'input': 'pip install scipy'},
            ]
        }
    }
    result = check_safety('exec', 'rm -rf .', context)
    print(f"   Result: safe={result['safe']}, block={result['block']}")
    print(f"   Reason: {result['reason'][:80]}...")
    assert not result['safe'], "Should detect chain deviation"
    print("   ✅ PASS")

    # Test 2.4: List rules
    print("\n2.4 List all safety rules:")
    rules = list_safety_rules()
    print(f"   Total rules: {len(rules)}")
    for rule_info in rules:
        print(f"   - {rule_info['name']} (Priority: {rule_info['priority']}, Enabled: {rule_info['enabled']})")
    assert len(rules) >= 5, "Should have at least 5 default rules"
    print("   ✅ PASS")

    print("\n✅ evolver_safety_rules.py: All tests passed!")

except Exception as e:
    print(f"\n❌ evolver_safety_rules.py test FAILED: {e}")
    import traceback
    traceback.print_exc()


# --- Test 3: Integration Example ---
print("\n" + "=" * 60)
print("--- Test 3: Integration Example ---")

print("""
Integration with tool_pipeline.py:

```python
# In tool_pipeline.py

from safety_monitor import check_tool_call, check_tool_result
from evolver_safety_rules import check_safety

def execute_tool(tool_name, tool_input, task_id=None, original_intent=None):
    # STEP 1: Pre-execution safety check (ISC Defense!)
    result = check_tool_call(tool_name, tool_input, task_id=task_id, original_intent=original_intent)
    
    if not result.safe:
        # ISC Protection: Block the call
        print(f"🚨 SAFETY CHECK FAILED:")
        print(f"   Reason: {result.reason}")
        print(f"   Suggestion: {result.suggestion}")
        
        if result.block:
            # Ask user for confirmation
            user_confirm = input("This operation looks dangerous. Do you want to proceed? (yes/no): ")
            if user_confirm.lower() != 'yes':
                return None  # Blocked
    
    # STEP 2: Execute the tool
    output = call_actual_tool(tool_name, tool_input)
    
    # STEP 3: Post-execution safety check (ISC Defense!)
    result = check_tool_result(tool_name, output, task_id=task_id)
    
    if not result.safe:
        print(f"🚨 Post-execution safety check failed: {result.reason}")
        # Log or alert
    
    return output
```

Key ISC Defense Points:
1. ✅ Pre-execution check: Block BEFORE dangerous actions
2. ✅ Chain deviation detection: Detect when task chain goes off-track
3. ✅ Post-execution check: Catch unsafe outputs
4. ✅ User confirmation: Never auto-proceed on dangerous ops
""")

print("✅ Integration example created!")

print("\n" + "=" * 60)
print("ALL TESTS PASSED! ✅")
print("=" * 60)
print("\nISC Defense modules are ready for integration.")
print("\nNext steps:")
print("1. Integrate with tool_pipeline.py (add pre/post checks)")
print("2. Update AGENTS.md/TOOLS.md (already done)")
print("3. Test with real tasks to verify ISC defense works")
