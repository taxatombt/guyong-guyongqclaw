# Karpathy micrograd — 反向传播引擎逆向工程

> 来源：karpathy/micrograd (MIT, ~200 行核心代码)
> 落地：2026-04-17

## 核心定位

**autograd 引擎**：反向模式自动微分（reverse-mode autodiff），在动态构建的计算图上做 backpropagation。
- **engine.py (2730B)**：核心 `Value` 类，约 100 行
- **nn.py (1613B)**：神经网络层，约 50 行

## Value 类 — autograd 核心

```python
class Value:
    def __init__(self, data, _children=(), _op=''):
        self.data = data          # 前向值
        self.grad = 0             # 梯度（默认0）
        self._backward = lambda: None  # 反向回调
        self._prev = set(_children)     # 前向图的子节点
        self._op = _op                  # 操作标签（调试用）

    def backward(self):
        # 拓扑排序 + chain rule
        topo = []; visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._prev: build_topo(child)
                topo.append(v)
        build_topo(self)
        self.grad = 1  # loss 对自己的导数 = 1
        for v in reversed(topo): v._backward()
```

**核心思想**：每个操作保存 `(children, op)`，backward 时从 loss 反向遍历拓扑序，对每个节点执行链式法则。

### 支持的操作

| 操作 | 导数 |
|------|------|
| `a + b` | `da = db = out.grad` |
| `a * b` | `da = b.data * out.grad`, `db = a.data * out.grad` |
| `a ** n` | `da = n * a.data**(n-1) * out.grad` |
| `relu` | `da = (out.data > 0) * out.grad` |

### Python 运算符重载（自动构建计算图）

```python
def __add__(self, other):   # self + other
def __radd__(self, other):   # other + self
def __mul__(self, other):    # self * other
def __rmul__(self, other):   # other * self
def __neg__(self):           # -self
def __sub__(self, other):    # self - other
def __rsub__(self, other):   # other - self
def __pow__(self, other):    # self ** other
def __truediv__(self, other): # self / other
def __rtruediv__(self, other): # other / self
def relu(self):              # max(0, self)
```

## nn.py — PyTorch-like 层

```python
class Module:  # 基础类
    def zero_grad(self): ...
    def parameters(self): return []  # 子类覆盖

class Neuron(Module):
    def __init__(self, nin, nonlin=True):
        self.w = [Value(random.uniform(-1,1)) for _ in range(nin)]
        self.b = Value(0)
        self.nonlin = nonlin
    def __call__(self, x):
        act = sum((wi*xi for wi,xi in zip(self.w, x)), self.b)
        return act.relu() if self.nonlin else act
    def parameters(self): return self.w + [self.b]

class Layer(Module):
    def __init__(self, nin, nout, **kwargs):
        self.neurons = [Neuron(nin, **kwargs) for _ in range(nout)]
    def __call__(self, x):
        return [n(x) for n in self.neurons]
    def parameters(self): ...

class MLP(Module):
    def __init__(self, nin, nouts):  # nouts = [16, 16, 1]
        sz = [nin] + nouts
        self.layers = [Layer(sz[i], sz[i+1],
                             nonlin=i!=len(nouts)-1)
                       for i in range(len(nouts))]
    def __call__(self, x):
        for layer in self.layers: x = layer(x)
        return x
```

## qclaw 可移植设计点

### 1. 拓扑排序反向遍历（通用模式）

```python
# 通用拓扑排序（从 loss 反向遍历依赖图）
def topological_sort(root):
    topo, visited = [], set()
    def build(v):
        if v not in visited:
            visited.add(v)
            for child in v._prev: build(child)
            topo.append(v)  # 后序：children 先于 parent
    build(root)
    return reversed(topo)
```

**qclaw 应用**：evolver 的 rule → outcome 链式推理，或 self_review 的 feedback → belief 更新。

### 2. _backward 闭包捕获（延迟计算）

```python
# 每个操作定义自己的反向函数
def __mul__(self, other):
    out = Value(self.data * other.data, (self, other), '*')
    def _backward():
        self.grad += other.data * out.grad   # 闭包捕获
        other.grad += self.data * out.grad
    out._backward = _backward
    return out
```

**qclaw 应用**：在 evolver.py 的规则引擎中，每个 rule 的执行结果可以用同样方式注册 backward hook，实现因果链的可追踪。

### 3. Module.parameters() 递归收集

```python
def parameters(self):
    return [p for layer in self.layers for p in layer.parameters()]
```

**qclaw 应用**：agents/tool_registry.py 的工具递归注册，或 skill_evolution/registry.py 的 skill 树形收集。

### 4. zero_grad 模式（梯度清零）

```python
def zero_grad(self):
    for p in self.parameters(): p.grad = 0
```

**qclaw 应用**：evolver 每轮重置 confidence 计分，或 heartbeat 心跳间的状态清零。

## 与 micrograd 互补的 qclaw 已有模块

| micrograd 概念 | qclaw 对应 |
|---------------|-----------|
| Value(data, grad) | evolver_rule(success, attempts) |
| backward() | evolver.record() |
| topological sort | evolver.recall() 路径搜索 |
| Neuron(weights) | skill_evolution/registry |
| MLP.forward() | agents/multi_agent_dispatcher |

## 扩展方向

- **Jacobian**：Value.grad 从标量扩展到矩阵（用于多输出 loss）
- **GPU 支持**：用 CUDA tensor 替代标量（nanoGPT 的做法）
- **JIT 编译**：torch.compile() 加速（nanoGPT 的做法）
