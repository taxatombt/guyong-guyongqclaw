# SKILL-blender-mcp.md — blender-mcp MCP 集成

> 来源：ahujasid/blender-mcp（GitHub），v1.5.5
> 落地时间：2026-04-19
> 更新：2026-04-19（完整 server.py 源码解析）

---

## 架构（三层协同）

```
┌──────────────────────┐     socket:9876     ┌──────────────────────┐
│  Blender 软件         │◄─────────────────►│  addon.py（插件）     │
│  (bpy 模块)           │                     │  BlenderMCPServer     │
└──────────────────────┘                     │  (port 9876)          │
                                              └──────────┬───────────┘
                                                         │
                                              ┌──────────▼───────────┐
                                              │  server.py (49KB)   │
                                              │  @mcp.server.fastmcp │
                                              │  22 tools + 1 prompt │
                                              └──────────┬───────────┘
                                                         │
                                              ┌──────────▼───────────┐
                                              │  mcporter / Claude   │
                                              │  (MCP Client)        │
                                              └──────────────────────┘
```

**两层通信**：
- addon.py ↔ Blender：Python API（`bpy.ops.*` 等）
- server.py ↔ addon.py：JSON-RPC over socket（port 9876，timeout 180s）
- mcporter ↔ server.py：标准 MCP stdio

---

## 核心文件

| 文件 | 大小 | 作用 |
|------|------|------|
| `addon.py` | 111KB | Blender 插件（装在 Blender 里） |
| `src/blender_mcp/server.py` | 49KB | **MCP stdio 服务器，22个工具** |
| `src/blender_mcp/telemetry.py` | 11KB | 遥测数据记录 |
| `pyproject.toml` | 846B | 依赖：`mcp[cli]>=1.3.0`, `supabase>=2.0.0` |

---

## 22 个 MCP 工具（来自 server.py 完整解析）

### 场景查询（3个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `get_scene_info` | ctx | 获取场景信息（对象列表、灯光、材质等） |
| `get_object_info` | object_name | 获取指定对象详情 |
| `get_viewport_screenshot` | max_size=800 | 视口截图，返回 Image |

### Blender 直接控制（1个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `execute_blender_code` | code (str) | 直接执行 Blender Python 代码 |

### Poly Haven 纹理资产（5个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `get_polyhaven_categories` | asset_type="hdris" | 获取可用类别 |
| `search_polyhaven_assets` | query, asset_type | 搜索 Poly Haven 资产 |
| `download_polyhaven_asset` | url, asset_type, output_name | 下载资产到 Blender 场景 |
| `set_texture` | texture_path, object_name | 为对象设置纹理 |
| `get_polyhaven_status` | — | 检查 Poly Haven API 状态 |

### Sketchfab 模型（4个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `get_sketchfab_status` | — | 检查 Sketchfab API 状态 |
| `search_sketchfab_models` | query, categories, max_results | 搜索 Sketchfab 模型 |
| `get_sketchfab_model_preview` | model_uid | 获取模型预览图 |
| `download_sketchfab_model` | model_uid, target_folder | 下载模型到本地 |

### Hyper3D 模型生成（3个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `get_hyper3d_status` | — | 检查 Hyper3D API 状态 |
| `generate_hyper3d_model_via_text` | prompt, target_folder | 文本生成 3D 模型 |
| `generate_hyper3d_model_via_images` | image_paths, target_folder | 多图生成 3D 模型 |
| `import_generated_asset` | job_id | 导入 Rodin 生成的资产到 Blender |

### 混元3D（腾讯，4个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `get_hunyuan3d_status` | — | 检查混元3D API 状态 |
| `generate_hunyuan3d_model` | prompt, target_folder | 文本生成混元3D模型 |
| `poll_hunyuan_job_status` | job_id | 轮询混元任务状态 |
| `import_generated_asset_hunyuan` | job_id | 导入混元生成的资产 |

