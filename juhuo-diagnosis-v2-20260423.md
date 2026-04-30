# 聚活(juhuo)项目深度诊断 v2 — 2026-04-23 19:24

## 汇报人：顾庸（只给建议，不动手）

---

## 一、数据现状（无变化）

数据库 `juhuo.db` 共8张表：

| 表 | 行数 | 状态 |
|---|---|---|
| judgment_snapshots | 283 | 83%缺outcome（236/283=NULL），最后活跃2026-04-21 |
| causal_chain | 100 | 54%缺outcome（54/100=NULL） |
| outcome_predictions | 119 | 73条未verified，46条有score |
| dimension_beliefs | 10 | 全卡0.05，last_updated=None |
| lessons | 0 | 空表 |
| snapshots | 0 | 空表 |
| health_metrics | 1 | 初始benchmark |

**关键发现**：上次诊断后（2天前），数据库没有任何新数据写入。系统已经停转。

---

## 二、上次诊断遗漏的3个关键问题

### 问题1：`verdict_outcomes` 和 `dimension_stats` 表不存在

`self_evolver.py` 的 `check_trigger()` 直接查询：
```sql
SELECT * FROM verdict_outcomes ORDER BY created_at DESC LIMIT 6
SELECT * FROM dimension_stats WHERE total_count >= 3
```

`fitness_evolution.py` 的 `get_stats()` 也查询这两张表。

**但这两张表在数据库里根本不存在！**

`_schema_tables.py` 的 `init_schema()` 可能没创建这两张表，或者它们被设计在另一个数据库文件里。结果是：self_evolver每次触发都报错，被 except 静默吞掉。

### 问题2：auto_verdicts 44条全标记为 "pending"

`data/verdicts/auto_verdicts.jsonl` 有44条记录，但**全部 verdict="pending"**，source="auto"。

这意味着 `auto_collect()` 虽然在运行并导入了数据，但没有能力判断对错（因为没有标注），所以全部标记为pending。这些数据对进化没有意义——pending不是有效信号。

### 问题3：outcomes.jsonl 只有1条测试数据

`data/outcomes.jsonl` 只有1条记录，还是2026-04-14的测试数据（task_text="安装npm包"，verdict_recorded=false）。

verdict_listener启动后：
1. 读到这条数据
2. 看到 verdict_recorded=false
3. 调用 receive_verdict
4. 但这条是测试数据，task_text中文乱码，chain_id=test_chain_1
5. 找不到匹配的causal_chain记录 → no_record_found
6. 连续3次空读 → listener退出

**listener的3次空读退出机制太激进了**。系统正式使用时，如果用户不是频繁给反馈，listener会很快自杀。

---

## 三、真正的断裂点分析

### 闭环设计（理论）

```
用户输入任务
  → router.check10d() → 十维分析 → 输出verdict
  → snapshot_judgment() → 写入judgment_snapshots + causal_chain
  → 用户事后反馈"对/错"
  → receive_verdict() → 更新dimension_beliefs → 触发fitness/evolver
  → 权重进化 → 下次判断更准
```

### 闭环实际（现实）

```
用户输入任务
  → router.check10d() → 十维分析 → 输出verdict ✅
  → snapshot_judgment() → 写入judgment_snapshots + causal_chain ✅
  → 用户事后反馈"对/错" ❌（没有机制收集）
  → receive_verdict() → 从未被调用 → dimension_beliefs不更新 ❌
  → listener自杀（3次空读退出，outcomes.jsonl只有1条测试数据）❌
  → verdict_outcomes/dimension_stats表不存在 → evolver报错被静默 ❌
```

**断裂发生在"用户反馈→系统接收"这一步。**

不是算法问题，不是架构问题，是**没有人把用户的反馈写入系统**。

---

## 四、5个具体建议

### 建议1（最重要）：建立反馈入口

**现状**：没有UI/CLI让用户方便地给判断打分。

**建议**：在agent.py的interactive模式中，每次输出verdict后追问：

```
这个判断：[1]对了 [2]错了 [3]不确定 [4]跳过
```

这个改动最小（约20行），效果最大——直接解决数据断层。

如果用CoPaw/OpenClaw集成，可以用reaction/quick-reply按钮，但最简单的起点是CLI交互。

### 建议2：listener改为"不退出"模式

**现状**：3次空读退出。

**建议**：去掉退出机制，或者改为指数退避（2s→4s→8s→30s→30s...）。listener应该是持久后台服务，不是按需启停的。

```python
# 改为指数退避
poll_interval = 2
max_interval = 30
while not _listener_stop.is_set():
    # ... 处理逻辑 ...
    if empty_count > 0:
        poll_interval = min(poll_interval * 2, max_interval)
    else:
        poll_interval = 2  # 有数据时恢复快轮询
```

### 建议3：创建缺失的数据库表

`verdict_outcomes` 和 `dimension_stats` 表需要在 `_schema_tables.py` 的 `init_schema()` 中创建，否则 `self_evolver` 和 `fitness_evolution` 永远无法正常工作。

需要确认：这两张表的设计在哪个文件里定义？如果在代码注释或文档中有描述，需要落地到DDL。

### 建议4：auto_verdicts pending→有效verdict

44条pending数据没有反馈信号，可以考虑：

- **方案A**：让系统对每条pending发起自评——拿task_text重新跑一遍check10d，对比两次verdict的一致性，一致=correct，不一致=review
- **方案B**：直接清掉pending数据，因为没有标注的数据对进化没有帮助
- **方案C**：在交互模式中逐条让用户确认

方案A最自动化但可能引入偏差，方案B最干净，方案C最准确但需要用户参与。

### 建议5：合并双路径

`judgment/` 和 `subsystems/judgment/` 两个路径仍然并存：
- `judgment/` 下49个文件，大部分是shim（re-export）
- `subsystems/judgment/` 下是实际代码
- import路径混乱

建议：确认 `subsystems/judgment/` 是canonical路径后，把 `judgment/` 下的shim保留但标注 deprecated，新代码只从 `subsystems.judgment` 导入。

---

## 五、修复优先级

| 优先级 | 改动 | 工作量 | 效果 |
|--------|------|--------|------|
| **P0** | CLI追问反馈（建议1） | ~20行 | 打通闭环数据入口 |
| **P0** | 创建verdict_outcomes/dimension_stats表 | ~30行DDL | 修复evolver静默失败 |
| **P1** | listener不退出+指数退避 | ~15行 | 保持后台持续监听 |
| **P2** | 处理44条pending | 10-50行 | 清理无效数据/激活自评 |
| **P3** | 双路径合并标注 | ~49个文件改注释 | 代码整洁 |

---

## 六、一句话总结

**系统设计完整，代码量大（closed_loop.py 1100+行），但核心闭环的"反馈接收"这一步没有入口。建议1（CLI追问）是打通一切的开关，建议2和3是让它持续运行的基础设施。**

其他都是优化。先把闭环跑通，再谈进化。
