#!/usr/bin/env python3
"""
extract-design.py — 从网站自动提取设计 token，输出 DESIGN.md 格式
用法: python extract-design.py <url> [output.md]
"""

import re
import sys
import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from urllib.parse import urljoin


def extract_colors(soup, url):
    """提取颜色：hex, rgb, rgba, hsl"""
    colors = []
    seen = set()
    
    # 1. 从 CSS 内联样式
    for style in soup.find_all(style=True):
        css_text = style.get('style', '')
        found = re.findall(r'(?:color|background|background-color|border-color|fill|stroke)[\s:]*([#\d]+[\da-fA-F]{3,8}|rgb\([^)]+\)|rgba\([^)]+\)|hsl\([^)]+\))', css_text)
        for c in found:
            if c.lower() not in seen:
                seen.add(c.lower())
                colors.append({'raw': c, 'source': 'inline style'})
    
    # 2. 从 <link> CSS 文件（最多抓 3 个）
    css_links = soup.find_all('link', href=re.compile(r'\.css'))
    for link in css_links[:3]:
        css_url = urljoin(url, link.get('href', ''))
        try:
            r = requests.get(css_url, timeout=5)
            if r.status_code == 200:
                found = re.findall(r'#[0-9a-fA-F]{3,8}|rgb\([^)]+\)|rgba\([^)]+\)|hsl\([^)]+\)', r.text)
                for c in found:
                    if c.lower() not in seen:
                        seen.add(c.lower())
                        colors.append({'raw': c, 'source': css_url.split('/')[-1]})
        except:
            pass
    
    # 3. 从 <meta theme-color>
    meta_color = soup.find('meta', attrs={'name': re.compile(r'color|theme')})
    if meta_color and meta_color.get('content'):
        c = meta_color.get('content')
        if c.lower() not in seen:
            seen.add(c.lower())
            colors.append({'raw': c, 'source': 'meta theme-color'})
    
    # 4. 从 manifest.json
    manifest = soup.find('link', href=re.compile(r'manifest'))
    if manifest:
        try:
            r = requests.get(urljoin(url, manifest['href']), timeout=5)
            if r.status_code == 200:
                import json
                m = json.loads(r.text)
                for key in ['theme_color', 'background_color', 'primary_color']:
                    if key in m and m[key]:
                        c = m[key]
                        if c.lower() not in seen:
                            seen.add(c.lower())
                            colors.append({'raw': c, 'source': f'manifest.{key}'})
        except:
            pass
    
    return colors[:50]


def extract_fonts(soup):
    """提取字体"""
    fonts = []
    seen = set()
    
    # 1. 从 Google Fonts link
    for link in soup.find_all('link', href=re.compile(r'fonts\.(googleapis|gstatic)')):
        href = link.get('href', '')
        found = re.findall(r'family=([^&:]+)', href)
        for f in found:
            f_clean = f.replace('+', ' ')
            if f_clean not in seen:
                seen.add(f_clean)
                fonts.append({'family': f_clean, 'source': 'Google Fonts'})
    
    # 2. 从 CSS font-family
    for elem in soup.find_all(style=True):
        ff = re.findall(r'font-family[\s:]*([^;]+)', elem.get('style', ''))
        for f in ff:
            families = re.findall(r'["\']?([^"\',;]+)["\']?', f)
            for fam in families[:2]:  # 只取前两个
                if fam.strip() and fam.lower() not in seen:
                    seen.add(fam.lower())
                    fonts.append({'family': fam.strip(), 'source': 'inline style'})
    
    return fonts[:10]


