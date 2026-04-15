# emotion_display.py
# 顾庸 · 心情符号表情系统 v1.0
# 灵感来源: Hermes agent/display.py (NousResearch)
# 整合: KawaiiSpinner + 心情表情 + 皮肤系统

import sys
import time
import threading
import os


# ─────────────────────────────────────────
# 皮肤配色系统（适配亮/暗终端）
# ─────────────────────────────────────────
class SkinAwareColors:

    """根据终端/皮肤自动适配颜色"""

    LIGHT = {
        'primary':   '\033[38;5;208m',   # 琥珀橙
        'secondary': '\033[38;5;75m',    # 天蓝
        'accent':    '\033[38;5;141m',   # 紫
        'success':  '\033[38;5;71m',    # 绿色
        'error':    '\033[38;5;196m',   # 红色
        'muted':    '\033[38;5;245m',   # 灰色
        'reset':    '\033[0m',
    }

    DARK = {
        'primary':   '\033[38;5;208m',
        'secondary': '\033[38;5;75m',
        'accent':    '\033[38;5;141m',
        'success':  '\033[38;5;114m',
        'error':    '\033[38;5;203m',
        'muted':    '\033[38;5;241m',
        'reset':    '\033[0m',
    }

    def __init__(self, skin=None):
        if skin:
            self.c = self.LIGHT if skin == 'light' else self.DARK
        else:
            if os.name == 'nt':
                self.c = self.DARK
            else:
                term = os.environ.get('TERM', '')
                self.c = self.DARK if 'dark' in term else self.LIGHT

    def color(self, key, text):
        return "{}{}{}".format(self.c.get(key, ''), text, self.c['reset'])

    def primary(self, text):   return self.color('primary', text)
    def secondary(self, text): return self.color('secondary', text)
    def accent(self, text):    return self.color('accent', text)
    def success(self, text):   return self.color('success', text)
    def error(self, text):     return self.color('error', text)
    def muted(self, text):     return self.color('muted', text)

    def supports_color(self):
        return sys.stdout.isatty() or (
            'TERM' in os.environ and 'xterm' in os.environ.get('TERM', '')
        )


# ─────────────────────────────────────────
# 心情表情库（从 Hermes 移植并扩充）
# ─────────────────────────────────────────
class KawaiiFaces:

    """心情符号表情集合"""

    WAITING = [
        '(.\u203f\u203f\u25d5\u203f\u25d5.)', '(*^^*)', '(\u25d5\u203f\u203f\u25d5)', '(.\u2661\u203f\u2661.)', '(*^_\u2212^*)',
        '(\u25e0\u203f\u203f\u25e0)', '(\u2267\u25d5\u2266)', '(★\u203f★)', '(\u25d4\u203f\u203f\u25d4)', '(\u2312\u203f\u203f\u2312)',
    ]

    THINKING = [
        '(-_-?)', '(._. )', '( -_-)', '(=_\u2015=)',
        '(*_*)', '(?_\u203f?)', '(o_o)', '(-\u03c9-)',
        '(=\u2060^.\u2060^=\u2060)',
    ]

    WORKING = [
        '(\u84ee \u2022\u30ce\u2022\u30ce)\u30ee', '(\u2500\u25e3\u203f\u25e3)\u2500', '(\u3065\u2265\u25d5\u2264)\u3064', '(\u2265\u25d5\u2264)/',
        '(\u2605\u2265\u25d5\u2264)\u2605', '(\u84ee \u2022\u03c9\u2022\u30ce)\u30ee',
    ]

    SUCCESS = [
        '( \u25d1\u25d1)', '(★^O^★)', '(\u2312\u25d5\u2312)\u2606', '( \u203f\u03c9`)',
        '( \u2265\u25d5\u2264 )/', '(*^_\u2212^*)\uff01',
    ]

    WORRIED = [
        '(\uff89\u203f\u03c9`)\uff89', '(\u00b0_\u00b0\uff89)', '( \u00ac_\u00ac)', '( \'_\')',
    ]

    RESTING = [
        '(=_\u2015=)', '(\uff0d\u03c9\u2015\uff0d) zzZ', '(\u2312_\u2312)',
    ]

    @classmethod
    def random(cls, mood='waiting'):
        import random
        moods = {
            'waiting': cls.WAITING,
            'thinking': cls.THINKING,
            'working': cls.WORKING,
            'success': cls.SUCCESS,
            'worried': cls.WORRIED,
            'resting': cls.RESTING,
        }
        arr = moods.get(mood, cls.WAITING)
        return random.choice(arr)


