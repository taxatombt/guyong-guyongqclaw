import urllib.request, json, base64, os

dst = r'C:\Users\yiseg\.qclaw\workspace\_claude_howto'
os.makedirs(dst, exist_ok=True)

def fetch_gh(path):
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/luongnv89/claude-howto/contents/{path}',
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'error': str(e)}

def fetch_file(path, save_name):
    data = fetch_gh(path)
    if isinstance(data, dict) and data.get('encoding') == 'base64':
        content = base64.b64decode(data['content']).decode('utf-8', errors='ignore')
        save_path = os.path.join(dst, save_name)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return len(content)
    return 0

# CLAUDE.md 入口
l = fetch_file('CLAUDE.md', 'CLAUDE_entry.md')
print(f'CLAUDE.md: {l} chars')

# 中文目录
zh = fetch_gh('zh')
if isinstance(zh, list):
    print('=== ZH files ===')
    for f in zh[:20]:
        print(f"  {f['name']} ({f['type']})")
    
    # 抓中文README
    for zhf in zh[:5]:
        if zhf['type'] == 'file' and zhf['name'].endswith('.md'):
            l = fetch_file(f"zh/{zhf['name']}", f"zh_{zhf['name']}")
            print(f"zh/{zhf['name']}: {l} chars")

# prompts 目录
prompts = fetch_gh('prompts')
if isinstance(prompts, list):
    print('=== prompts files ===')
    for f in prompts[:15]:
        print(f"  {f['name']} ({f['type']})")
        if f['type'] == 'file' and f['name'].endswith('.md'):
            l = fetch_file(f"prompts/{f['name']}", f"prompts_{f['name']}")
            print(f"  -> {l} chars")

print('\nDone!')
