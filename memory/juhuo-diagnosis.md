# juhuo项目诊断归档

> 从 MEMORY.md 迁出，2026-04-24 精简时归档

## 终极目标（2026-04-23确认）

"模拟那个具体的某个juhuo的使用者，然后超越整个人类"

与顾庸分身同构：模拟→超越，数字替身非工具

## 闭环断裂诊断（2026-04-22~24）

三层失效：
1. P0闭环断裂：receive_verdict()几乎未被调用，verdict_collector是stub，outcomes.jsonl监听器3次空读退出无重启
2. P1 dimension_beliefs死锁：10维全0.05，更新依赖receive_verdict
3. P2 self_model.json矛盾：weights全0.75 vs DB全0.05，无同步

根因：experiences表缺chain_id列 → UPDATE失败 → 无反馈写入

## 10条建议

P0：agent.py加反馈入口 + 建缺失表 + listener不退出改退避
P1：dimension_beliefs初始化0.5 + 清理44条pending + self_model同步
P2：双路径合并 + 死引用清理 + 6函数重复定义 + predicted_action全NULL

## 闭环三通路融合

设计已存在：biography/experiences/behavior加权融合，experiences > biography > behavior
