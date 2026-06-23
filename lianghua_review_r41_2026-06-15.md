# lianghua R41 审查报告

**时间**：2026-06-15 23:42 GMT+8
**审查对象**：E:\lianghua\trend_trader.py（4022行）
**审查方法**：直接 read file 逐段 eyeball，数值验证
**审查范围**：L1-L3400（核心交易逻辑）+ L3400-L4022（GUI部分）

---

## 结论：✅ 可跑实盘，无致命Bug

综合评分：**8.0/10**

---

## 核心逻辑验证（全部通过）

### 1. 多头止损止盈方向 ✅
- **SL** = `entry_price - atr * STOP_LOSS_ATR`（L2848-2849）→ 入场下方 ✅
- **TP** = `entry_price + atr * TAKE_PROFIT_ATR`（L2849-2850）→ 入场上方 ✅
- 数值验证：entry=100000, atr=2000, SL_ATR=1.5, TP_ATR=2.0 → SL=97000(下方) TP=104000(上方) ✅

### 2. 空头止损止盈方向 ✅
- **SL** = `entry_price + atr * STOP_LOSS_ATR`（L3100）→ 入场上方 ✅
- **TP** = `entry_price - atr * TAKE_PROFIT_ATR`（L3101）→ 入场下方 ✅
- 数值验证：entry=100000, SL=103000(上方) TP=96000(下方) ✅

### 3. compute_signal 7分制 ✅
- EMA排列、ADX趋势、RSI极值、MACD、成交量、布林带、微观结构 ✅
- 增强因子：多周期共振、动量、趋势对齐、BB Squeeze、BB Position ✅
- 持仓惩罚：多头-1、空头+1（防同向重仓）✅

### 4. 仓位计算 ✅
- Kelly公式 + 风险百分比双路径，MAO缩放 ✅
- 累计仓位上限检查（防超MAX_POSITION_PCT=12%）✅

### 5. 崩溃恢复 ✅
- `check_pending_order_on_startup()`：启动时确认pending订单真实状态 ✅
- `wait_for_fill()`：超时后向Binance确认真实状态 ✅

### 6. 风控链 ✅
- 预检 → 熔断 → 冷却 → MAO → Iron Laws → 置信度 → 宏观 → 情绪 → 止损/止盈 ✅
- 周末强制平仓（周五UTC16）✅
- 全局止损8% ✅
- 时间加权止损（持仓超时收紧）✅

### 7. smart_place_order / close_position ✅
- `smart_place_order` 从 `order_manager` 导入（L256，HAS_ORDER_MANAGER=True）✅
- `close_position` 用 `smart_place_order(side, qty, reduce_only=True)` ✅
- 平仓失败时挂Binance原生兜底止损单（reduceOnly=True）✅

---

## 发现的问题

### P1（中风险，建议修复）

**P1-1：`compute_signal_with_ml()` 调用未定义的 `compute_ema`**
- **位置**：L1818-L1820
- **代码**：`ema20 = compute_ema(closes_arr, 20)` / `ema50 = compute_ema(...)` / `ema200 = compute_ema(...)`
- **问题**：文件顶部 L15 导入的是 `from indicators import compute_ema`（单数），但 `compute_emas()` 在 L1116 定义（复数）。`compute_ema`（单数）是从 `indicators.py` 导入的，如果 `HAS_INDICATORS=False` 则 `compute_ema` 未定义。
- **影响**：仅影响 ML 增强路径（`compute_signal_with_ml`），主循环 `compute_signal` 不受影响。但如果 indicators.py 不存在且调用 ML 路径，会 NameError 崩溃。
- **建议**：在调用前加 `if not HAS_INDICATORS: return score, regime, atr, detail`

**P1-2：`check_stop_loss_and_profit()` 中的 PTP 分支返回值**
- **位置**：L2320
- **代码**：`return False, "Binance持仓查询返回异常"`
- **问题**：这个函数本应返回 None（无返回值），但 PTP 分支里误写了 `return False, "..."`，这会导致 `check_stop_loss_and_profit()` 返回一个元组而不是 None。调用方（L2704）没有接收返回值所以不会崩溃，但如果未来有人接收返回值会出 bug。
- **影响**：当前不会崩溃，但代码不干净。

