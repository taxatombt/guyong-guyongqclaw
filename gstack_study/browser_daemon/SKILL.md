# gstack Browser Daemon — 核心设计

> 来源：gstack-main/gstack/browse/src/server.ts (102KB)
> gstack 的持久化 Chromium 浏览器 Daemon 核心架构

## 核心价值

gstack 的核心创新不是 skill 格式，不是 review checklist，
而是这个 Daemon——让 Playwright 从"每次 3-5 秒冷启动"变成"~100ms 响应"。

---

## 架构总览

```
Agent (Claude Code)              gstack CLI
      ↓                            ↑
 Tool call: $B snapshot -i  →   read state file
                            →   HTTP POST /command
                            ←   JSON response
                                   ↑
                          Bun.serve HTTP Server (localhost)
                                   ↑
                          Playwright API
                                   ↑
                          Chromium (headless)
                                   ↑
                          Cookie/tab/login 跨命令保持
```

**关键数字：**
- 首次调用：~3秒（启动浏览器 + 服务器）
- 后续调用：~100ms（纯 HTTP）
- 空闲超时：30分钟自动关闭
- 端口：随机 10000-60000（10个workspace不冲突）

---

## State File 设计（原子写）

```json
{
  "pid": 12345,
  "port": 34567,
  "token": "uuid-v4",
  "startedAt": "2026-04-12T10:00:00Z",
  "binaryVersion": "abc123"
}
```

**原子写流程：**
```python
import json, tempfile, os

def write_state(state: dict, path: Path):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state), encoding='utf-8')
    os.replace(tmp, path)  # 原子操作，避免读到半写入状态
```

**为什么原子写重要：**
- Agent 可能在任意时刻读取 state file
- 如果写到一半被读 → token 损坏 → 401
- rename 是原子操作，可以保证一致性

---

## 健康检查替代 PID

```python
import urllib.request

def health_check(url: str) -> bool:
    """比 psutil.pid_exists() 更可靠的存活检测"""
    try:
        req = urllib.request.Request(
            url + '/health',
            headers={'Authorization': f'Bearer {token}'}
        )
        with urllib.request.urlopen(req, timeout=1) as r:
            return r.status == 200
    except:
        return False

def ensure_server_running(state_path: Path):
    state = json.loads(state_path.read_text())
    if not health_check(f"http://localhost:{state['port']}"):
        spawn_server()  # 旧服务已死，启动新的
        state = read_state()  # 新 state
```

**为什么不用 PID：**
- Windows 进程退出后 PID 会被复用
- Bun 编译二进制中 PID 感知不可靠
- HTTP 健康检查对所有平台一致

---

## Bearer Token Auth

```typescript
const AUTH_TOKEN = crypto.randomUUID()

function validateAuth(req: Request): boolean {
  const header = req.headers.get('authorization')
  return header === `Bearer ${AUTH_TOKEN}`
}

function validate(req: Request) {
  if (!validateAuth(req)) {
    return new Response('Unauthorized', { status: 401 })
  }
}
```

**安全理由：**
- 防止同一机器上其他进程调用你的 browse 服务
- localhost only，不需要 HTTPS
- Token 存 state file（mode 0o600，只有所有者可读）

---

## Ref 系统（ARIA Tree → Locator）

```
用户看到：@e3 "Log in"
Agent 内部：
  1. snapshot -i
     → page.locator().ariaSnapshot() 返回 accessibility tree
  2. 解析树 → 分配 @e1, @e2, @e3...
  3. 为每个 ref 构建 Playwright Locator：
     getByRole('button', { name: 'Log in' }).nth(0)
  4. 存储 Map<string, Locator> 在 BrowserManager
  5. 返回带 ref 标注的纯文本树

用户：click @e3
  → 查找 e3 → Locator → locator.click()
```

**为什么不用 DOM 注入 data-ref：**
- CSP（Content Security Policy）阻止 `element.setAttribute`
- React/Vue hydration 清除注入属性
- Shadow DOM 无法从外部访问
- ARIA tree 是 Chromium 内部维护的，比 DOM 更稳定

**Ref 失效设计：**
- 导航后自动清空 refs（`framenavigated` 事件）
- 页面内容变化（React router）→ `resolveRef()` 做 `count()` 检查
- 过期 ref → 报错而不是静默点错元素

---

## Tab 所有权（多 Agent 隔离）

```typescript
private tabOwnership: Map<number, string> = new Map()

function getTab(tabId: number, clientId: string): Page | null {
  const owner = this.tabOwnership.get(tabId)
  // 未分配的 tab：只有 root 可写
  // 已分配的 tab：只有 owner 可写
  if (owner !== undefined && owner !== clientId) {
    throw new Error('Tab owned by another client')
  }
  return this.pages.get(tabId)
}
```

**用途：**
- 多 Agent 并发访问同一浏览器
- 每个 Agent 隔离操作自己的 tab
- 防止 Agent A 意外修改 Agent B 的登录状态

---

## Cookie 安全三原则

1. **Keychain 访问需用户确认**：macOS Keychain dialog 弹出，用户必须手动点"Allow"
2. **解密在内存中**：PBKDF2 + AES-128-CBC 解密后直接加载到 Playwright，不落盘
3. **只读临时副本**：复制浏览器 DB 到临时文件，read-only 打开，不碰原 DB

```typescript
// 读取 cookie 的正确方式
const tempDb = await copyToTemp(originalCookieDbPath)
const db = await openDatabase(tempDb, { readonly: true })
// 解密 → 内存 → Playwright context
// temp 文件在 server 关闭时自动删除
```

---

## 关键源码文件

| 文件 | 大小 | 内容 |
|------|------|------|
| `server.ts` | 102KB | HTTP 服务器（路由/认证/生命周期） |
| `browser-manager.ts` | 44KB | Chromium 管理（Tab/对话/watch） |
| `snapshot.ts` | 20KB | ARIA tree 解析/ref/Locator 构建 |
| `tab-session.ts` | 4KB | Tab 会话（ref 存储/失效检测） |
| `buffers.ts` | 4KB | Console/Network/Dialog 环形缓冲区 |
| `token-registry.ts` | 14KB | Token 管理/rate limiting |

---

## 与 OpenClaw 的结合点

**当前 OpenClaw 的 browser 工具：**
- 每次调用是独立的（无状态）
- 需要登录时要每次重新登录
- 对 SPA / 需要多步骤的流程效率低

**可移植的设计：**
1. **State file + 健康检查**：替代 PID 检测（Windows 可靠方案）
2. **原子写**：任何多进程共享状态的文件都用这个模式
3. **Ref 系统理念**：用 accessibility tree 而非 CSS selector 做 UI 自动化
4. **Tab 所有权**：如果未来做多 Agent 协作浏览器，这是隔离方案
