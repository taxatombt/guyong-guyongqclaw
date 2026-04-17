# Karpathy nanoGPT — GPT 语言模型逆向工程

> 来源：karpathy/nanoGPT (16.3KB model.py + 14.8KB train.py)
> 落地：2026-04-17

## 核心定位

最小可运行的 GPT 实现（Attention + FFN + LayerNorm）。model.py 约 300 行，train.py 约 300 行。

## model.py — GPT 架构

### 组件层级

```
GPT
├── transformer
│   ├── wte (Embedding: vocab_size → n_embd)
│   ├── wpe (Embedding: block_size → n_embd, 位置编码)
│   ├── h (ModuleList of Block × n_layer)
│   │   └── Block × n_layer
│   │       ├── ln_1 (LayerNorm)
│   │       ├── attn (CausalSelfAttention)
│   │       ├── ln_2 (LayerNorm)
│   │       └── mlp (MLP: n_embd → 4×n_embd → n_embd, GELU)
│   └── ln_f (LayerNorm)
└── lm_head (Linear: n_embd → vocab_size)
```

### GPTConfig 默认值（GPT-2 124M）

| 参数 | 值 | 说明 |
|------|-----|------|
| block_size | 1024 | 上下文长度 |
| vocab_size | 50304 | GPT-2 50257 填充到 64 倍数 |
| n_layer | 12 | Transformer 层数 |
| n_head | 12 | 注意力头数 |
| n_embd | 768 | 嵌入维度 |
| bias | True | Linear/LayerNorm 是否加 bias |

### 权重共享（Weight Tying）

```python
self.transformer.wte.weight = self.lm_head.weight
# token embedding 和 output projection 共享权重
# 省参数量，但不省计算量
```

### 训练流程（forward）

```python
def forward(self, idx, targets=None):
    b, t = idx.size()
    pos = torch.arange(0, t, device=idx.device)  # 位置 ID
    
    tok_emb = self.transformer.wte(idx)  # (b, t, n_embd)
    pos_emb = self.transformer.wpe(pos)  # (t, n_embd)
    x = self.transformer.drop(tok_emb + pos_emb)
    
    for block in self.transformer.h:
        x = block(x)                      # 12层 Transformer
    x = self.transformer.ln_f(x)          # 最终 LayerNorm
    
    if targets is not None:
        logits = self.lm_head(x)
        loss = F.cross_entropy(
            logits.view(-1, logits.size(-1)),
            targets.view(-1), ignore_index=-1
        )
    else:  # inference 优化：只算最后一个位置
        logits = self.lm_head(x[:, [-1], :])
        loss = None
    return logits, loss
```

**inference 优化**：不需要算整个序列的 logits，只算最后位置，省计算量。

### Attention 实现

```python
# Flash Attention（PyTorch 2.0+，优先）
if self.flash:
    y = F.scaled_dot_product_attention(
        q, k, v,
        attn_mask=None,
        dropout_p=self.dropout if self.training else 0,
        is_causal=True  # 自动生成 causal mask
    )
else:
    # 手动实现
    att = (q @ k.transpose(-2, -1)) / math.sqrt(k.size(-1))
    att = att.masked_fill(self.bias[:,:,:T,:T] == 0, float('-inf'))
    att = F.softmax(att, dim=-1)
    y = att @ v
```

**因果 mask**：`torch.tril(...)` 保证只attend到当前位置及之前。

### 预训练权重加载

```python
@classmethod
def from_pretrained(cls, model_type):
    # 从 HuggingFace GPT2LMHeadModel 加载权重
    model_hf = GPT2LMHeadModel.from_pretrained(model_type)
    sd_hf = model_hf.state_dict()
    
    # Conv1D → Linear 转置（GPT-2 用 Conv1D，nanoGPT 用 Linear）
    transposed = ['attn.c_attn.weight', 'attn.c_proj.weight',
                  'mlp.c_fc.weight', 'mlp.c_proj.weight']
    for k in sd_keys_hf:
        if any(k.endswith(w) for w in transposed):
            sd[k].copy_(sd_hf[k].t())  # 转置
        else:
            sd[k].copy_(sd_hf[k])
```

### 优化器配置

```python
def configure_optimizers(self, weight_decay, lr, betas, device):
    # 2D 参数 weight decay，1D 参数不 decay
    decay_params = [p for n, p in param_dict.items() if p.dim() >= 2]
    nodecay_params = [p for n, p in param_dict.items() if p.dim() < 2]
    optimizer = torch.optim.AdamW(decay_params, lr=lr, betas=betas)
    
    # fused AdamW（CUDA 融合核，省显存）
    fused_available = 'fused' in inspect.signature(torch.optim.AdamW).parameters
    use_fused = fused_available and 'cuda' in device
```

**关键设计**：bias/LayerNorm 参数不做 weight decay，符合 GPT-2 原版设置。

## train.py — 训练循环

### 核心流程

```
初始化 → 数据加载 → 模型 → 优化器 → 编译(compile) → 训练循环
                                              ├── 学习率调度 (cosine warmup)
                                              ├── forward + backward
                                              ├── GradScaler (float16)
                                              ├── 梯度裁剪 (clip)
                                              ├── 评估 + Checkpoint
                                              └── 日志
```

