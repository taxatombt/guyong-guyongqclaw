"""
nanoGPT Model — 精简自 karpathy/nanoGPT
https://github.com/karpathy/nanoGPT

关键设计:
- 因果注意力 (Causal Self-Attention)
- RoPE 旋转位置编码 (从 MiniMind)
- GQA 分组查询注意力 (Grouped Query Attention)
- Weight Tying (embedding = lm_head)
- Flash Attention (PyTorch 2.0+)
- last-token 推理优化: inference 时只算最后位置的 logits

⚠️ 这是教学用精简版 (~300行)，删除了:
- 深度压缩 (DeepSpeed/gradient checkpointing)
- 完整优化器重初始化
- 多GPU DDP
"""

import math
import inspect
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
from torch.nn import functional as F


# ─────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────

@dataclass
class GPTConfig:
    """GPT 模型配置"""
    vocab_size: int = 50257
    block_size: int = 1024
    n_layer: int = 12
    n_head: int = 12
    n_embd: int = 768
    dropout: float = 0.0
    bias: bool = True
    # RoPE 参数 (从 MiniMind)
    rope_theta: float = 10000.0
    rope_dim: Optional[int] = None  # None = n_embd // n_head
    # GQA 参数 (从 MiniMind)
    num_kv_heads: int = 0  # 0 = n_head (标准 MHA)
    # MoE 参数 (可选)
    use_moe: bool = False
    num_experts: int = 8
    moe_top_k: int = 2


# ─────────────────────────────────────────────────────────────────
# RMSNorm (from MiniMind)
# ─────────────────────────────────────────────────────────────────

class RMSNorm(nn.Module):
    """Root Mean Square Layer Normalization
    
    比 LayerNorm 少一个 bias 参数，训练更稳定。
    """
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        norm = x.pow(2).mean(-1, keepdim=True).add(self.eps).rsqrt()
        return x * norm * self.weight


# ─────────────────────────────────────────────────────────────────
# RoPE — 旋转位置编码 (from MiniMind)
# ─────────────────────────────────────────────────────────────────

def precompute_freqs_cis(
    seq_len: int,
    dim: int,
    theta: float = 10000.0,
    device: Optional[torch.device] = None,
) -> torch.Tensor:
    """预计算 RoPE 频率，复用时直接查表 O(1)
    
    RoPE 核心思想：用旋转矩阵编码位置信息，
    attention score = q·k 的位置相关性通过旋转自然引入。
    """
    assert dim % 2 == 0
    # 频率倒数的指数
    freqs = 1.0 / (theta ** (torch.arange(0, dim, 2, device=device).float() / dim))
    # 生成位置
    t = torch.arange(seq_len, device=device)
    # 外积得到 (seq_len, dim//2)
    freqs = torch.outer(t, freqs)
    # 转为复数角度
    freqs_cis = torch.polar(torch.ones_like(freqs), freqs)
    return freqs_cis


