---
name: dpo-training
description: MiniMind DPO (Direct Preference Optimization) 训练框架。基于 jingyaogong/minimind 架构，不修改源码，独立运行。用于对 SFT 后的模型做偏好对齐训练。
---

# DPO Training Skill

基于 MiniMind (jingyaogong/minimind) 的 DPO 实现，独立封装，不改源码。

## 核心算法

DPO 通过偏好对（chosen / rejected）直接优化策略模型，无需单独训练 reward model：

```
loss = -log σ(β × (Δlogπ - Δlogπ_ref))
     = -log σ(β × ((log π(y_w|x) - log π(y_l|x)) - (log π_ref(y_w|x) - log π_ref(y_l|x))))
```

**与 PPO 的区别**：
- PPO：需要 4 个模型（policy / ref / reward / value）+ GAE 估计
- DPO：只需 2 个模型（policy / ref）+ 偏好对

## 文件结构

```
dpo_training_skill/
├── SKILL.md                          # 本文档
├── README.md                         # 使用说明
├── train_dpo.py                      # DPO 训练主脚本
├── generate_preference_data.py        # 偏好数据生成工具
├── generate_preference_data_batch.py # 批量生成偏好数据
├── run_training.bat                  # Windows 一键启动
├── run_generate.bat                  # 生成偏好数据
├── requirements.txt                  # 依赖
├── data/
│   ├── dpo_example.jsonl             # 数据格式示例
│   └── README.md                     # 数据格式说明
└── out/                              # 模型输出目录
```

## 快速开始

### Step 1: 安装依赖

```bash
pip install torch transformers datasets tqdm numpy
```

### Step 2: 准备 SFT 后的模型权重

DPO 需要先有 SFT 后的模型。权重路径配置在脚本中：
```python
# train_dpo.py 中的 model_path 配置
from_weight = "path/to/your/sft_model"
```

推荐从 HuggingFace 下载预训练权重：
```python
# 自动下载（脚本内置）
from transformers import AutoTokenizer, AutoModelForCausalLM
tokenizer = AutoTokenizer.from_pretrained("jingyaogong/minimind-3B", trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained("jingyaogong/minimind-3B", trust_remote_code=True)
```

### Step 3: 准备偏好数据

格式（JSONL，每行一个样本）：
```json
{
  "chosen": [
    {"role": "user", "content": "问题"},
    {"role": "assistant", "content": "好的回答"}
  ],
  "rejected": [
    {"role": "user", "content": "问题"},
    {"role": "assistant", "content": "差的回答"}
  ]
}
```

生成合成数据（用大模型 API）：
```bash
python generate_preference_data.py --num_samples 100 --output data/synthetic_dpo.jsonl
```

### Step 4: 运行训练

```bash
python train_dpo.py \
  --data_path data/your_dpo_data.jsonl \
  --from_weight path/to/sft_model \
  --save_dir out \
  --epochs 1 \
  --batch_size 2 \
  --learning_rate 4e-8 \
  --beta 0.15
```

或直接运行：
```bash
run_training.bat
```

## 核心参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--from_weight` | full_sft | SFT 模型路径（作为 policy 和 ref 的起点）|
| `--beta` | 0.15 | DPO 温度，越大越保守（参考值 0.1~0.3）|
| `--learning_rate` | 4e-8 | 学习率，**必须 ≤ 5e-8** 避免遗忘 |
| `--batch_size` | 4 | batch size（根据显存调整）|
| `--epochs` | 1 | 训练轮数 |
| `--max_seq_len` | 1024 | 最大序列长度 |
| `--hidden_size` | 768 | 模型隐层维度 |
| `--num_hidden_layers` | 8 | 模型层数 |

## 数据格式详解

### DPODataset 加载逻辑

1. 每个样本包含 `chosen` 和 `rejected`（都是 message list）
2. 用 `tokenizer.apply_chat_template()` 构造成完整 prompt
3. 只在 assistant 回复部分计算 loss（prompt 部分 mask 掉）
4. chosen 和 rejected 拼成 batch，`batch_size // 2` 对应 chosen/rejected

### loss mask 原理

```python
def generate_loss_mask(self, input_ids):
    # 找到 assistant 回复的起始位置，只对该区域计算 loss
    # prompt 部分 mask = 0，不参与梯度更新
    loss_mask = [0] * len(input_ids)
    # 定位 assistant 标签后开始 mask = 1
    ...
```

### 推荐偏好数据来源

1. **LLM-as-Judge**：用 GPT-4o / Claude 生成同一问题的多个回答，人工或模型评选 preferred/rejected
2. **规则生成**：含特殊 token（</think>）的回答 preferred，不含的 rejected
3. **人类标注**：最准确但成本高
4. **合成数据**：用强模型生成 pair，参考 MiniMind 的 rule-based reward

## DPO vs 其他训练阶段的关系

```
Pretrain → SFT → DPO → (GRPO/PPO)
              ↑
         必须先有 SFT 模型才能做 DPO
```

**常见误区**：
- ❌ from scratch 直接 DPO（会灾难性遗忘）
- ❌ 学习率太大（DPO 对学习率极敏感，必须 ≤ 5e-8）
- ❌ 用 unaligned 的模型做 ref（ref 应该是 SFT 后未训练的版本）

## 故障排除

**loss 不下降**：检查 chosen 是否真的比 rejected 好，数据质量是关键
**loss 爆炸**：降低 learning_rate（改到 1e-8 试试）
**OOM**：降低 batch_size 或 max_seq_len
**模型遗忘**：learning_rate 必须 ≤ 5e-8，建议 1e-8 ~ 4e-8

## 参考资料

- 原版 DPO 论文：Rafailov et al. 2023
- MiniMind GRPO 实现：trainer_train_grpo.py
- HuggingFace DPO Trainer：transformers 内置 DPO trainer
