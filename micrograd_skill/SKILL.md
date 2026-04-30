# micrograd Skill — 自动微分引擎

> 基于 karpathy/micrograd 源码逆向工程
> 代码路径: `micrograd_skill/engine.py`, `train.py`

---

## 快速开始

```bash
python train.py
```

输出示例:
```
XOR 问题演示
Epoch    0 | loss=0.2500 | acc=25.0%
Epoch   50 | loss=0.1234 | acc=75.0%
Epoch  100 | loss=0.0412 | acc=100.0%
  [0,0] -> pred=0 (prob=0.021)
  [0,1] -> pred=1 (prob=0.978)
  ...
```

---

## 核心概念

### 计算图

```
a = Value(2.0)
b = Value(3.0)
c = a * b      # c = 6.0, _prev = (a, b), _op = '*'
d = c + a      # d = 8.0, _prev = (c, a), _op = '+'
d.backward()   # 反向传播: dc/da = ?, dc/db = ?, ...
```

每个 `Value` 对象记住:
- `data`: 当前值
- `grad`: 梯度 (d loss / d this value)
- `_prev`: 输入节点 tuple
- `_op`: 操作名 (调试用)
- `_backward`: 闭包，计算梯度

### 反向传播算法

```python
def backward(self):
    # 1. 拓扑排序 (保证从叶子到根)
    topo = []
    visited = set()
    def build_topo(v):
        if id(v) not in visited:
            visited.add(id(v))
            for child in v._prev:
                build_topo(child)
            topo.append(v)
    build_topo(self)
    
    # 2. 根梯度 = 1
    self.grad = 1.0
    
    # 3. 逆序执行 _backward()
    for node in reversed(topo):
        node._backward()
```

---

## 关键设计: grad += 累积模式

**最重要**: 梯度是累积的 `+=`，不是覆盖的 `=`。

```python
# 场景: f(a) = a + a  (a 出现在两个分支)
# 正确: da = 1 + 1 = 2
# 错误: da = 1  (只记录最后一次)

# micrograd 正确做法:
def _backward():
    self.grad += other.data * out.grad  # += 累积
    other.grad += self.data * out.grad  # += 累积
```

**为什么这重要**:
- 多条路径时，梯度需要相加
- 覆盖会丢失信息，导致错误梯度
- 这是 Karpathy micrograd 最重要的设计之一

**→ 这正是 evolver.py `accumulate_signal()` 的设计来源** (MEMORY.md 已记录)

---

## 已知 Bug (碰巧测试对)

micrograd 源码中有几处数学实现错误，但测试碰巧通过:

| 操作 | Bug | 说明 |
|------|-----|------|
| `__rsub__` | 顺序反了 | `3 - a` 时 `a.__rsub__(3)` 的实现和预期相反 |
| `__pow__` | 公式对 | 但实现和 `__rpow__` 混淆 |
| `__rpow__` | 公式反了 | `2 ** a` 的梯度应该是 `2^a * ln(2)`，但实现错了 |

这些 bug 在简单测试中对是因为:
- `__rsub__` 很少直接调用
- `__pow__` 在常见场景下正好公式对

---

## MLP 初始化的死神经元问题

**Bug**: Karpathy nanoGPT 的 MLP 初始化用 `uniform(-1, 1)`:

```python
# 错误 (会导致大量死神经元):
torch.nn.init.uniform_(module.weight, -1.0, 1.0)

# ReLU 后: 负数全部变 0
# → 约 50% 的神经元初始就是死的
```

**正确做法**: Kaiming 初始化:
```python
# 对于 ReLU: std = sqrt(2/n_in)
torch.nn.init.normal_(module.weight, std=math.sqrt(2.0/nin))
```

→ 这提醒我们: **初始化方法会直接影响训练稳定性**。

---

## micrograd → nanoGPT 的对应关系

理解 micrograd 后，nanoGPT 的核心就清晰了:

| micrograd | nanoGPT (PyTorch) |
|-----------|------------------|
| `Value.backward()` | `loss.backward()` |
| `Value._backward` 闭包 | PyTorch autograd 自动生成 |
| `Module.parameters()` | `model.parameters()` |
| `Neuron(W, b)` | `nn.Linear` |
| `MLP` | `nn.Sequential` |
| `SGD.step()` | `optimizer.step()` |
| `zero_grad()` | `optimizer.zero_grad()` |

---

## evolver.py 落地 (grad +=)

MEMORY.md 已记录，evolver.py (Lines 599-645) 实现了 Karpathy 的 grad+= 累积模式:

```python
def accumulate_signal(self, delta: float):
    """Karpathy grad+= pattern: accumulate confidence signal.
    
    Like micrograd's `self.grad += out.grad`:
    - Positive delta = success signal → confidence goes up
    - Negative delta = failure signal → confidence goes down
    """
    # Decay old signal
    self.confidence_signal *= self.confidence_decay
    # Accumulate new signal (grad += not grad =)
    self.confidence_signal += delta
    self.confidence_signal = max(0.0, min(1.0, self.confidence_signal))
```

这是 micrograd 的 `grad +=` 累积模式在 qclaw 系统中的具体应用。

---

## 可视化 (可选扩展)

如果想可视化计算图，可以扩展:

```python
def draw_dot(root: Value) -> ...:
    """用 Graphviz 可视化计算图"""
    # 节点 = Value 对象
    # 边 = _prev 关系
    # 标签 = data 和 grad
```

参考: karpathy 微积分课程中的 `southpark` 可视化脚本。
