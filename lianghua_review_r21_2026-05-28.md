# lianghua — 第21轮审查报告（配置一致性审查）
**审查时间**: 2026-05-28 02:10 CST
**审查方式**: 实际执行脚本验证（不只是读代码）

---

## 🔴 配置偏差（config.py vs 代码期望值）

| 参数 | config.py 实际值 | STRATEGY.md / 期望值 | 偏差 |
|---|---|---|---|
| `TAKE_PROFIT_ATR` | **2.0** | 3.0 | 🔴 ATR止盈空间少33% |
| `TRAILING_ATR` | **None(未定义)** | 2.0 | 🔴 跟踪止盈完全失效 |
| `SIGNAL_THRESHOLD` | **4** | 4.5 | 🟡 多头阈值偏低 |
| `LEVERAGE` | **1.5** | 5 | 🔴 杠杆偏低（影响仓位计算）|
| `ENABLE_KELLY` | **None(未定义)** | False | 🟡 未定义会导致读取报错 |
| `ATR_ADAPTIVE` | **None(未定义)** | True | 🔴 自适应ATR失效，退回固定周期 |
| `HAS_CONFIG_HOT_RELOAD` | **None(未定义)** | False | 🟡 未定义→导入失败→HAS=false |

---

## ✅ 验证通过项

| 检查项 | 结果 |
|---|---|
| `PAPER_SIMULATE` = True | ✅ |
| `DETECT_BEAR_MARKET` = False | ✅ |
| `STOP_LOSS_ATR` = 1.5 | ✅ |
| `SHORT_SIGNAL_THRESHOLD` = -3.0 | ✅ |
| `MAX_DAILY_TRADES` = 5 | ✅ |
| P1-3 空头 `should_forbid_new_position` | ✅ **已修复！**（上次R20我误判，实际已有）|
| 核心函数全部可导入 | ✅ |
| 平仓/止损/止盈逻辑 | ✅ |

---

## 🟡 GUI 问题（非致命）

**gui_only.py Tab内label仍用 `bg=_BG`**
- 影响：白底Tab上出现暗色标签块，视觉不统一
- 位置：L129/L131/L160/L163/L165/L167等约**20处**
- 修复：`bg=_BG` → `bg="white"`, `fg=_FG` → `fg="#333"`

---

## 🔴 关键Bug：`TRAILING_ATR` 未定义

**位置**: `trend_trader.py` L1384
```python
if atr and price <= tp - atr * TRAILING_ATR:   # ← NameError!
```

**后果**: 多头跟踪止盈**必崩**（`NameError: name 'TRAILING_ATR' is not defined`）

**同理空头** L1395:
```python
if atr and price >= tp + atr * TRAILING_ATR:   # ← 同样 NameError
```

**修复**: 在 `config.py` 中加 `TRAILING_ATR = 2.0`

---

## 🔴 关键Bug：`ATR_ADAPTIVE` 未定义

**位置**: `trend_trader.py` L509
```python
def get_adaptive_atr_period(adx_val):
    if not ATR_ADAPTIVE:   # ← NameError!
```

**后果**: `get_adaptive_atr()` 调用时**必崩**

**修复**: 在 `config.py` 中加 `ATR_ADAPTIVE = True`

---

## 综合评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 配置一致性 | **40%** | 6个参数偏差/缺失 |
| 交易逻辑 | 70% | 2个NameError会导致运行时崩溃 |
| GUI体验 | 85% | label颜色不统一（非致命）|
| 代码质量 | 75% | 8处裸except:pass |

---

## 建议修复（按优先级）

| 序号 | 内容 | 文件 | 级别 |
|---|---|---|---|
| 1 | `config.py` 加 `TRAILING_ATR = 2.0` | config.py | 🔴 P0 |
| 2 | `config.py` 加 `ATR_ADAPTIVE = True` | config.py | 🔴 P0 |
| 3 | `config.py` 加 `ENABLE_KELLY = False` | config.py | 🟡 P1 |
| 4 | `TAKE_PROFIT_ATR` 3.0 → 2.0（确认是否故意） | config.py | 🟡 P2 |
| 5 | gui_only.py label `bg=_BG` → `bg="white"` | gui_only.py | 🟡 P2 |

---

*审查人: 顾庸 | 第21轮（配置一致性审查）| 2026-05-28 02:10 CST*