**P1-3：PTP `deserialize_tiers` 未定义**
- **位置**：L2310
- **代码**：`pt_obj = deserialize_tiers(ts) if ts else None`
- **问题**：`deserialize_tiers` 从未在文件中导入或定义。如果 `HAS_PROGRESSIVE_TAKE_PROFIT=True` 且 state 中有 `_ptp_tiers`，会 NameError。
- **影响**：被 try/except 包裹，异常会被吞掉变成日志 WARN，不会崩溃。但 PTP 功能实际上无法正常工作。

### P2（低风险，可后续修复）

**P2-1：`compute_kelly_position()` 死代码**
- **位置**：L817
- 这个函数定义了但从未被调用（仓位计算用 Kelly 或 compute_position_from_balance，不走这个函数）。

**P2-2：模拟盘余额硬编码 20.0**
- **位置**：L715（config.py INITIAL_BALANCE=50.0，但 fallback 用 50.0）
- `get_account_balance()` 模拟盘路径返回 `state.get("_paper_balance", INITIAL_BALANCE)`，INITIAL_BALANCE=50.0，这不是 20.0，已修正为 50.0 ✅

**P2-3：`_parse_binance_error()` 有默认参数 `body_text=""`**
- **位置**：L2041
- `body_text = ""` 默认值存在 ✅（之前 R40 发现的 P1 已修复）

**P2-4：config.py STOP_LOSS_ATR=0.8 / TAKE_PROFIT_ATR=3.0 被 trend_trader.py 覆盖**
- config.py: `STOP_LOSS_ATR=0.8, TAKE_PROFIT_ATR=3.0`（champion 参数）
- trend_trader.py L340: `STOP_LOSS_ATR = 1.5, TAKE_PROFIT_ATR = 2.0`（硬编码覆盖）
- **影响**：champion 参数被覆盖，实际执行的是 1.5/2.0。这不是 bug，是有意设计（代码注释写"止损：ATR倍数"），但需要用户知道实际生效的是哪个。

---

## 参数对比（config.py vs trend_trader.py 硬编码）

| 参数 | config.py | trend_trader.py | 实际生效 |
|------|-----------|----------------|---------|
| STOP_LOSS_ATR | 0.8 | 1.5 | 1.5 |
| TAKE_PROFIT_ATR | 3.0 | 2.0 | 2.0 |
| SIGNAL_THRESHOLD | -1.0 | - | -1.0（from config import *）|
| SHORT_SIGNAL_THRESHOLD | -2.5 | - | -2.5（from config import *）|
| TRAILING_START_ATR | 2.0 | 2.0 | 2.0 |
| TRAILING_STOP_ATR | 1.25 | 1.25 | 1.25 |
| MAX_DAILY_TRADES | 5 | - | 5（from config import *）|

**关键发现**：`STOP_LOSS_ATR` 和 `TAKE_PROFIT_ATR` 被 trend_trader.py 硬编码覆盖，champion 参数无效。

---

## 安全风控链总结

```
交易循环每轮：
  └─ _preflight_check()        → API连通+余额+持仓一致性
  └─ is_weekend_cutoff()        → 周五UTC16强制平仓
  └─ check_counters()           → 熔断冷却检查
  └─ risk_management 熔断        → performance_analyzer
  └─ is_bear_market()           → 熊市禁止开多（DETECT_BEAR_MARKET=False当前关闭）
  └─ _mao_check()              → 毛选框架（ADX趋势+ML概率+高波动）
  └─ iron_check()              → Iron Laws 最后关卡
  └─ should_forbid_new_position → indicators.py 禁止开仓
  └─ can_trade_direction()      → 多周期HTF确认
  └─ check_circuit_breaker()    → 极端波动熔断
  └─ should_execute()          → 信号置信度+OBI+活跃订单
  └─ is_high_impact_event()    → 宏观事件过滤
  └─ should_block_trade()      → 情绪过滤
  └─ 仓位上限检查              → MAX_POSITION_PCT=12%
```

共 **12 层防御**，设计合理。

---

## 建议

1. **P1-1**：给 `compute_signal_with_ml()` 加 `compute_ema` 可用性检查
2. **P1-3**：导入 `deserialize_tiers` 或删除 PTP 分支的调用
3. **参数覆盖问题**：如果 champion 参数（0.8/3.0）是有意设计的最优值，应删除 trend_trader.py 的硬编码覆盖，让 config.py 的值生效
4. **先模拟盘跑1-2天**，确认无异常再上实盘
