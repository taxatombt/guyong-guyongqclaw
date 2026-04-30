"""
DPO 偏好数据生成工具

用大模型 API 为指定问题生成 chosen/rejected 回答对。
支持 OpenAI / Claude / 本地模型（LM Studio / Ollama）。

数据格式输出：
{
  "chosen": [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "好回答"}],
  "rejected": [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "差回答"}]
}
"""

import os
import sys
import json
import argparse
import time
from tqdm import tqdm

# 可用的 provider
PROVIDERS = {}


def register_provider(name):
    """装饰器：注册 provider"""
    def decorator(func):
        PROVIDERS[name] = func
        return func
    return decorator


@register_provider("openai")
def call_openai(model, messages, api_key=None, base_url=None):
    """调用 OpenAI API（ChatGPT / GPT-4）"""
    import openai
    client = openai.OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    return response.choices[0].message.content


@register_provider("claude")
def call_claude(model, messages, api_key=None):
    """调用 Anthropic Claude API"""
    import anthropic
    client = anthropic.Anthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
    )
    # 将 messages 转换为 Claude 格式
    claude_messages = []
    for msg in messages:
        if msg["role"] == "system":
            continue
        role = "assistant" if msg["role"] == "assistant" else "user"
        claude_messages.append({"role": role, "content": msg["content"]})
    
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=claude_messages
    )
    return response.content[0].text


@register_provider("lmstudio")
def call_lmstudio(model, messages, base_url="http://localhost:1234/v1"):
    """调用 LM Studio 本地模型"""
    import openai
    client = openai.OpenAI(base_url=base_url)
    
    # LM Studio 通常不需要 system prompt 在 messages 中
    response = client.chat.completions.create(
        model=model or "local-model",
        messages=messages,
        temperature=0.8,
    )
    return response.choices[0].message.content


@register_provider("ollama")
def call_ollama(model, messages, base_url="http://localhost:11434/api/chat"):
    """调用 Ollama 本地模型"""
    import requests
    
    # 转换 messages 格式
    ollama_messages = []
    for msg in messages:
        if msg["role"] == "system":
            continue
        ollama_messages.append({"role": msg["role"], "content": msg["content"]})
    
    payload = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
        "options": {"temperature": 0.8}
    }
    
    response = requests.post(base_url, json=payload)
    data = response.json()
    return data["message"]["content"]


def generate_preference_pair(provider, model, question, api_key=None, base_url=None):
    """
    为一个问题生成 chosen 和 rejected 回答
    
    策略：
    1. 用较高 temperature 生成 2 个回答
    2. 用规则/规则+模型评选 preferred / rejected
    """
    
    prompt_question = [
        {"role": "user", "content": question}
    ]
    
    if provider == "lmstudio":
        # lmstudio 生成两个回答
        answer1 = call_lmstudio(model, prompt_question, base_url)
        answer2 = call_lmstudio(model, prompt_question, base_url)
    elif provider == "ollama":
        answer1 = call_ollama(model, prompt_question, base_url)
        answer2 = call_ollama(model, prompt_question, base_url)
    elif provider == "openai":
        answer1 = call_openai(model, prompt_question, api_key, base_url)
        answer2 = call_openai(model, prompt_question, api_key, base_url)
    elif provider == "claude":
        answer1 = call_claude(model, prompt_question, api_key)
        answer2 = call_claude(model, prompt_question, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")
    
    # 简单的规则评选：更长的、包含更多细节的作为 chosen
    def score_answer(answer):
        score = 0
        score += len(answer) * 0.1       # 长度加分
        if '</think>' in answer: score += 2  # 含思维链加分
        if '首先' in answer or '第一' in answer: score += 1  # 有结构
        if '。' in answer: score += len(answer.split('。')) * 0.1  # 句子数
        return score
    
    score1, score2 = score_answer(answer1), score_answer(answer2)
    
    if score1 >= score2:
        chosen, rejected = answer1, answer2
    else:
        chosen, rejected = answer2, answer1
    
    return {
        "chosen": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": chosen}
        ],
        "rejected": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": rejected}
        ]
    }


def generate_synthetic_data(
    questions,
    output_path,
    provider="lmstudio",
    model=None,
    api_key=None,
    base_url=None,
    rate_limit_delay=1.0
):
    """
    批量生成偏好数据
    
    questions: 问题列表或包含问题文本的列表
    output_path: 输出 JSONL 文件路径
    """
    results = []
    
    print(f"使用 provider: {provider}, model: {model or 'default'}")
    print(f"生成 {len(questions)} 个偏好对...")
    
    for i, q in enumerate(tqdm(questions, desc="生成偏好数据")):
        try:
            pair = generate_preference_pair(
                provider=provider,
                model=model,
                question=q if isinstance(q, str) else q.get("question", q.get("text", str(q))),
                api_key=api_key,
                base_url=base_url
            )
            results.append(pair)
            
            # Rate limiting
            if rate_limit_delay > 0:
                time.sleep(rate_limit_delay)
                
        except Exception as e:
            print(f"\n生成失败 (问题 {i+1}): {e}")
            continue
        
        # 每 10 个保存一次（防丢失）
        if (i + 1) % 10 == 0:
            _save_results(results, output_path)
    
    # 最终保存
    _save_results(results, output_path)
    print(f"\n完成！共生成 {len(results)} 个偏好对 -> {output_path}")
    return results


def _save_results(results, output_path):
    """保存到 JSONL"""
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')


# ============================================================
# 默认问题列表（示例）
# ============================================================

DEFAULT_QUESTIONS = [
    "请介绍一下你自己",
    "什么是人工智能？",
    "如何学习编程？",
    "解释一下量子计算的基本原理",
    "写一个 Python 函数来计算斐波那契数列",
    "如何保持健康的生活习惯？",
    "推荐几本科幻小说",
    "解释什么是机器学习",
    "如何提高写作能力？",
    "什么是区块链技术？",
]


def main():
    parser = argparse.ArgumentParser(description="生成 DPO 偏好数据")
    parser.add_argument("--output", type=str, default="data/synthetic_dpo.jsonl", help="输出文件")
    parser.add_argument("--provider", type=str, default="lmstudio", 
                        choices=["openai", "claude", "lmstudio", "ollama"],
                        help="API provider")
    parser.add_argument("--model", type=str, default=None, help="模型名")
    parser.add_argument("--api_key", type=str, default=None, help="API Key")
    parser.add_argument("--base_url", type=str, default=None, help="API Base URL")
    parser.add_argument("--num_samples", type=int, default=10, help="生成数量")
    parser.add_argument("--questions_file", type=str, default=None, 
                        help="问题文件（一行一个问题）")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔（秒）")
    args = parser.parse_args()
    
    # 读取问题
    if args.questions_file:
        with open(args.questions_file, 'r', encoding='utf-8') as f:
            questions = [line.strip() for line in f if line.strip()]
    else:
        questions = DEFAULT_QUESTIONS[:args.num_samples]
    
    generate_synthetic_data(
        questions=questions,
        output_path=args.output,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        rate_limit_delay=args.delay
    )


if __name__ == "__main__":
    main()
