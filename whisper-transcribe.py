#!/usr/bin/env python3
"""
Whisper 语音转文字工具
用法: python whisper-transcribe.py <音频文件路径> [--model small|medium|large]
"""

import sys
import os

# 设置 HuggingFace 镜像（国内用户）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 设置 FFmpeg 路径
os.environ["PATH"] = r"C:\Users\yiseg\AppData\Local\Microsoft\WinGet\Packages\yt-dlp.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-N-123074-g4e32fb4c2a-win64-gpl\bin" + os.pathsep + os.environ.get("PATH", "")

from faster_whisper import WhisperModel

def transcribe(audio_path, model_size="small", language="zh"):
    """转录音频文件"""
    print(f"正在加载模型: {model_size}...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    print(f"正在转录: {audio_path}")
    segments, info = model.transcribe(audio_path, language=language)
    
    print(f"\n检测语言: {info.language} (概率: {info.language_probability:.2%})")
    print("-" * 50)
    
    full_text = ""
    for segment in segments:
        print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
        full_text += segment.text
    
    print("-" * 50)
    print(f"\n完整文本:\n{full_text}")
    
    return full_text

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python whisper-transcribe.py <音频文件> [--model small|medium|large]")
        print("示例: python whisper-transcribe.py audio.mp3 --model small")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    model_size = "small"
    
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model_size = sys.argv[idx + 1]
    
    if not os.path.exists(audio_file):
        print(f"错误: 文件不存在: {audio_file}")
        sys.exit(1)
    
    transcribe(audio_file, model_size)
