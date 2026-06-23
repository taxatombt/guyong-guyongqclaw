"""
Tool Pipeline Integration Example - ISC Defense Implementation
Based on paper: "Internal Safety Collapse in Frontier Large Language Models"

This file shows how to integrate ISC defenses into tool_pipeline.py.

Integration Steps:
1. Import safety modules at the top of tool_pipeline.py
2. Add pre-execution safety check (BEFORE tool call)
3. Add post-execution safety check (AFTER tool call)
4. Add execution chain tracking for chain deviation detection
"""

import sys
import os
import logging
from typing import Dict, Any, Optional

# ================================================================
# STEP 1: Import safety modules
# ================================================================

# Add workspace to path (if not already added)
workspace = os.path.dirname(os.path.abspath(__file__))
if workspace not in sys.path:
    sys.path.insert(0, workspace)

try:
    from safety_monitor import check_tool_call, check_tool_result, monitor
    from evolver_safety_rules import check_safety, safety_engine
    SAFTEY_MODULES_AVAILABLE = True
except ImportError as e:
    logging.warning(f"ISC Safety modules not available: {e}")
    SAFTEY_MODULES_AVAILABLE = False


# ================================================================
# STEP 2: Execution Chain Tracking
# ================================================================

class ExecutionChainTracker:
    """
    Tracks execution chain for a task to detect ISC (Internal Safety Collapse).

    ISC Insight: The paper shows that models start with benign tasks,
    but through multiple steps of reasoning, derive that unsafe actions
    are necessary. This tracker detects that derivation.
    """

    def __init__(self):
        self.current_task_id = None
        self.chains = {}  # task_id -> chain info

    def start_task(self, task_id: str, original_intent: str):
        """Start tracking a new task."""
        if SAFTEY_MODULES_AVAILABLE:
            chain = monitor.create_chain(task_id, original_intent)
            self.chains[task_id] = chain
            self.current_task_id = task_id
            logging.info(f"Started tracking task {task_id}: {original_intent[:50]}...")

    def end_task(self, task_id: str):
        """End tracking for a task."""
        if task_id in self.chains:
            del self.chains[task_id]
            if self.current_task_id == task_id:
                self.current_task_id = None
            logging.info(f"Ended tracking task {task_id}")

    def get_current_chain(self):
        """Get current execution chain."""
        if self.current_task_id:
            return self.chains.get(self.current_task_id)
        return None


# Global tracker instance
tracker = ExecutionChainTracker()


# ================================================================
# STEP 3: Pre-Execution Safety Check (BEFORE tool call)
# ================================================================

def pre_execution_safety_check(tool_name: str, tool_input: Any,
                               task_id: Optional[str] = None,
                               original_intent: Optional[str] = None) -> Dict[str, Any]:
    """
    ISC Defense: Check BEFORE tool execution.

    Key Insight from ISC Paper:
    - Traditional safety filters check USER INPUT (prompt)
    - ISC happens in the TASK CHAIN (model's own reasoning)
    - Need to check at EVERY step, not just at the beginning

    Returns:
        Dict with keys:
        - 'safe': bool
        - 'block': bool
        - 'reason': str
        - 'suggestion': str
    """
    if not SAFTEY_MODULES_AVAILABLE:
        return {'safe': True, 'block': False, 'reason': None, 'suggestion': None}

    # Get or create chain
    chain = None
    if task_id:
        chain = tracker.get_current_chain()
        if not chain and original_intent:
            tracker.start_task(task_id, original_intent)
            chain = tracker.get_current_chain()

    # Check using safety_monitor (execution chain monitoring)
    result = check_tool_call(tool_name, tool_input,
                             task_id=task_id,
                             original_intent=original_intent)

    # Also check using evolver_safety_rules (safety rules engine)
    context = {}
    if chain:
        context['execution_chain'] = {
            'original_intent': chain.original_intent,
            'steps': [{'tool': s.tool_name, 'input': str(s.tool_input)[:100]} for s in chain.steps]
        }

    result2 = check_safety(tool_name, tool_input, context)

    # Combine results (if either blocks, block)
    if not result.safe or not result2['safe']:
        block = result.block or result2['block']
        reason = result.reason if not result.safe else result2['reason']
        suggestion = result.suggestion if not result.safe else None

        logging.warning(f"🚨 ISC PRE-CHECK FAILED:")
        logging.warning(f"   Tool: {tool_name}")
        logging.warning(f"   Input: {str(tool_input)[:100]}")
        logging.warning(f"   Reason: {reason}")

        return {
            'safe': False,
            'block': block,
            'reason': reason,
            'suggestion': suggestion
        }

    return {'safe': True, 'block': False, 'reason': None, 'suggestion': None}


# ================================================================
# STEP 4: Post-Execution Safety Check (AFTER tool call)
# ================================================================