# ─────────────────────────────────────────
# 思考动词库
# ─────────────────────────────────────────
THINKING_VERBS = [
    '思考中', '分析中', '检索中', '学习中',
    '推理中', '搜索中', '整理中', '整理记忆',
    '规划中', '评估中', '计划中', '回忆中',
    '研究中', '沉淀中', '构建中', '深化中',
    '诊断中', '学习中',
]


# ─────────────────────────────────────────
# 动画帧库（Hermes灵感：9种动画）
# ─────────────────────────────────────────
class SpinnerFrames:

    SPARKLES = ['\u2726', '\u2727', '⋆', '\u2727', '\u2726', '⋆', '\u2727', '\u2726']
    DOTS     = ['\u094b', '\u0949', '\u0979', '\u0978', '\u097c', '\u0974', '\u0972', '\u0967', '\u0947', '\u094f']
    BOUNCE   = ['○', '◡', '●', '◡', '○', '◡', '●', '◡']
    GROW     = ['\u258f', '\u258e', '\u258d', '\u258c', '\u038b', '\u2549', '\u2589', '\u2589', '\u2549', '\u2549']
    ARROWS   = ['\u2190', '\u2196', '\u2191', '\u2197', '\u2192', '\u2198', '\u2193', '\u2199']
    STAR     = ['\u2736', '\u2737', '\u2738', '\u2739', '\u2738', '\u2737', '\u2736', '\u2738']
    MOON     = ['\u263e', '\u2742', '\u2600', '\u2742', '\u263e', '\u2742', '\u2600', '\u2742']
    PULSE    = ['\u25cf', '○', '\u25ce', '\u25cf', '\u25cc', '\u25ce', '○', '\u25cf']
    BRAIN    = ['\u25d0', '\u25d3', '\u25d1', '\u25d2', '\u25d0', '\u25d3', '\u25d1', '\u25d2']

    ALL = {
        'sparkles': SPARKLES,
        'dots':     DOTS,
        'bounce':   BOUNCE,
        'grow':     GROW,
        'arrows':   ARROWS,
        'star':     STAR,
        'moon':     MOON,
        'pulse':    PULSE,
        'brain':    BRAIN,
    }


# ─────────────────────────────────────────
# KawaiiSpinner（核心类）
# ─────────────────────────────────────────
class KawaiiSpinner:

    """
    Hermes 进度条系统 Python 版。
    Thread-based 动画，\\r 行覆写，非 TTY 自动降级。
    """

    DEFAULT_INTERVAL = 0.12

    def __init__(self, message='', spinner_type='dots', interval=None, skin=None):
        self.message = message
        self.spinner_type = spinner_type
        self.interval = interval or self.DEFAULT_INTERVAL
        self.skin = SkinAwareColors(skin=skin)
        self.frames = SpinnerFrames.ALL.get(spinner_type, SpinnerFrames.DOTS)
        self._running = False
        self._thread = None
        self._isatty = sys.stdout.isatty()

    def _clear_line(self):
        if self._isatty:
            try:
                sys.stdout.write('\r\033[K')
                sys.stdout.flush()
            except Exception:
                pass
        else:
            sys.stdout.write('\n')

    def _write(self, text):
        if self._isatty:
            try:
                sys.stdout.write('\r{}'.format(text))
                sys.stdout.flush()
            except Exception:
                sys.stdout.write('{}\n'.format(text))
        else:
            sys.stdout.write('{}\n'.format(text))

    def _spin_loop(self):
        frame_idx = 0
        verb_idx = 0
        while self._running:
            frame = self.frames[frame_idx % len(self.frames)]
            verb_idx = (verb_idx + 1) % len(THINKING_VERBS)
            verb = THINKING_VERBS[verb_idx] if frame_idx % 3 == 0 else ''

            if self.skin.supports_color():
                line = "  {} {} {}  {}".format(
                    self.skin.primary(frame), self.message, verb, self.skin.muted('...'))
            else:
                line = "  {} {} {}  ...".format(frame, self.message, verb)

            self._write(line)

            end_time = time.time() + self.interval
            while time.time() < end_time and self._running:
                time.sleep(0.01)
            frame_idx += 1

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._thread.start()
        return self

    def update(self, message=None, spinner_type=None):
        if message is not None:
            self.message = message
        if spinner_type and spinner_type != self.spinner_type:
            self.spinner_type = spinner_type
            self.frames = SpinnerFrames.ALL.get(spinner_type, SpinnerFrames.DOTS)

    def update_message(self, message):
        self.message = message

    def stop(self, final_message=None, mood='success'):
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass
        self._clear_line()

        if final_message:
            face = KawaiiFaces.random(mood)
            if self.skin.supports_color():
                if mood == 'success':
                    line = "{} {} {}".format(self.skin.success('\u2713'), self.skin.primary(final_message), face)
                elif mood == 'error':
                    line = "{} {}".format(self.skin.error('\u2717'), final_message)
                else:
                    line = "{} {}".format(self.skin.primary(final_message), face)
            else:
                line = "[OK] {} {}".format(final_message, face)
            self._write(line)

        return self


