# Karpathy AI — 学习总纲

> 三个项目：micrograd / nanoGPT / llm.c
> 来源：karpathy/ (GitHub)
> 落地：2026-04-17

---

## 三项目总览

| 项目 | 规模 | 核心 | 落地文件 |
|------|------|------|---------|
| **micrograd** | ~200行 | autograd 引擎，标量计算图，backward 传播 | SKILL-micrograd.md |
| **nanoGPT** | ~600行 | GPT-2 实现，Attention + FFN + 训练循环 | SKILL-nanoGPT.md |
| **llm.c** | ~50KB C | 纯 C 训练，无 PyTorch 依赖 | llmc_README（未深入） |

## 核心设计原则（三个项目共同体现）

### 1. 最小可用（Minimal Viable）

- **micrograd**：100 行 engine + 50 行 nn = 可训练 MLP
- **nanoGPT**：300 行 model.py + 300 行 train.py = 可运行 GPT-2
- **哲学**：先跑通，再优化

### 2. 动态计算图（Dynamic Graph）

- micrograd 用 Python 对象构建 DAG（`_prev` + `_backward` 闭包）
- nanoGPT 用 PyTorch 动态图（每个 batch 重新构建）
- **优势**：灵活性高，调试友好

### 3. 降级设计（Graceful Degradation）

```python
# nanoGPT Flash Attention 降级
if self.flash:
    y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
else:
    # 手动实现，打 warning
```

→ **qclaw 应用**：工具注册 fallback（高效工具优先，降级打日志）

### 4. 权重共享（Weight Tying）

```python
self.transformer.wte.weight = self.lm_head.weight
# token embedding = output projection，省参数
```

→ **qclaw 应用**：evolver confidence ↔ skill_metrics 共用同一 baseline

### 5. 配置热覆写（Config Override）

```python
exec(open('configurator.py').read())  # 运行时覆写
```

→ **qclaw 应用**：agents/agent_types.py 的角色参数化配置

### 6. 精细化 weight decay

```python
# 只有 dim >= 2 的参数做 decay（Embedding/LayerNorm 不做）
decay_params = [p for n, p in param_dict.items() if p.dim() >= 2]
```

→ **qclaw 应用**：evolver 高频规则强约束、低频规则弱约束

## 可移植到 qclaw 的具体设计

### micrograd → qclaw

| 模式 | qclaw 应用 |
|------|-----------|
| 拓扑排序反向遍历 | evolver 因果链追踪 |
| _backward 闭包注册 | agents/tool_pipeline.py 危险模式 hook |
| Module.parameters() 递归收集 | agents/tool_registry.py 工具树收集 |
| zero_grad 梯度清零 | heartbeat 心跳状态重置 |

### nanoGPT → qclaw

| 模式 | qclaw 应用 |
|------|-----------|
| inference 只算最后位置 | prompt_cache 分片推理策略 |
| Flash Attention 降级 | 工具高效/降级 fallback |
| GradScaler 混合精度 | qclaw_compactor token 压缩 |
| Cosine LR + warmup | evolver 置信度 cosine 衰减 |
| MFU 计算 | insights token/cost 计量 |
| DDP 多卡并行 | MultiAgentDispatcher 多 agent 并行 |
| register_buffer（非梯度持久） | agents/tool_registry.py 危险模式注册 |

## 重要认知

**micrograd 是理解 nanoGPT 的钥匙**：
- nanoGPT 的 backprop = micrograd 的 backward
- nanoGPT 的 nn.Module = micrograd 的 Module
- nanoGPT 的 `optimizer.step()` = micrograd 的 `value.grad` 反向累积

**两个项目合起来 = 一个完整的学习系统**：
- micrograd = 梯度引擎
- nanoGPT = 模型架构
- train.py = 优化器 + 数据
- evolver.py = nanoGPT 的 optimizer + data loader

## 落地文件清单

```
karpathy_study/
├── SKILL.md              ← 本文件（总纲）
├── SKILL-micrograd.md    ← autograd 引擎逆向
└── SKILL-nanoGPT.md      ← GPT 实现逆向
```
