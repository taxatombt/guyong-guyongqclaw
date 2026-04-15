# -*- coding: utf-8 -*-
from __future__ import annotations
"""
pdf_extract_structured.py — PDF 语义结构化提取（对齐 OpenDataLoader-PDF schema）

来源：opendataloader-project/opendataloader-pdf（⭐14,852）

核心理念：
1. Schema-first：先定义 JSON schema，再实现
2. 语义结构 > 纯文本：paragraph/heading/table/list/image/caption
3. Bounding-box 定位：[left, bottom, right, top]
4. 元素关联：caption→image, table→跨页链接, list→item
5. 处理流水线：可组合的 processor

qclaw 适配：Python 实现，不依赖 Java

用法：
python pdf_extract_structured.py input.pdf --format json
python pdf_extract_structured.py input.pdf --format markdown
python pdf_extract_structured.py input.pdf --format html
"""

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from enum import Enum


# ═══════════════════════════════════════════════════════════════════
# Schema（对齐 OpenDataLoader-PDF schema.json）
# ═══════════════════════════════════════════════════════════════════

class ElementType(str, Enum):
    """元素类型（对齐 schema.json contentElement）"""
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    LIST = "list"
    LIST_ITEM = "list item"
    IMAGE = "image"
    CAPTION = "caption"
    TEXT_BLOCK = "text block"
    HEADER = "header"
    FOOTER = "footer"
    TABLE_ROW = "table row"
    TABLE_CELL = "table cell"


@dataclass
class BoundingBox:
    """边界框 [left, bottom, right, top]"""
    left: float
    bottom: float
    right: float
    top: float

    def to_list(self) -> List[float]:
        return [self.left, self.bottom, self.right, self.top]

    @classmethod
    def from_list(cls, arr: List) -> "BoundingBox":
        if len(arr) >= 4:
            return cls(left=arr[0], bottom=arr[1], right=arr[2], top=arr[3])
        return cls(left=0, bottom=0, right=0, top=0)


@dataclass
class TextProperties:
    """文本属性（font/size/color/content）"""
    font: str = "unknown"
    font_size: float = 12.0
    text_color: str = "#000000"  # RGB hex
    content: str = ""
    hidden_text: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font": self.font,
            "font size": self.font_size,
            "text color": self.text_color,
            "content": self.content,
            "hidden text": self.hidden_text,
        }


@dataclass
class BaseElement:
    """基础元素（对齐 schema.json baseElement）"""
    element_type: str
    id: int
    page_number: int
    bounding_box: BoundingBox
    level: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.element_type,
            "id": self.id,
            "page number": self.page_number,
            "bounding box": self.bounding_box.to_list(),
        }
        if self.level:
            result["level"] = self.level
        return result


@dataclass
class Paragraph(BaseElement):
    """段落"""
    text_props: TextProperties = field(default_factory=TextProperties)

    def __init__(self, page: int, bbox: BoundingBox, text: str,
                 font: str = "unknown", font_size: float = 12.0,
                 color: str = "#000000"):
        super().__init__(ElementType.PARAGRAPH.value, id=0, page_number=page, bounding_box=bbox)
        self.text_props = TextProperties(font=font, font_size=font_size,
                                          text_color=color, content=text)

    def to_dict(self) -> Dict[str, Any]:
        return {**super().to_dict(), **self.text_props.to_dict()}


@dataclass
class Heading(BaseElement):
    """标题"""
    heading_level: int = 1
    text_props: TextProperties = field(default_factory=TextProperties)

    def __init__(self, page: int, bbox: BoundingBox, text: str,
                 level: int = 1, font: str = "unknown", font_size: float = 18.0):
        super().__init__(ElementType.HEADING.value, id=0, page_number=page, bounding_box=bbox)
        self.heading_level = level
        self.text_props = TextProperties(font=font, font_size=font_size, content=text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "heading level": self.heading_level,
            **self.text_props.to_dict(),
        }


