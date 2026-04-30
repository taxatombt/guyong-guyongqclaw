# juhuo项目诊断报告 2026-04-23

## 汇报人：顾庸（只给建议，不动手）

---

## 一、数据库现状

| 表 | 行数 | 状态 |
|---|---|---|
| judgment_snapshots | 283 | 83%缺outcome_auto |
| causal_chain | 100 | 54%缺outcome |
| outcome_predictions | 119 | 73条未验证 |
| dimension_beliefs | 10 | 全卡0.05 |
| lessons | 0 | 空表 |
| snapshots | 0 | 空表 |
| health_metrics | 1 | 仅有初始benchmark |

**最后数据时间**：2026-04-21 14:09（已停更2天）

---

## 二、核心问题定位（3个层次）

### P0：闭环断裂 — 189条verdict无outcome

**现象**：283条judgment_snapshots中，235条有verdict，但189条outcome_auto=NULL。

**根因**：`closed_loop.py`的`receive_verdict()`才是写outcome_auto的唯一入口，但它只在这些情况下被调用：
1. `_verdict_signal_listener`（轮询outcomes.jsonl）— 但这个文件可能根本不存在或没数据
2. `verdict_collector.auto_collect()` — 是stub，只返回空
3. 外部手动调用`receive_verdict()` — 没看到谁在调

**结果**：verdict写了，但没人"事后验证"，outcome永远是NULL，belief永远0.05。

### P1：dimension_beliefs死锁

**现象**：10个维度全部belief=0.05，miss=32，hit=17-22，last_updated=None。

**根因**：
- belief更新在`receive_verdict()`里
- receive_verdict几乎不被调用（见P0）
- 即使被调用，当前公式：`delta = BELIEF_DECAY × magnitude × sign`，MAX_DELTA=0.15
- miss全32说明所有维度都被统一惩罚，没有差异化

**关键bug**：`last_updated=None`说明belief从未被更新过。hit_count有值说明某处代码在更新hit但不是通过receive_verdict。

### P2：self_model.json与DB不同步

- self_model.json：weights全是0.75，total_decisions=2，只有cognitive和emotional两个strength
- DB dimension_beliefs：全是0.05
- 两个数据源完全矛盾，没有同步机制

---

## 三、架构问题（5个）

### 1. verdict_collector是半成品
- `import_from_judgment_db()`引用了不存在的`judgment_db.get_conn()`
- `auto_collect()`是stub（只检查chats.json，不实际处理）
- 数据库schema里没有`created_at`列（但代码假设有）

### 2. outcomes.jsonl监听器不可靠
- `_verdict_signal_listener`启动后连续3次空读就退出
- 没有重启机制
- outcomes.jsonl文件路径可能根本没数据写入

### 3. 双路径混乱（judgment/ vs subsystems/judgment/）
- `E:\juhuo\judgment\` 有49个文件（实际使用的）
- `E:\juhuo\subsystems\judgment\` 有27个文件（shim/stub）
- closed_loop.py在两个路径都存在，内容不同
- import时到底用哪个？路径混乱是bug温床

### 4. experiences表已不存在
- 之前的诊断说experiences表40行全NULL
- 现在数据库里根本没experiences表
- 但closed_loop.py的receive_verdict()还在尝试UPDATE experiences
- 这会静默失败（try/except pass）

### 5. outcome_predictions的predicted_action全是NULL
- 119条prediction中，大部分predicted_action=NULL
- `auto_predict_from_verdict()`只在verdict非空时触发
- 但verdict写入时的中文编码问题可能导致提取失败

---

## 四、建议（按优先级）

### P0修复：让outcome_auto真正写入

**方案A**（最简单）：在`snapshot_judgment()`写入judgment_snapshots时，如果verdict非空，直接用LLM评估verdict质量作为outcome_auto的初始值。

```python
# 在snapshot_judgment末尾添加
if verdict_text:
    # 简单启发式：verdict包含"不确定"/"需要更多信息"→0.3
    # verdict包含"建议"/"推荐"→0.7
    # 其他→0.5
    initial_outcome = _heuristic_outcome(verdict_text)
    c.execute("UPDATE judgment_snapshots SET outcome_auto=? WHERE chain_id=?",
              (initial_outcome, chain_id))
```

**方案B**（更彻底）：让verdict_listener持续运行，加上重启机制。把outcomes.jsonl换成直接监听judgment_snapshots表的变化。

### P1修复：重置dimension_beliefs

当前10维全0.05没有区分度，建议：
1. 重置为0.5（中性起点）
2. 修复`receive_verdict`中的belief更新公式：miss不应统一+1，应根据该维度在判断中的参与度加权
3. 修复`last_updated`始终为None的bug

### P2修复：self_model同步

self_model.json和dimension_beliefs是两个独立的数据源，需要：
1. 在receive_verdict成功更新belief后，同步写self_model.json的weights
2. 或者统一到一个数据源

### P3清理：双路径合并

judgment/和subsystems/judgment/二选一，删掉另一个。推荐保留judgment/（代码更完整），subsystems/judgment/改名为_legacy_judgment/或直接删。

### P4：experiences表重建或删除引用

experiences表已经不存在了，但代码还在尝试UPDATE。要么重建表（加chain_id列），要么删掉closed_loop.py中对experiences的引用。

---

## 五、最关键的一句话

**聚活的闭环设计是完整的，但"验证"这一步从来没有真正执行过。**

189条verdict停在那里，没有人告诉系统"你判断对了吗"。没有这个信号，belief不会变，fitness不会算，进化不会发生。

这不是算法问题，是流程断点。修这个，比优化任何算法都重要。
