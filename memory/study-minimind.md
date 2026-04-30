# MiniMind 项目学习笔记

> 学习时间：2026-04-29
> 原始 repo：jingyaogong/minimind（⭐48.5k, Fork 6k+，非 jiaweizzhao）
> 地址：https://github.com/jingyaogong/minimind

---

## 一、项目概览

MiniMind 是一个**从零训练小型 GPT** 的完整项目，特点是：
- 参数极小：26M / 64M / 108M / 145M / 198M（dense 和 MoE 两版本）
- 训练时间短：2 小时训完 64M 模型
- 技术栈完整：PreTrain → SFT → DPO → GRPO → Tool Calling → 知识蒸馏
- 开源友好：Apache 2.0 许可证，含完整权重

---

## 二、核心架构（model/model_minimind.py）

### 2.1 MiniMindConfig 关键参数

```python
class MiniMindConfig(PretrainedConfig):
    model_type = "minimind"
    def __init__(self,
        hidden_size=768,          # 隐层维度
        num_hidden_layers=8,     # 层数
        use_moe=False,           # 是否用 MoE
        vocab_size=6400,         # 词表大小
        intermediate_size=...,    # FFN 中间维度
        max_position_embeddings=32768,  # 最大上下文
        rope_theta=1e6,          # RoPE 基础频率
        rope_scaling={           # YaRN 扩展
            "beta_fast": 32, "beta_slow": 1,
            "factor": 16, "original_max_position_embeddings": 2048,
            "attention_factor": 1.0, "type": "yarn"
        },
        num_attention_heads=8,   # GQA 查询头数
        num_key_value_heads=4,   # GQA KV 头数（比 query 少 = 节省 cache）
        num_experts=4,           # MoE expert 数量
        num_experts_per_tok=1,   # MoE 每 token 激活 expert 数
        ...
    )
```

### 2.2 关键技术点

#### RoPE（旋转位置编码）+ YaRN 扩展
- 普通 RoPE 的 `θ` = 10000，MiniMind 用 `1e6`（长上下文友好）
- YaRN scaling：当 context 超过预训练长度时自动 scale attention
- 实现：`precompute_freqs_cis()` 计算 cos/sin 旋转矩阵，然后在 attention 中应用

#### Grouped Query Attention（GQA）
- Query: 8 heads, Key/Value: 4 heads（K/V heads 少 → cache 小）
- `repeat_kv()` 将 K/V 在推理时扩展到 Query 维度
- 显存节省 ≈ 50%（相比 MHA）

#### MoE（混合专家）
```python
class MOEFeedForward(nn.Module):
    # 每个 expert 是独立的 FFN
    # top-k routing：选 k=1 个 expert（实际就是稀疏激活）
    # 训练时用 `router_aux_loss` 鼓励负载均衡
```
- MiniMind-MoE：4 experts, 每 token 激活 1 个 expert

#### RMSNorm（无偏置的 LayerNorm）
```python
class RMSNorm(nn.Module):
    def norm(x): return x * (x.pow(2).mean(-1, keepdim=True) + eps)**-0.5
```

---

## 三、训练流程（trainer/ 目录）

### 3.1 阶段总览

| 阶段 | 脚本 | 目标 |
|------|------|------|
| Tokenizer | train_tokenizer.py | BPE 分词 |
| PreTrain | train_pretrain.py | 续写训练（next token prediction）|
| Full SFT | train_full_sft.py | 指令微调 |
| LoRA SFT | train_lora.py | 高效微调 |
| DPO | train_dpo.py | 偏好对齐（比 PPO 简单）|
| GRPO | train_grpo.py | 强化学习优化（无 critic）|
| Tool Calling | train_agent.py | 工具调用 + RL |
| 知识蒸馏 | train_distillation.py | 大模型 → 小模型 |

### 3.2 PreTrain

```python
# train_pretrain.py 核心
model = MiniMindForCausalLM(config)
# 损失：CrossEntropy（next token prediction）
loss = F.cross_entropy(logits[:, :-1], labels[:, 1:])
```

### 3.3 SFT（Supervised Fine-Tuning）

```python
# train_full_sft.py
# 数据格式：[SYSTEM] + [USER] + [ASSISTANT]
# 损失：只在 assistant token 上算 CE，system/prompt mask 掉
mask = labels != -100
loss = F.cross_entropy(logits[mask], labels[mask])
```

### 3.4 DPO（Direct Preference Optimization）

