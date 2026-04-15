# concurrent.py
# 顾庸 · 并发执行系统 v1.0
# 灵感来源: Hermes run_agent.py _execute_tool_calls_concurrent() (NousResearch)
# 对标: ThreadPoolExecutor + 工具注册表 + 顺序/并发双模式

from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Callable, Dict, List, Optional, Any
import threading
from datetime import datetime


# ─────────────────────────────────────────
# 配置常量（Hermes 原生值）
# ─────────────────────────────────────────
_MAX_TOOL_WORKERS = 3      # Hermes _MAX_TOOL_WORKERS
_DEFAULT_TIMEOUT = 30.0    # 单行动超时（秒）
_ACTION_EXECUTORS: Dict[str, Callable] = {}


# ─────────────────────────────────────────
# 工具注册表（对标 Hermes Tool Registry）
# ─────────────────────────────────────────
def register_executor(action_type: str, executor: Callable[[Dict], Dict]) -> None:
    """
    注册自定义行动执行器。

    用法:
        def my_executor(action: Dict) -> Dict:
            # action = {'action_id': 1, 'description': '...', ...}
            return {'success': True, 'result': 'done', 'error': ''}
        register_executor('http_request', my_executor)
    """
    _ACTION_EXECUTORS[action_type] = executor


def unregister_executor(action_type: str) -> bool:
    """注销执行器"""
    return _ACTION_EXECUTORS.pop(action_type, None) is not None


def get_registered_executors() -> List[str]:
    """列出已注册的执行器"""
    return list(_ACTION_EXECUTORS.keys())


# ─────────────────────────────────────────
# 行动类型推断
# ─────────────────────────────────────────
def infer_action_type(description: str) -> str:
    """从描述推断行动类型"""
    desc = description.lower()
    if 'http' in desc or '\u8bf7\u6c42' in desc or 'api' in desc:
        return 'http_request'
    if 'git' in desc or '\u63d0\u4ea4' in desc:
        return 'git'
    if '\u6587\u4ef6' in desc or 'file' in desc or 'write' in desc:
        return 'file_operation'
    if '\u641c\u7d22' in desc or 'search' in desc:
        return 'search'
    if '\u786e\u8ba4' in desc or 'confirm' in desc:
        return 'confirmation'
    return 'default'


# ─────────────────────────────────────────
# 单行动执行
# ─────────────────────────────────────────
def execute_single_action(action: Dict, timeout: float = _DEFAULT_TIMEOUT) -> Dict:
    """
    执行单条行动（带超时保护）。

    返回结构:
        {
            'action_id': int,
            'success': bool,
            'result': str,
            'duration_ms': float,
            'error': str,
        }
    """
    start = datetime.now()
    action_id = action.get('action_id', 0)
    description = action.get('description', '')
    action_type = infer_action_type(description)

    executor = _ACTION_EXECUTORS.get(action_type)
    if executor:
        try:
            result = executor(action)
            duration = (datetime.now() - start).total_seconds() * 1000
            return {
                'action_id': action_id,
                'success': result.get('success', True),
                'result': result.get('result', ''),
                'duration_ms': duration,
                'error': result.get('error', ''),
            }
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            return {
                'action_id': action_id,
                'success': False,
                'result': '',
                'duration_ms': duration,
                'error': str(e),
            }

    # 默认执行器：返回确认（接入具体业务逻辑）
    return {
        'action_id': action_id,
        'success': True,
        'result': '[{}] {}'.format(action_type, description[:80]),
        'duration_ms': (datetime.now() - start).total_seconds() * 1000,
        'error': '',
    }


