"""
MiniMind DPO (Direct Preference Optimization) 训练脚本
基于 jingyaogong/minimind/trainer/train_dpo.py 适配
独立运行，不修改 minimind_study 源码
"""

import os
import sys
import argparse
import time
import warnings
import math

import torch
import torch.nn.functional as F
from torch import optim
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoConfig
from tqdm import tqdm

warnings.filterwarnings('ignore')


# ============================================================
# 数据格式：JSONL，每行格式
# {
#   "chosen": [{"role": "user"/"assistant", "content": "..."}],
#   "rejected": [{"role": "user"/"assistant", "content": "..."}]
# }
# ============================================================

class SimpleDPODataset(Dataset):
    """简化的 DPO 数据集，加载 JSONL 格式的偏好对"""
    
    def __init__(self, file_path: str, tokenizer, max_length: int = 1024):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.padding_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0
        
        # 加载数据
        self.samples = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    self.samples.append(eval(line))
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        chosen = sample['chosen']
        rejected = sample['rejected']
        
        # 构造成完整 prompt
        chosen_text = self.tokenizer.apply_chat_template(
            chosen, tokenize=False, add_generation_prompt=False
        )
        rejected_text = self.tokenizer.apply_chat_template(
            rejected, tokenize=False, add_generation_prompt=False
        )
        
        # Tokenize
        chosen_ids = self.tokenizer(
            chosen_text, truncation=True, max_length=self.max_length,
            padding='max_length', return_tensors='pt'
        )
        rejected_ids = self.tokenizer(
            rejected_text, truncation=True, max_length=self.max_length,
            padding='max_length', return_tensors='pt'
        )
        
        chosen_input_ids = chosen_ids['input_ids'][0]
        rejected_input_ids = rejected_ids['input_ids'][0]
        
        # 生成 loss mask（只在 assistant 部分计算 loss）
        chosen_mask = self._make_loss_mask(chosen_input_ids)
        rejected_mask = self._make_loss_mask(rejected_input_ids)
        
        return {
            'x_chosen': chosen_input_ids[:-1],
            'y_chosen': chosen_input_ids[1:],
            'mask_chosen': chosen_mask[1:],
            'x_rejected': rejected_input_ids[:-1],
            'y_rejected': rejected_input_ids[1:],
            'mask_rejected': rejected_mask[1:],
        }
    
    def _make_loss_mask(self, input_ids):
        """找到 assistant 回复区域的 mask"""
        mask = [0] * len(input_ids)
        # 在 tokenizer 的 special tokens 中，assistant 回复通常以特殊 token 开始
        # 简化处理：从序列后半部分开始 mask（假设 prompt 在前一半）
        # 实际应用中应该解析 chat template 的特殊 token
        seq_len = len(input_ids)
        
        # 简化策略：找到第一个非 pad/eos 的位置作为回复开始
        start_idx = 0
        for i, tid in enumerate(input_ids):
            if tid != self.padding_id and tid != self.tokenizer.eos_token_id:
                start_idx = max(0, i - 1)
                break
        
        # 更简化：从序列 60% 位置开始 mask（假设 prompt 占 40%）
        # 这是保守策略，实际应该用 chat template 解析
        # 参考 minimind 的逻辑：找到 assistant 的 bos token
        assistant_token = self.tokenizer(f'{self.tokenizer.bos_token}assistant\n', 
                                         add_special_tokens=False).input_ids
        eos_token = self.tokenizer(f'{self.tokenizer.eos_token}\n', 
                                   add_special_tokens=False).input_ids
        
        # 查找 assistant 开始位置
        for i in range(len(input_ids) - len(assistant_token)):
            if input_ids[i:i+len(assistant_token)].tolist() == assistant_token:
                start_idx = i + len(assistant_token)
                break
        
        for j in range(start_idx, len(mask)):
            mask[j] = 1
        
        return torch.tensor(mask, dtype=torch.long)


# ============================================================
# DPO 核心算法
# ============================================================

def logits_to_log_probs(logits, labels):
    """
    从 logits 计算每个 token 的 log probability
    logits: (batch, seq_len, vocab_size)
    labels: (batch, seq_len)
    return: (batch, seq_len)
    """
    log_probs = F.log_softmax(logits, dim=-1)
    log_probs_per_token = torch.gather(log_probs, dim=2, index=labels.unsqueeze(2)).squeeze(-1)
    return log_probs_per_token


def dpo_loss(ref_log_probs, policy_log_probs, mask, beta=0.15):
    """
    DPO 核心损失函数
    
    ref_log_probs: (batch, seq_len) 参考模型的 log prob
    policy_log_probs: (batch, seq_len) 当前策略模型的 log prob
    mask: (batch, seq_len) 有效位置 mask
    beta: DPO 温度参数
    
    公式: loss = -log σ(β * (Δlogπ - Δlogπ_ref))
    其中 Δlogπ = log π(y_w|x) - log π(y_l|x)
    """
    # 在 mask 范围内求和
    ref_log_probs = (ref_log_probs * mask).sum(dim=1)  # (batch,)
    policy_log_probs = (policy_log_probs * mask).sum(dim=1)  # (batch,)
    
    batch_size = ref_log_probs.shape[0]
    half = batch_size // 2
    
    # 分离 chosen 和 rejected
    chosen_ref = ref_log_probs[:half]
    rejected_ref = ref_log_probs[half:]
    chosen_policy = policy_log_probs[:half]
    rejected_policy = policy_log_probs[half:]
    
    # DPO 核心公式
    pi_logratios = chosen_policy - rejected_policy      # Δlogπ
    ref_logratios = chosen_ref - rejected_ref           # Δlogπ_ref
    logits = pi_logratios - ref_logratios              # β * (...) / temperature
    
    loss = -F.logsigmoid(beta * logits)
    return loss.mean()


