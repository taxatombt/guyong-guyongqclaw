# MiniMind DPO Training Skill

基于 `jingyaogong/minimind` 的 DPO（Direct Preference Optimization）训练框架。

## 一、项目背景

DPO 是一种简化的偏好对齐训练方法，比 PPO 简单 10 倍：
- **不需要 reward model**：直接用偏好对训练
- **不需要 critic network**：只需要 policy + reference 两个模型
- **离线训练**：只需要 pre-collected preference data

## 二、快速开始

### 前置条件

1. Python 3.8+
2. PyTorch 2.0+
3. 至少有 8GB 显存的 GPU（推荐 16GB+）

### Step 1: 安装

```bash
pip install -r requirements.txt
```

### Step 2: 准备数据

**方式 A：使用示例数据（测试用）**
```bash
# 已包含 3 条示例数据在 data/dpo_example.jsonl
```

**方式 B：生成合成数据**
```bash
python generate_preference_data.py \
    --provider lmstudio \
    --num_samples 100 \
    --output data/my_dpo_data.jsonl
```

**方式 C：准备自己的数据**
```json
{
  "chosen": [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "好回答"}],
  "rejected": [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "差回答"}]
}
```

### Step 3: 开始训练

**方式 A：命令行**
```bash
python train_dpo.py \
    --data_path data/dpo_example.jsonl \
    --from_weight jingyaogong/minimind-3B \
    --save_dir out \
    --epochs 1 \
    --batch_size 2 \
    --learning_rate 4e-8 \
    --beta 0.15
```

**方式 B：一键脚本（Windows）**
```bash
run_training.bat
```

## 三、参数配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--from_weight` | jingyaogong/minimind-3B | SFT 模型（HuggingFace 或本地路径）|
| `--data_path` | data/dpo_example.jsonl | 偏好数据路径 |
| `--beta` | 0.15 | DPO 温度，越大越保守 |
| `--learning_rate` | 4e-8 | 学习率（必须 ≤ 5e-8）|
| `--batch_size` | 2 | batch size |
| `--epochs` | 1 | 训练轮数 |
| `--max_seq_len` | 1024 | 最大序列长度 |

## 四、支持的数据生成 Provider

| Provider | 说明 | 配置 |
|----------|------|------|
| `lmstudio` | 本地模型（LM Studio）| `http://localhost:1234/v1` |
| `ollama` | 本地模型（Ollama）| `http://localhost:11434/api/chat` |
| `openai` | GPT-4 / GPT-3.5 | 需要 `OPENAI_API_KEY` 环境变量 |
| `claude` | Claude 3 | 需要 `ANTHROPIC_API_KEY` 环境变量 |

## 五、核心文件说明

```
dpo_training_skill/
├── SKILL.md                          # 详细文档
├── README.md                         # 本文件
├── train_dpo.py                      # DPO 训练主脚本
├── generate_preference_data.py        # 偏好数据生成工具
├── run_training.bat                  # Windows 快速启动
├── run_generate.bat                  # 数据生成脚本
├── requirements.txt                  # 依赖
├── data/
│   ├── dpo_example.jsonl             # 示例数据（3条）
│   └── README.md                     # 数据格式说明
└── out/                              # 模型输出目录
```

## 六、注意事项

1. **DPO 不能 from scratch**：必须有 SFT 后的模型才能做 DPO
2. **学习率要小**：建议 1e-8 ~ 4e-8，太大导致灾难性遗忘
3. **数据质量第一**：100 条高质量 > 1000 条低质量
4. **reference model 要冻结**：不要在 DPO 训练中更新 ref model

## 七、参考资料

- DPO 原始论文：Rafailov et al. 2023
- MiniMind repo：`jingyaogong/minimind`
- HuggingFace DPO Trainer：`transformers.DPOTrainer`