# ─────────────────────────────────────────
# 上下文管理器
# ─────────────────────────────────────────
def spin(message='', spinner_type='dots', mood='success', skin=None):
    """上下文管理器: with spin('分析中'): ..."""
    return _SpinContext(message, spinner_type, mood, skin)


class _SpinContext:

    def __init__(self, message, spinner_type, mood, skin):
        self.message = message
        self.spinner_type = spinner_type
        self.mood = mood
        self.skin = skin
        self.spinner = None

    def __enter__(self):
        self.spinner = KawaiiSpinner(self.message, self.spinner_type, skin=self.skin)
        self.spinner.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.spinner:
            if exc_type:
                self.spinner.stop('失败: {}'.format(exc_val), mood='worried')
            else:
                self.spinner.stop(self.message, mood=self.mood)
        return False

    def update(self, msg):
        if self.spinner:
            self.spinner.update_message(msg)


# ─────────────────────────────────────────
# 快捷函数
# ─────────────────────────────────────────
_spinner_global = None


def spin_start(message='', spinner_type='dots'):
    global _spinner_global
    _spinner_global = KawaiiSpinner(message, spinner_type)
    _spinner_global.start()
    return _spinner_global


def spin_update(message):
    if _spinner_global:
        _spinner_global.update_message(message)


def spin_stop(final_message='', mood='success'):
    global _spinner_global
    if _spinner_global:
        _spinner_global.stop(final_message, mood)
        _spinner_global = None


# ─────────────────────────────────────────
# FileSnapshot（Hermes灵感: LocalEditSnapshot）
# ─────────────────────────────────────────
class FileSnapshot:

    """
    写操作前自动快照，支持 unified_diff 预览。
    用法:

        snap = FileSnapshot.backup('file.txt')
        ... 修改文件 ...
        print(snap.diff(new_content))  # 预览
        snap.restore()  # 回滚
    """

    _cache = {}

    @classmethod
    def backup(cls, path):
        import pathlib
        p = pathlib.Path(path)
        content = p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''
        cls._cache[str(p.absolute())] = content
        return cls(str(p.absolute()))

    def __init__(self, snap_key):
        self.key = snap_key

    def diff(self, new_content=None):
        import difflib
        old = self._cache.get(self.key, '')
        new = new_content if new_content is not None else self._get_current()
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, lineterm='')
        return ''.join(diff)

    def preview(self, new_content, skin=None):
        s = SkinAwareColors(skin=skin)
        diff_lines = self.diff(new_content).splitlines()
        result = []
        for line in diff_lines[:60]:
            if line.startswith('+') and not line.startswith('+++'):
                result.append(s.success(line))
            elif line.startswith('-') and not line.startswith('---'):
                result.append(s.error(line))
            elif line.startswith('@@'):
                result.append(s.accent(line))
            else:
                result.append(line)
        return '\n'.join(result)

    def restore(self):
        import pathlib
        p = pathlib.Path(self.key)
        p.write_text(self._cache.get(self.key, ''), encoding='utf-8')

    def _get_current(self):
        import pathlib
        p = pathlib.Path(self.key)
        return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''

    def discard(self):
        self._cache.pop(self.key, None)


