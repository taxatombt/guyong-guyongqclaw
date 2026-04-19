# 聚活项目深度分析与建议

> 分析时间：2026-04-18
> 数据来源：GitHub API + raw.githubusercontent.com

---

## 一、项目概览

**guyong-juhuo** 是一个 12 子系统 AI Agent 框架，目标是：
- **Mimic Mode**: 模拟特定个人的判断风格
- **Transcend Mode**: 基于纯推理判断，闭环进化直到超越人类

核心创新：**10维并行评估 + 闭环反馈进化**

---

## 二、架构亮点（做得好的）

### 1. 十维判断框架
```
cognitive · game_theory · economic · dialectical · emotional
intuitive · moral · social · temporal · metacognitive
```
覆盖全面，有理论依据。

### 2. 闭环设计完整
```
判断 → 记录链 → 用户反馈 verdict → 信念更新 → 下次判断改善
```
- `closed_loop.py`: 25KB，实现了完整的因果链记录
- `outcome_predictions` 表：预测→验证→评分闭环

### 3. Benchmark 系统（GDPVal）
- 22个测试案例，覆盖9大领域
- A/B/C/D四级评分标准
- 当前基准准确率：63.9%（36条种子verdicts）

### 4. 代码组织清晰
```
subsystems/
├── judgment/          # 十维判断核心
├── causal_memory/     # 因果记忆
├── self_evolover/     # 自我进化
├── action_system/     # 执行系统
└── ...
```

### 5. 最近进展（v1.9）
- ✅ ActionExecutor 三通道执行层
- ✅ Outcome Prediction + Verification
- ✅ Benchmark 修复（11/11 mock cases PASS）
- ✅ 闭环数据链路修复

---

## 三、核心问题识别

### 🔴 P0：维度信念未更新

**现象**：`dimension_beliefs` 表中所有维度的 belief 值都是 **0.5**（初始值）

**根因分析**：
```python
# closed_loop.py 中的 receive_verdict()
# 虽然更新了 hit_count/miss_count，但 belief 值计算可能有问题
```

**建议**：
1. 检查 `update_dimension_beliefs()` 函数是否正确计算新 belief
2. 添加日志确认每次 verdict 后 belief 是否变化
3. 考虑引入贝叶斯更新公式：
   ```
   P_new = (P_prior * likelihood) / evidence
   ```

### 🟡 P1：关键词匹配规则脆弱

**现象**：`judgment_rules.py` 使用简单的关键词计数

**问题**：
```python
# 当前实现（推测）
if "风险" in task and "投资" in task:
    return {"economic": 0.9, "cognitive": 0.8}
```

**建议**：
1. 引入语义相似度（sentence-transformers）
2. 或使用 LLM 做零样本分类
3. 建立规则优先级机制（硬规则 > 软规则 > 默认）

### 🟡 P2：情绪检测是占位实现

**现象**：`emotions.json` 中 16 条记录全是 "兴奋"

**建议**：
1. 承认当前是占位实现
2. 接入真实的情绪检测（如 MiniMax 的情绪识别 API）
3. 或基于 PAD 模型手动标注种子数据

### 🟢 P3：模块级副作用过重

**现象**：`router.py` import 时启动后台线程

```python
# router.py
start_verdict_listener()      # 启动监听线程
start_evolver_scheduler()     # 启动调度器
```

**问题**：
- 难以测试
- 难以控制生命周期
- 可能导致资源泄漏

**建议**：
```python
# 改为显式初始化
class JudgmentRouter:
    def __init__(self):
        self._listener = None
        self._scheduler = None
    
    def start(self):
        self._listener = start_verdict_listener()
        self._scheduler = start_evolver_scheduler()
    
    def stop(self):
        # 清理资源
```

---

## 四、具体改进建议

### 1. 立即执行（本周）

#### 1.1 修复 belief 更新逻辑
```python
# closed_loop.py
def update_dimension_beliefs(dim: str, is_correct: bool):
    """贝叶斯更新维度信念"""
    conn = _get_db_conn()
    row = conn.execute(
        "SELECT belief, hit_count, miss_count FROM dimension_beliefs WHERE dim_id=?",
        (dim,)
    ).fetchone()
    
    prior = row[0]
    hits = row[1]
    misses = row[2]
    
    # 贝叶斯更新
    if is_correct:
        new_belief = min(prior + 0.1, 0.95)  # 上限保护
        hits += 1
    else:
        new_belief = max(prior - 0.1, 0.05)  # 下限保护
        misses += 1
    
    conn.execute(
        "UPDATE dimension_beliefs SET belief=?, hit_count=?, miss_count=? WHERE dim_id=?",
        (new_belief, hits, misses, dim)
    )
    conn.commit()
```