@dataclass
class TableCell(BaseElement):
    """表格单元格"""
    row_number: int = 1
    column_number: int = 1
    row_span: int = 1
    column_span: int = 1
    kids: List[Dict] = field(default_factory=list)

    def __init__(self, page: int, bbox: BoundingBox,
                 row: int, col: int, content: str = "",
                 row_span: int = 1, col_span: int = 1):
        super().__init__(ElementType.TABLE_CELL.value, id=0, page_number=page, bounding_box=bbox)
        self.row_number = row
        self.column_number = col
        self.row_span = row_span
        self.column_span = col_span
        self.kids = [{"type": "paragraph", "content": content}] if content else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "row number": self.row_number,
            "column number": self.column_number,
            "row span": self.row_span,
            "column span": self.column_span,
            "kids": self.kids,
        }


@dataclass
class TableRow:
    """表格行"""
    row_number: int
    cells: List[Dict]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": ElementType.TABLE_ROW.value,
            "row number": self.row_number,
            "cells": self.cells,
        }


@dataclass
class Table(BaseElement):
    """表格"""
    num_rows: int = 0
    num_cols: int = 0
    previous_table_id: Optional[int] = None
    next_table_id: Optional[int] = None
    rows: List[Dict] = field(default_factory=list)

    def __init__(self, page: int, bbox: BoundingBox, rows: List[List[str]]):
        super().__init__(ElementType.TABLE.value, id=0, page_number=page, bounding_box=bbox)
        self.num_rows = len(rows)
        self.num_cols = max(len(r) for r in rows) if rows else 0
        self.rows = []
        for i, row_data in enumerate(rows):
            cells = []
            for j, cell_text in enumerate(row_data):
                bbox = BoundingBox(left=0, bottom=i, right=j+1, top=i+1)
                cell = TableCell(page=page, bbox=bbox, row=i+1, col=j+1, content=cell_text)
                cells.append(cell.to_dict())
            self.rows.append(TableRow(row_number=i+1, cells=cells).to_dict())

    def to_dict(self) -> Dict[str, Any]:
        result = {
            **super().to_dict(),
            "number of rows": self.num_rows,
            "number of columns": self.num_cols,
            "rows": [r.to_dict() for r in self.rows],
        }
        if self.previous_table_id:
            result["previous table id"] = self.previous_table_id
        if self.next_table_id:
            result["next table id"] = self.next_table_id
        return result


@dataclass
class ListItem(BaseElement):
    """列表项"""
    kids: List[Dict] = field(default_factory=list)

    def __init__(self, page: int, bbox: BoundingBox, text: str,
                 font: str = "unknown", font_size: float = 12.0):
        super().__init__(ElementType.LIST_ITEM.value, id=0, page_number=page, bounding_box=bbox)
        self.text_props = TextProperties(font=font, font_size=font_size, content=text)
        self.kids = [{"type": "paragraph", "content": text}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            **self.text_props.to_dict(),
            "kids": self.kids,
        }


@dataclass
class List(BaseElement):
    """列表"""
    numbering_style: str = "bullet"
    list_items: List[Dict] = field(default_factory=list)

    def __init__(self, page: int, bbox: BoundingBox,
                 items: List[str], style: str = "bullet",
                 font: str = "unknown", font_size: float = 12.0):
        super().__init__(ElementType.LIST.value, id=0, page_number=page, bounding_box=bbox)
        self.numbering_style = style
        self.list_items = []
        for item_text in items:
            item_bbox = BoundingBox(left=bbox.left, bottom=bbox.bottom,
                                   right=bbox.right, top=bbox.top)
            item = ListItem(page=page, bbox=item_bbox, text=item_text,
                           font=font, font_size=font_size)
            self.list_items.append(item.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "numbering style": self.numbering_style,
            "number of list items": len(self.list_items),
            "list items": self.list_items,
        }


@dataclass
class Image(BaseElement):
    """图片"""
    source: str = ""
    data_uri: str = ""  # base64 data URI
    format: str = "png"

    def __init__(self, page: int, bbox: BoundingBox,
                 source: str = "", data_uri: str = "", fmt: str = "png"):
        super().__init__(ElementType.IMAGE.value, id=0, page_number=page, bounding_box=bbox)
        self.source = source
        self.data_uri = data_uri
        self.format = fmt

    def to_dict(self) -> Dict[str, Any]:
        result = {**super().to_dict()}
        if self.source:
            result["source"] = self.source
        if self.data_uri:
            result["data"] = self.data_uri
        result["format"] = self.format
        return result


