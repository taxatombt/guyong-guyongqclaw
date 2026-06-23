#!/usr/bin/env python3
"""R29 简化审查：检查 compute_adx/compute_ema 问题"""
import sys

fp = r'E:\lianghua\trend_trader.py'

print("=" * 60)
print("R29 审查：UnboundLocalError 修复验证")
print("=" * 60)

# 读取文件
try:
    with open(fp, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 自动处理 BOM
        lines = f.readlines()
    print("✅ 文件读取成功（已处理 BOM）")
except Exception as e:
    print("❌ 文件读取失败：%s" % e)
    sys.exit(1)

# 检查1：compute_adx 是否在 trading_loop 内被导入
print("\n[检查1] compute_adx 是否在 trading_loop 内被导入...")
bad_lines = []
for i, line in enumerate(lines, 1):
    if 'from indicators import' in line and 'compute_adx' in line:
        bad_lines.append((i, line.strip()))

if bad_lines:
    print("❌ 发现 %d 处错误导入：" % len(bad_lines))
    for ln, line in bad_lines:
        print("  L%d: %s" % (ln, line[:80]))
else:
    print("✅ 未发现 compute_adx 的错误导入")

# 检查2：compute_ema 是否在 trading_loop 内被导入
print("\n[检查2] compute_ema 是否在 trading_loop 内被导入...")
bad_ema = []
for i, line in enumerate(lines, 1):
    if 'from indicators import' in line and 'compute_ema' in line:
        bad_ema.append((i, line.strip()))

if bad_ema:
    print("⚠️ 发现 %d 处 compute_ema 导入：" % len(bad_ema))
    for ln, line in bad_ema:
        print("  L%d: %s" % (ln, line[:80]))
    print("\n建议：检查这些导入是否在 trading_loop() 内部")
else:
    print("✅ 未发现 compute_ema 的错误导入")

# 检查3：验证函数定义是否存在
print("\n[检查3] 验证函数定义...")
def check_def(func_name):
    for i, line in enumerate(lines, 1):
        if ('def %s(' % func_name) in line:
            return i
    return None

for func in ['compute_adx', 'compute_ema']:
    ln = check_def(func)
    if ln:
        print("✅ %s 定义在 L%d: %s" % (func, ln, lines[ln-1].strip()[:60]))
    else:
        print("❌ 未找到 %s 定义" % func)

# 检查4：尝试编译语法
print("\n[检查4] 验证文件语法...")
try:
    with open(fp, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    compile(content, fp, 'exec')
    print("✅ 语法正确")
except SyntaxError as e:
    print("❌ 语法错误：%s (L%d)" % (e.msg, e.lineno))
except Exception as e:
    print("❌ 检查失败：%s" % e)

print("\n" + "=" * 60)
print("审查完成")
print("=" * 60)
