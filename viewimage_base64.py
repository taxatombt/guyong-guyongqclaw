# -*- coding: utf-8 -*-
"""
viewimage_base64.py - Base64 图片查看辅助

来源: 顾庸t workspace_tools/viewimage_base64.py
参考: Claude Code image handling

功能:
  1. 图片文件 → base64 编码
  2. base64 → 获取图片信息（格式/尺寸估算）
  3. Markdown 图片链接生成
  4. 支持格式: PNG, JPG, GIF, WebP, SVG
"""

import base64
import os
import struct
from dataclasses import dataclass
from typing import Optional, Tuple, List
from pathlib import Path


@dataclass
class ImageInfo:
    """图片信息"""
    path: str
    format: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    base64_size: int = 0
    mime_type: str = ""


# JPEG 尺寸解析
def _parse_jpeg_size(data: bytes) -> Optional[Tuple[int, int]]:
    i = 2
    while i < len(data) - 1:
        if data[i] == 0xFF:
            marker = data[i+1]
            if marker == 0xD9 or marker == 0xDA:
                break
            if marker in (0xC0, 0xC1, 0xC2):
                h = struct.unpack('>H', data[i+5:i+7])[0]
                w = struct.unpack('>H', data[i+7:i+9])[0]
                return w, h
            length = struct.unpack('>H', data[i+2:i+4])[0]
            i += 2 + length
        else:
            i += 1
    return None


# PNG 尺寸解析
def _parse_png_size(data: bytes) -> Optional[Tuple[int, int]]:
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w = struct.unpack('>I', data[16:20])[0]
    h = struct.unpack('>I', data[20:24])[0]
    return w, h


# GIF 尺寸解析
def _parse_gif_size(data: bytes) -> Optional[Tuple[int, int]]:
    if data[:6] not in (b'GIF87a', b'GIF89a'):
        return None
    w = struct.unpack('<H', data[6:8])[0]
    h = struct.unpack('<H', data[8:10])[0]
    return w, h


MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}

SIZE_PARSERS = {
    ".jpg": _parse_jpeg_size,
    ".jpeg": _parse_jpeg_size,
    ".png": _parse_png_size,
    ".gif": _parse_gif_size,
}


def analyze_image(file_path: str) -> ImageInfo:
    """分析图片文件"""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {file_path}")
    
    suffix = p.suffix.lower()
    size_bytes = os.path.getsize(file_path)
    mime = MIME_TYPES.get(suffix, "application/octet-stream")
    
    width = None
    height = None
    
    parser = SIZE_PARSERS.get(suffix)
    if parser:
        try:
            with open(file_path, "rb") as f:
                header = f.read(1024)
            dims = parser(header)
            if dims:
                width, height = dims
        except Exception:
            pass
    
    # Base64 编码
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read())
    base64_size = len(b64)
    
    return ImageInfo(
        path=str(p),
        format=suffix.replace(".", "").upper(),
        size_bytes=size_bytes,
        width=width,
        height=height,
        base64_size=base64_size,
        mime_type=mime,
    )


def to_base64(file_path: str) -> str:
    """图片转 base64 字符串"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def to_data_url(file_path: str) -> str:
    """生成 data URL"""
    info = analyze_image(file_path)
    b64 = to_base64(file_path)
    return f"data:{info.mime_type};base64,{b64}"


def format_size(bytes_val: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} GB"


def format_info(info: ImageInfo) -> str:
    """格式化图片信息"""
    lines = [
        f"Path: {info.path}",
        f"Format: {info.format}",
        f"MIME: {info.mime_type}",
        f"Size: {format_size(info.size_bytes)}",
        f"Base64: {format_size(info.base64_size)}",
    ]
    if info.width and info.height:
        lines.append(f"Dimensions: {info.width}x{info.height}")
    return "\n".join(lines)
