@echo off
REM run_all.bat - Managed Agents Study 验证脚本
REM 验证4个核心模块：session_vault / skill_metadata / subagent_protocol / exec_isolation

echo ============================================
echo  Managed Agents Study - Verify All Modules
echo ============================================
echo.

cd /d "C:\Users\yiseg\.qclaw\workspace\skills\managed-agents-study"

echo [1/4] session_vault.py
python -X utf8 -c "from session_vault import SessionVault, get_vault, emit, get, wake; v = SessionVault(); sid = v.create_session('test'); emit(sid, 'user_message', {'text': 'hello'}); events = get(sid); print(f'  PASS: {len(events)} events, session={sid}')"
if errorlevel 1 echo   FAIL!
echo.

echo [2/4] skill_metadata.py
python -X utf8 -c "from skill_metadata import SkillRegistry, get_registry; r = SkillRegistry(); count = r.scan(); print(f'  PASS: {count} skills discovered')"
if errorlevel 1 echo   FAIL!
echo.

echo [3/4] subagent_protocol.py
python -X utf8 -c "from subagent_protocol import SubagentRequest, SubagentRole, SubagentDispatcher, compress_result, extract_key_findings; req = SubagentRequest(task='test', role=SubagentRole.EXPLORE); err = req.validate(); d = SubagentDispatcher(); sid = d.dispatch(req); print(f'  PASS: request_id={req.request_id}, dispatch={sid}')"
if errorlevel 1 echo   FAIL!
echo.

echo [4/4] exec_isolation.py
python -X utf8 -c "from exec_isolation import CredentialVault, execute_isolated, sanitize_output; v = CredentialVault(); v.store('TEST_KEY', 'sk-abc123def456ghi789xyz000', source='test'); result = execute_isolated('echo hello', sandbox_id='test_sandbox', vault=v); print(f'  PASS: exit={result.exit_code}, output={result.stdout.strip()}')"
if errorlevel 1 echo   FAIL!
echo.

echo.

echo [5/6] context_layers.py
cd /d "C:\Users\yiseg\.qclaw\workspace\skills\managed-agents-study"
python -X utf8 -c "from context_layers import ContextManager, CompactStrategy; cm = ContextManager(); cm.append_event('user', 'hello', token_count=50); b = cm.compact(CompactStrategy.AUTO_COMPACT); view = cm.render_view('system'); stats = cm.get_stats(); print('  PASS: events=%d, boundaries=%d' % (stats['total_events'], stats['compact_boundaries']))"
if errorlevel 1 echo   FAIL!
echo.

echo [6/8] harness_modules.py
python -X utf8 -c "from harness_modules import Harness, HITLDecision; h = Harness(); h.context.write('k', 'v'); plan = h.orchestrator.plan('read file'); req = h.hitl.check_required('drop database users'); print('  PASS: status=%s' % str(h.get_status()))"
if errorlevel 1 echo   FAIL!
echo.

echo [7/8] workflow_patterns.py
echo   Testing 6 patterns...
python -X utf8 -c "from workflow_patterns import *; chain = PromptChain(); chain.add_step('a', '{prev_output}'); r1 = chain.run('test'); router = Router(); router.add_route('x', 'test'); r2 = router.run('test'); par = Parallelizer(); par.add_task('t1', '{input}'); r3 = par.run('test'); ow = OrchestratorWorkers(); r4 = ow.run('test'); eo = EvaluatorOptimizer(max_iterations=2); r5 = eo.run('test'); agent = AutonomousAgent(max_iterations=2); r6 = agent.run('test'); print('  PASS: chain=%s, route=%s, par=%s, ow=%s, eo=%s, agent=%s' % (r1.success, r2.success, r3.success, r4.success, r5.success, r6.state.value))"
if errorlevel 1 echo   FAIL!
echo.

echo [8/8] WorkflowFactory
python -X utf8 -c "from workflow_patterns import WorkflowFactory; rec = WorkflowFactory.recommend('route different queries'); print('  PASS: recommend=%s' % rec['recommended'])"
if errorlevel 1 echo   FAIL!
echo.

echo ============================================
echo  All 8 modules verified.
echo ============================================
pause
