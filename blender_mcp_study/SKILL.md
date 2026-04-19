# SKILL-blender-mcp.md — blender-mcp 深度落地

> 来源：ahujasid/blender-mcp（GitHub），v1.5.5
> 落地时间：2026-04-19（基础版）→ 2026-04-20（深度版）
> 源码：addon.py(2635行) + server.py(1186行) + telemetry.py(300行)

---

## 完整架构（三层协同）

```
┌─────────────────────────────────────────────────────────────────┐
│  MCP Client（mcporter / Claude Desktop / qclaw）                │
│  JSON-RPC over stdio                                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  server.py      │  ← FastMCP，22工具+1prompt
                    │  (src/, 49KB)   │    @telemetry_tool装饰器
                    │  BlenderConnection│   持久连接socket（180s超时）
                    │  send_command()  │
                    └────────┬────────┘
                             │ TCP localhost:9876
                    ┌────────▼────────┐
                    │  addon.py       │  ← Blender插件（BlenderMCPServer）
                    │  (2,635行)      │    socket_server线程（bpy.app.timers调度）
                    │  BlenderAPI调用  │    bpy.context.temp_override()
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Blender (bpy)   │  ← 3D场景
                    └─────────────────┘
```

---

## addon.py 核心实现（2,635行）

### BlenderMCPServer（socket服务器）

```python
class BlenderMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host, self.port = host, port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(1)
        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()

    def _server_loop(self):
        # 线程中循环accept，每client一个处理线程
        while self.running:
            client, _ = self.socket.accept()
            client_thread = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
            client_thread.start()
```

### 关键：Blender主线程执行（bpy.app.timers）

```python
def _handle_client(self, client):
    buffer = b''
    while self.running:
        data = client.recv(8192)
        if not data:
            break
        buffer += data
        try:
            command = json.loads(buffer.decode('utf-8'))
            buffer = b''

            # ★ 关键：Blender API必须在主线程调用
            # bpy.app.timers.register 让 Blender 在下一个可用帧执行
            bpy.app.timers.register(execute_wrapper, first_interval=0.0)

            def execute_wrapper():
                try:
                    response = self.execute_command(command)
                    client.sendall(json.dumps(response).encode('utf-8'))
                except Exception as e:
                    client.sendall(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                return None  # 不再重复调用

        except json.JSONDecodeError:
            pass  # 数据不完整，继续等待
```

### 动态handler注册（按addon偏好启用）

```python
def _execute_command_internal(self, command):
    cmd_type = command.get("type")
    params = command.get("params", {})

    handlers = {
        "get_scene_info": self.get_scene_info,
        "get_object_info": self.get_object_info,
        "get_viewport_screenshot": self.get_viewport_screenshot,
        "execute_code": self.execute_code,
    }

    # 按addon启用状态动态加入handler
    if bpy.context.scene.blendermcp_use_polyhaven:
        handlers.update({
            "search_polyhaven_assets": self.search_polyhaven_assets,
            "download_polyhaven_asset": self.download_polyhaven_asset,
            "set_texture": self.set_texture,
        })

    if bpy.context.scene.blendermcp_use_hyper3d:
        handlers.update({
            "create_rodin_job": self.create_rodin_job,
            "poll_rodin_job_status": self.poll_rodin_job_status,
            "import_generated_asset": self.import_generated_asset,
        })

    handler = handlers.get(cmd_type)
    if handler:
        return {"status": "success", "result": handler(**params)}
```

### 视口截图（context override）

```python
def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
    # 找到3D视口
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area_3d = area
            break

    # context override（切换区域不打断用户操作）
    with bpy.context.temp_override(area=area_3d):
        bpy.ops.screen.screenshot_area(filepath=filepath)

    # Blender内resize（避免传大图）
    img = bpy.data.images.load(filepath)
    if max(*img.size) > max_size:
        scale = max_size / max(*img.size)
        img.scale(int(img.size[0]*scale), int(img.size[1]*scale))
        img.save()
```

### AABB世界坐标计算（碰撞检测基础）

```python
@staticmethod
def _get_aabb(obj):
    """对象的世界空间轴对齐包围盒"""
    if obj.type != 'MESH':
        raise TypeError("Object must be a mesh")

    local_bbox = [mathutils.Vector(corner) for corner in obj.bound_box]
    world_bbox = [obj.matrix_world @ corner for corner in local_bbox]

    min_corner = mathutils.Vector(map(min, zip(*world_bbox)))
    max_corner = mathutils.Vector(map(max, zip(*world_bbox)))

    return [[*min_corner], [*max_corner]]
```

### ZIP安全（防止Zip Slip攻击）

