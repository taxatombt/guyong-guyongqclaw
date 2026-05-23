#!/usr/bin/env python3
"""
模拟 qclaw-text-file 技能的 write_file.py 脚本
实现跨平台文本文件写入，自动处理编码、BOM、换行符
"""

import argparse
import os
import sys

def write_file(path, content, platform=None):
    """
    写入文本文件，自动处理编码、BOM、换行符
    :param path: 文件路径
    :param content: 文件内容
    :param platform: 目标平台（windows/mac/linux，默认自动检测）
    """
    # 自动检测平台
    if platform is None:
        platform = sys.platform
    
    # 根据平台和文件类型确定编码和 BOM
    ext = os.path.splitext(path)[1].lower()
    
    # 默认编码：utf-8（无 BOM）
    encoding = "utf-8"
    bom = False
    
    # Windows 下特定文件类型需要 BOM 或 GBK 编码
    if platform == "win32":
        if ext in [".csv", ".bat", ".cmd", ".ps1"]:
            # CSV 文件需要 UTF-8 BOM（Windows Excel 兼容）
            encoding = "utf-8-sig"
            bom = True
        elif ext in [".txt", ".md", ".json", ".yaml", ".yml"]:
            # 文本文件默认 UTF-8 无 BOM
            encoding = "utf-8"
            bom = False
    else:
        # 非 Windows 平台默认 UTF-8 无 BOM
        encoding = "utf-8"
        bom = False
    
    # 处理换行符：Windows 用 CRLF，其他用 LF
    if platform == "win32":
        newline = "\r\n"
    else:
        newline = "\n"
    
    # 写入文件
    with open(path, "w", encoding=encoding, newline="") as f:
        # 如果需要 BOM（如 UTF-8 BOM），先写入 BOM
        if bom and encoding == "utf-8-sig":
            f.write("\ufeff")
        
        # 替换换行符
        content = content.replace("\r\n", newline).replace("\n", newline)
        f.write(content)
    
    print(f"成功写入文件: {path} (编码: {encoding}, 换行符: {repr(newline)})")

def main():
    parser = argparse.ArgumentParser(description="跨平台文本文件写入工具（模拟 qclaw-text-file 技能）")
    parser.add_argument("--path", required=True, help="文件路径")
    parser.add_argument("--content", required=True, help="文件内容")
    parser.add_argument("--platform", help="目标平台（windows/mac/linux，默认自动检测）")
    
    args = parser.parse_args()
    
    write_file(args.path, args.content, args.platform)

if __name__ == "__main__":
    main()