# ============================================================
# 训练循环
# ============================================================

def train_epoch(epoch, model, ref_model, dataloader, optimizer, beta, device, log_interval=10):
    model.train()
    total_loss = 0
    total_dpo = 0
    num_batches = 0
    
    pbar = tqdm(dataloader, desc=f"Epoch {epoch+1}")
    for batch in pbar:
        # 合并 chosen 和 rejected
        x_chosen = batch['x_chosen'].to(device)
        x_rejected = batch['x_rejected'].to(device)
        y_chosen = batch['y_chosen'].to(device)
        y_rejected = batch['y_rejected'].to(device)
        mask_chosen = batch['mask_chosen'].to(device)
        mask_rejected = batch['mask_rejected'].to(device)
        
        x = torch.cat([x_chosen, x_rejected], dim=0)
        y = torch.cat([y_chosen, y_rejected], dim=0)
        mask = torch.cat([mask_chosen, mask_rejected], dim=0)
        
        # 参考模型（冻结，不反向传播）
        with torch.no_grad():
            ref_outputs = ref_model(x)
            ref_log_probs = logits_to_log_probs(ref_outputs.logits, y)
        
        # 策略模型
        outputs = model(x)
        policy_log_probs = logits_to_log_probs(outputs.logits, y)
        
        # DPO 损失
        dpo_loss_val = dpo_loss(ref_log_probs, policy_log_probs, mask, beta=beta)
        
        # 反向传播
        optimizer.zero_grad()
        dpo_loss_val.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        
        total_loss += dpo_loss_val.item()
        total_dpo += dpo_loss_val.item()
        num_batches += 1
        
        pbar.set_postfix({'loss': f'{dpo_loss_val.item():.4f}'})
    
    avg_loss = total_loss / num_batches
    return avg_loss


def main():
    parser = argparse.ArgumentParser(description="MiniMind DPO Training")
    parser.add_argument("--data_path", type=str, default="data/dpo_example.jsonl", help="DPO 数据路径")
    parser.add_argument("--from_weight", type=str, default="jingyaogong/minimind-3B", 
                        help="SFT 模型路径或 HuggingFace 模型名")
    parser.add_argument("--save_dir", type=str, default="out", help="输出目录")
    parser.add_argument("--save_name", type=str, default="dpo_final", help="保存模型名")
    parser.add_argument("--epochs", type=int, default=1, help="训练轮数")
    parser.add_argument("--batch_size", type=int, default=2, help="batch size")
    parser.add_argument("--learning_rate", type=float, default=4e-8, help="学习率（必须 ≤ 5e-8）")
    parser.add_argument("--beta", type=float, default=0.15, help="DPO 温度参数")
    parser.add_argument("--max_seq_len", type=int, default=1024, help="最大序列长度")
    parser.add_argument("--log_interval", type=int, default=10, help="日志间隔")
    parser.add_argument("--save_interval", type=int, default=100, help="保存间隔（steps）")
    parser.add_argument("--hidden_size", type=int, default=768, help="隐层维度")
    parser.add_argument("--num_layers", type=int, default=8, help="层数")
    parser.add_argument("--device", type=str, default=None, help="设备（自动检测）")
    args = parser.parse_args()
    
    # 设备
    if args.device:
        device = args.device
    else:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"使用设备: {device}")
    
    # 加载 tokenizer 和模型
    print(f"加载模型: {args.from_weight}")
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.from_weight, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(args.from_weight, trust_remote_code=True)
    except Exception as e:
        print(f"从本地加载失败 ({e})，尝试其他方式...")
        # 如果是 MiniMind 架构，尝试从 config 创建
        tokenizer = AutoTokenizer.from_pretrained("j细细iaogong/minimind-3B", trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained("jingyaogong/minimind-3B", trust_remote_code=True)
    
    model = model.to(device)
    
    # 克隆一份作为参考模型（冻结）
    ref_model = AutoModelForCausalLM.from_pretrained(args.from_weight, trust_remote_code=True)
    ref_model = ref_model.to(device)
    ref_model.eval()
    for param in ref_model.parameters():
        param.requires_grad = False
    
    print(f"策略模型参数量: {sum(p.numel() for p in model.parameters()) / 1e6:.2f}M")
    print(f"参考模型参数量: {sum(p.numel() for p in ref_model.parameters()) / 1e6:.2f}M")
    
    # 加载数据集
    print(f"加载数据: {args.data_path}")
    dataset = SimpleDPODataset(args.data_path, tokenizer, max_length=args.max_seq_len)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    print(f"数据集大小: {len(dataset)} 样本")
    
    # 优化器
    optimizer = optim.AdamW(model.parameters(), lr=args.learning_rate)
    
    # 创建输出目录
    os.makedirs(args.save_dir, exist_ok=True)
    
    # 训练循环
    print(f"\n开始训练: {args.epochs} epochs")
    global_step = 0
    
    for epoch in range(args.epochs):
        avg_loss = train_epoch(
            epoch, model, ref_model, dataloader, 
            optimizer, args.beta, device, args.log_interval
        )
        print(f"Epoch {epoch+1} 完成, 平均 loss: {avg_loss:.4f}")
        
        # 保存
        save_path = os.path.join(args.save_dir, f"{args.save_name}_epoch{epoch+1}.pt")
        torch.save({
            'model': model.state_dict(),
            'optimizer': optimizer.state_dict(),
            'epoch': epoch,
            'args': args,
        }, save_path)
        print(f"模型已保存: {save_path}")
    
    # 最终保存
    final_path = os.path.join(args.save_dir, f"{args.save_name}.pt")
    torch.save(model.state_dict(), final_path)
    print(f"最终模型已保存: {final_path}")


if __name__ == "__main__":
    main()