### 异步任务（2个）
| 工具 | 参数 | 功能 |
|------|------|------|
| `poll_rodin_job_status` | job_id | 轮询 Rodin（Hyper3D后端）任务状态 |
| `import_generated_asset` | job_id | 导入生成的资产到 Blender |

### Prompt（1个）
| prompt | 作用 |
|--------|------|
| `asset_creation_strategy` | 根据用户需求生成 3D 资产生成策略（内置 prompt 模板） |

---

## 安装步骤

### 前提：安装 Blender
去 https://www.blender.org/download/ 下载 Windows 版安装

### Blender 内装插件
1. 打开 Blender → 编辑 → 偏好设置 → 附加组件
2. 点击「从磁盘安装」→ 选择 `addon.py`
3. 按 `N` 键 → Blender MCP 面板 → 启用 → Start MCP Server

### 安装 MCP 服务器
```bash
pip install blender-mcp
# 或（推荐，无 pip 污染）
uvx blender-mcp
```

### mcporter 注册（qclaw 用）
```bash
mcporter config add blender-mcp --stdio "uvx blender-mcp"
mcporter call "blender-mcp.get_scene_info"
```

---

## qclaw 接入代码

```python
# 方式 A：mcporter CLI
mcporter call --stdio "uvx blender-mcp" get_scene_info

# 方式 B：Python subprocess（直接用 MCP JSON-RPC）
import subprocess, json

proc = subprocess.Popen(
    ["blender-mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# 初始化
init_req = {
    "jsonrpc": "2.0", "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "qclaw", "version": "1.0"}
    }
}
proc.stdin.write(json.dumps(init_req) + "\n")
proc.stdin.flush()
resp = proc.stdout.readline()

# 调工具
tool_req = {
    "jsonrpc": "2.0", "id": 2,
    "method": "tools/call",
    "params": {
        "name": "get_scene_info",
        "arguments": {}
    }
}
proc.stdin.write(json.dumps(tool_req) + "\n")
proc.stdin.flush()
print(proc.stdout.readline())
```

---

## 关键设计细节

### BlenderConnection（socket 客户端）
- 连接：`localhost:9876`（可配置）
- 超时：180 秒（socket recv timeout）
- 协议：JSON-RPC over TCP
- 自动重连：`get_blender_connection()` 函数管理连接生命周期

### execute_blender_code（最强大的工具）
```python
@mcp.tool()
def execute_blender_code(ctx: Context, code: str) -> str:
    # 用户传 Python 代码字符串，在 Blender 的 bpy 上下文执行
    # 返回 stdout/stderr 或截图
```
**用途**：任何其他工具做不到的操作，直接写 Blender Python 代码。

### 多 API 并行支持
- Poly Haven（纹理/HDRI，REST API）
- Sketchfab（3D 模型市场，API key）
- Hyper3D/Rodin（AI 模型生成，异步 job）
- 混元3D（腾讯，AI 模型生成，异步 job）

---

## qclaw 可移植设计点

1. **FastMCP 框架**：`@mcp.tool()` 装饰器 + `Context` 注入 → 可迁移到其他 MCP 服务器开发
2. **socket ↔ stdio 桥接**：addon.py（socket server）+ server.py（stdio client）两层分离 → 适用于任何需要「GUI 程序 + AI Agent」集成的场景
3. **异步任务轮询**：`poll_*_job_status` + `import_*` 两步确认 → 适用于任何异步 API 场景
4. **Prompt 模板**：`asset_creation_strategy` → qclaw 可以用类似方式内嵌 prompt 生成策略

---

## 当前限制

- **Blender 必须运行**：addon.py 启动 socket 服务器，Blender 关了就断
- **端口 9876** 被占用则启动失败
- 部分工具（Sketchfab/Hyper3D/混元）需要对应 API key

---

## blender_mcp_study 目录文件

```
blender_mcp_study/
└── SKILL.md   ← 本文件（3.8KB）
```
