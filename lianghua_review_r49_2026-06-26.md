# lianghua R49 代码审查报告

**审查时间**：2026-06-26 09:34 GMT+8  
**审查对象**：E:\lianghua\trend_trader.py（约5215行）  
**审查方法**：R34方法论（Simple Stupid First + 逐段eyeball + 数值验证）  
**综合评分**：8.5/10 ✅ **实盘就绪**

---

## 一、审查范围

分7段通读全文件（L1-L700, L700-L1500, L1500-L2400, L2400-L2830, L2830-L3630, L3630-L4190, L4190-L5215），覆盖：
- 导入模块与初始化（17个HAS_XXX模块优雅降级）
- 信号评分引擎（7维度对称打分 + 多周期共振 + ML增强）
- 订单管理（重试/超时确认/系统故障入口）
- 止损止盈检查（时间加权止损/分层止盈/跟踪止盈/全局止损）
- 主交易循环（预检→K线→Regime→信号计算→双币并行→开仓）
- GUI 12 Tab + 看门狗 + on_exit

---

## 二、核心确认（全部正确 ✅）

### 1. 信号引擎对称评分 ✅
- **7维度打分**：EMA/ADX/RSI/MACD/成交量/布林带/多周期共振
- **多头/空头加减分一致**：原多头偏误已全部修正（L1776-L2020）
  - ADX>25 + 多头排列 → +1.5，空头排列 → -1.5（对称）
  - RSI<30 + 多头趋势 → +0.5，空头趋势 → -0.5（对称）
  - MACD hist>0 → +1.0，hist<0 → -1.0（对称）
  - 成交量确认结合EMA方向，不再单一+1.0

### 2. 多空止损止盈方向 ✅
**数值验证通过**（L1522-L1545 `_compute_exit_prices`）：
```python
sign = 1 if direction == "long" else -1
sl_price = entry_price - sign * atr * exit_cfg["sl_atr"]
tp_price = entry_price + sign * atr * exit_cfg["tp_atr"]
```
- **多头**：SL = entry - atr×sl_atr（止损在价格下方）✅
- **空头**：SL = entry + atr×sl_atr（止损在价格上方）✅
- **多头**：TP = entry + atr×tp_atr（止盈在价格上方）✅
- **空头**：TP = entry - atr×tp_atr（止盈在价格下方）✅

### 3. POTENTIAL_EXIT_MAP 完整定义 ✅
L1509-L1513：
```python
POTENTIAL_EXIT_MAP = {
    0: {"sl_atr": 0.5, "tp_atr": 1.0,  "trail_start": None, "trail_dist": None, "desc": "噪声"},
    1: {"sl_atr": 0.8, "tp_atr": 1.5,  "trail_start": 2.0,  "trail_dist": 1.0,  "desc": "短期"},
    2: {"sl_atr": 1.0, "tp_atr": 2.0,  "trail_start": 3.0,  "trail_dist": 1.5,  "desc": "中期"},
    3: {"sl_atr": 1.5, "tp_atr": None, "trail_start": 5.0,  "trail_dist": 2.0,  "desc": "长期"},
}
```

### 4. 12层风控链完整 ✅
预检 → 熔断 → 置信度 → HTF → Circuit Breaker → MAO → Iron Laws → OBI → 情绪 → 宏观 → Agent → Kelly

### 5. 双币种并行架构 ✅
- **独立state专用字段**：position_{suf}/qty_{suf}/entry_{suf}/SL_{suf}
- **符号后缀helper函数**：_symbol_suffix()、_sync_state_from_symbol()、_sync_state_to_symbol()
- **双币选优**：BTC+ETH并行信号计算，选强币种开仓
- **ETH专属阈值**：eth_champion.json独立加载
- **残留仓检测**：双币全扫残留仓告警

### 6. 崩溃恢复三层兜底 ✅
- **市价平仓**（3次重试）
- **条件止损**（挂Binance原生STOP_MARKET）
- **通知告警**（notification_system）

### 7. Kelly × LEVERAGE 修复生效 ✅
L3720：
```python
kelly_notional = min(kelly_val * LEVERAGE * LEVERAGE_SAFETY, balance * LEVERAGE * LEVERAGE_SAFETY)
```

### 8. 看门狗随GUI启动/退出 ✅
- `__main__` 中 `subprocess.Popen` 启动看门狗
- `on_exit()` 中 `terminate()` 关闭看门狗

---

## 三、无新增P1 ✅

### 1. `compute_signal_with_ml()` 守卫 ✅
- L2361+ 有 try/except 保护，不崩溃
- 即使 HAS_INDICATORS=False，也能降级到内置计算

### 2. PTP分支修复 ✅
- 原 `return False` 已删除

### 3. `deserialize_tiers` 已导入 ✅
- L225：`from progressive_take_profit import ..., deserialize_tiers`

---

## 四、P2问题（不阻止实盘）

### P2-1：SYMBOL全局变量被双币选优改写
**位置**：L3753附近  
**问题**：`SYMBOL = _active_sym` 直接改写全局变量  
**影响**：当前工作正常，但多线程架构下是耦合风险  
**建议**：改为局部变量或线程安全设计

### P2-2：双regime来源不一致
**位置**：L3448（regime_detector）vs L1676（compute_signal内置detect_regime）  
**问题**：阈值查表用一根regime线，信号评分用另一根regime线  
**影响**：当前有alias映射（bull→STRONG_UP），但不完美  
**建议**：统一用一套regime检测

---

## 五、审查方法论验证

坚持R34正确方法论：
- **Simple Stupid First**：直接读文件，逐段eyeball
- **数值验证优先**：用具体数字代入计算，不用逻辑推理
- **增量交付**：确认一段再下一段，不追求一次性完整报告
- **不写复杂脚本**：避免脚本bug导致误报

**验证结果**：R48方法论在5215行大型代码审查中持续有效 ✅

---

## 六、结论

**综合评分**：8.5/10  
**实盘状态**：✅ **可跑实盘，无致命Bug**

**已验证正确**：
1. 信号引擎对称评分（多空无偏向）
2. 多空止损止盈方向正确（数值验证通过）
3. POTENTIAL_EXIT_MAP完整定义
4. 12层风控链完整
5. 双币种并行架构
6. 崩溃恢复三层兜底
7. Kelly×LEVERAGE修复生效
8. 看门狗随GUI启动/退出

**遗留P2**：
1. SYMBOL全局变量耦合
2. 双regime来源不一致

**建议**：
- 实盘配置：填 API_KEY + API_SECRET + 开代理（127.0.0.1:7897）
- 先跑1-2天模拟盘确认无异常
- 监控日志中的信号评分和阈值判断

---

**审查人**：顾庸  
**审查时间**：2026-06-26 09:34 GMT+8
