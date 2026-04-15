"""
融合系统：extract-design + Evolver + 十维判断
用法：python fusion.py <URL>
"""
import sys
import os
import json

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def analyze_url_complexity(url):
    """十维判断：URL 复杂度分析"""
    complexity_indicators = 0
    
    # 检测复杂特征
    if 'github' in url: complexity_indicators += 1
    if 'anthropic' in url: complexity_indicators += 1
    if 'vercel' in url: complexity_indicators += 1
    if 'stripe' in url: complexity_indicators += 1
    
    # 默认中等复杂度
    if complexity_indicators >= 2:
        return {'level': 'high', 'strategy': 'deep', 'timeout': 30}
    else:
        return {'level': 'medium', 'strategy': 'standard', 'timeout': 15}

def main():
    if len(sys.argv) < 2:
        print("用法: python fusion.py <URL> [输出名]")
        print("示例: python fusion.py https://anthropic.com anthropic")
        sys.exit(1)
    
    url = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"=== 融会贯通系统 ===")
    print(f"URL: {url}")
    
    # 步骤1：十维判断 - 复杂度分析
    print(f"\n[1] 十维判断：复杂度分析...")
    complexity = analyze_url_complexity(url)
    print(f"    复杂度: {complexity['level']}")
    print(f"    策略: {complexity['strategy']}")
    print(f"    超时: {complexity['timeout']}秒")
    
    # 步骤2：调用 extract-design.py
    print(f"\n[2] 执行：extract-design...")
    if output_name:
        cmd = f'python "{os.path.dirname(os.path.abspath(__file__))}/extract-design.py" {url} {output_name}'
    else:
        cmd = f'python "{os.path.dirname(os.path.abspath(__file__))}/extract-design.py" {url}'
    
    result = os.system(cmd)
    
    # 步骤3：记录到 Evolver（模拟）
    print(f"\n[3] 进化：记录经验...")
    record = {
        'task': f'extract-design: {url}',
        'method': f'strategy={complexity["strategy"]}',
        'success': result == 0,
        'complexity': complexity['level']
    }
    print(f"    记录: {json.dumps(record, ensure_ascii=False)}")
    
    print(f"\n=== 完成 ===")
    print(f"输出文件: {output_name or '自动生成'}")
    print(f"复杂度: {complexity['level']} | 策略: {complexity['strategy']}")

if __name__ == '__main__':
    main()