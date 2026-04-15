# -*- coding: utf-8 -*-
"""
qclaw_display.py — Hermes KawaiiSpinner + MoodOutput qclaw 集成层
来源：hermes_study/display/emotion_display.py
用途：给 hooks/ evolver/ 等系统提供心情化 UI 反馈

用法：
  from qclaw_display import spin, MoodOutput, ThinkingVerb
  with spin('处理中...'):
      do_work()
  
  m = MoodOutput()
  m.success('完成！')
  m.thinking('正在分析...')
  m.block('报告')
      print('...')
  m.block_end()
"""
import sys, os
from pathlib import Path

# 优先从 hermes_study 加载，fallback 到内联
HERMES_DISPLAY = Path(__file__).parent / 'hermes_study' / 'display' / 'emotion_display.py'
try:
    if HERMES_DISPLAY.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location('emotion_display', HERMES_DISPLAY)
        mod = importlib.util.module_from_spec(spec)
        sys.modules['emotion_display'] = mod
        spec.loader.exec_module(mod)
        _em = mod
    else:
        raise FileNotFoundError()
except Exception:
    _em = None

# === 重新导出 ===
if _em:
    KawaiiSpinner = _em.KawaiiSpinner
    SkinAwareColors = _em.SkinAwareColors
    KawaiiFaces = _em.KawaiiFaces
    MoodOutput = _em.MoodOutput
    FileSnapshot = _em.FileSnapshot
    ThinkingVerb = getattr(_em, 'ThinkingVerb', None)
    spin = _em.spin
else:
    # Fallback：空桩
    KawaiiSpinner = SkinAwareColors = KawaiiFaces = MoodOutput = FileSnapshot = object
    ThinkingVerb = None
    def spin(*a, **kw): import contextlib; return contextlib.nullcontext()


# === qclaw 专用快捷函数 ===
def thinking_verb() -> str:
    """随机思考动词（用于日志前缀）"""
    verbs = ['分析', '推理', '计算', '检索', '规划', '评估', '比对', '推理中']
    import random
    return random.choice(verbs)


def kawaii_spin(message: str = '', spinner_type: str = 'dots'):
    """启动心情动画（返回上下文管理器）"""
    if _em:
        return _em.spin(message, spinner_type)
    import contextlib
    return contextlib.nullcontext()


# === 集成到 evolver 风格的日志 ===
def evolver_log(action: str, mood: str = 'working', detail: str = '') -> None:
    """给 evolver/hooks 用的带心情的日志"""
    colors = SkinAwareColors()
    faces = KawaiiFaces()
    face = faces.random(mood)
    msg = f'{face} {action}'
    if detail:
        msg += f' {colors.muted(detail)}'
    print(msg)


def hook_log(hook_name: str, event: str, mood: str = 'working') -> None:
    """给 hooks 用的心情化日志"""
    evolver_log(f'[{hook_name}] {event}', mood)


# === 快捷使用 ===
__all__ = [
    'KawaiiSpinner', 'SkinAwareColors', 'KawaiiFaces', 'MoodOutput',
    'FileSnapshot', 'ThinkingVerb', 'spin', 'kawaii_spin',
    'thinking_verb', 'evolver_log', 'hook_log',
]