@dataclass
class Caption(BaseElement):
    """图注"""
    linked_content_id: Optional[int] = None

    def __init__(self, page: int, bbox: BoundingBox, text: str,
                 linked_id: Optional[int] = None,
                 font: str = "unknown", font_size: float = 10.0):
        super().__init__(ElementType.CAPTION.value, id=0, page_number=page, bounding_box=bbox)
        self.text_props = TextProperties(font=font, font_size=font_size, content=text)
        self.linked_content_id = linked_id

    def to_dict(self) -> Dict[str, Any]:
        result = {**super().to_dict(), **self.text_props.to_dict()}
        if self.linked_content_id is not None:
            result["linked content id"] = self.linked_content_id
        return result


# ═══════════════════════════════════════════════════════════════════
# 处理流水线
# ═══════════════════════════════════════════════════════════════════

class PDFProcessor:
    """
    PDF 处理流水线（对齐 OpenDataLoader-PDF DocumentProcessor）

    策略：检测文本块类型 → 分类为语义元素
    """
    def __init__(self):
        self._element_id = 1
        self._elements: List[Dict] = []

    def _next_id(self) -> int:
        eid = self._element_id
        self._element_id += 1
        return eid

    def add_element(self, element: BaseElement):
        element.id = self._next_id()
        self._elements.append(element.to_dict())

    def process(self, text_blocks: List[Dict]) -> List[Dict]:
        """
        处理文本块列表 → 语义元素列表

        text_blocks: [{"text": str, "bbox": [l,b,r,t], "font": str, "size": float, "page": int}]
        """
        self._elements = []
        self._element_id = 1

        # 简单策略：按行判断类型
        for block in text_blocks:
            elem = self._classify_block(block)
            if elem:
                self.add_element(elem)

        return self._elements

    def _classify_block(self, block: Dict) -> Optional[BaseElement]:
        """根据文本特征分类块类型"""
        text = block.get("text", "").strip()
        if not text:
            return None

        page = block.get("page", 1)
        size = block.get("size", 12.0)
        font = block.get("font", "unknown")
        color = block.get("color", "#000000")
        bbox_data = block.get("bbox", [0, 0, 0, 0])
        bbox = BoundingBox.from_list(bbox_data)

        # 标题判断：字号大 或 全大写 或 # 开头
        if size >= 16 or (text.isupper() and len(text) < 80) or re.match(r"^#{1,6}\s", text):
            level = self._heading_level(size)
            return Heading(page=page, bbox=bbox, text=text, level=level,
                         font=font, font_size=size)

        # 列表项判断：-/*/数字. 开头
        if re.match(r"^[\-\*\•·]\s", text) or re.match(r"^\d+[\.\)]\s", text):
            style = "bullet" if re.match(r"^[\-\*\•]", text) else "ordered"
            return List(page=page, bbox=bbox, items=[text], style=style,
                       font=font, font_size=size)

        # 表格判断：包含多个 | 分隔的列
        if "|" in text and text.count("|") >= 2:
            cols = [c.strip() for c in text.split("|") if c.strip() and c.strip() != "---"]
            if len(cols) >= 2:
                return Table(page=page, bbox=bbox, rows=[cols])

        # 默认段落
        return Paragraph(page=page, bbox=bbox, text=text,
                        font=font, font_size=size, color=color)


    def _heading_level(self, size: float) -> int:
        """根据字号估算标题级别"""
        if size >= 28: return 1
        if size >= 22: return 2
        if size >= 18: return 3
        if size >= 15: return 4
        return 5


# ═══════════════════════════════════════════════════════════════════
# PDF 提取器
# ═══════════════════════════════════════════════════════════════════