### 学习率调度（Cosine with Warmup）

```python
def get_lr(it):
    if it < warmup_iters:
        return learning_rate * (it + 1) / (warmup_iters + 1)  # 线性 warmup
    if it > lr_decay_iters:
        return min_lr  # 最终退火到 min_lr
    # Cosine 衰减
    decay_ratio = (it - warmup_iters) / (lr_decay_iters - warmup_iters)
    coeff = 0.5 * (1.0 + math.cos(math.pi * decay_ratio))
    return min_lr + coeff * (learning_rate - min_lr)
```

### 混合精度（GradScaler）

```python
ptdtype = {'float32': torch.float32,
           'bfloat16': torch.bfloat16,
           'float16': torch.float16}[dtype]
ctx = torch.amp.autocast(device_type=device_type, dtype=ptdtype)
scaler = torch.cuda.amp.GradScaler(enabled=(dtype == 'float16'))

# 训练步
with ctx:
    logits, loss = model(X, Y)
scaler.scale(loss).backward()
if grad_clip:
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
scaler.step(optimizer)
scaler.update()
```

### DDP 分布式训练

```python
ddp = int(os.environ.get('RANK', -1)) != -1
if ddp:
    model = DDP(model, device_ids=[ddp_local_rank])
    # 梯度同步只在最后一个 micro_step
    model.require_backward_grad_sync = (micro_step == gradient_accumulation_steps - 1)
```

### MFU 计算（Model FLOPS Utilization）

```python
def estimate_mfu(model, fwdbwd_per_iter, dt):
    N = model.get_num_params()
    L, H, Q, T = cfg.n_layer, cfg.n_head, cfg.n_embd//cfg.n_head, cfg.block_size
    flops_per_token = 6*N + 12*L*H*Q*T
    flops_per_fwdbwd = flops_per_token * T
    mfu = flops_per_fwdbwd * fwdbwd_per_iter * (1.0/dt) / 312e12
    return mfu  # A100 bfloat16 峰值 FLOPS = 312 TFLOPS
```

## qclaw 可移植设计点

### 1. Flash Attention 降级设计

```python
self.flash = hasattr(torch.nn.functional, 'scaled_dot_product_attention')
if not self.flash:
    print("WARNING: using slow attention...")
    self.register_buffer("bias", torch.tril(...))
```

**qclaw 应用**：OpenClaw 的工具 fallback 机制——优先用高效工具，降级到简单工具并打 warning。

### 2. inference 优化（只算最后一个位置）

```python
# train 时：算整个序列的 loss
logits = self.lm_head(x)  # (b, t, vocab)
loss = F.cross_entropy(...)

# inference 时：只算最后位置
logits = self.lm_head(x[:, [-1], :])  # (b, 1, vocab)
```

**qclaw 应用**：agents/prompt_cache_manager.py 的分片推理策略——评估用全量，生产用单点。

### 3. weight_decay 精细化配置

```python
# 只有 dim >= 2 的参数做 weight decay
# Embedding、LayerNorm bias 不做 decay
```

**qclaw 应用**：evolver 的规则按重要度分层 decay——高频高置信度规则强约束，低频低置信度规则弱约束。

### 4. 配置覆盖机制

```python
config_keys = [k for k,v in globals().items() if not k.startswith('_')
               and isinstance(v, (int, float, bool, str))]
exec(open('configurator.py').read())  # 从命令行覆写
config = {k: globals()[k] for k in config_keys}
```

**qclaw 应用**：agents/agent_types.py 的角色配置热覆写，或 skill registry 的参数化 skill。

### 5. CausalSelfAttention 的 causal mask 注册

```python
self.register_buffer("bias", torch.tril(torch.ones(config.block_size, config.block_size))
                              .view(1, 1, config.block_size, config.block_size))
# register_buffer：自动移动到正确设备，且不参与梯度计算
```

**qclaw 应用**：agents/tool_pipeline.py 的危险模式注册表（持久但不参与推理）。

## nanoGPT vs qclaw 对照

| nanoGPT 概念 | qclaw 对应 |
|------------|-----------|
| Token Embedding (wte) | evolver.record() — 输入编码 |
| Positional Encoding (wpe) | memory 时间戳 |
| Transformer Block | agents/agent_types.py 四角色 |
| LayerNorm | agents/tool_pipeline.py 标准化 |
| Attention (causal mask) | agents/exec_adapter.py 权限过滤 |
| Weight Tying | agents/prompt_cache_manager.py 缓存复用 |
| GradScaler (float16) | qclaw_compactor 上下文压缩 |
| Cosine LR decay | evolver 置信度衰减 |
| MFU | insights token/cost 计量 |
| DDP | MultiAgentDispatcher 多 agent 并行 |

## llm.c 补充（C 训练）

**train_gpt2.c (50KB)**：纯 C/CUDA 实现 GPT-2 训练，无 PyTorch 依赖。
- 直接用 CUDA kernel
- 多卡用 NCCL 或 MPI
- 参考：llmc/ 目录下 llama2.c 的 C 版本