核心思想：直接优化"chosen > rejected"的偏好，不需要 reward model。

```python
# train_dpo.py
def dpo_loss(ref_log_probs, policy_log_probs, mask, beta=0.1):
    # ref_log_probs: 参考模型（一般 SFT 后）的 log prob
    # policy_log_probs: 当前策略模型的 log prob
    # mask: 只在 chosen/rejected 的对应位置算
    
    pi_logps = (policy_log_probs * mask).sum(-1)  # shape: (batch,)
    ref_logps = (ref_log_probs * mask).sum(-1)
    
    # DPO 损失 = -log σ(β * (log π(y_w) - log π(y_l) - log π_ref(y_w) + log π_ref(y_l)))
    loss = -torch.logsigmoid(beta * (pi_logps[won] - pi_logps[lost] - ref_logps[won] + ref_logps[lost]))
```

**核心洞察**：DPO 比 PPO 简单太多：
- 不需要单独训练 reward model
- 不需要 critic network
- 只需要 preference pairs（chosen + rejected）

### 3.5 GRPO（Group Relative Policy Optimization）

MiniMind 的 GRPO 比 PPO 简单得多：

```python
# train_grpo.py 核心
def calculate_rewards(prompts, responses, reward_model):
    rewards = torch.zeros(len(responses))
    for i in range(len(prompts)):
        response = responses[i]
        # 规则奖励：
        # - 长度 20-800 tokens: +0.5 / -0.5
        # - 含 </think> 且长度 20-300: +1.0 / -0.5
        # - reward model 打分
        if '</think>' in response:
            rewards[i] += 1.0
        reward_model_score = reward_model.get_score(messages, answer)
        rewards[i] += reward_model_score
    return rewards
```

**GRPO vs PPO 关键区别**：

| | PPO | GRPO |
|--|-----|------|
| Critic | 需要单独训练 | 不需要 |
| Baseline | GAElambda 估计 | 采样均值作为 baseline |
| 采样 | 一次生成一个 response | 一次生成 G 个（group）|
| 稳定性 | 需要 clipping | 天然稳定（group 内归一化）|

```python
# GRPO 策略梯度
grouped_rewards = rewards.view(-1, num_generations)  # [B, G]
mean_r = grouped_rewards.mean(dim=1)                  # baseline
advantages = (rewards - mean_r) / (rewards.std() + 1e-4)  # 归一化 advantage

# 策略损失 = -E[advantage * log π(a|s)]
```

### 3.6 知识蒸馏（Distillation）

```python
# train_distillation.py
# 核心：让小模型（student）学习大模型（teacher）的输出分布
def distillation_loss(student_logits, teacher_logits, labels, alpha=0.5, temperature=2.0):
    # 硬标签交叉熵
    hard_loss = F.cross_entropy(student_logits, labels)
    # 软标签 KL 散度（温度缩放）
    soft_loss = F.kl_div(
        F.log_softmax(student_logits / temperature),
        F.softmax(teacher_logits / temperature),
        reduction='batchmean'
    ) * (temperature ** 2)
    return alpha * hard_loss + (1 - alpha) * soft_loss
```

### 3.7 Agent / Tool Calling

```python
# train_agent.py
# 数据格式：包含 tool_call 标签的对话
# <tool_call>{"name": "get_weather", "args": {"city": "Beijing"}}</tool_call>
# 奖励信号来自外部（wandb 或规则）

# rollout_engine.py 负责生成 responses
rollout_result = rollout_engine.rollout(
    prompt_ids=prompt_input_ids,
    num_generations=6,  # 一次生成 6 个 response
    max_gen_len=1024,
)
```

---

## 四、数据集格式

### 4.1 PreTrain 数据

```json
// rlhf.jsonl / pretrain_data.jsonl
{"text": "自然语言文本..."}
```

### 4.2 SFT 数据

```json
// sft_data.jsonl
{"messages": [
    {"role": "system", "content": "你是一个有帮助的助手"},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
]}
```

### 4.3 DPO 数据

```json
// dpo.jsonl
{
    "chosen": {"messages": [...], "content": "好的回答"},
    "rejected": {"messages": [...], "content": "差的回答"}
}
```

---

## 五、落地到自有系统的方案

### 5.1 可复用的组件