#### 1.2 添加 E2E 测试
```python
# tests/test_closed_loop.py
def test_belief_update():
    """测试维度信念是否正确更新"""
    init()
    
    # 模拟一次判断
    chain_id = "test_001"
    task = "要不要辞职创业？"
    result = check10d(task)
    
    # 记录 snapshot
    snapshot_judgment(chain_id, task, result["dimensions"], ...)
    
    # 模拟 verdict
    receive_verdict(chain_id, verdict=1, notes="测试")
    
    # 验证 belief 是否变化
    conn = _get_db_conn()
    belief = conn.execute("SELECT belief FROM dimension_beliefs WHERE dim_id='economic'").fetchone()[0]
    assert belief != 0.5, "belief 应该被更新"
```

### 2. 短期优化（本月）

#### 2.1 引入语义匹配
```python
# judgment_rules.py
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

def semantic_match(task: str, rule_pattern: str) -> float:
    """语义相似度匹配"""
    emb1 = _model.encode(task)
    emb2 = _model.encode(rule_pattern)
    return cosine_similarity([emb1], [emb2])[0][0]
```

#### 2.2 重构 router.py 生命周期
```python
# 新设计：显式生命周期管理
class JuhuoCore:
    def __init__(self, config: Config):
        self.config = config
        self.judgment_router = None
        self.causal_memory = None
        self.self_model = None
        
    def initialize(self):
        """显式初始化所有子系统"""
        self.causal_memory = CausalMemory(self.config.causal)
        self.self_model = SelfModel(self.config.self_model)
        self.judgment_router = JudgmentRouter(
            causal_memory=self.causal_memory,
            self_model=self.self_model,
        )
        
    def start(self):
        """启动所有后台服务"""
        self.judgment_router.start()
        
    def stop(self):
        """优雅关闭"""
        self.judgment_router.stop()
```

#### 2.3 拆分 closed_loop.py
当前 25KB，建议拆分为：
```
closed_loop/
├── __init__.py          # 统一导出
├── core.py              # 核心逻辑（snapshot, verdict）
├── beliefs.py           # 信念更新
├── outcomes.py          # outcome prediction
├── storage.py           # 数据库操作
└── listener.py          # 后台监听
```

### 3. 中期规划（下月）

#### 3.1 引入权重可视化
```python
# web_console.py 新增页面
@app.route('/weights')
def show_weights():
    """显示当前维度权重热力图"""
    beliefs = get_dimension_beliefs()
    return render_template('weights.html', beliefs=beliefs)
```

#### 3.2 建立 A/B 测试框架
```python
# ab_test.py
class ABTest:
    """对比两种判断策略的效果"""
    def __init__(self, strategy_a, strategy_b):
        self.a = strategy_a
        self.b = strategy_b
        
    def run(self, test_cases: List[str]) -> ABResult:
        """运行对比测试"""
        results_a = [self.a(case) for case in test_cases]
        results_b = [self.b(case) for case in test_cases]
        return compare(results_a, results_b)
```

#### 3.3 引入持续学习
```python
# continuous_learning.py
class ContinuousLearner:
    """从 verdict 流中持续学习"""
    def __init__(self):
        self.model = None
        
    def on_new_verdict(self, verdict: VerdictRecord):
        """每条新 verdict 触发增量学习"""
        self.update_beliefs(verdict)
        if self.should_retrain():
            self.retrain()
```

---

## 五、优先级总结

| 优先级 | 任务 | 预期收益 |
|--------|------|---------|
| 🔴 P0 | 修复 belief 更新 | 闭环真正跑通 |
| 🔴 P0 | 添加 E2E 测试 | 防止回归 |
| 🟡 P1 | 语义匹配规则 | 判断准确率 +10% |
| 🟡 P1 | 重构 router 生命周期 | 可测试性 |
| 🟡 P2 | 情绪检测真实实现 | 完整功能 |
| 🟢 P3 | 拆分大文件 | 可维护性 |
| 🟢 P3 | 权重可视化 | 用户体验 |

---

## 六、关键指标监控

建议添加以下监控：

```python
# metrics.py
METRICS = {
    "belief_update_rate": "信念更新频率",
    "verdict_accuracy": "verdict 准确率",
    "dimension_coverage": "维度覆盖率",
    "outcome_prediction_accuracy": "结果预测准确率",
    "avg_judgment_time_ms": "平均判断耗时",
}
```

---

## 七、总结

**聚活项目架构设计优秀，12子系统划分合理，闭环设计完整。**

**当前最大瓶颈**：维度信念更新逻辑未跑通，导致进化闭环形同虚设。

**建议立即**：
1. 停新功能开发
2. 写 E2E 测试验证 belief 更新
3. 修复更新逻辑
4. 跑通 50+ 真实 verdict 积累

**只有数据闭环跑通，其他优化才有意义。**

---

*分析完成*