def apply_rotary_pos_emb(
    q: torch.Tensor,
    k: torch.Tensor,
    freqs_cis: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """对 q/k 应用 RoPE
    
    重要：只对 head 的前半部分 (dim//2) 做旋转，
    后半部分保持不变。这是一种 ALiBi 或类似的设计。
    """
    _, seq_len, n_heads, head_dim = q.shape
    assert head_dim * 2 == freqs_cis.shape[-1]
    
    # 转为复数格式 (real, imag) → 旋转后转回 real
    q_complex = torch.view_as_complex(q.float().reshape(*q.shape[:-1], -1, 2))
    k_complex = torch.view_as_complex(k.float().reshape(*k.shape[:-1], -1, 2))
    
    # 旋转
    q_out = torch.view_as_real(q_complex * freqs_cis.unsqueeze(0).unsqueeze(2)).flatten(-2).type_as(q)
    k_out = torch.view_as_real(k_complex * freqs_cis.unsqueeze(0).unsqueeze(2)).flatten(-2).type_as(k)
    
    return q_out, k_out


# ─────────────────────────────────────────────────────────────────
# Attention — Causal Self-Attention + GQA + Flash
# ─────────────────────────────────────────────────────────────────

class CausalSelfAttention(nn.Module):
    """因果自注意力 + GQA + Flash Attention
    
    GQA (Grouped Query Attention): 
    - Query: n_head 个头
    - Key/Value: num_kv_heads 个头 (通常 n_head > num_kv_heads)
    - K/V 在所有 Query 头间共享，大幅减少 KV cache 内存
    """

    def __init__(self, config: GPTConfig):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        
        self.n_head = config.n_head
        self.n_kv_head = config.num_kv_heads if config.num_kv_heads > 0 else config.n_head
        self.head_dim = config.n_embd // config.n_head
        self.rope_dim = config.rope_dim or self.head_dim
        
        # Q, K, V 投影 (Q 用 n_head, K/V 用 num_kv_heads)
        self.w_qkv = nn.Linear(config.n_embd, (self.n_head + 2 * self.n_kv_head) * self.head_dim, bias=config.bias)
        self.w_out = nn.Linear(config.n_embd, config.n_embd, bias=config.bias)
        
        self.dropout = config.dropout
        self.flash = hasattr(F, 'scaled_dot_product_attention')
        
        if not self.flash:
            # 手动 causal mask
            self.register_buffer(
                'causal_mask',
                torch.tril(torch.ones(config.block_size, config.block_size))
                    .view(1, 1, config.block_size, config.block_size)
            )
        
        # RoPE 频率缓存
        self.max_seq_len = config.block_size
        self._freqs_cis = None

    def forward(
        self,
        x: torch.Tensor,
        freqs_cis: Optional[torch.Tensor] = None,
        use_cache: bool = False,
    ):
        B, T, C = x.size()  # batch, seq_len, n_embd
        
        # QKV 投影
        qkv = self.w_qkv(x)
        q_size = self.n_head * self.head_dim
        q, k, v = qkv.split([q_size, self.n_kv_head * self.head_dim, self.n_kv_head * self.head_dim], dim=-1)
        
        # reshape: (B, T, n_head, head_dim)
        q = q.view(B, T, self.n_head, self.head_dim)
        k = k.view(B, T, self.n_kv_head, self.head_dim)
        v = v.view(B, T, self.n_kv_head, self.head_dim)
        
        # RoPE (只在 q/k 的前半部分做)
        if freqs_cis is not None and self.rope_dim > 0:
            q_rope, k_rope = q[..., :self.rope_dim], k[..., :self.rope_dim]
            q_rem, k_rem = q[..., self.rope_dim:], k[..., self.rope_dim:]
            q_rope, k_rope = apply_rotary_pos_emb(q_rope, k_rope, freqs_cis)
            q = torch.cat([q_rope, q_rem], dim=-1)
            k = torch.cat([k_rope, k_rem], dim=-1)
        
        # GQA: 如果 n_kv_head < n_head，需要把 k/v 扩展到所有 query 头
        if self.n_kv_head < self.n_head:
            n_rep = self.n_head // self.n_kv_head
            k = k.repeat_interleave(n_rep, dim=2)  # (B, T, n_head, head_dim)
            v = v.repeat_interleave(n_rep, dim=2)
        
        # attention
        if self.flash:
            y = F.scaled_dot_product_attention(
                q, k, v,
                attn_mask=None,
                dropout_p=self.dropout if self.training else 0,
                is_causal=True,
            )
        else:
            att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(self.head_dim))
            att = att.masked_fill(self.causal_mask[:, :, :T, :T] == 0, float('-inf'))
            att = F.softmax(att, dim=-1)
            y = att @ v
        
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.w_out(y)


# ─────────────────────────────────────────────────────────────────
# FFN / MoE
# ─────────────────────────────────────────────────────────────────

class MLP(nn.Module):
    """标准 FFN: GELU(xW1)W2"""
    def __init__(self, config: GPTConfig):
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd, bias=config.bias)
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd, bias=config.bias)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x):
        x = self.c_fc(x)
        x = F.gelu(x, approximate='tanh')
        x = self.c_proj(x)
        return self.dropout(x)


class MoEFeedForward(nn.Module):
    """Mixture of Experts FFN
    
    每个 token 只激活 top-k 个 expert，
    大幅减少激活参数，适合小模型的稀疏激活。
    """
    def __init__(self, config: GPTConfig):
        super().__init__()
        self.num_experts = config.num_experts
        self.top_k = config.moe_top_k
        self.experts = nn.ModuleList([nn.Linear(4 * config.n_embd, config.n_embd, bias=config.bias) 
                                       for _ in range(self.num_experts)])
        self.gate = nn.Linear(config.n_embd, self.num_experts, bias=False)

    def forward(self, x):
        B, T, C = x.shape
        gate_logits = self.gate(x)  # (B, T, num_experts)
        weights, selected = torch.topk(gate_logits, self.top_k, dim=-1)
        weights = F.softmax(weights, dim=-1)  # (B, T, top_k)
        
        out = torch.zeros(B, T, C, device=x.device, dtype=x.dtype)
        for k in range(self.top_k):
            expert_idx = selected[..., k]
            w = weights[..., k].unsqueeze(-1)  # (B, T, 1)
            for e in range(self.num_experts):
                mask = expert_idx == e  # (B, T)
                if mask.any():
                    expert_out = self.experts[e](x[mask])
                    out[mask] += expert_out * w[mask]
        return out


# ─────────────────────────────────────────────────────────────────
# Block — 单个 Transformer 层
# ─────────────────────────────────────────────────────────────────

