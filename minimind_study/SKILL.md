# MiniMind 项目深度学习与qclaw落地

> 来源：jingyaogong/minimind（⭐48422）
> 学习日期：2026-04-28
> 定位：从零训练64M参数GPT的全流程教程+实现，覆盖7种训练方法

---

## 一、项目概览

**核心卖点**：2小时/3块钱，从零训练一个64M参数的GPT。

**规模**：最小版本体积约为 GPT-3 的 1/2700，普通个人GPU即可训练复现。

**与nanoGPT的区别**：

| 维度 | nanoGPT (Karpathy) | MiniMind |
|------|-------------------|----------|
| 参数量 | 可配置（125M~1.5B） | 固定64M（极小） |
| 训练方法 | 仅Pretrain | 7种（Pretrain/SFT/LoRA/DPO/PPO/GRPO/蒸馏） |
| MoE | 无 | 有（MoE版本） |
| 工具调用 | 无 | 有（Tool Use + Agentic RL） |
| 视觉 | 无 | 有（MiniMind-V） |
| 教育性 | 代码简洁但缺注释 | 大量中文注释+教程 |
| 第三方依赖 | PyTorch only | PyTorch only（零依赖） |
| 数据 | 需自备 | 自带数据集+清洗脚本 |

---

## 二、模型架构（model_minimind.py）

### 2.1 核心类：MiniMindModel + MiniMindLM

```python
class MiniMindModel(nn.Module):
    # 底层Transformer
    def __init__(self, config):
        self.embed_tokens = nn.Embedding(vocab_size, dim)
        self.layers = nn.ModuleList([TransformerBlock(config) for _ in range(n_layers)])
        self.norm = RMSNorm(dim)
        self.freqs_cis = precompute_freqs_cis(dim // n_heads, max_seq_len)

class MiniMindLM(MiniMindModel):
    # 加了LM Head
    def __init__(self, config):
        super().__init__(config)
        self.lm_head = nn.Linear(dim, vocab_size, bias=False)
        # Weight Tying: 共享embedding和lm_head权重
        self.lm_head.weight = self.embed_tokens.weight
```

### 2.2 RMSNorm（代替LayerNorm）

```python
class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-6):
        self.weight = nn.Parameter(torch.ones(dim))
    def forward(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + eps) * self.weight
```

**为什么用RMSNorm？** LayerNorm需要计算均值和方差两步，RMSNorm只计算均方根，省掉均值计算。在LLaMA等现代架构中已成为标配。

### 2.3 Rotary Position Embedding（RoPE）

```python
def precompute_freqs_cis(dim, end):
    # 预计算旋转位置编码的频率
    freqs = 1.0 / (theta ** (torch.arange(0, dim, 2)[:dim//2].float() / dim))
    t = torch.arange(end)
    freqs = torch.outer(t, freqs)
    return torch.polar(torch.ones_like(freqs), freqs)  # 复数形式

def apply_rotary_emb(xq, xk, freqs_cis):
    # 将RoPE应用到Query和Key
    xq_ = torch.view_as_complex(xq.float().reshape(*xq.shape[:-1], -1, 2))
    xk_ = torch.view_as_complex(xk.float().reshape(*xk.shape[:-1], -1, 2))
    xq_out = torch.view_as_real(xq_ * freqs_cis).flatten(3)
    xk_out = torch.view_as_real(xk_ * freqs_cis).flatten(3)
    return xq_out.type_as(xq), xk_out.type_as(xk)
```

**RoPE vs 绝对位置编码（nanoGPT）**：
- nanoGPT用`nn.Embedding(max_seq_len, dim)`，绝对位置，训练时长度固定
- RoPE用旋转矩阵编码相对位置，可外推到更长序列
- LLaMA/Qwen/DeepSeek都用RoPE，已是现代LLM标配

### 2.4 Grouped Query Attention（GQA）

```python
class Attention(nn.Module):
    def __init__(self, config):
        self.n_kv_heads = config.n_kv_heads  # KV头数 < Q头数
        self.n_local_heads = config.n_heads   # Q头数
        # KV heads重复使用，减少KV cache
```

