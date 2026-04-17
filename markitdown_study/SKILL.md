# MarkItDown — Microsoft 文档转 Markdown 工具

> 来源：microsoft/markitdown (PyPI: 0.1.5, Feb 2026)
> 落地：2026-04-17

## 核心定位

**通用文档格式转换工具**：将各种文件格式转换为 Markdown，用于索引和文本分析。

- **版本**：0.1.5
- **作者**：Adam Fourney (Microsoft)
- **许可证**：MIT
- **Python**：>=3.10

## 安装

```bash
# 完整安装（所有格式支持）
pip install markitdown[all]

# 按需安装
pip install markitdown[pdf]       # PDF
pip install markitdown[docx]      # Word
pip install markitdown[xlsx]      # Excel
pip install markitdown[pptx]      # PowerPoint
pip install markitdown[audio-transcription]  # 音频转录
pip install markitdown[youtube-transcription] # YouTube字幕
pip install markitdown[az-doc-intel]  # Azure 文档智能
```

## 支持格式

| 格式 | 依赖 | 说明 |
|------|------|------|
| **PDF** | pdfminer-six, pdfplumber | 纯 Python |
| **DOCX** | mammoth, lxml | Word 文档 |
| **XLSX** | openpyxl, pandas | Excel |
| **XLS** | pandas, xlrd | 旧版 Excel |
| **PPTX** | python-pptx | PowerPoint |
| **Outlook** | olefile | 邮件 |
| **音频** | pydub, speechrecognition | 音频转录 |
| **YouTube** | youtube-transcript-api | 字幕提取 |
| **Azure** | azure-ai-documentintelligence | 高精度 Azure AI |

## 使用方式

### 命令行

```bash
markitdown path-to-file.pdf > document.md
markitdown path-to-file.docx -o output.md
```

### Python API

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("test.xlsx")
print(result.text_content)

# 指定插件
md = MarkItDown()
md.add_plugin(YourCustomPlugin())
result = md.convert("document.pdf")
```

## 核心设计

### 1. 插件架构

```python
# 内置插件示例
class TextPlugin:
    name = "text"
    extensions = [".txt"]
    
    def convert(self, file, content):
        return content.decode("utf-8")
```

### 2. Magika 文件类型检测

- 使用 `magika~=0.6.1` 自动检测文件类型
- 智能选择合适的转换插件

### 3. Markdownify

- 使用 `markdownify` 将 HTML 转为 Markdown
- 支持自定义 Markdown 样式

## qclaw 可移植设计点

### 1. 插件化架构

```python
# markitdown 的插件系统
class MarkItDown:
    def __init__(self):
        self.plugins = []
    
    def add_plugin(self, plugin):
        self.plugins.append(plugin)
```

**qclaw 应用**：agents/tool_registry.py 的工具注册系统

### 2. 文件类型自动检测 (Magika)

```python
# 自动检测文件类型，选择合适插件
from magika import Magika
magika = Magika()
result = magika.identify(path)
```

**qclaw 应用**：skillhub 文件类型检测 + 路由

### 3. 依赖分组安装

```python
# extras_require 设计
requires_extras = {
    "all": [...],
    "pdf": ["pdfminer-six", "pdfplumber"],
    "docx": ["mammoth", "lxml"],
}
```

**qclaw 应用**：skillhub_install 按需安装依赖

### 4. 结果统一抽象

```python
class Result:
    def __init__(self, text_content, metadata=None):
        self.text_content = text_content
        self.metadata = metadata or {}
```

**qclaw 应用**：agents/exec_adapter.py 统一返回格式

## markitdown vs MinerU 对比

| 特性 | markitdown | MinerU |
|------|-------------|--------|
| **定位** | 通用格式转换 | 高精度文档解析 |
| **精度** | 一般 | 86-90+ |
| **依赖** | 纯 Python | 需要 GPU (VLM) |
| **输出** | Markdown | Markdown + JSON |
| **优势** | 格式多、无需 GPU | 精度高、版面分析 |
| **场景** | 快速转换、索引 | LLM 训练数据、RAG |

## qclaw 已有模块对照

| markitdown 概念 | qclaw 对应 |
|----------------|-----------|
| 插件系统 | tool_registry |
| 文件类型检测 | magika → skillhub |
| 依赖分组 | skillhub_install extras |
| 结果抽象 | exec_adapter Result |
| PDF 转换 | pdf skill |
| Excel 转换 | xlsx skill |

## 场景选择

- **快速索引、简单转换** → markitdown
- **高精度 RAG、LLM 训练** → MinerU
- **两者结合**：markitdown 预处理 → MinerU 精修