def hex_to_name(hex_color):
    """简单颜色命名"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c*2 for c in hex_color])
    
    if len(hex_color) < 6:
        return "unknown"
    
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    except ValueError:
        return "unknown"
    
    brightness = (r*299 + g*587 + b*114) / 1000
    saturation = max(r,g,b) - min(r,g,b) if max(r,g,b) > 0 else 0
    
    if brightness > 200:
        return "light"
    elif brightness < 60:
        return "dark"
    elif saturation > 180:
        if r > g and r > b: return "red"
        elif g > r and g > b: return "green"
        elif b > r and b > g: return "blue"
        elif r > 200 and g > 100: return "orange"
        elif r > 150 and b > 200: return "purple"
        elif b > 200 and g > 200: return "cyan"
    elif brightness > 130:
        return "neutral"
    
    return "gray"


def guess_semantic_roles(colors):
    """猜测颜色的语义角色"""
    roles = []
    dark_colors = []
    light_colors = []
    accent_colors = []
    
    for c in colors:
        raw = c['raw']
        if not raw.startswith('#'):
            continue
        role = hex_to_name(raw)
        if role == 'dark':
            dark_colors.append((raw, c.get('source', '')))
        elif role == 'light':
            light_colors.append((raw, c.get('source', '')))
        elif role not in ('gray', 'neutral'):
            accent_colors.append((raw, c.get('source', '')))
        c['role'] = role
    
    return dark_colors, light_colors, accent_colors


def extract_spacing(soup):
    """提取间距 token"""
    spacing = []
    seen = set()
    
    for style in soup.find_all(style=True):
        css = style.get('style', '')
        found = re.findall(r'(?:margin|padding|gap|spacing)[\s:-]*(?:top|right|bottom|left)?[\s:]*(\d+(?:\.\d+)?(?:px|rem|em))', css)
        for s in found:
            val = re.search(r'(\d+(?:\.\d+)?)', s)
            if val:
                num = float(val.group(1))
                if 2 <= num <= 64 and s not in seen:
                    seen.add(s)
                    spacing.append(s)
    
    return sorted(set(spacing), key=lambda x: float(re.search(r'\d+', x).group()))[:20]


def extract_shadows(soup):
    """提取阴影"""
    shadows = []
    seen = set()
    
    for style in soup.find_all(style=True):
        css = style.get('style', '')
        found = re.findall(r'box-shadow[\s:]*([^;]+)', css)
        for s in found:
            if s.strip() and s not in seen:
                seen.add(s)
                shadows.append(s.strip())
    
    return shadows[:10]


def extract_border_radius(soup):
    """提取圆角"""
    radii = []
    seen = set()
    
    for style in soup.find_all(style=True):
        css = style.get('style', '')
        found = re.findall(r'border-radius[\s:]*(\d+(?:\.\d+)?(?:px|rem|em|%))', css)
        for r in found:
            if r not in seen:
                seen.add(r)
                radii.append(r)
    
    return sorted(set(radii), key=lambda x: float(re.search(r'\d+', x).group()))[:10]


def get_page_title(soup):
    """获取页面标题"""
    title = soup.find('title')
    if title:
        return title.get_text().strip()
    
    og_title = soup.find('meta', property='og:title')
    if og_title:
        return og_title.get('content', 'Untitled')
    
    h1 = soup.find('h1')
    if h1:
        return h1.get_text().strip()
    
    return 'Untitled'


def guess_theme(soup):
    """猜测主题氛围"""
    # 检测深色模式
    body_bg = None
    for style in soup.find_all(style=True):
        css = style.get('style', '')
        m = re.search(r'background(?:-color)?[\s:]*([#\da-fA-F]+|rgb)', css)
        if m and 'background' in css:
            body_bg = m.group(1)
            break
    
    dark_keywords = ['dark', 'night', 'midnight', 'void', 'terminal', 'black', 'charcoal']
    light_keywords = ['light', 'bright', 'white', 'clean', 'minimal']
    
    text = soup.get_text().lower()
    
    is_dark = False
    for kw in dark_keywords:
        if kw in text or (body_bg and len(body_bg) > 4 and int(body_bg[1:3], 16) < 80):
            is_dark = True
            break
    
    # 检测密度
    has_many_elements = len(soup.find_all(['div', 'section', 'article'])) > 50
    density = "high" if has_many_elements else "medium"
    
    return {
        'dark_mode': is_dark,
        'density': density,
        'description': f"{'Dark' if is_dark else 'Light'} theme, {density} density interface"
    }


def generate_design_md(url, colors, fonts, spacing, shadows, radii, theme, title):
    """生成 DESIGN.md 内容"""
    dark_colors, light_colors, accent_colors = guess_semantic_roles(colors)
    
    md = f"""# {title} — DESIGN.md (Auto-Generated)

> ⚠️ **Auto-generated** — Review and refine before use in production.
> Source: {url}

## 1. Visual Theme & Atmosphere

- **Theme:** {theme['description']}
- **Mood:** Professional, modern
- **Density:** {theme['density']}
- **Key Characteristics:** Clean lines, {theme['dark_mode'] and 'dark surfaces' or 'light surfaces'}

## 2. Color Palette & Roles

### Primary Colors
"""

    for i, (color, src) in enumerate(accent_colors[:5]):
        role = hex_to_name(color)
        md += f"- **{role.title()}** `{color}` — {src}\n"
    
    md += "\n### Background Colors\n"
    for color, src in (light_colors[:3] if not theme['dark_mode'] else dark_colors[:3]):
        md += f"- `{color}` — {src}\n"
    
    md += "\n### Neutral Colors\n"
    md += f"- `light` — Light backgrounds\n"
    md += f"- `dark` — Dark surfaces\n"
    
    md += "\n### Full Palette\n"
    md += "| Color | Hex | Role |\n|-------|-----|------|\n"
    for c in colors[:20]:
        role = c.get('role', 'unknown')
        md += f"| {role} | `{c['raw']}` | {c.get('source', '')} |\n"
    
    md += "\n## 3. Typography Rules\n\n"
    
    for font in fonts[:5]:
        md += f"- **{font['family']}** — {font['source']}\n"
    
    md += f"""
