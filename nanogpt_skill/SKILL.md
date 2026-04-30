# nanoGPT Skill — 从零构建小型 GPT

> 基于 karpathy/nanoGPT 源码深度逆向工程
> 代码路径: `nanogpt_skill/model.py`, `train.py`, `sample.py`

---

## 快速开始

```bash
# 1. 准备数据 (任意文本文件)
echo "Hello world" > data/input.txt

# 2. 训练 (最简配置)
python train.py --data_path data/input.txt --n_layer 4 --n_head 4 --n_embd 128 --max_iters 1000

# 3. 生成
python sample.py --checkpoint out/ckpt_best.pt --prompt "Hello"
```

---

## 架构设计

### 文件结构

```
nanogpt_skill/
├── model.py    ← GPT 模型 (14KB, ~400行)
├── train.py    ← 训练脚本 (10KB)
├── sample.py   ← 文本生成脚本 (4KB)
└── SKILL.md    ← 本文档
```

### 核心组件 (model.py)

| 类/函数 | 行数 | 功能 |
|--------|------|------|
| `GPTConfig` | ~15 | 模型配置 dataclass |
| `RMSNorm` | ~15 | 无 bias 的 LayerNorm，比标准 LN 更轻 |
| `precompute_freqs_cis` | ~20 | 预计算 RoPE 频率表 |
| `apply_rotary_pos_emb` | ~20 | 对 q/k 施 RoPE 旋转 |
| `CausalSelfAttention` | ~70 | GQA + Flash Attention + RoPE |
| `Block` | ~15 | Transformer Block |
| `GPT` | ~80 | 完整模型 + generate() + estimate_mfu() |

---

## 关键技术点

### 1. RoPE 旋转位置编码

**原理**: 不使用绝对位置编码，而是把位置信息编码成旋转矩阵，加到 attention 的 q/k 上。

```python
# 旋转角度 = θ^(2i/d)
freqs = 1.0 / (theta ** (2i / d))
# q 和 k 都旋转后，点积自然带有相对位置信息
```

**优势**: 
- 理论上有更好的外推能力 (外推到更长序列)
- 不需要学习位置参数
- 被 LLaMA、MiniMind 等现代模型广泛采用

### 2. GQA — Grouped Query Attention

**问题**: 标准 MHA 中，K/V 头数 = Q 头数，每个 token 都要存完整的 K/V。

**GQA 解法**: K/V 头数 < Q 头数，多个 query 头共享同一个 K/V 头。

```python
self.n_kv_head = 4  # 少 KV 头
self.n_head = 8    # 多 Query 头

# K/V 需要复制扩展到所有 Query 头
k = k.repeat_interleave(n_head // n_kv_head, dim=2)
```

**效果**: KV cache 减少 50%+，而不显著损失 attention 质量。

### 3. last-token 推理优化

**关键代码** (model.py forward):

```python
if targets is not None:
    # 训练模式: 算所有 token
    logits = self.lm_head(x)
    loss = F.cross_entropy(logits.view(-1, ...), targets.view(-1), ...)
else:
    # ⚡ 推理优化: 只算最后位置的 logits
    # x[:, [-1], :] 而不是 x[:, -1, :]，保留时间维度
    logits = self.lm_head(x[:, [-1], :])
    loss = None
```

**为什么有效**: 
- 自回归生成时，每次 forward 只需要最后一个 token 的 logits
- 完整序列的 logits (O(T)) → 只算最后 token (O(1))
- 这个优化在 `generate()` 的每次迭代中省去 T-1 次冗余计算

### 4. MFU — Model FLOPs Utilization

**概念**: 实际 FLOPS / 理论峰值 FLOPS。衡量 GPU 利用率的黄金指标。

```python
def estimate_mfu(self, fwdbwd_per_iter, dt):
    N = self.get_num_params()
    # PaLM paper 公式:
    flops_per_token = 6*N + 12*L*H*Q*T
    flops_per_iter = flops_per_token * T * fwdbwd_per_iter
    flops_achieved = flops_per_iter / dt
    flops_promised = 312e12  # A100 bfloat16 peak = 312 TFLOPS
    return flops_achieved / flops_promised
```

**典型值**:
- 30-40%: 低效实现或小模型
- 40-55%: 正常实现
- 55-70%: 高效实现 (Flash Attention + 编译)
- 70%+: 接近硬件极限

### 5. Weight Tying

```python
# lm_head 和 token embedding 共享权重
self.lm_head.weight = self.wte.weight
```

**效果**: 节省 vocab_size × n_embd 个参数。对于大 vocab 模型（50k+）效果显著。

### 6. Flash Attention

```python
if self.flash:
    y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
else:
    # 手动实现，PyTorch 2.0+ 自动用 CUDA kernel 加速
    att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(head_dim))
    att = att.masked_fill(bias == 0, float('-inf'))
    y = att @ v
```

Flash Attention 把 attention 从 O(T²) 内存降到 O(T)，同时实际运行更快。

---

## MFU → evolver.py 落地

从 nanoGPT 的 MFU 设计中学到的: **量化才有反馈**。

已在 evolver.py 中实现 (Lines 599-645):
```python
def confidence(self):
    """Hybrid confidence: recomputed base + accumulated signal."""
    base = compute_from_counts()
    signal = self.confidence_signal  # Karpathy grad+=
    return 0.7 * base + 0.3 * signal

def accumulate_signal(self, delta):
    self.confidence_signal *= self.confidence_decay  # 旧信号衰减
    self.confidence_signal += delta  # 新信号累积 (grad+=)
```

---

## 训练参数参考

| 配置 | 小型 | 中型 | 大型 |
|------|------|------|------|
| n_layer | 4-6 | 8-12 | 16-32 |
| n_head | 4-8 | 8-16 | 16-32 |
| n_embd | 128-256 | 384-768 | 1024+ |
| block_size | 128-256 | 512-1024 | 1024+ |
| 参数量 | ~10M | ~100M | ~1B |
| GPU 显存 | ~1GB | ~8GB | ~24GB |

---

## 已知限制

1. **字符级 tokenization**: 简单但效率低，适合演示，不适合生产
2. **无 EOS/padding token**: 生成会一直持续到 max_new_tokens
3. **RoPE 外推**: 理论上支持外推，但实际效果取决于训练数据
4. **单 GPU**: 未包含 DDP 分布式训练支持

---

## 下一步

- 想实际训练一个模型? → 准备一个文本文件，运行 train.py
- 想理解注意力机制? → 从 micrograd_skill/ 开始
- 想看完整参数调优? → 参考 miniMind (jingyaogong/minimind) 的训练流程
