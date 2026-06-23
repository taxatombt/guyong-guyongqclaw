#!/usr/bin/env python3
"""修复 UnboundLocalError: compute_adx"""
import sys

fp = r'E:\lianghua\trend_trader.py'
with open(fp, 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixed = 0
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # 匹配 L1642 和 L1747 附近的 import 行
    if 'from indicators import' in line and 'compute_adx' in line:
        # 去掉 , compute_adx
        new_line = line.replace(', compute_adx', '')
        print(f'L{i+1}: {line.rstrip()[:80]}')
        print(f'  → {new_line.rstrip()[:80]}')
        new_lines.append(new_line)
        fixed += 1
    else:
        new_lines.append(line)
    i += 1

if fixed == 0:
    print('未找到需要修复的行')
    sys.exit(1)

with open(fp, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'\n✅ 修复完成，共 {fixed} 处')
print('现在可以重新运行 trend_trader.py 了')
