# lianghua R43 审查报告

**时间**：2026-06-18 11:51 GMT+8
**审查对象**：E:\lianghua\trend_trader.py（4210行，11:36更新）
**审查方法**：直接 read file 逐段 eyeball，变量追踪

---

## 结论：🔴 有 P0 致命Bug，空头开仓100%失败

综合评分：**4.0/10**（存在P0致命Bug，必须修复后才能运行）

---

## 🔴 P0 致命Bug（必须立即修复）

**P0-1：`POTENTIAL_EXIT_MAP` 未定义**
- **位置**：L3493
- **代码**：`exit_cfg = POTENTIAL_EXIT_MAP.get(pot, POTENTIAL_EXIT_MAP[1])`
- **问题**：`POTENTIAL_EXIT_MAP` 变量从未在文件中定义，也不在 config.py 中
- **影响**：空头开仓时 100% 触发 NameError，虽然被外层 try/except 捕获不会崩溃，但空头信号永远无法开仓
- **严重性**：🔴 P0 致命（功能完全失效）
- **验证**：
  ```powershell
  Get-Content "E:\lianghua\trend_trader.py" | Select-String "POTENTIAL_EXIT"
  # 只有一行输出：L3493 使用，无定义
  ```

---

## 新增功能（相比 R42）

1. **多币种回退（ETHUSDT）** — L3030-L3040
   - BTC 评分不足时，尝试用 ETH 信号开仓
   - 问题：`from trend_trader import compute_signal` 在自己模块内导入自己，可能循环依赖

2. **去噪过滤（potential=0）** — L3227, L3360
   - potential=0 的信号跳过，避免噪声开仓

3. **potential 分级止损** — 空头用 POTENTIAL_EXIT_MAP（但未定义！）

4. **auto_start=True** — L458
   - 开机自动连接并启动交易循环

5. **Signal Quality Tracker (SQT)** — L468
   - 信号质量追踪，连续低质量信号暂停开仓

---

## 核心逻辑验证（部分通过）

### 1. 多头止损止盈 ✅（仍然正确）
- SL = entry - atr * STOP_LOSS_ATR（下方）
- TP = entry + atr * TAKE_PROFIT_ATR（上方）

### 2. 空头止损止盈 🔴（致命Bug）
- 代码意图：SL = entry + atr * exit_cfg["sl_atr"]（上方）
- **实际：NameError，无法执行**

### 3. compute_signal ✅（未变化）

### 4. 仓位计算 ✅（增加了 potential 参数）

---

## P1/P2 问题（延续 R41/R42）

**P1-1**：`compute_signal_with_ml()` 调用 `compute_ema` 未做 HAS_INDICATORS 检查（未变化）

**P1-2**：PTP 分支返回值问题（未变化）

**P1-3**：`deserialize_tiers` 未定义（未变化）

**P2-1**：参数覆盖问题（未变化）

---

## 修复建议（按优先级）

### 🔴 P0-1 修复（紧急）

**方案A**：添加默认定义（在 L480 附近）
```python
POTENTIAL_EXIT_MAP = {
    1: {"sl_atr": 1.5, "tp_atr": 2.5, "trail_start": None, "trail_dist": None},
    2: {"sl_atr": 2.0, "tp_atr": 3.0, "trail_start": 2.5, "trail_dist": 1.5},
    3: {"sl_atr": 2.5, "tp_atr": 0, "trail_start": 3.0, "trail_dist": 1.25},
}
```

**方案B**：从 config.py 导入（需在 config.py 中定义）
```python
# config.py 中添加
POTENTIAL_EXIT_MAP = {...}

# trend_trader.py 中添加
try:
    from config import POTENTIAL_EXIT_MAP
except ImportError:
    POTENTIAL_EXIT_MAP = {...}  # fallback
```

---

## 建议

1. **立即修复 P0-1**（空头开仓完全失效）
2. 修复后重新测试：模拟盘跑1-2天
3. P1/P2 问题可在后续迭代修复
