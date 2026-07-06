# SKILL-ard.md — Agentic Resource Discovery 协议

> 学习日期：2026-06-27 | 来源：https://agenticresourcediscovery.org/ | ★301 | 状态：Draft v0.9
> 对 qclaw 贡献度：⭐⭐⭐（光学备用，未达 🔥🔥🔥）

---

## 一句话

**像 Google 搜索发现网页一样，让 AI Agent 动态发现工具、MCP 服务、Agent Cards。**

---

## 为什么需要它

AI Agent 的"工具发现"现在靠手动配置（MCP servers、Skills、Plugins），但未来 Agent 需要：

- 自动找到能用的 MCP 服务，而不是用户手动填 URL
- 用自然语言描述需求，不用精确知道工具名
- 跨 Registry、跨发布商、跨平台搜索

ARD 就是干这个的标准。

---

## 核心概念（5 个）

### 1. ai-catalog.json — 发布者的资源清单

每个发布者（如 HuggingFace、GitHub）在 `/.well-known/ai-catalog.json` 放一个 manifest：

```json
{
  "ai-catalog": "https://agenticresourcediscovery.org/ai-catalog-schema.json",
  "publisher": {
    "id": "urn:air:huggingface:co:ardo",
    "name": "Hugging Face"
  },
  "resources": [
    {
      "type": "application/a2a-agent-card+json",
      "id": "urn:air:huggingface:co:smolagents",
      "name": "Smolagents",
      "description": "Hugging Face official agents"
    },
    {
      "type": "application/mcp-server-card+json",
      "id": "urn:air:huggingface:co:discover/mcp-server",
      "name": "HF Discover MCP",
      "url": "https://huggingface.co/.well-known/mcp/servers.json"
    }
  ]
}
```

### 2. URN 标识 `urn:air:` — 每个资源的身份证

```
urn:air:<publisher-namespace>:<sub-namespace>:<resource-name>
```

- `urn:air:` 固定前缀（air = Agentic Resource）
- 例：`urn:air:com.github:my-org:email-agent`

### 3. Search-First — 搜索，不是安装

搜到就能用，和搜索引擎一样。不需要用户先"安装"或"配置"。

### 4. 4 种静态发现方式

| 方式 | 路径 |
|------|------|
| Well-known URI | `/.well-known/ai-catalog.json` |
| robots.txt | `Agentmap: /.well-known/ai-catalog.json` |
| HTML link tag | `<link rel="ai-catalog" href="...">` |
| DNS-SD | `_ard._tcp.example.com` |

### 5. Registry 搜索 API

**POST /search**（必需）

```json
// 请求
{
  "query": {
    "text": "找能发邮件的 agent",
    "filter": { "type": "application/mcp-server-card+json" }
  },
  "federation": "auto"
}

// 响应
{
  "results": [
    {
      "id": "urn:air:com.github:ardo-corp:mail-agent",
      "type": "application/a2a-agent-card+json",
      "name": "Email Agent Pro",
      "description": "AI-powered email assistant",
      "relevance": 0.89
    }
  ],
  "pagination": { "totalResults": 14 }
}
```

**POST /explore**（可选）— 类似浏览目录

---

## 联邦模式

| 模式 | 行为 |
|------|------|
| `none` | 只查本地 |
| `referrals` | 查本地 + 告诉你还有哪些 Registry 可查（默认）|
| `auto` | 自动递归查所有已知 Registry 并合并结果 |

---

## 跟现有协议的关系

| 协议 | ARD 的角色 |
|------|-----------|
| **MCP** | ARD 搜到 MCP Server Card → Agent 按 MCP 协议连上它 |
| **A2A** | ARD 搜到 A2A Agent Card → Agent 按 A2A 协议通信 |
| **OpenAPI** | ARD 不替代，通过 `type: application/openapi+json` 桥接 |

**ARD 不是替代品，是"发现层"。** MCP/A2A/OpenAPI 是资源本身的协议，ARD 是找到这些资源的协议。

---

## 参考实现

| 项目 | ★ | 说明 |
|------|---|------|
| ards-project/ard-spec | 301 | 规范 + Python 原型（CLI + 测试）|
| huggingface/hf-discover | 26 | HuggingFace 官方 ARD 客户端/服务端 |

---

## 对 qclaw 的落地启发（备用）

### 可借鉴的设计

1. **Search-First 资源发现**：qclaw 可以添加 ARD Registry 支持，让 Agent 动态发现外部 MCP/A2A 服务，而不需要用户手动配置 provider
2. **ai-catalog.json**：每个服务站点发布清单，Agent 按需索引
3. **白名单联邦**：qclaw 的 tools/providers 配置中的可用服务，可以组织成 `referrals` 联邦模式
4. **URN 标识系统**：`urn:air:` 格式可统一内部工具标识

### 可能的集成点（未来）

```
qclaw 启动
  → 检查 ~/.qclaw/ai-catalog.json（本地）
  → 查询已配置的远程 Registry（如 HuggingFace Discover）
  → 合并可用的 MCP/A2A 服务
  → 注入 agent 上下文
```

### 当前不集成的理由

- ARD 规范还在 Draft v0.9（2026-05-28），未到稳定版
- qclaw 当前没有动态发现 MCP 服务的需求（skill 靠 skillhub 安装）
- 贡献度未达 🔥🔥🔥 级，按规则光学备用

---

## 参考链接

- 规范文档：https://agenticresourcediscovery.org/spec/
- GitHub：https://github.com/ards-project/ard-spec
- 快速上手：https://agenticresourcediscovery.org/get_started/
- 如何发布：https://agenticresourcediscovery.org/how_to_publish/
- 如何加 ARD 支持：https://agenticresourcediscovery.org/how_to_build_a_client/
- hf-discover：https://github.com/huggingface/hf-discover
