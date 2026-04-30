"""
nanoGPT 文本生成脚本

从训练好的 checkpoint 生成文本。

用法:
    python sample.py --checkpoint out/ckpt_best.pt --prompt "The quick brown"
    python sample.py --checkpoint out/ckpt_best.pt --prompt_file prompts/story.txt
"""

import os
import argparse
import torch

from model import GPT, GPTConfig


def load_checkpoint(checkpoint_path: str, device: str = 'cuda'):
    """加载 checkpoint"""
    ckpt = torch.load(checkpoint_path, map_location=device)
    config = GPTConfig(**ckpt['config'])
    model = GPT(config)
    model.load_state_dict(ckpt['model'])
    model.to(device)
    model.eval()
    return model, ckpt


def encode_text(text: str, vocab: dict) -> torch.Tensor:
    """把字符串转成 token tensor"""
    ids = [vocab.get(c, 0) for c in text]
    return torch.tensor(ids, dtype=torch.long, device=device).unsqueeze(0)


def decode_text(ids: torch.Tensor, itos: dict) -> str:
    """把 token tensor 转成字符串"""
    return ''.join(itos[i] for i in ids.tolist())


def main():
    parser = argparse.ArgumentParser(description='nanoGPT text generation')
    parser.add_argument('--checkpoint', type=str, default='out/ckpt_best.pt')
    parser.add_argument('--prompt', type=str, default='\n', 
                        help='Starting text (or FILE:path to read from file)')
    parser.add_argument('--max_new_tokens', type=int, default=500)
    parser.add_argument('--temperature', type=float, default=0.8,
                        help='1.0 = no change, <1.0 = less random, >1.0 = more random')
    parser.add_argument('--top_k', type=int, default=200,
                        help='Only sample from top_k most likely tokens')
    parser.add_argument('--num_samples', type=int, default=3,
                        help='Number of samples to generate')
    args = parser.parse_args()
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    if not os.path.exists(args.checkpoint):
        print(f"ERROR: checkpoint not found: {args.checkpoint}")
        print("Train a model first: python train.py --data_path data/input.txt")
        return
    
    model, ckpt = load_checkpoint(args.checkpoint, device)
    print(f"Loaded model from {args.checkpoint} (iter {ckpt.get('iter', '?')})")
    print(f"Params: {model.get_num_params():,}")
    
    # 处理 prompt
    prompt = args.prompt
    if prompt.startswith('FILE:'):
        with open(prompt[5:], 'r', encoding='utf-8', errors='ignore') as f:
            prompt = f.read().strip()
    
    print(f"\nPrompt: {repr(prompt[:50])}")
    print("=" * 60)
    
    # 简单的字符编码 (假设 checkpoint 包含 vocab 信息)
    # 注: 完整实现需要从 meta.pkl 或 checkpoint 中恢复 vocab
    # 这里假设 vocab_size=256 (字节级)
    vocab_size = ckpt['config'].get('vocab_size', 256)
    
    # 生成
    with torch.no_grad():
        for i in range(args.num_samples):
            # 用 prompt 初始化 token 序列
            if vocab_size == 256:
                # 字节级: 直接用字符的 ord 值
                start_ids = torch.tensor(
                    [[ord(c) % 256 for c in prompt]], 
                    dtype=torch.long, device=device
                )
            else:
                # 简单字符映射
                chars = [c for c in prompt]
                start_ids = torch.tensor([[ord(c) % vocab_size for c in chars]], dtype=torch.long, device=device)
            
            # 生成
            torch.manual_seed(1337 + i)
            generated = model.generate(
                start_ids,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_k=args.top_k,
            )
            
            # 解码 (字节级)
            if vocab_size == 256:
                text = ''.join(chr(b) for b in generated[0].tolist())
            else:
                text = ''.join(chr(t % vocab_size) for t in generated[0].tolist())
            
            print(text)
            if i < args.num_samples - 1:
                print("-" * 40)


if __name__ == '__main__':
    main()
