# SKILL-blender-mcp.md — blender-mcp MCP 集成

> 来源：ahujasid/blender-mcp（GitHub），v1.5.5
> 落地时间：2026-04-19

---

## 架构（两部分协同）

```
┌─────────────────────┐     socket:9876      ┌──────────────────────┐
│  Blender 软件        │◄──────────────────►│  addon.py（插件）     │
│  (bpy 模块)          │                      │  BlenderMCPServer      │
└─────────────────────┘                      │  (port 9876)          │
                                             └──────────┬───────────┘
                                                        │
                                             ┌──────────▼───────────┐
                                             │  server.py           │
                                             │  (MCP stdio 服务器)  │
                                             │  @modelcontextprotocol│
                                             └──────────┬───────────┘
                                                        │
                                             ┌──────────▼───────────┐
                                             │  mcporter / Claude   │
                                             │  (MCP Client)        │
                                             └──────────────────────┘
```

**关键点**：Blender 必须运行，addon.py 才能启动 socket 服务器。

---

## 核心文件

| 文件 | 大小 | 作用 |
|------|------|------|
| `addon.py` | 111KB | Blender 插件（装在 Blender 里）|
| `src/blender_mcp/server.py` | 49KB | MCP stdio 服务器 |
| `pyproject.toml` | 846B | 依赖：`mcp[cli]>=1.3.0`, `supabase>=2.0.0` |

---

## 安装步骤

### 前提：安装 Blender
```bash
# 下载 Windows 版：https://www.blender.org/download/
# 安装时勾选 "Add to PATH"（可选）
```

### 第一步：在 Blender 里装插件
1. 打开 Blender → 编辑 → 偏好设置 → 附加组件
2. 点击右上角「从磁盘安装」→ 选择下载的 `addon.py`
3. 按 `N` 键打开侧边栏 → Blender MCP 面板 → 启用插件
4. 点击 **"Start MCP Server"**

### 第二步：安装 MCP 服务器
```bash
pip install blender-mcp
# 或（推荐，无 pip 污染）
uvx blender-mcp
```

### 第三步：验证
```bash
mcporter list
# 应该看到 blender-mcp
```

---

## qclaw 接入方式

### 方式 A：mcporter（推荐）
```bash
# 配置 mcporter 连接 blender-mcp
mcporter config add blender-mcp --stdio "blender-mcp"

# 调用工具
mcporter call "blender-mcp.list_scene"
mcporter call "blender-mcp.create_cube"
mcporter call "blender-mcp.render_scene"
```

### 方式 B：mcporter stdio 直连
```bash
mcporter call --stdio "uvx blender-mcp" <tool_name> <args>
```

### 方式 C：Python 脚本调用
```python
import subprocess
import json

# 启动 blender-mcp 并发 JSON-RPC
proc = subprocess.Popen(
    ["blender-mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# 发送 initialize 请求
init_req = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "qclaw", "version": "1.0"}}
}
proc.stdin.write(json.dumps(init_req) + "\n")
proc.stdin.flush()
print(proc.stdout.readline())
```

---

## 主要工具（来自 addon.py）

| 工具 | 功能 |
|------|------|
| `list_objects` | 列出场景中所有对象 |
| `create_cube` | 创建立方体 |
| `create_sphere` | 创建球体 |
| `create_plane` | 创建平面 |
| `delete_object` | 删除对象 |
| `set_material` | 设置材质 |
| `add_light` | 添加光源 |
| `render_scene` | 渲染场景 |
| `get_properties` | 获取对象属性 |
| `set_location` | 设置对象位置 |
| `set_rotation` | 设置对象旋转 |
| `set_scale` | 设置对象缩放 |

---

## 坑

1. **Blender 必须运行**：addon.py 启动的 socket 服务器依赖 Blender 进程，Blender 关了就断
2. **端口 9876**：如果端口被占用，addon.py 启动会失败
3. **mcporter offline**：playwright MCP server 目前 offline，不影响 blender-mcp
4. **Addon 安装方式**：不能直接拖文件到 Blender，要用「从磁盘安装」

---

## qclaw 可移植设计点

1. **两部分架构**：本地 UI 插件（socket server）+ 标准化 MCP 接口（server.py）
   → 可迁移到任何需要「GUI 程序 + AI Agent」集成的场景
2. **mcporter stdio 模式**：`--stdio "command"` 封装任意 CLI 为 MCP 服务器
   → qclaw 的 mcporter skill 可直接用

---

## 与 qclaw 的整合思路

- blender-mcp 可以作为 mcporter 的一个 stdio server 注册
- qclaw → mcporter → blender-mcp → Blender
- 前提：Blender 在后台运行 + addon 启用