```python
with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
    for file_info in zip_ref.infolist():
        file_path = file_info.filename
        target_path = os.path.join(temp_dir, os.path.normpath(file_path))
        abs_temp_dir = os.path.abspath(temp_dir)
        abs_target_path = os.path.abspath(target_path)

        # 两道防线
        if not abs_target_path.startswith(abs_temp_dir):
            return {"error": "Security issue: Zip Slip path traversal"}
        if ".." in file_path:
            return {"error": "Security issue: '..' sequence in path"}
```

---

## telemetry.py（隐私优先遥测，300行精华）

### 设计原则：consent-gated两级数据收集

```python
def _check_user_consent(self) -> bool:
    """通过Blender addon检查用户是否同意收集私密数据"""
    blender = get_blender_connection()
    result = blender.send_command("get_telemetry_consent", {})
    return result.get("consent", False)

def record_event(self, event_type, tool_name=None, prompt_text=None, ...):
    user_consent = self._check_user_consent()

    if not user_consent:
        # 无同意 → 只收集最少的匿名数据
        prompt_text = None          # 不收集用户prompt
        metadata = None             # 不收集代码片段/参数/截图
        if error_message:
            error_message = "Error occurred (details withheld without consent)"
    # 同意 → 正常收集，但截断过长字段
```

### 匿名UUID持久化

```python
def _get_or_create_uuid(self) -> str:
    data_dir = self._get_data_directory()  # APPDATA/BlenderMCP/
    uuid_file = data_dir / "customer_uuid.txt"

    if uuid_file.exists():
        return uuid_file.read_text().strip()

    customer_uuid = str(uuid.uuid4())
    uuid_file.write_text(customer_uuid)
    os.chmod(uuid_file, 0o600)  # Unix: 仅所有者可读写
    return customer_uuid
```

### 后台队列+worker线程

```python
def __init__(self):
    self._customer_uuid = self._get_or_create_uuid()
    self._session_id = str(uuid.uuid4())

    # 后台队列（队列满自动丢弃，不阻塞主线程）
    self._queue: queue.Queue[TelemetryEvent] = queue.Queue(maxsize=1000)
    self._worker = threading.Thread(target=self._worker_loop, daemon=True)
    self._worker.start()
```

### 禁用机制（环境变量）

```python
def _is_disabled(self) -> bool:
    disable_vars = [
        "DISABLE_TELEMETRY",
        "BLENDER_MCP_DISABLE_TELEMETRY",
        "MCP_DISABLE_TELEMETRY"
    ]
    for var in disable_vars:
        if os.environ.get(var, "").lower() in ("true", "1", "yes", "on"):
            return True
    return False
```

### TelemetryEvent dataclass

```python
@dataclass
class TelemetryEvent:
    event_type: EventType  # STARTUP | TOOL_EXECUTION | PROMPT_SENT | CONNECTION | ERROR
    customer_uuid: str      # 匿名持久化UUID
    session_id: str        # 每次启动新session
    timestamp: float
    version: str
    platform: str

    # 可选字段
    tool_name: str | None = None
    prompt_text: str | None = None          # 需同意
    success: bool = True
    duration_ms: float | None = None
    error_message: str | None = None
    blender_version: str | None = None
    metadata: dict[str, Any] | None = None  # 需同意
```

---

## server.py 关键设计

### 持久连接 + 连接健康检测

```python
_blender_connection = None  # 全局单例

def get_blender_connection():
    global _blender_connection

    if _blender_connection is not None:
        try:
            # 发ping验证连接仍有效
            result = _blender_connection.send_command("get_polyhaven_status")
            _polyhaven_enabled = result.get("enabled", False)
            return _blender_connection
        except Exception:
            _blender_connection.disconnect()
            _blender_connection = None

    # 重建连接
    _blender_connection = BlenderConnection(host=os.getenv("BLENDER_HOST", DEFAULT_HOST),
                                           port=int(os.getenv("BLENDER_PORT", DEFAULT_PORT)))
    _blender_connection.connect()
    return _blender_connection
```

### 分块接收 + JSON完整性验证

```python
def receive_full_response(self, sock, buffer_size=8192):
    chunks = []
    sock.settimeout(180.0)  # 与addon同步的180s超时

    while True:
        try:
            chunk = sock.recv(buffer_size)
            if not chunk:  # 空chunk = 连接关闭
                if not chunks:
                    raise Exception("Connection closed before receiving any data")
                break

            chunks.append(chunk)

            # 每收一块就尝试JSON解析，完整才退出
            try:
                data = b''.join(chunks)
                json.loads(data.decode('utf-8'))
                return data  # 完整JSON，退出
            except json.JSONDecodeError:
                continue  # 不完整，继续收

        except socket.timeout:
            break  # 超时但有数据 → 尝试使用

    # 超时场景：使用已收到的数据
    if chunks:
        data = b''.join(chunks)
        json.loads(data.decode('utf-8'))  # 验证
        return data
    raise Exception("No data received")
```

### @telemetry_tool装饰器

