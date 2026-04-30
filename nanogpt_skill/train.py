"""
nanoGPT 训练脚本 — 精简自 karpathy/nanoGPT

关键特性:
- 字符级 tokenization (无需外部 tokenizer)
- Mixed Precision (torch.amp, BF16)
- Flash Attention (PyTorch 2.0+)
- MFU 效率监控
- 梯度累积 (模拟大 batch)
- Learning rate warmup + cosine decay
- 断点续训

使用方法:
    python train.py --data_path data/input.txt --n_layer 6 --n_head 8 --n_embd 256
"""

import os
import time
import math
import json
import argparse
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
from torch.nn import functional as F
from torch.utils.data import Dataset, DataLoader

from model import GPT, GPTConfig


# ─────────────────────────────────────────────────────────────────
# 数据集
# ─────────────────────────────────────────────────────────────────

class CharDataset(Dataset):
    """字符级数据集
    
    把文本转成 token 序列，每个字符对应一个整数 ID。
    优点: 简单，无需外部 tokenizer
    缺点: vocabulary 受限于字符集
    """
    
    def __init__(self, data_path: str, block_size: int = 128, train_ratio: float = 0.9):
        with open(data_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        # 建立字符表
        chars = sorted(set(text))
        self.stoi = {c: i for i, c in enumerate(chars)}
        self.itos = {i: c for c, i in self.stoi}
        self.vocab_size = len(chars)
        
        # 转成 token
        data = [self.stoi[c] for c in text]
        
        # 划分 train/val
        n = int(len(data) * train_ratio)
        self.train_data = data[:n]
        self.val_data = data[n:]
        
        self.block_size = block_size
        print(f"Dataset: {len(text):,} chars, vocab_size={self.vocab_size}, "
              f"train={len(self.train_data):,}, val={len(self.val_data):,}")
    
    def encode(self, s: str) -> list[int]:
        return [self.stoi[c] for c in s if c in self.stoi]
    
    def decode(self, ids: list[int]) -> str:
        return ''.join(self.itos[i] for i in ids if i in self.itos)
    
    def __len__(self):
        return len(self.train_data) - self.block_size
    
    def __getitem__(self, idx: int):
        x = torch.tensor(self.train_data[idx:idx + self.block_size], dtype=torch.long)
        y = torch.tensor(self.train_data[idx + 1:idx + self.block_size + 1], dtype=torch.long)
        return x, y


# ─────────────────────────────────────────────────────────────────
# 学习率调度
# ─────────────────────────────────────────────────────────────────

def get_lr(it: int, config) -> float:
    """Cosine LR schedule with warmup
    
    - warmup_iters: 线性上升
    - 之后: cosine 下降到 min_lr
    """
    if it < config.warmup_iters:
        return config.learning_rate * it / config.warmup_iters
    if it > config.max_iters:
        return config.min_lr
    decay_ratio = (it - config.warmup_iters) / (config.max_iters - config.warmup_iters)
    coeff = 0.5 * (1.0 + math.cos(math.pi * decay_ratio))
    return config.min_lr + coeff * (config.learning_rate - config.min_lr)


# ─────────────────────────────────────────────────────────────────
# 训练
# ─────────────────────────────────────────────────────────────────

@dataclass
class TrainConfig:
    # 模型
    n_layer: int = 6
    n_head: int = 8
    n_embd: int = 256
    block_size: int = 128
    bias: bool = False
    # RoPE
    rope_theta: float = 10000.0
    # 训练
    learning_rate: float = 1e-3
    max_iters: int = 5000
    warmup_iters: int = 100
    min_lr: float = 1e-4
    batch_size: int = 64
    grad_accum_steps: int = 1
    weight_decay: float = 0.1
    # 设备
    device: str = 'cuda' if torch.cuda.is_available() else 'cpu'
    dtype: str = 'bfloat16' if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else 'float16'
    # 效率
    compile: bool = False
    # 日志
    log_interval: int = 100
    eval_interval: int = 500
    save_interval: int = 1000
    out_dir: str = 'out'


def train(config: TrainConfig):
    os.makedirs(config.out_dir, exist_ok=True)
    
    device = torch.device(config.device)
    dtype = {'float32': torch.float32, 'bfloat16': torch.bfloat16, 'float16': torch.float16}[config.dtype]
    
    print(f"Device: {device}, dtype: {dtype}")
    
    # ── 数据 ──
    train_ds = CharDataset(
        data_path=os.path.join(config.out_dir, 'data.txt'),
        block_size=config.block_size,
    )
    val_ds = CharDataset(
        data_path=os.path.join(config.out_dir, 'data.txt'),
        block_size=config.block_size,
        train_ratio=0.9,
    )
    
    train_loader = DataLoader(train_ds, batch_size=config.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=config.batch_size, num_workers=0)
    
    # ── 模型 ──
    model_cfg = GPTConfig(
        vocab_size=train_ds.vocab_size,
        block_size=config.block_size,
        n_layer=config.n_layer,
        n_head=config.n_head,
        n_embd=config.n_embd,
        bias=config.bias,
        rope_theta=config.rope_theta,
    )
    model = GPT(model_cfg)
    model.to(device)
    
    n_params = model.get_num_params()
    print(f"Model: {n_params:,} parameters, vocab_size={train_ds.vocab_size}")
    
    # ── 优化器 ──
    param_dict = {pn: p for pn, p in model.named_parameters() if p.requires_grad}
    decay_params = [p for p in param_dict.values() if p.dim() >= 2]
    nodecay_params = [p for p in param_dict.values() if p.dim() < 2]
    optim_groups = [
        {'params': decay_params, 'weight_decay': config.weight_decay},
        {'params': nodecay_params, 'weight_decay': 0.0},
    ]
    optimizer = torch.optim.AdamW(optim_groups, lr=config.learning_rate, betas=(0.9, 0.95))
    
    # ── 编译 (PyTorch 2.0+) ──
    if config.compile and hasattr(torch, 'compile'):
        print("Compiling model (PyTorch 2.0+)...")
        model = torch.compile(model)
    
    # ── 混合精度 ──
    scaler = torch.amp.GradScaler('cuda', enabled=(dtype == torch.bfloat16))
    
    # ── MFU 追踪 ──
    # MFU = Model FLOPs Utilization = 实际 FLOPS / 理论峰值 FLOPS
    # A100 bfloat16 peak = 312 TFLOPS
    mfu_history = []
    
    # ── 训练循环 ──
    iter_num = 0
    best_val_loss = float('inf')
    
    t0 = time.time()
    cumulative_tokens = 0
    
    while iter_num < config.max_iters:
        # ── validation ──
        if iter_num % config.eval_interval == 0:
            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for x, y in val_loader:
                    x, y = x.to(device), y.to(device)
                    with torch.amp.autocast(device_type='cuda', dtype=dtype):
                        _, loss = model(x, y)
                    val_loss += loss.item()
            val_loss /= len(val_loader)
            
            # MFU
            recent_mfu = mfu_history[-10:] if mfu_history else [0]
            avg_mfu = sum(recent_mfu) / len(recent_mfu)
            
            print(f"step {iter_num:5d} | val_loss={val_loss:.4f} | "
                  f"MFU={avg_mfu:.1%} | best={best_val_loss:.4f}")
            
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                # 保存 best
                ckpt = {
                    'model': model.state_dict(),
                    'config': vars(model_cfg),
                    'val_loss': val_loss,
                    'iter': iter_num,
                }
                torch.save(ckpt, os.path.join(config.out_dir, 'ckpt_best.pt'))
            
            model.train()
        
        # ── training step ──
        for micro_step in range(config.grad_accum_steps):
            x, y = next(iter(train_loader))
            x, y = x.to(device), y.to(device)
            
            with torch.amp.autocast(device_type='cuda', dtype=dtype):
                logits, loss = model(x, y)
                loss = loss / config.grad_accum_steps
            
            scaler.scale(loss).backward()
            cumulative_tokens += x.numel()
        
        # ── optimizer step ──
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)
        
        # ── LR schedule ──
        lr = get_lr(iter_num, config)
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr
        
        # ── MFU 计算 ──
        if iter_num % 10 == 0 and iter_num > 0:
            dt = time.time() - t0
            tokens_per_step = cumulative_tokens / 10
            # fwdbwd_per_iter = 2 (forward + backward for each micro step)
            mfu = model.estimate_mfu(fwdbwd_per_iter=2 * config.grad_accum_steps, dt=dt)
            mfu_history.append(mfu)
            t0 = time.time()
            cumulative_tokens = 0
        
        # ── checkpoint ──
        if iter_num % config.save_interval == 0 and iter_num > 0:
            ckpt = {
                'model': model.state_dict(),
                'config': vars(model_cfg),
                'optimizer': optimizer.state_dict(),
                'iter': iter_num,
                'val_loss': best_val_loss,
            }
            torch.save(ckpt, os.path.join(config.out_dir, f'ckpt_{iter_num}.pt'))
            print(f"  ✓ Saved checkpoint at iter {iter_num}")
        
        iter_num += 1
    
    print(f"\nTraining complete. Best val_loss={best_val_loss:.4f}")


# ─────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='nanoGPT training')
    parser.add_argument('--data_path', type=str, default='data/input.txt', help='Path to text data')
    parser.add_argument('--n_layer', type=int, default=6)
    parser.add_argument('--n_head', type=int, default=8)
    parser.add_argument('--n_embd', type=int, default=256)
    parser.add_argument('--block_size', type=int, default=128)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--learning_rate', type=float, default=1e-3)
    parser.add_argument('--max_iters', type=int, default=5000)
    parser.add_argument('--out_dir', type=str, default='out')
    args = parser.parse_args()
    
    # 复制数据到 out_dir
    os.makedirs(args.out_dir, exist_ok=True)
    if args.data_path != os.path.join(args.out_dir, 'data.txt') and os.path.exists(args.data_path):
        import shutil
        shutil.copy(args.data_path, os.path.join(args.out_dir, 'data.txt'))
    
    config = TrainConfig(
        n_layer=args.n_layer,
        n_head=args.n_head,
        n_embd=args.n_embd,
        block_size=args.block_size,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_iters=args.max_iters,
        out_dir=args.out_dir,
    )
    train(config)


if __name__ == '__main__':
    main()
