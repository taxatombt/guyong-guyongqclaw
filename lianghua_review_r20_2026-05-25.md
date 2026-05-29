# lianghua — 第20轮功能审查报告
**审查时间**: 2026-05-25 18:00 CST
**审查范围**: `trading_loop()` 完整流程（L1471-1791）+ 平仓逻辑 + 持仓管理

---

## 功能走查结果

### ✅ 正常工作的部分

| 模块 | 状态 | 说明 |
|---|---|---|
| 交易循环入口 | ✅ | `trading_loop()` 结构完整 |
| 周末熔断 | ✅ | `is_weekend_cutoff()` 强制平仓 |
| 冷却检查 | ✅ | `check_counters()` 熔断冷却 |
| 风险熔断 | ✅ | `circuit_breaker` 禁止开仓 |
| K线获取 | ✅ | `get_klines()` 有超时+降级 |
| 信号计算 | ✅ | ADX+ATR+RSI+得分 全部计算 |
| Kronos增强 | ✅ | `get_signal_score()` 有try/except |
| HeikinAshi增强 | ✅ | `heikin_ashi_signal_score()` 有try/except |
| 多头开仓 | ✅ | 全套检查（regime+HTF+置信度+仓位上限）|
| 空头开仓 | 🟡 | 缺 regime 检查（见下） |
| 持仓止损止盈 | ✅ | `check_stop_loss_and_profit()` 多/空均处理 |
| 跟踪止盈 | ✅ | 多/空均正确更新激活价 |
| 平仓 | ✅ | `close_position()` 状态重置完整 |
|  SQLite持久化 | ✅ | `open_position/close_position_db()` 有try/except |

---

## 🔴 P1-3 功能漏洞：空头缺 `should_forbid_new_position`（确认）

**位置**: L1684（空头信号块）

**多头有，空头无**：
```python
# L1580-1596 多头 ✅ 有
if HAS_INDICATORS:
    from indicators import should_forbid_new_position
    if should_forbid_new_position(regime_ind, price, ema200_ind, adx_ind, pos != "none"):
        log(f"禁止开仓 | regime={regime_ind}", "RISK")
        continue

# L1684+ 空头 ❌ 完全没有这段
```

**后果**: 熊市/弱势市场可以开空（多头会被 `should_forbid_new_position` 拦住，空头不会）。

**修复**: 在 L1684（`elif score <= SHORT_SIGNAL_THRESHOLD`）之后、HTF 确认之前，加入和多头相同的 regime 检查块。

---

## 🟡 P1-1：`price` 未定义（首轮静默失败）

**位置**: L1506
```python
lp = t.get("lastPrice", price)   # price 此时未定义（L1516才定义）
```

**保护**: 在 `try: except Exception: pass` 内，静默失败。

**后果**: 首轮循环市场快照失效，但 `get_price()` 在 L1516 会重新获取，不影响交易。

**优先级**: P2（有保护，不影响功能）

---

## 🟡 `is_bear_market` 只拦多头（是否 Bug？）

**位置**: L1483
```python
if is_bear_market(klines) and state.get("position", "none") == "none":
    log("熊市检测触发，禁止开多仓", "RISK")
```

**分析**: 熊市做空是合理的，所以只拦多头可能是**有意设计**。

**建议**: 加注释说明设计意图，或改为可配置（熊市禁开仓/仅允许开空）。

---

## ✅ 平仓逻辑验证

`close_position()` (L1252-1302):
- 锁外读取 position/qty/entry_price ✅
- 锁外调用 `place_order()` ✅（避免死锁）
- 锁内更新 state ✅（position→none, qty→0, SL→0, trailing→0）
- SQLite 记录平仓 ✅
- 状态立即持久化（不受 debounce 影响）✅

**结论**: 平仓逻辑无功能漏洞。

---

## ✅ 持仓管理验证

`check_stop_loss_and_profit()` (L1316-1396+):
- 多/空止损均正确 ✅
- 多/空固定止盈均正确 ✅
- 多/空跟踪止盈均正确 ✅
- 分层止盈（PTP）有 `HAS_PROGRESSIVE_TAKE_PROFIT` 保护 ✅

**结论**: 持仓管理无功能漏洞。

---

## 综合评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 交易逻辑完整性 | 85% | 空头缺 regime 检查（-15%）|
| 风险管理 | 90% | 熔断/冷却/仓位上限均完整 |
| 状态管理 | 95% | 锁粒度合理，持久化及时 |
| 错误处理 | 70% | 8处 `except:pass` 静默吞错 |

---

## 建议修复（按优先级）

| 序号 | 内容 | 位置 | 级别 |
|---|---|---|---|
| 1 | 空头加 `should_forbid_new_position` 检查 | L1684 | P1 |
| 2 | `is_bear_market` 加注释或改为可配置 | L1483 | P2 |
| 3 | `price` 提前到 L1506 之前定义 | L1506 | P2 |
| 4 | 8处 `except:pass` 至少加 `log()` | 多处 | P2 |

---

*审查人: 顾庸 | 第20轮（功能审查）| 2026-05-25 18:00 CST*