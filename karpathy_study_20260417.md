# karpathy_study — 反向传播 + GPT 源码逆向（2026-04-17）

## 任务
研究 Karpathy 三个 GitHub 项目（micrograd / nanoGPT / llm.c），提取核心设计，落地到 qclaw workspace。

## 执行

1. **并行扫描**三个仓库结构，确认文件大小
2. **GitHub API** 批量拉取核心文件（raw+json）
3. **读源码**：micrograd engine(2730B) → nn(1613B) → nanoGPT model(16345B) → train(14857B)
4. **写落地 SKILL**：3个文档，共 14KB
5. **更新 MEMORY.md**：追加今日研究记录

## 关键发现

### micrograd（~200行，autograd 引擎）

核心是 `Value` 类：
- `_prev`（前向子节点）+ `_backward`（链式法则闭包）
- `backward()`：拓扑排序 + 反向遍历
- 支持全部 Python 运算符重载，自动构建计算图

nn.py 三层：Module → Neuron(w+b,relu) → Layer → MLP

**可移植到 qclaw**：
- 拓扑排序反向遍历 → evolver 因果链追踪
- `_backward` 闭包注册 → tool_pipeline hook 机制
- `Module.parameters()` 递归收集 → tool_registry 树形收集
- `zero_grad()` → heartbeat 状态重置

### nanoGPT（~600行，GPT-2 实现）

model.py（300行）：
- `GPTConfig`：block_size/vocab_size/n_layer/n_head/n_embd
- `GPT`：wte(wpe) + Block×n_layer + ln_f + lm_head
- `CausalSelfAttention`：Flash Attention 优先 + 手动 fallback
- `from_pretrained`：HuggingFace 权重加载（Conv1D→Linear 转置）
- 权重共享：wte = lm_head

train.py（300行）：
- 梯度累积（simulate larger batch）
- GradScaler（float16 混合精度）
- Cosine LR + warmup
- DDP 多卡并行
- MFU 计算（A100 FLOPS 利用率）

**可移植到 qclaw**：
- inference 只算最后位置 → prompt_cache 分片推理
- Flash Attention 降级 → 工具高效/降级 fallback
- 精细 weight_decay → evolver 置信度分层衰减
- GradScaler → qclaw_compactor token 压缩

## 落地文件

```
karpathy_study/
├── SKILL.md              2.6KB 总纲
├── SKILL-micrograd.md    4.6KB autograd逆向
└── SKILL-nanoGPT.md      7.8KB GPT逆向
```

## MEMORY.md 更新

追加 2026-04-17 条目，记录三个项目核心发现。