| MiniMind 组件 | 自有系统对应 | 优先级 |
|--------------|-------------|--------|
| BPE Tokenizer | 当前用 HuggingFace tokenizer | 中（可对比）|
| RoPE + YaRN | 当前可能有 RoPE | 高（长上下文扩展）|
| GQA | 当前 MHA | 高（显存节省）|
| MoE | 当前 dense | 中（可实验）|
| PreTrain pipeline | 自有 PretrainPipeline | 高（参考数据格式）|
| DPO | 自有 DPOTrainer | 高（比 PPO 简单，效果好）|
| GRPO | 无 | 高（适合无 critic 场景）|
| Knowledge Distillation | 无 | 中（模型压缩）|

### 5.2 下一步行动计划

1. **优先落地 DPO**：DPO 比 PPO 简单，效果好，适合当前系统
   - 需要准备 preference pairs 数据
   - 参考 `train_dpo.py` 的 `dpo_loss` 实现

2. **参考 GRPO 做 RL**：不需要 critic，适合工具调用场景
   - 实现 `calculate_rewards()` 函数
   - 参考 `rollout_engine.py` 实现 response 生成

3. **改进模型架构**：
   - 引入 GQA 减少 KV cache
   - 引入 YaRN 扩展上下文长度

4. **知识蒸馏**：用大模型蒸馏到小模型
   - 适合边缘部署场景

---

## 六、关键代码片段

### 6.1 RoPE + YaRN 实现

```python
def precompute_freqs_cis(dim: int, end: int, theta: float = 1e6,
                         use_scaled_rope: bool = False, mscale: float = 1.0):
    freqs = 1.0 / (theta ** (torch.arange(0, dim, 2).float() / dim))
    t = torch.arange(end, device=freqs.device)
    freqs = torch.outer(t, freqs)
    if use_scaled_rope:
        freqs = freqs * mscale  # YaRN 缩放
    return torch.polar(torch.ones_like(freqs), freqs)  # 复数形式 cos+isin
```

### 6.2 GRPO 奖励计算

```python
def calculate_rewards(prompts, responses, reward_model):
    rewards = torch.zeros(len(responses))
    for i in range(len(prompts)):
        response = responses[i]
        # 长度奖励
        if 20 <= len(response.strip()) <= 800:
            rewards[i] += 0.5
        else:
            rewards[i] -= 0.5
        # 思维标签奖励
        if '</think>' in response:
            thinking_content, answer = response.split('</think>', 1)
            if 20 <= len(thinking_content.strip()) <= 300:
                rewards[i] += 1.0
            else:
                rewards[i] -= 0.25
            # repetition penalty
            rewards[i] -= rep_penalty(answer)
        # reward model 打分
        rewards[i] += reward_model.get_score(messages, answer)
    return rewards
```

### 6.3 DPO 损失

```python
def dpo_loss(ref_log_probs, policy_log_probs, mask, beta=0.1):
    """
    ref_log_probs: [2B, seq, vocab] 参考模型（通常 SFT 后的模型）
    policy_log_probs: [2B, seq, vocab] 当前策略模型
    mask: [2B, seq] 有效位置掩码
    beta: DPO 温度，通常 0.1-0.5
    """
    # 提取 chosen 和 rejected 的 log prob
    chosen_log_ps = (policy_log_probs[won] * mask[won]).sum(-1)
    rejected_log_ps = (policy_log_probs[lost] * mask[lost]).sum(-1)
    ref_chosen_log_ps = (ref_log_probs[won] * mask[won]).sum(-1)
    ref_rejected_log_ps = (ref_log_probs[lost] * mask[lost]).sum(-1)
    
    # DPO 核心公式
    logits = beta * ((chosen_log_ps - rejected_log_ps) - (ref_chosen_log_ps - ref_rejected_log_ps))
    return -torch.logsigmoid(logits).mean()
```

---

## 七、踩坑记录

1. **repo 名字**：jiaweizzhao/minimind 返回 404，实际是 `jingyaogong/minimind`
2. **GitHub 访问**：直接 git clone 不通，但 GitHub API 可用
3. **GRPO 的 advantage 计算**：必须 group 内归一化，否则不稳定
4. **DPO 需要 reference model**：不能用 from scratch 的模型做 DPO，必须先 SFT
5. **YaRN scaling 参数**：factor=16 表示 context 扩展到 16 倍时仍有效

---

## 八、参考资料

- 原项目：https://github.com/jingyaogong/minimind
- HuggingFace 模型：https://huggingface.co/jingyaogong/minimind-3B
- 相关解读：hans0809/MiniMind-in-Depth（源码解读，含 tokenizer/RoPE/MoE/KV Cache/pretraining/SFT/LoRA/DPO）
