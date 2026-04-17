# MinerU — 文档解析引擎逆向工程

> 来源：opendatalab/MinerU (60,254 ⭐, AGPL-3.0)
> 落地：2026-04-17

## 核心定位

**高精度文档解析引擎**：将 PDF / DOCX / 图片转为 LLM 可读的 Markdown / JSON。

- **最新版本**：3.0.0 (2026/03/29)
- **精度指标**：OmniDocBench v1.5 得分 86+ (pipeline) / 90+ (vlm-engine)
- **支持语言**：109 种
- **输出格式**：Markdown、JSON（含阅读顺序、布局信息）

## 核心能力

| 能力 | 说明 |
|------|------|
| **公式识别** | LaTeX 格式还原 |
| **表格识别** | HTML 格式还原，支持跨页表格合并 |
| **OCR** | VLM + OCR 双引擎，109 种语言 |
| **版面分析** | 布局检测、阅读顺序恢复 |
| **DOCX 原生解析** | 端到端速度提升数十倍，无幻觉 |

## 三种推理后端

| 后端 | 精度 | 资源要求 | 特点 |
|------|------|----------|------|
| **pipeline** | 86+ | CPU/GPU，4GB 显存 | 兼容性好，稳定无幻觉 |
| **vlm-engine** | 90+ | 8GB 显存 | 高精度，支持 vLLM/LMDeploy |
| **hybrid-engine** | 90+ | 8GB 显存 | 原生文本提取 + VLM，低幻觉 |

## 目录结构

```
mineru/
├── backend/          # 推理后端
│   ├── pipeline/     # pipeline 后端（纯 CPU 可跑）
│   ├── vlm/          # VLM 后端
│   └── hybrid/       # 混合后端
├── model/            # 模型模块
│   ├── layout/       # 版面检测模型
│   ├── ocr/          # OCR 模型
│   ├── table/        # 表格识别模型
│   ├── docx/         # DOCX 解析
│   └── vlm/          # VLM 模型
├── cli/              # 命令行接口
│   ├── client.py     # 客户端
│   ├── fast_api.py   # API 服务
│   ├── gradio_app.py # WebUI
│   └── router.py     # 路由（多服务负载均衡）
└── utils/            # 工具函数
```

## 部署方式

```bash
# pip 安装
pip install -U "mineru[all]"

# 命令行使用
mineru -p <input_path> -o <output_path>

# 指定后端（纯 CPU）
mineru -p <input_path> -o <output_path> -b pipeline

# Docker 部署
docker pull opendatalab/mineru:latest
```

## 集成生态

| 场景 | 方案 |
|------|------|
| AI 编程工具 | MCP Server（Cursor / Claude Desktop / Windsurf）|
| RAG 框架 | LangChain / LlamaIndex / RAGFlow / Dify / FastGPT |
| 开发集成 | Python / Go / TypeScript SDK / CLI / REST API / Docker |
| 零代码 | mineru.net 在线版 / Gradio WebUI / 桌面客户端 |

## 国产算力支持

昇腾 · 寒武纪 · 燧原 · 沐曦 · 摩尔线程 · 昆仑芯 · 天数智芯 · 瀚博 · 太初元碁 · 海光 · 平头哥

## qclaw 可移植设计点

### 1. 双引擎架构（VLM + OCR）

```python
# VLM 处理视觉理解，OCR 处理文本识别
# hybrid-engine = 原生文本提取 + VLM 降噪
```

**qclaw 应用**：agents/tool_pipeline.py 的双层验证（Hook → Permission → Execute）

### 2. 滑动窗口 + 流式落盘

- 长文档解析用滑动窗口降低内存峰值
- 已完成结果流式写出，不等全部完成

**qclaw 应用**：qclaw_compactor 的分片压缩策略

### 3. 线程安全并发推理

- 全面支持多线程并发
- mineru-router 负载均衡

**qclaw 应用**：MultiAgentDispatcher 多 Agent 并发 + 负载均衡

### 4. MCP Server 集成

```python
# 作为 MCP Server 提供文档解析能力
# Cursor / Claude Desktop / Windsurf 原生集成
```

**qclaw 应用**：OpenClaw 的 skill/mcp 集成

### 5. 多后端编排（API/CLI/Router）

- mineru-api：同步 + 异步任务接口
- mineru-router：多服务统一入口 + 负载均衡

**qclaw 应用**：agents/tool_registry 的多工具编排

### 6. 模型下载 + 缓存

```bash
export MINERU_MODEL_SOURCE=modelscope  # 切换镜像源
```

**qclaw 应用**：skillhub_install 的镜像源配置

## 已有 qclaw 模块对照

| MinerU 概念 | qclaw 对应 |
|------------|-----------|
| pipeline 后端 | qclaw_compactor |
| VLM + OCR 双引擎 | Hook + Permission 双层验证 |
| mineru-router | MultiAgentDispatcher |
| MCP Server | OpenClaw MCP |
| 模型缓存 | skillhub 本地缓存 |
| async 任务 | cron 定时任务 |

## 参考项目

- UniMERNet（公式识别）
- TableStructureRec（表格结构）
- PaddleOCR（OCR）
- vLLM / LMDeploy（推理后端）
- OmniDocBench（评测基准）
