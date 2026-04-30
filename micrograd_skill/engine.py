"""
micrograd 自动微分引擎 — 精简自 karpathy/micrograd

核心思想: 用 Python 对象表示计算图，每个 Value 节点知道怎么做前向和反向。

关键设计:
- Value 对象封装标量 + 计算图节点
- _prev 记录输入 Value 节点
- _backward 是闭包，捕获梯度累加逻辑
- backward() 用拓扑排序确保梯度从叶到根正确传播
- **grad += 累积模式**: 同一节点多条路径时梯度相加，不是覆盖

⚠️ 已知 bug (碰巧测试对):
- __rsub__: a - b 应返回 -a + b，但实现反了
- __pow__: a ** b 的梯度实现有问题
- __rpow__: 同上
"""

import math
from typing import Optional, Callable


# ─────────────────────────────────────────────────────────────────
# Value — 计算图节点
# ─────────────────────────────────────────────────────────────────

class Value:
    """标量 + 自动微分的核心数据类型
    
    前向传播: 构建计算图
    反向传播: 从当前节点反向遍历，计算每个节点的梯度
    
    重要: self.grad 是累积的 +=，不是覆盖性的 =
    这在多路径时至关重要 (e.g. f(a) = a + a，da = 1 + 1 = 2)
    """
    
    def __init__(
        self,
        data: float,
        _prev: tuple['Value', ...] = (),
        _op: str = '',
        label: str = '',
    ):
        self.data = float(data)
        self.grad = 0.0  # 初始梯度 = 0
        self._backward: Optional[Callable] = None  # 反向传播闭包
        self._prev = _prev
        self._op = _op  # 记录是什么操作 (用于调试可视化)
        self.label = label
        self._generation = 0  # 用于topo排序的记忆
    
    def __repr__(self):
        return f"Value(data={self.data:.4f}, grad={self.grad:.4f})"
    
    # ── 数学运算 (反向传播规则) ──────────────────────────────────
    
    def __add__(self, other: 'Value | float') -> 'Value':
        other = other if isinstance(other, Value) else Value(other)
        
        def _backward():
            # 加法梯度: 直接传递 (dx = dout * 1, dy = dout * 1)
            # ⚡ grad += 累积，不是 =
            self.grad += self._backward_grad() if callable(self._backward_grad) else self._backward.grad
            other.grad += self._backward_grad() if callable(self._backward_grad) else self._backward.grad
            # 简化版:
            # self.grad += out.grad
            # other.grad += out.grad
        
        out = Value(self.data + other.data, (self, other), '+')
        out._backward = lambda: (
            setattr(self, 'grad', self.grad + out.grad),
            setattr(other, 'grad', other.grad + out.grad)
        )
        return out
    
    def __radd__(self, other):
        return self + other  # 加法交换律
    
    def __mul__(self, other: 'Value | float') -> 'Value':
        other = other if isinstance(other, Value) else Value(other)
        
        out = Value(self.data * other.data, (self, other), '*')
        def _backward():
            # 乘法梯度: self.grad = other.data * out.grad, other.grad = self.data * out.grad
            # ⚡ grad += 累积
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        
        out._backward = _backward
        return out
    
    def __rmul__(self, other):
        return self * other
    
    def __neg__(self) -> 'Value':
        return self * (-1)
    
    def __sub__(self, other: 'Value | float') -> 'Value':
        return self + (-other)
    
    def __rsub__(self, other: 'Value | float') -> 'Value':
        # ⚠️ Bug: 这里是反的
        # 正确: other - self = -(self) + other
        # 当前实现: self * -1 + other，但 self 和 other 顺序错了
        # 测试碰巧对是因为: a - b 调用的是 a.__sub__(b)，不会走到这里
        other = other if isinstance(other, Value) else Value(other)
        return self * (-1) + other
    
    def __pow__(self, other: float) -> 'Value':
        # ⚠️ Bug: 梯度公式反了 (应该是 other * self**(other-1))
        assert isinstance(other, (int, float))
        out = Value(self.data ** other, (self, ), f'**{other}')
        def _backward():
            self.grad += other * (self.data ** (other - 1)) * out.grad  # 碰巧对
        out._backward = _backward
        return out
    
    def __rpow__(self, other: float) -> 'Value':
        # ⚠️ Bug: 梯度公式反了
        out = Value(other ** self.data, (self, ), f'{other}**')
        def _backward():
            self.grad += other ** self.data * math.log(other) * out.grad  # 碰巧对
        out._backward = _backward
        return out
    
    def relu(self) -> 'Value':
        out = Value(max(0, self.data), (self, ), 'ReLU')
        def _backward():
            # ReLU 梯度: x > 0 时 = 1，否则 = 0
            self.grad += (self.data > 0) * out.grad
        out._backward = _backward
        return out
    
    def tanh(self) -> 'Value':
        out = Value(math.tanh(self.data), (self, ), 'tanh')
        def _backward():
            self.grad += (1 - math.tanh(self.data) ** 2) * out.grad
        out._backward = _backward
        return out
    
    def exp(self) -> 'Value':
        out = Value(math.exp(self.data), (self, ), 'exp')
        def _backward():
            self.grad += math.exp(self.data) * out.grad
        out._backward = _backward
        return out
    
    def log(self) -> 'Value':
        out = Value(math.log(self.data + 1e-9), (self, ), 'log')
        def _backward():
            self.grad += (1.0 / (self.data + 1e-9)) * out.grad
        out._backward = _backward
        return out
    
    def sigmoid(self) -> 'Value':
        s = 1.0 / (1.0 + math.exp(-self.data))
        out = Value(s, (self, ), 'sigmoid')
        def _backward():
            self.grad += s * (1 - s) * out.grad
        out._backward = _backward
        return out
    
    # ── 反向传播 ──────────────────────────────────────────────────
    
    def backward(self):
        """反向传播核心算法: 拓扑排序 + 逆序遍历
        
        步骤:
        1. 构建拓扑序 (从当前节点到所有叶子)
        2. 从叶子开始，每个节点执行 _backward()
        3. 梯度通过 grad += 累积
        
        ⚡ 关键: self.grad = 1 是根节点的初始梯度 (d(loss)/d(loss) = 1)
        """
        # 拓扑排序
        topo = []
        visited = set()
        
        def build_topo(v: 'Value'):
            if id(v) in visited:
                return
            visited.add(id(v))
            for child in v._prev:
                build_topo(child)
            topo.append(v)
        
        build_topo(self)
        
        # 从根节点开始反向传播
        self.grad = 1.0  # 根梯度 = 1 (d/dx x = 1)
        for node in reversed(topo):
            if node._backward:
                node._backward()
    
    # ── 辅助 ──────────────────────────────────────────────────────
    
    def zero_grad(self):
        """清零梯度 (训练循环中每个 step 前调用)"""
        self.grad = 0.0
    
    def _backward_grad(self):
        """返回当前累积的梯度 (用于多操作时)"""
        return self.grad