class PDFExtractor:
    """
    PDF 语义结构化提取器

    支持多种后端（按优先级）：
    1. pdfplumber — 表格+文本提取
    2. pypdf2 — 基础文本提取
    3. pymupdf — 备用
    4. (opendataloader-pdf Java CLI) — 最高质量（可选）

    输出格式：对齐 opendataloader-pdf schema.json
    """

    def __init__(self):
        self.processor = PDFProcessor()
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        for name in ["pdfplumber", "pypdf", "fitz"]:
            try:
                __import__(name)
                return name
            except ImportError:
                continue
        return "none"

    def extract(self, pdf_path: str) -> Dict[str, Any]:
        """
        提取 PDF → OpenDataLoader-PDF 风格 JSON

        返回对齐 schema.json 的结构：
        {
          "file name": str,
          "number of pages": int,
          "author": null,
          "title": null,
          "creation date": null,
          "modification date": null,
          "kids": [contentElement...]
        }
        """
        pdf_path = Path(pdf_path)

        # 读取文本块
        blocks = self._extract_blocks(str(pdf_path))

        # 处理流水线
        elements = self.processor.process(blocks)

        return {
            "file name": pdf_path.name,
            "number of pages": self._count_pages(str(pdf_path)),
            "author": None,
            "title": pdf_path.stem,
            "creation date": None,
            "modification date": None,
            "kids": elements,
        }

    def _extract_blocks(self, pdf_path: str) -> List[Dict]:
        """从 PDF 提取文本块"""
        blocks = []

        if self._backend == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    words = page.extract_words()
                    lines = page.extract_text_lines() or []

                    for line in lines:
                        text = line.get("text", "").strip()
                        if not text:
                            continue
                        bbox = line.get("bbox", [0, 0, 0, 0])
                        chars = line.get("chars", [])
                        font = "unknown"
                        size = 12.0
                        if chars:
                            font = chars[0].get("fontname", "unknown")
                            size = chars[0].get("size", 12.0)

                        blocks.append({
                            "text": text,
                            "bbox": list(bbox) if bbox else [0, 0, 0, 0],
                            "font": font,
                            "size": size,
                            "page": page_num,
                        })

        elif self._backend == "pypdf":
            import pypdf
            with open(pdf_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text() or ""
                    for line in text.split("\n"):
                        line = line.strip()
                        if line:
                            blocks.append({
                                "text": line,
                                "bbox": [0, 0, 0, 0],
                                "font": "unknown",
                                "size": 12.0,
                                "page": page_num,
                            })

        elif self._backend == "fitz":
            import fitz  # pymupdf
            doc = fitz.open(pdf_path)
            for page_num, page in enumerate(doc, 1):
                        blocks_page = page.get_text("dict")  # blocks
                        for block in blocks_page.get("blocks", []):
                            if block.get("type") == 0:  # text block
                                for line in block.get("lines", []):
                                    text = "".join(
                                        span["text"] for span in line.get("spans", [])
                                    ).strip()
                                    if not text:
                                        continue
                                    bbox = line.get("bbox", [0, 0, 0, 0])
                                    spans = line.get("spans", [])
                                    font = spans[0].get("font", "unknown") if spans else "unknown"
                                    size = spans[0].get("size", 12.0) if spans else 12.0
                                    blocks.append({
                                        "text": text,
                                        "bbox": list(bbox),
                                        "font": font,
                                        "size": size,
                                        "page": page_num,
                                    })
            doc.close()

        else:
            raise RuntimeError(
                f"No PDF backend available. Install one of: "
                f"pdfplumber, pypdf2, pymupdf"
            )

        return blocks

    def _count_pages(self, pdf_path: str) -> int:
        """计算页数"""
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages)
        except:
            pass
        try:
            import pypdf
            with open(pdf_path, "rb") as f:
                return len(pypdf.PdfReader(f).pages)
        except:
            return 1

    def to_markdown(self, json_data: Dict) -> str:
        """JSON → Markdown（对齐 opendataloader-pdf markdown 输出）"""
        lines = [f"# {json_data.get('title', 'Document')}"]
        lines.append("")

        for elem in json_data.get("kids", []):
            t = elem.get("type")
            content = elem.get("content", "")

            if t == "heading":
                level = elem.get("heading level", 1)
                lines.append(f"{'#' * level} {content}")
            elif t == "paragraph":
                lines.append(content)
                lines.append("")
            elif t == "table":
                rows = elem.get("rows", [])
                if rows:
                    # 取第一行作为表头
                    header = rows[0].get("cells", [])
                    if header:
                        headers = []
                        for cell in header:
                            cell_text = ""
                            for kid in cell.get("kids", []):
                                cell_text += kid.get("content", "")
                            headers.append(cell_text or "")
                        lines.append("| " + " | ".join(headers) + " |")
                        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for row in rows[1:]:
                        cells = row.get("cells", [])
                        row_data = []
                        for cell in cells:
                            cell_text = ""
                            for kid in cell.get("kids", []):
                                cell_text += kid.get("content", "")
                            row_data.append(cell_text or "")
                        if row_data:
                            lines.append("| " + " | ".join(row_data) + " |")
                    lines.append("")
            elif t == "list item":
                content = elem.get("content", "")
                lines.append(f"- {content}")
            elif t == "image":
                source = elem.get("source", "")
                if source:
                    lines.append(f"![image]({source})")
                lines.append("")

        return "\n".join(lines)

    def to_html(self, json_data: Dict) -> str:
        """JSON → HTML（对齐 opendataloader-pdf html 输出）"""
        parts = [
            "<!DOCTYPE html>",
            "<html><head><meta charset='utf-8'>",
            f"<title>{json_data.get('title', 'Document')}</title>",
            "<style>body{font-family:sans-serif;max-width:800px;margin:0 auto;padding:20px}",
            "h1,h2,h3{margin-top:1.5em}h1{font-size:2em}h2{font-size:1.5em}h3{font-size:1.2em}",
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}",
            "img{max-width:100%;height:auto}p{margin:0.5em 0}li{margin:0.3em 0}",
            "</style></head><body>",
        ]

        for elem in json_data.get("kids", []):
            t = elem.get("type")
            content = elem.get("content", "")

            if t == "heading":
                level = elem.get("heading level", 1)
                tag = f"h{level}"
                parts.append(f"<{tag}>{self._escape(content)}</{tag}>")
            elif t == "paragraph":
                parts.append(f"<p>{self._escape(content)}</p>")
            elif t == "table":
                rows = elem.get("rows", [])
                if rows:
                    parts.append("<table>")
                    for ri, row in enumerate(rows):
                        tag = "th" if ri == 0 else "td"
                        cells = row.get("cells", [])
                        parts.append("<tr>")
                        for cell in cells:
                            cell_text = "".join(k.get("content", "") for k in cell.get("kids", []))
                            parts.append(f"<{tag}>{self._escape(cell_text)}</{tag}>")
                        parts.append("</tr>")
                    parts.append("</table>")
            elif t == "list item":
                content = elem.get("content", "")
                parts.append(f"<li>{self._escape(content)}</li>")
            elif t == "image":
                source = elem.get("source", "")
                if source:
                    parts.append(f"<img src='{source}' alt='image' />")

        parts.extend(["</body></html>"])
        return "\n".join(parts)

    def _escape(self, text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="PDF 语义结构化提取（对齐 OpenDataLoader-PDF schema）"
    )
    parser.add_argument("input", help="输入 PDF 文件")
    parser.add_argument("--format", "-f", choices=["json", "markdown", "html"],
                       default="json", help="输出格式")
    parser.add_argument("--output", "-o", help="输出文件（默认 stdout）")
    parser.add_argument("--embed-images", action="store_true",
                       help="嵌入图片为 base64（需要 opendataloader-pdf Java CLI）")
    parser.add_argument("--enrich-formula", action="store_true",
                       help="LaTeX 公式提取（需要 Java CLI）")
    parser.add_argument("--enrich-picture-description", action="store_true",
                       help="图片描述生成（需要 Java CLI + AI backend）")
    parser.add_argument("--filter-hidden-text", action="store_true",
                       help="过滤隐藏文本（需要 Java CLI）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        exit(1)

    print(f"[pdf_extract] Backend: {PDFExtractor()._backend}", file=sys.stderr)

    try:
        extractor = PDFExtractor()
        result = extractor.extract(str(input_path))

        if args.format == "json":
            output = json.dumps(result, ensure_ascii=False, indent=2)
        elif args.format == "markdown":
            output = extractor.to_markdown(result)
        elif args.format == "html":
            output = extractor.to_html(result)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"[pdf_extract] Written: {args.output}")
        else:
            print(output)

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\n安装 PDF 处理库（任选其一）：", file=sys.stderr)
        print("  pip install pdfplumber   # 推荐：表格+文本", file=sys.stderr)
        print("  pip install pymupdf      # 备用：文本+图片", file=sys.stderr)
        print("  pip install pypdf2       # 基础：仅文本", file=sys.stderr)
        exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        exit(1)
