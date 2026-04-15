#!/usr/bin/env python3
"""
External hook: evolver_observer.py
- 触发: post_tool (每次工具成功执行后)
- 作用: 默默记录工具调用到日志，不阻断不干扰
- 输出: allow (静默，不影响主流程)
"""
import os, json, sys
from datetime import datetime

WORKSPACE = os.environ.get('WORKSPACE', r'C:\Users\yiseg\.qclaw\workspace')
LOG = os.path.join(WORKSPACE, 'memory', 'tool_observations.jsonl')

def log_observation(tool_name, tool_input, tool_output):
    """追加到 observation 日志"""
    try:
        # 提取关键信息（不记录大输出）
        input_summary = _summarize_input(tool_name, tool_input)
        output_summary = _summarize_output(tool_name, tool_output)
        
        entry = {
            'ts': datetime.now().isoformat(),
            'tool': tool_name,
            'input': input_summary,
            'output_summary': output_summary,
            'success': tool_output.get('success', True) if isinstance(tool_output, dict) else True
        }
        
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        pass  # fail-silent

def _summarize_input(tool_name, inp):
    """提取关键输入信息，忽略大文本"""
    if not isinstance(inp, dict):
        return str(inp)[:100]
    
    # 按工具类型提取关键字段
    summaries = {
        'exec': lambda: inp.get('cmd', '')[:100] if isinstance(inp.get('cmd'), str) else str(inp)[:100],
        'read': lambda: inp.get('path', '') or inp.get('file_path', ''),
        'write': lambda: inp.get('path', '') or inp.get('file_path', ''),
        'edit': lambda: inp.get('path', '') or inp.get('file_path', ''),
        'web_fetch': lambda: inp.get('url', ''),
        'browser': lambda: inp.get('action', '') + ' ' + (inp.get('url', '') or inp.get('targetUrl', '') or ''),
        'message': lambda: inp.get('action', '') + ' → ' + (inp.get('target', '') or ''),
    }
    
    fn = summaries.get(tool_name, lambda: str(inp)[:80])
    try:
        return fn()
    except:
        return str(inp)[:80]

def _summarize_output(tool_name, out):
    """提取关键输出信息"""
    if not isinstance(out, dict):
        s = str(out)
        return s[:100] + ('...' if len(s) > 100 else '')
    
    # 关注输出中的关键信息
    if tool_name == 'exec':
        return out.get('stdout', '')[:80] or out.get('stderr', '')[:80] or 'ok'
    if tool_name in ('read', 'web_fetch'):
        text = out.get('text', out.get('content', ''))
        return text[:80] if text else 'ok'
    if tool_name == 'message':
        return out.get('result', out.get('status', 'ok'))[:50]
    
    return 'ok'

# 主流程
if __name__ == '__main__':
    tool_name = os.environ.get('TOOL_NAME', '')
    tool_input_raw = os.environ.get('TOOL_INPUT', '{}')
    tool_output_raw = os.environ.get('TOOL_OUTPUT', '{}')
    
    try:
        tool_input = json.loads(tool_input_raw)
        tool_output = json.loads(tool_output_raw)
    except:
        tool_input = {}
        tool_output = {}
    
    log_observation(tool_name, tool_input, tool_output)
    
    # 始终返回 allow，不阻断任何操作
    print('allow')