class Block(nn.Module):
    """单个 Transformer Block"""
    def __init__(self, config: GPTConfig):
        super().__init__()
        self.attn = CausalSelfAttention(config)
        self.ffn = MoEFeedForward(config) if config.use_moe else MLP(config)
        self.ffn_norm = RMSNorm(config.n_embd)
        self.attn_norm = RMSNorm(config.n_embd)

    def forward(self, x, freqs_cis=None):
        x = x + self.attn(self.attn_norm(x), freqs_cis)
        x = x + self.ffn(self.ffn_norm(x))
        return x


# ─────────────────────────────────────────────────────────────────
# GPT — 完整模型
# ─────────────────────────────────────────────────────────────────

class GPT(nn.Module):
    """完整 GPT 模型
    
    关键设计:
    - RoPE 替代绝对位置编码
    - Weight Tying: wte.weight = lm_head.weight (省参数量)
    - RMSNorm 替代 LayerNorm
    - GQA 减少 KV cache
    """

    def __init__(self, config: GPTConfig):
        super().__init__()
        self.config = config
        
        # Token Embedding
        self.wte = nn.Embedding(config.vocab_size, config.n_embd)
        # RoPE 位置编码 (不用 wpe)
        self.freqs_cis = None
        
        # Transformer Blocks
        self.h = nn.ModuleList([Block(config) for _ in range(config.n_layer)])
        self.ln_f = RMSNorm(config.n_embd)
        
        # Language Model Head
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        
        # Weight Tying: lm_head 和 wte 共享权重
        self.lm_head.weight = self.wte.weight
        
        # 初始化
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx: torch.Tensor, targets: Optional[torch.Tensor] = None):
        """前向传播
        
        ⚡ 推理优化 (last-token 模式):
        当 targets=None 时，只算最后位置的 logits，
        不算整个序列的 logits。O(T) → O(1)
        """
        B, T = idx.size()
        device = idx.device
        
        # RoPE 频率 (lazy init，缓存复用)
        if self.freqs_cis is None or self.freqs_cis.shape[0] < T:
            self.freqs_cis = precompute_freqs_cis(
                max(T, self.config.block_size),
                self.config.rope_dim or self.config.n_embd // self.config.n_head,
                self.config.rope_theta,
                device,
            )
        freqs_cis = self.freqs_cis[:T]
        
        # Token embeddings
        x = self.wte(idx)
        
        # Transformer blocks
        for block in self.h:
            x = block(x, freqs_cis)
        x = self.ln_f(x)
        
        # LM head
        if targets is not None:
            # 训练模式: 算所有 token 的 logits
            logits = self.lm_head(x)
            loss = F.cross_entropy(
                logits.view(-1, logits.size(-1)),
                targets.view(-1),
                ignore_index=-1,
            )
        else:
            # ⚡ 推理优化: 只算最后位置的 logits (last-token 模式)
            # 注意用 [[-1]] 而不是 [-1] 来保留时间维度
            logits = self.lm_head(x[:, [-1], :])
            loss = None
        
        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        idx: torch.Tensor,
        max_new_tokens: int,
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ):
        """自回归生成
        
        每次只 forward 一次 (last-token 优化后，forward 本身已经很快)
        然后把预测的 token 追加到序列，继续生成。
        """
        for _ in range(max_new_tokens):
            # 截断到 block_size
            idx_cond = idx if idx.size(1) <= self.config.block_size else idx[:, -self.config.block_size:]
            
            # forward (last-token 优化在 forward 内部)
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / temperature  # 最后 token 的 logits
            
            # top-k 过滤
            if top_k is not None:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float('-inf')
            
            # 采样
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat([idx, idx_next], dim=1)
        
        return idx

    def estimate_mfu(self, fwdbwd_per_iter: float, dt: float) -> float:
        """估算 Model FLOPs Utilization (MFU)
        
        MFU = 实际 FLOPS / 理论峰值 FLOPS
        
        参考 PaLM paper Appendix B:
        https://arxiv.org/abs/2204.02311
        
        Args:
            fwdbwd_per_iter: 每次迭代的 forward+backward 次数
            dt: 每次迭代耗时 (秒)
        """
        N = self.get_num_params()
        cfg = self.config
        L, H, Q, T = cfg.n_layer, cfg.n_head, cfg.n_embd // cfg.n_head, cfg.block_size
        
        # 每个 token 的 FLOPs
        flops_per_token = 6 * N + 12 * L * H * Q * T
        flops_per_fwdbwd = flops_per_token * T
        flops_per_iter = flops_per_fwdbwd * fwdbwd_per_iter
        
        # A100 bfloat16 峰值 = 312 TFLOPS
        flops_achieved = flops_per_iter / dt
        flops_promised = 312e12
        
        mfu = flops_achieved / flops_promised
        return mfu

    def get_num_params(self, non_embedding: bool = True) -> int:
        """返回模型参数量"""
        n = sum(p.numel() for p in self.parameters())
        if non_embedding:
            n -= self.wte.weight.numel()  # 减去 embedding (weight tying)
        return n