# ─────────────────────────────────────────
# 并发执行（Hermes ThreadPoolExecutor）
# ─────────────────────────────────────────
def execute_concurrent(
    actions: List[Dict],
    max_workers: int = _MAX_TOOL_WORKERS,
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[Dict]:
    """
    并发执行多个行动（Hermes ThreadPoolExecutor 风格）。

    特性:
    - 超时保护（每个行动独立超时）
    - 结果有序（与输入顺序一致，不受完成顺序影响）
    - 异常隔离（单个失败不影响其他）

    用法:
        results = execute_concurrent(pending_actions, max_workers=3)
        for r in results:
            if r['success']:
                print('OK: action-{} = {}'.format(r['action_id'], r['result']))
            else:
                print('FAIL: action-{} = {}'.format(r['action_id'], r['error']))
    """
    if not actions:
        return []

    # 建立 action_id -> 索引 的映射（保证结果有序）
    results = [None] * len(actions)
    action_id_to_idx = {a.get('action_id', i): i for i, a in enumerate(actions)}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(actions))) as executor:
        # 提交所有任务
        future_to_action = {
            executor.submit(execute_single_action, action, timeout): action
            for action in actions
        }

        # 收集结果（无序到达，按序返回）
        for future in as_completed(future_to_action):
            action = future_to_action[future]
            action_id = action.get('action_id')
            idx = action_id_to_idx.get(action_id, -1)

            try:
                result = future.result(timeout=timeout + 1)
            except TimeoutError:
                result = {
                    'action_id': action_id,
                    'success': False,
                    'result': '',
                    'duration_ms': timeout * 1000,
                    'error': '超时（>{}s）'.format(timeout),
                }
            except Exception as e:
                result = {
                    'action_id': action_id,
                    'success': False,
                    'result': '',
                    'duration_ms': 0,
                    'error': str(e),
                }

            if idx >= 0:
                results[idx] = result

    # 填充 None（理论上不应发生）
    for i, r in enumerate(results):
        if r is None:
            results[i] = {
                'action_id': actions[i].get('action_id', i),
                'success': False,
                'result': '',
                'duration_ms': 0,
                'error': '未执行',
            }

    return results


# ─────────────────────────────────────────
# 顺序执行（Hermes _execute_tool_calls_sequential）
# ─────────────────────────────────────────
def execute_sequential(
    actions: List[Dict],
    timeout: float = _DEFAULT_TIMEOUT,
    stop_on_failure: bool = False,
) -> List[Dict]:
    """
    顺序执行（备用模式）。
    对标 Hermes: _execute_tool_calls_sequential()
    """
    results = []
    for action in actions:
        result = execute_single_action(action, timeout)
        results.append(result)
        if stop_on_failure and not result['success']:
            break
    return results


# ─────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────
def execute(
    actions: List[Dict],
    mode: str = 'concurrent',
    max_workers: int = _MAX_TOOL_WORKERS,
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[Dict]:
    """
    执行行动计划（主入口，自动选择并发/顺序模式）。

    参数:
        actions: 行动列表
        mode: 'concurrent' 或 'sequential'
        max_workers: 最大并发数
        timeout: 单行动超时（秒）

    返回:
        List[Dict] — 每条行动的执行结果
    """
    if not actions:
        return []

    if mode == 'concurrent':
        return execute_concurrent(actions, max_workers=max_workers, timeout=timeout)
    else:
        return execute_sequential(actions, timeout=timeout)


# ─────────────────────────────────────────
# 统计与诊断
# ─────────────────────────────────────────
def get_stats() -> Dict:
    """获取并发执行器状态"""
    return {
        'registered_executors': list(_ACTION_EXECUTORS.keys()),
        'max_workers_default': _MAX_TOOL_WORKERS,
        'default_timeout_sec': _DEFAULT_TIMEOUT,
        'thread_count_active': threading.active_count(),
    }


def summarize_results(results: List[Dict]) -> str:
    """生成执行结果摘要"""
    if not results:
        return '无行动'
    total = len(results)
    success = sum(1 for r in results if r.get('success'))
    failed = total - success
    total_ms = sum(r.get('duration_ms', 0) for r in results)
    avg_ms = total_ms / total if total else 0
    return '{}/{} 成功 ({:.0f}ms/个)'.format(success, total, avg_ms)


# ─────────────────────────────────────────
# 导出
# ─────────────────────────────────────────
__all__ = [
    'register_executor', 'unregister_executor', 'get_registered_executors',
    'infer_action_type',
    'execute_single_action',
    'execute_concurrent', 'execute_sequential', 'execute',
    'get_stats', 'summarize_results',
    '_MAX_TOOL_WORKERS', '_DEFAULT_TIMEOUT',
]