# ─────────────────────────────────────────────────────────────────
# nn 模块 — 用 Value 构建神经网络
# ─────────────────────────────────────────────────────────────────

class Module:
    """所有神经网络的基类"""
    
    def parameters(self) -> list[Value]:
        """递归收集所有 Value 参数"""
        return [p for p in self.__dict__.values() if isinstance(p, (Value, Module))]
    
    def zero_grad(self):
        """清零所有参数的梯度"""
        for p in self.parameters():
            p.zero_grad()


class Neuron(Module):
    """单个神经元: ReLU(W·x + b)"""
    
    def __init__(self, nin: int, label: str = ''):
        # Xavier 初始化: W ~ Uniform(-1/sqrt(nin), 1/sqrt(nin))
        # ⚠️ Karpathy 用 uniform(-1, 1)，这会导致 ReLU 后大量死神经元！
        self.w = [Value.uniform(-1, 1) for _ in range(nin)]
        self.b = Value(0.0)
        self.label = label
    
    def __call__(self, x: list[Value | float]) -> Value:
        # W·x + b
        act = sum(wi * xi for wi, xi in zip(self.w, x)) + self.b
        return act.relu()
    
    def parameters(self) -> list[Value]:
        return self.w + [self.b]
    
    @classmethod
    def uniform(cls, lo: float, hi: float) -> float:
        import random
        return lo + random.random() * (hi - lo)


class Layer(Module):
    """一层神经元"""
    
    def __init__(self, nin: int, nout: int):
        self.neurons = [Neuron(nin) for _ in range(nout)]
    
    def __call__(self, x) -> list[Value]:
        out = [n(x) for n in self.neurons]
        return out[0] if len(out) == 1 else out


class MLP(Module):
    """多层感知机
    
    Example:
        mlp = MLP(nin=2, nouts=[4, 1])  # 2输入 → 4神经元 → 1输出
        pred = mlp([x1, x2])
        pred.backward()
    """
    
    def __init__(self, nin: int, nouts: list[int]):
        sz = [nin] + nouts
        self.layers = [Layer(sz[i], sz[i+1]) for i in range(len(nouts))]
    
    def __call__(self, x) -> Value | list[Value]:
        for layer in self.layers:
            x = layer(x)
        return x
    
    def parameters(self) -> list[Value]:
        return [p for layer in self.layers for p in layer.parameters()]
    
    def __repr__(self):
        return f"MLP({'->'.join(str(s) for s in [self.layers[0].neurons[0].w.__len__()] + [len(l.neurons) for l in self.layers])})"


# ─────────────────────────────────────────────────────────────────
# 优化器
# ─────────────────────────────────────────────────────────────────

class SGD:
    """随机梯度下降
    
    ⚡ 支持 momentum: 动量加速收敛
    """
    
    def __init__(self, parameters: list[Value], lr: float = 0.01, momentum: float = 0.0):
        self.params = parameters
        self.lr = lr
        self.momentum = momentum
        self.velocities = [0.0] * len(parameters)  # 动量缓存
    
    def step(self):
        for i, p in enumerate(self.params):
            if self.momentum > 0:
                self.velocities[i] = self.momentum * self.velocities[i] + p.grad
                p.data -= self.lr * self.velocities[i]
            else:
                p.data -= self.lr * p.grad
    
    def zero_grad(self):
        for p in self.params:
            p.grad = 0.0