```python
# telemetry_decorator.py
def telemetry_tool(tool_name: str):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error = None
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                record_tool_usage(tool_name, success, duration_ms, error)
        return sync_wrapper
    return decorator

# 使用：自动追踪每个工具的执行
@telemetry_tool("get_scene_info")
@mcp.tool()
def get_scene_info(ctx: Context) -> str: ...
```

### asset_creation_strategy（内置prompt，AI指导）

```python
@mcp.prompt()
def asset_creation_strategy() -> str:
    # 告诉AI：资源优先级 + 工作流程
    # 1. PolyHaven → 纹理/HDRI/模型库
    # 2. Sketchfab → 真实感模型（种类更多）
    # 3. Hyper3D(Rodin) → 单品生成（不支持场景/地面/分块生成）
    # 4. Hunyuan3D → 腾讯单品生成
    # 5. 最后才fallback到脚本
    #
    # 每个工具流程：
    # 生成任务 → poll状态 → import资产 → 调整位置和尺寸
    #
    # 资源优先级：
    # 特定物品 → Sketchfab > PolyHaven
    # 通用物品 → PolyHaven > Sketchfab
    # 自定义物品 → Hyper3D / Hunyuan3D
```

---

## Hyper3D/Rodin 异步Job流程

```python
# 1. 提交生成任务
def create_rodin_job_main_site(self, text_prompt=None, images=None, bbox_condition=None):
    # 返回 {"uuid": <task_uuid>, "jobs": {"subscription_key": <key>}, "submit_time": timestamp}
    ...

# 2. 轮询状态（主动轮询）
def poll_rodin_job_status_main_site(self, subscription_key: str):
    # 返回 {"status": "PENDING"|"RUN"|"DONE"|"FAILED", ...}
    ...

# 3. 导入资产
def import_generated_asset_main_site(self, task_uuid: str, name: str):
    # 从Rodin下载GLB → bpy.ops.import_scene.gltf() → 导入Blender
    # 计算world_bounding_box → 归一化尺寸
    ...
```

---

## qclaw 可移植设计点

| blender-mcp设计 | qclaw现状 | 落地 |
|----------------|---------|------|
| **@telemetry_tool装饰器** | agents/event_bus.py追踪事件 | **可迁移**：改造成带装饰器的工具调用追踪 |
| **consent-gated两级数据** | evolver.py记录成功率 | **可迁移**：加同意层+匿名UUID |
| **后台Queue+Worker线程** | 心跳自检定时 | **可迁移**：后台队列异步记录 |
| **bpy.app.timers.register** | exec_adapter同步执行 | **可迁移**：需要异步的长任务用队列 |
| **context temp_override** | exec在子进程 | **不适用**：qclaw无GUI |
| **JSON分块接收+验证** | socket/stdio | **可借鉴**：receive_full_response |
| **持久连接+健康检测** | agents/tool_registry | **已有**：连接池 |
| **动态handler注册** | skill路由 | **可借鉴**：按配置启用/禁用 |
| **DISABLE_TELEMETRY环境变量** | evolver.py开关 | **可迁移**：3种禁用方式 |
| **ZIP Slip双重检查** | 下载文件安全 | **已有**：path traversal检查 |

---

## 最高价值落地点

### 1. telemetry.py → qclaw隐私追踪系统

当前 qclaw evolver.py 直接写数据库，缺乏：
- consent-gated 两级数据
- 匿名 UUID 持久化
- 环境变量禁用（`DISABLE_*`）
- 后台队列不阻塞主线程
- graceful degradation（队列满 → drop，不报错）

```python
# qclaw 版本设计
@dataclass
class EvolverEvent:
    event_type: str           # tool_execution | evolver_record | session_start
    customer_uuid: str        # 匿名持久化
    session_id: str
    timestamp: float
    tool_name: str | None = None
    success: bool = True
    duration_ms: float | None = None
    metadata: dict | None = None

class EvolverCollector:
    def __init__(self):
        self._uuid = self._get_or_create_uuid()
        self._queue = queue.Queue(maxsize=500)
        threading.Thread(target=self._worker_loop, daemon=True).start()

    def record_async(self, event_type, **kwargs):
        if os.getenv("QCLAW_DISABLE_EVOLVER_TELEMETRY"):
            return
        self._queue.put_nowait(EvolverEvent(event_type=event_type, customer_uuid=self._uuid, **kwargs))
```

### 2. server.py receive_full_response → socket数据接收

当前 qclaw 的 socket/stdio 处理没有分块接收 + JSON完整性验证。

### 3. addon.py 动态handler注册 → skill路由

blender-mcp 根据 addon 配置动态启用 handler，qclaw 的 skill 可以根据配置启用/禁用特定工具。

---

## 文件结构

```
blender_mcp_study/
├── SKILL.md   ← 本文件（深度版，2026-04-20）
```
