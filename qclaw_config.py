"""
qclaw_config.py — Poor Man's Configurator (Karpathy nanoGPT pattern)

来源: karpathy/nanoGPT/configurator.py
核心思路: exec(config_file) 直接在调用者的globals()里覆盖变量
          命令行 --key=value 用 literal_eval 自动类型推断

用法:
    # 在任何脚本顶部:
    from qclaw_config import load_config
    load_config()  # 自动从 ~/.qclaw/config.py 或环境变量加载

    # 或手动:
    exec(open('qclaw_config.py').read())  # Karpathy原版风格

    # 命令行覆盖:
    python my_script.py --model=gpt-4 --temperature=0.7
"""

import os
import sys
from ast import literal_eval


DEFAULT_CONFIG_PATH = os.path.expanduser("~/.qclaw/config.py")


def _parse_overrides(args=None):
    """Parse --key=value overrides from command line.
    
    Karpathy pattern: sys.argv中带=的参数视为配置覆盖，
    用literal_eval自动推断类型（bool/int/float/str）。
    """
    if args is None:
        args = sys.argv[1:]
    
    overrides = {}
    for arg in args:
        if '=' in arg:
            key, val = arg.split('=', 1)
            key = key.lstrip('-')  # --key=value → key
            try:
                overrides[key] = literal_eval(val)
            except (ValueError, SyntaxError):
                overrides[key] = val  # fallback: treat as string
    return overrides


def load_config(config_path=None, globals_dict=None):
    """Load configuration from file + command line overrides.
    
    Karpathy's configurator.py pattern:
    1. If config file exists, exec() it in caller's globals
    2. If command line has --key=value, override those globals
    
    This means:
    - Default values are set in the calling script
    - Config file can override any of them
    - Command line can override config file
    - Priority: defaults < config_file < CLI_overrides
    
    Args:
        config_path: Path to config file (default: ~/.qclaw/config.py)
        globals_dict: Globals dict to update (default: caller's globals)
    
    Returns:
        dict of applied overrides
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    
    if globals_dict is None:
        import inspect
        # Get caller's globals (frame 1 = caller, frame 0 = this function)
        frame = inspect.currentframe().f_back
        globals_dict = frame.f_globals
    
    applied = {}
    
    # Step 1: Load config file (if exists)
    if os.path.exists(config_path):
        with open(config_path, encoding='utf-8') as f:
            config_code = f.read()
        # exec in caller's namespace — Karpathy's key insight:
        # no JSON parsing, no YAML, just Python code
        exec(config_code, globals_dict)
        applied['_config_file'] = config_path
    
    # Step 2: Command line overrides
    overrides = _parse_overrides()
    for key, val in overrides.items():
        globals_dict[key] = val
        applied[key] = val
    
    return applied


# === Karpathy原版exec风格（直接在调用者globals()里执行）===
# 用法：在脚本顶部加一行
#   exec(open(os.path.expanduser("~/.qclaw/config.py")).read())
# 然后命令行 --key=value 覆盖：
#   for arg in sys.argv[1:]:
#       if '=' in arg:
#           k, v = arg.split('=', 1); k = k.lstrip('-')
#           try: exec(f"{k} = {literal_eval(v)!r}")
#           except: exec(f"{k} = {v!r}")


if __name__ == "__main__":
    # Demo: show what config would be loaded
    print(f"Config path: {DEFAULT_CONFIG_PATH}")
    print(f"Exists: {os.path.exists(DEFAULT_CONFIG_PATH)}")
    
    # Demo override parsing
    test_args = ["--model=gpt-4", "--temperature=0.7", "--debug=True"]
    overrides = _parse_overrides(test_args)
    print(f"Parsed overrides: {overrides}")
    print(f"  model type: {type(overrides['model'])}")  # str
    print(f"  temperature type: {type(overrides['temperature'])}")  # float
    print(f"  debug type: {type(overrides['debug'])}")  # bool