**GQA vs MHA（nanoGPT）**：
- nanoGPT：Q/K/V头数相同（Multi-Head Attention）
- MiniMind：K/V头数< Q头数（Grouped Query Attention）
- 好处：KV cache更小，推理更快，性能几乎不降
- LLaMA-2/3、Mistral、Qwen都用GQA

### 2.5 SwiGLU激活（代替ReLU）

```python
class FeedForward(nn.Module):
    def __init__(self, dim, hidden_dim):
        self.w1 = nn.Linear(dim, hidden_dim, bias=False)
        self.w2 = nn.Linear(hidden_dim, dim, bias=False)
        self.w3 = nn.Linear(dim, hidden_dim, bias=False)  # Gate
    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))  # SwiGLU
```

**SwiGLU = SiLU(x·W1) × (x·W3) · W2**
- 比ReLU多一个gate分支（W3），参数量增加但效果更好
- LLaMA/Mistral/Qwen标配
- nanoGPT用GELU，MiniMind用SiGLU

### 2.6 MoE版本（Mixture of Experts）

```python
class MoE(nn.Module):
    def __init__(self, config):
        self.gate = nn.Linear(dim, num_experts, bias=False)  # 路由器
        self.experts = nn.ModuleList([FeedForward(config) for _ in range(num_experts)])
    def forward(self, x):
        # 每个token只激活top-k个专家（通常k=2）
        router_logits = self.gate(x)
        weights, selected_experts = torch.topk(router_logits, self.top_k)
        # 只计算被选中的专家，跳过其他
```

**MoE vs Dense**：
- Dense：每个token经过所有参数（64M全参与）
- MoE：每个token只经过top-k专家（总参数可能100M+，但每次只激活20M）
- DeepSeek-V3、Mixtral都用MoE

---

## 三、7种训练方法全解析

### 3.1 Pretrain（预训练）

```python
# trainer/train_pretrain.py
# 目标：学习语言的统计规律
# 损失：Next Token Prediction (交叉熵)
# 数据：大规模无标注文本
for batch in dataloader:
    logits = model(X)
    loss = F.cross_entropy(logits.view(-1, vocab_size), Y.view(-1))
    loss.backward()
    optimizer.step()
```

### 3.2 SFT（监督微调）

```python
# trainer/train_sft.py
# 目标：学习指令遵循能力
# 损失：只在response部分计算loss（prompt部分不算）
# 数据：指令-回答对
# 关键：loss_mask屏蔽prompt部分的梯度
for batch in sft_dataloader:
    logits = model(input_ids)
    # shift + loss_mask
    shift_logits = logits[..., :-1, :].contiguous()
    shift_labels = labels[..., 1:].contiguous()
    loss = F.cross_entropy(shift_logits.view(-1, vocab_size),
                          shift_labels.view(-1), reduction='none')
    loss = (loss * loss_mask.view(-1)).sum() / loss_mask.sum()
```

**核心设计**：`loss_mask`只在回答部分计算梯度，不训练模型"记住问题"。这是SFT和Pretrain的关键区别。

### 3.3 LoRA（低秩适配）

```python
# model/model_lora.py
class LoRA(nn.Module):
    def __init__(self, original_layer, rank=8):
        self.original = original_layer
        self.lora_A = nn.Linear(original.in_features, rank, bias=False)
        self.lora_B = nn.Linear(rank, original.out_features, bias=False)
        # 冻结原始参数，只训练A和B
        self.original.weight.requires_grad = False
    def forward(self, x):
        return self.original(x) + self.lora_B(self.lora_A(x))
```

**LoRA = 原始权重冻结 + 低秩增量ΔW = A×B**
- A: (dim, rank), B: (rank, dim)，rank通常4-64
- 可训练参数量：2×dim×rank vs 原始dim²
- 64M模型+rank=8：只训练0.5M参数

### 3.4 DPO（直接偏好优化）

```python
# trainer/train_dpo.py
# 目标：让模型偏好好的回答，拒绝差的回答
# 不需要奖励模型，直接用偏好对训练
# 损失 = -log σ(β × (log π(y_w|x) / π_ref(y_w|x) - log π(y_l|x) / π_ref(y_l|x)))
```

