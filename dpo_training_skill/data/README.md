# DPO 数据格式说明

## JSONL 格式

每行一个 JSON 对象，示例：

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

## 关键要求

1. **chosen 必须明显优于 rejected**：这是 DPO 有效的前提
2. **问题内容相同**：chosen 和 rejected 的 user prompt 相同
3. **assistant 回复不同**：只比较 assistant 的回复
4. **避免 trivial 差异**：不要只是长度差异，要有实质性质量差异

## 数据质量标准

| 维度 | Good | Bad |
|------|------|-----|
| 完整性 | 全面回答问题 | 答非所问或不完整 |
| 准确性 | 事实正确 | 包含错误信息 |
| 格式 | 结构清晰 | 混乱无序 |
| 长度 | 适中（不要太短也不要冗余）| 过长或过短 |

## 数据量建议

- 最小可用：100 对
- 推荐规模：1000-10000 对
- 质量 > 数量：100对高质量 > 1000对低质量

## 生成工具

使用 `generate_preference_data.py` 生成合成数据：

```bash
python generate_preference_data.py \
  --provider lmstudio \
  --num_samples 100 \
  --output data/synthetic_dpo.jsonl
```