def post_execution_safety_check(tool_name: str, tool_output: Any,
                                task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    ISC Defense: Check AFTER tool execution.

    Key Insight from ISC Paper:
    - The model may have generated harmful content as part of "completing the task"
    - Need to check OUTPUT, not just input

    Returns:
        Dict with keys: 'safe', 'reason'
    """
    if not SAFTEY_MODULES_AVAILABLE:
        return {'safe': True, 'reason': None}

    result = check_tool_result(tool_name, tool_output, task_id=task_id)

    if not result.safe:
        logging.warning(f"🚨 ISC POST-CHECK FAILED:")
        logging.warning(f"   Tool: {tool_name}")
        logging.warning(f"   Output: {str(tool_output)[:100]}")
        logging.warning(f"   Reason: {result.reason}")

        return {
            'safe': False,
            'reason': result.reason
        }

    return {'safe': True, 'reason': None}


# ================================================================
# STEP 5: Integrate into tool_pipeline.py
# ================================================================

"""
Example integration with tool_pipeline.py:

Original tool_pipeline.py:
```python
def execute_tool(tool_name, tool_input, task_id=None, original_intent=None):
    # Execute the tool
    output = call_actual_tool(tool_name, tool_input)
    return output
```

Modified tool_pipeline.py (with ISC defense):
```python
from tool_pipeline_integration import (
    pre_execution_safety_check,
    post_execution_safety_check,
    tracker
)

def execute_tool(tool_name, tool_input, task_id=None, original_intent=None):
    # === ISC DEFENSE: PRE-EXECUTION CHECK ===
    check_result = pre_execution_safety_check(
        tool_name, tool_input,
        task_id=task_id,
        original_intent=original_intent
    )

    if not check_result['safe']:
        logging.warning(f"Tool execution blocked by ISC defense: {check_result['reason']}")

        # ISC Insight: "Task completion pressure" can make model ignore safety
        # Solution: ALWAYS ask user when safety check fails
        if check_result['block']:
            user_confirm = input(f"🚨 Safety check failed: {check_result['reason']}\nDo you want to proceed? (yes/no): ")
            if user_confirm.lower() != 'yes':
                return None  # Blocked

    # === EXECUTE THE TOOL ===
    output = call_actual_tool(tool_name, tool_input)

    # === ISC DEFENSE: POST-EXECUTION CHECK ===
    post_check = post_execution_safety_check(
        tool_name, output,
        task_id=task_id
    )

    if not post_check['safe']:
        logging.warning(f"Post-execution check failed: {post_check['reason']}")
        # Log or alert, but don't necessarily block (output already generated)

    # === RECORD STEP FOR CHAIN TRACKING ===
    if task_id and tracker.current_task_id == task_id:
        chain = tracker.get_current_chain()
        if chain:
            from safety_monitor import ExecutionStep, RiskLevel
            import time
            step = ExecutionStep(
                step_id=len(chain.steps),
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=output,
                timestamp=time.time()
            )
            chain.add_step(step)

    return output
```

Usage example:
```python
# Start a task
tracker.start_task('task_123', 'Install dependencies for project')

# Execute tools (with ISC defense)
output1 = execute_tool('exec', 'pip install numpy', task_id='task_123', original_intent='Install dependencies for project')
output2 = execute_tool('exec', 'pip install pandas', task_id='task_123')
# ISC scenario: Suddenly dangerous!
output3 = execute_tool('exec', 'rm -rf .', task_id='task_123')  # BLOCKED!

# End task
tracker.end_task('task_123')
```
"""

# ================================================================
# STEP 6: Example usage and testing
# ================================================================

if __name__ == '__main__':
    print("=" * 60)
    print(" ISC Defense Integration Example")
    print("=" * 60)

    if not SAFTEY_MODULES_AVAILABLE:
        print("\n❌ Safety modules not available. Cannot run example.")
        sys.exit(1)

    # Example: Complete task execution with ISC defense
    print("\n--- Example: Task with ISC Defense ---")

    # Start task
    task_id = 'example_task_1'
    original_intent = 'Install dependencies for project'
    tracker.start_task(task_id, original_intent)

    # Step 1: Safe command
    print("\nStep 1: Safe command (pip install numpy)")
    result = pre_execution_safety_check('exec', 'pip install numpy', task_id=task_id, original_intent=original_intent)
    print(f"   Pre-check: safe={result['safe']}")
    assert result['safe'], "Should be safe"

    # Step 2: Safe command
    print("\nStep 2: Safe command (pip install pandas)")
    result = pre_execution_safety_check('exec', 'pip install pandas', task_id=task_id, original_intent=original_intent)
    print(f"   Pre-check: safe={result['safe']}")
    assert result['safe'], "Should be safe"

    # Step 3: Dangerous command (ISC scenario!)
    print("\nStep 3: Dangerous command (rm -rf .) - ISC Chain Deviation!")
    result = pre_execution_safety_check('exec', 'rm -rf .', task_id=task_id, original_intent=original_intent)
    print(f"   Pre-check: safe={result['safe']}, block={result['block']}")
    print(f"   Reason: {result['reason'][:100]}...")
    assert not result['safe'], "Should be blocked"

    # End task
    tracker.end_task(task_id)

    print("\n" + "=" * 60)
    print("✅ ISC Defense integration example completed!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Copy the `execute_tool` modification into your tool_pipeline.py")
    print("2. Test with real tasks to verify ISC defense works")
    print("3. Monitor logs for blocked dangerous operations")