**DPO vs PPO**：
- PPO：需要训练奖励模型→再用奖励信号训练策略→复杂且不稳定
- DPO：直接用偏好对（chosen/rejected）训练→简单稳定
- 但DPO只适用于离线数据，PPO可以在线探索

### 3.5 PPO（近端策略优化）

```python
# trainer/train_ppo.py
# 目标：在线强化学习，让模型生成更好的回答
# 需要：策略模型 + 参考模型 + 奖励模型 + 价值模型
# 4个模型同时运行，内存消耗大
```

### 3.6 GRPO（组相对策略优化）

```python
# trainer/train_grpo.py
# DeepSeek提出的PPO替代方案
# 不需要价值模型！用组内相对排名作为奖励信号
# 对于同一问题生成G个回答，组内排名高的奖励高
```

**GRPO vs PPO**：
- PPO：需要价值模型（4个模型）
- GRPO：不需要价值模型（3个模型），用组内排名替代
- DeepSeek-V3训练用GRPO，成本更低

### 3.7 蒸馏（Knowledge Distillation）

```python
# trainer/train_distill.py
# 目标：大模型→小模型的知识转移
# 损失 = KL散度(小模型logits, 大模型logits)
# 软标签比硬标签包含更多信息
```

---

## 四、数据工程

### 4.1 数据清洗流程

```
原始文本 → Unicode规范化 → 去重 → 分词 → 过滤短文本 → 二进制存储
```

### 4.2 二进制数据格式

```python
# dataset/lm_dataset.py
# 用numpy memmap存储token IDs为uint16
# 节省内存：10亿token只需2GB磁盘
```

---

## 五、对qclaw的落地启发

### 启发1：RoPE替代绝对位置编码

qclaw的记忆检索可以借鉴RoPE：**相对位置比绝对位置更自然**。记忆的"时间距离"比"绝对时间戳"更有意义。

### 启发2：GQA降低推理成本

qclaw多维度判断时，不需要每个维度都维护独立的KV cache。共享KV（GQA模式）可以降低内存。

### 启发3：SwiGLU代替ReLU/GELU

evolver的belief更新公式可以借鉴SwiGLU的gate机制：`更新 = 激活(输入) × 门控(输入)`，而不是简单的线性更新。

### 启发4：SFT的loss_mask设计

qclaw训练时，也应该只在"关键部分"计算梯度。不是所有对话都同等重要——用户明确纠正的部分权重应该更高。

### 启发5：GRPO的组内排名

evolver评估工具/方法时，可以用组内相对排名而非绝对分数。同一任务尝试多个方法，排名高的提升belief，排名低的降低belief。

### 启发6：MoE的条件路由

qclaw的技能系统可以借鉴MoE：不是所有技能每次都激活，根据任务类型只路由到top-k个技能。

### 启发7：LoRA的增量更新

qclaw更新SKILL.md时，不需要重写全部内容（全参数更新），只加增量（LoRA模式）。

### 启发8：蒸馏的知识转移

大模型的知识可以蒸馏到小模型。qclaw可以用GPT-4o生成训练信号，然后蒸馏到本地小模型。

---

## 六、与nanoGPT架构对比总结

| 维度 | nanoGPT | MiniMind |
|------|---------|----------|
| 位置编码 | 绝对位置Embedding | RoPE旋转位置 |
| 注意力 | MHA | GQA |
| 激活函数 | GELU | SwiGLU |
| 归一化 | LayerNorm | RMSNorm |
| 偏置 | 有 | 无（bias=False） |
| MoE | 无 | 有 |
| 训练方法 | Pretrain only | 7种 |
| 数据 | 自备 | 自带+清洗 |
| 教育性 | 代码简洁 | 详尽注释 |

**一句话**：nanoGPT是最简实现，MiniMind是现代LLM架构的完整教程。两者互补：先学nanoGPT理解原理，再学MiniMind掌握现代架构。

---

*学习完成：2026-04-28*
*源码：minimind_study/（README.md + model + trainer + dataset + eval）*