### Type Scale
| Element | Size | Weight | Line Height |
|---------|------|--------|-------------|
| H1 | 32px | 700 | 1.2 |
| H2 | 24px | 600 | 1.3 |
| Body | 16px | 400 | 1.5 |
| Small | 14px | 400 | 1.4 |
| Mono | 14px | 400 | 1.5 |

## 4. Component Stylings

### Buttons
- Border radius: {radii[0] if radii else '8px'}
- Padding: {spacing[4] if len(spacing) > 4 else '12px'} {spacing[8] if len(spacing) > 8 else '16px'}
- Primary color: {accent_colors[0][0] if accent_colors else '#000000'}

### Cards
- Border radius: {radii[1] if len(radii) > 1 else radii[0] if radii else '12px'}
- Shadow: {shadows[0] if shadows else 'none'}
- Padding: {spacing[6] if len(spacing) > 6 else '16px'}

### Inputs
- Border radius: {radii[0] if radii else '6px'}
- Padding: {spacing[3] if len(spacing) > 3 else '8px'} {spacing[4] if len(spacing) > 4 else '12px'}
- Border: 1px solid neutral

## 5. Layout Principles

### Spacing Scale
```
"""
    for s in spacing[:10]:
        md += f"- {s}\n"
    
    md += f"""
### Grid
- Columns: 12
- Gutter: {spacing[8] if len(spacing) > 8 else '24px'}
- Container max-width: 1200px

## 6. Depth & Elevation

### Shadow System
"""
    for s in shadows[:5]:
        md += f"- `{s}`\n"
    
    md += f"""
## 7. Do's and Don'ts

### ✅ Do
- Use consistent spacing scale
- Apply shadows for elevated elements
- Follow the color palette strictly

### ❌ Don't
- Mix different border-radius values
- Use colors outside the palette
- Add unnecessary decorations

## 8. Responsive Behavior

| Breakpoint | Width | Columns |
|------------|-------|---------|
| Mobile | < 768px | 4 |
| Tablet | 768px - 1024px | 8 |
| Desktop | > 1024px | 12 |

## 9. Agent Prompt Guide

### Quick Reference
```
Primary: {accent_colors[0][0] if accent_colors else '#000000'}
Background: {light_colors[0][0] if not theme['dark_mode'] and light_colors else dark_colors[0][0] if dark_colors else '#ffffff'}
Font: {fonts[0]['family'] if fonts else 'Inter'}
Border Radius: {radii[0] if radii else '8px'}
```

### Example Prompt
> "Build a {title} inspired page with these specifications: {theme['description']}, using the color palette from DESIGN.md, {fonts[0]['family'] if fonts else 'Inter'} typography, and the spacing scale defined here."
"""
    
    return md


def main():
    if len(sys.argv) < 2:
        print("用法: python extract-design.py <url> [output.md]")
        print("示例: python extract-design.py https://github.com output.md")
        sys.exit(1)
    
    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"[抓取网站] {url}")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[错误] 请求失败: {e}")
        sys.exit(1)
    
    soup = BeautifulSoup(r.text, 'html.parser')
    
    print("[提取设计 token]")
    
    title = get_page_title(soup)
    colors = extract_colors(soup, url)
    fonts = extract_fonts(soup)
    spacing = extract_spacing(soup)
    shadows = extract_shadows(soup)
    radii = extract_border_radius(soup)
    theme = guess_theme(soup)
    
    print(f"   找到 {len(colors)} 个颜色, {len(fonts)} 个字体, {len(spacing)} 个间距值")
    
    md = generate_design_md(url, colors, fonts, spacing, shadows, radii, theme, title)
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"[OK] saved: {output_file}")
    else:
        print("\n" + md)
    
    # 同时保存 JSON 格式的 token
    tokens_file = output_file.replace('.md', '_tokens.json') if output_file else 'design_tokens.json'
    if not output_file:
        tokens_file = None
    
    if tokens_file:
        import json
        tokens = {
            'url': url,
            'title': title,
            'theme': theme,
            'colors': colors,
            'fonts': fonts,
            'spacing': spacing,
            'shadows': shadows,
            'radii': radii
        }
        with open(tokens_file, 'w', encoding='utf-8') as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
        print(f"[JSON] saved: {tokens_file}")


if __name__ == '__main__':
    main()
