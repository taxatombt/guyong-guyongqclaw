"""
micrograd 训练演示 — 用自动微分训练 MLP

示例任务:
1. XOR 问题 — 经典的非线性可分问题
2. 简单函数逼近 — 学习 y = sin(x) 曲线

核心循环:
    for epoch in range(epochs):
        pred = model(inputs)        # 前向
        loss = criterion(pred, y)   # 计算 loss
        loss.backward()             # 反向传播 (自动求梯度!)
        optimizer.step()            # 更新参数
        optimizer.zero_grad()       # 清零梯度 (下一轮)
"""

import random
import math
from engine import Value, MLP, SGD


# ─────────────────────────────────────────────────────────────────
# 数据生成
# ─────────────────────────────────────────────────────────────────

def make_xor_data(n=100):
    """XOR 数据: 经典的非线性可分问题
    
    线性分类器无法解决，但 MLP 可以（隐藏层提供非线性）。
    
    数据:
        (0,0) → 0
        (0,1) → 1
        (1,0) → 1
        (1,1) → 0
    """
    X = [
        [0.0, 0.0],
        [0.0, 1.0],
        [1.0, 0.0],
        [1.0, 1.0],
    ]
    y = [0.0, 1.0, 1.0, 0.0]
    
    # 重复 n 次，加噪声
    X_out, y_out = [], []
    for _ in range(n):
        for xi, yi in zip(X, y):
            x = [xi[0] + random.uniform(-0.1, 0.1),
                 xi[1] + random.uniform(-0.1, 0.1)]
            X_out.append(x)
            y_out.append(yi)
    
    return X_out, y_out


def make_sine_data(n=200):
    """y = sin(x) 数据"""
    X, y = [], []
    for _ in range(n):
        x = random.uniform(-math.pi, math.pi)
        X.append([x])
        y.append(math.sin(x))
    return X, y


# ─────────────────────────────────────────────────────────────────
# MSE Loss
# ─────────────────────────────────────────────────────────────────

def mse_loss(pred: list[Value], y_true: list[float]) -> Value:
    """均方误差 Loss"""
    assert len(pred) == len(y_true)
    losses = [(p - yt) ** 2 for p, yt in zip(pred, y_true)]
    return sum(losses) / len(losses)


# ─────────────────────────────────────────────────────────────────
# 训练循环
# ─────────────────────────────────────────────────────────────────

def train(
    model: MLP,
    X: list[list[float]],
    y: list[float],
    epochs: int = 300,
    lr: float = 0.5,
    log_interval: int = 50,
):
    """训练 MLP"""
    
    optimizer = SGD(model.parameters(), lr=lr)
    
    losses = []
    for epoch in range(epochs):
        # 前向
        preds = [model(xi)[0] for xi in X]  # [0] 因为输出是单元素列表
        
        # Loss
        loss = mse_loss(preds, y)
        losses.append(loss.data)
        
        # 反向
        optimizer.zero_grad()
        loss.backward()
        
        # 更新
        optimizer.step()
        
        # 日志
        if epoch % log_interval == 0:
            # 计算准确率 (for classification)
            if set(y) == {0.0, 1.0}:
                correct = sum((p.data > 0.5) == (yt > 0.5) 
                             for p, yt in zip(preds, y))
                acc = correct / len(y)
                print(f"Epoch {epoch:4d} | loss={loss.data:.4f} | acc={acc:.1%}")
            else:
                print(f"Epoch {epoch:4d} | loss={loss.data:.6f}")
    
    return losses


# ─────────────────────────────────────────────────────────────────
# XOR 演示
# ─────────────────────────────────────────────────────────────────

def demo_xor():
    print("=" * 50)
    print("XOR 问题演示 (非线性可分)")
    print("=" * 50)
    
    X, y = make_xor_data(n=50)
    
    # 关键: 必须有隐藏层才能解决 XOR
    # 2 -> 4 -> 1: 2输入, 4隐藏神经元, 1输出
    model = MLP(nin=2, nouts=[4, 1])
    
    print(f"模型: {model}")
    print(f"参数: {len(model.parameters())} 个")
    print()
    
    losses = train(model, X, y, epochs=300, lr=0.5, log_interval=50)
    
    # 测试
    print("\n测试:")
    test_cases = [[0,0], [0,1], [1,0], [1,1]]
    for x in test_cases:
        out = model(x)[0]
        pred = 1 if out.data > 0.5 else 0
        print(f"  {x} -> pred={pred:.0f} (prob={out.data:.3f})")
    
    return losses


# ─────────────────────────────────────────────────────────────────
# Sine 逼近演示
# ─────────────────────────────────────────────────────────────────

def demo_sine():
    print("\n" + "=" * 50)
    print("y = sin(x) 函数逼近")
    print("=" * 50)
    
    X, y = make_sine_data(n=200)
    
    # 1 -> 8 -> 8 -> 1: 足够宽的隐藏层
    model = MLP(nin=1, nouts=[8, 8, 1])
    
    print(f"模型: {model}")
    print(f"参数: {len(model.parameters())} 个")
    print()
    
    losses = train(model, X, y, epochs=500, lr=0.1, log_interval=100)
    
    # 测试
    print("\n测试 (x -> pred vs true):")
    for x in [-math.pi, -math.pi/2, 0, math.pi/2, math.pi]:
        out = model([x])[0]
        print(f"  x={x:+.3f} -> pred={out.data:+.3f} (true={math.sin(x):+.3f})")
    
    return losses


# ─────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("micrograd 训练演示")
    print("核心: 前向 -> Loss -> backward() -> step()")
    print()
    
    # 固定随机种子 (可复现)
    random.seed(42)
    
    demo_xor()
    demo_sine()