# ─────────────────────────────────────────
# MoodOutput（心情化输出）
# ─────────────────────────────────────────
class MoodOutput:

    """心情化输出系统。"""

    def __init__(self, skin=None, use_emoji=True):
        self.skin = SkinAwareColors(skin=skin)
        self.use_emoji = use_emoji
        self._indent = ''

    def _face(self, mood):
        return KawaiiFaces.random(mood) if self.use_emoji else ''

    def say(self, message, mood='waiting', indent=None, prefix=None):
        face = self._face(mood)
        ind = indent if indent is not None else self._indent
        labels = {
            'thinking': self.skin.secondary('[思考]'),
            'success':   self.skin.success('[完成]'),
            'error':     self.skin.error('[错误]'),
            'working':   self.skin.primary('[进行]'),
            'waiting':   self.skin.muted('[等待]'),
            'worried':   self.skin.error('[疑问]'),
            'resting':   self.skin.muted('[休息]'),
        }
        label = labels.get(mood, labels['waiting'])
        prefix_str = "{} ".format(prefix) if prefix else "{} ".format(label)
        msg = "{}{}{}".format(ind, prefix_str, message)
        print(msg)
        return self

    def thinking(self, msg, **kw): return self.say(msg, mood='thinking', **kw)
    def success(self, msg, **kw): return self.say(msg, mood='success', **kw)
    def error(self, msg, **kw): return self.say(msg, mood='error', **kw)
    def working(self, msg, **kw): return self.say(msg, mood='working', **kw)
    def waiting(self, msg, **kw): return self.say(msg, mood='waiting', **kw)
    def worried(self, msg, **kw): return self.say(msg, mood='worried', **kw)

    def block(self, title, mood='thinking'):
        """开始信息块"""
        face = self._face(mood)
        bar = self.skin.accent('\u2500' * 40)
        print("\n{}".format(bar))
        print("{} {}".format(self.skin.primary('\u250c'), self.skin.accent(title)))
        print("{}".format(bar))
        self._indent = '\u2502 '
        return self

    def block_end(self):
        """结束信息块"""
        self._indent = ''
        print("{}\n".format(self.skin.accent('\u2500' * 40)))


# ─────────────────────────────────────────
# 导出
# ─────────────────────────────────────────
__all__ = [
    'KawaiiSpinner', 'KawaiiFaces', 'SkinAwareColors',
    'THINKING_VERBS', 'SpinnerFrames',
    'spin', 'spin_start', 'spin_update', 'spin_stop',
    'FileSnapshot', 'MoodOutput',
]


if __name__ == '__main__':
    print('=== 心情表情系统演示 ===\n')

    skin = SkinAwareColors()
    out = MoodOutput(skin=skin)

    out.thinking('\u6b63\u5728\u68c0\u7d22\u8bb0\u5fc6...')
    time.sleep(0.4)
    out.working('\u5206\u6790\u4e0a\u4e0b\u6587...')
    time.sleep(0.4)
    out.success('\u627e\u52303\u6761\u76f8\u5173\u7ecf\u9a8c')
    time.sleep(0.3)

    out.block('Hermes \u6e90\u7801\u5206\u6790\u7ed3\u679c', mood='thinking')
    out.thinking('\u53d1\u73b0\u8fdb\u5ea6\u6761\u7cfb\u7edf: KawaiiSpinner (9\u79cd\u52a8\u753b)')
    out.working('\u53d1\u73b0\u81ea\u6211\u8fdb\u5316\u673a\u5236: skill_manage \u5de5\u5177\u63cf\u8ff0')
    out.success('\u843d\u5730\u8def\u5f84: \u5fc3\u60c5\u8868\u60c5 -> \u8fdb\u5ea6\u6761 -> \u76ae\u80a4\u7cfb\u7edf')
    out.block_end()

    print('=== KawaiiSpinner \u6f14\u793a ===\n')
    s = KawaiiSpinner('\u5b66\u4e60 Hermes', spinner_type='dots')
    s.start()
    time.sleep(2.0)
    s.update('\u5206\u6790 display.py')
    time.sleep(1.5)
    s.stop('\u627e\u5230\u5fc3\u60c5\u7b26\u53f7\u8868\u60c5\u7cfb\u7edf\uff01', mood='success')

    print('\n=== \u5fc3\u60c5\u8868\u60c5\u5e93 ===\n')
    for mood in ['waiting', 'thinking', 'working', 'success', 'worried', 'resting']:
        face = KawaiiFaces.random(mood)
        print("  {:10s}: {}".format(mood, face))
