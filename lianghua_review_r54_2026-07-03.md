# lianghua R54 审查报告 — 配置加载链与参数覆盖顺序

**时间**：2026-07-03 01:20 GMT+8  
**审查对象**：E:\lianghua\trend_trader.py（6134 行）+ config_adapter.py + config_hot_reload.py  
**审查角度**：配置加载链、参数覆盖顺序、热重载一致性  
**方法**：完整追踪 `from config import *` → Champion 覆盖 → 热重载 → 实际交易参数读取 全链路

---

## 配置加载链（当前代码）

### 启动阶段（按执行顺序）

| 步骤 | 位置 | 动作 | 影响的变量 |
|------|------|------|-------------|
| 1 | L120-121 | `from config import *` | globals(): SIGNAL_THRESHOLD, STOP_LOSS_ATR, ... |
| 2 | L213-237 | `apply_champion_overrides(globals())` | 如果 `current_champion.json` 存在，覆盖 globals() 中的相关参数；设置 `_champion_active=True` |
| 3 | L184-L201 | `_get_current_tier()` | 从 globals() 读参数，构建 Tier 字典 |
| 4 | L752-L758 | `_sync_tier_params()` | 将 Tier 参数写入 state（供 GUI 显示） |

### 运行时

- 主循环调用 `_get_current_tier()` → 从 globals() 读参数 → 用 globals() 里的值（可能被 Champion 覆盖）
- GUI 显示通过 `_show_config()` → `from config import SIGNAL_THRESHOLD` → **重新 import**，拿到的是 config 模块当前值（不是 globals()）

### 热重载阶段（问题所在！）

| 步骤 | 位置 | 动作 | 问题 |
|------|------|------|------|
| 1 | L5363-L5370 `_reload_config()` | 调用 `reload_config()` | `reload_config()` 返回新 config 字典，但 **`_reload_config()` 没有用它更新 globals()** |
| 2 | config_hot_reload.py L45-L62 `reload_config()` | 重新 import config 模块，更新 `_config_cache` | **没有更新 trend_trader.py 的 globals()** |
| 3 | L5349-L5360 `_show_config()` | `from config import SIGNAL_THRESHOLD...` | 重新 import，拿到新值 → GUI 显示新值 |
| 4 | 主循环 | `_get_current_tier()` 读 globals() | globals() **没变** → 实际交易用旧值 |

---

## 发现的 P1 问题

### P1：热重载后 GUI 显示值 ≠ 实际交易值

**位置**：`_reload_config()`（L5363）  
**问题**：
1. 用户修改 config.py
2. 点"热重载" → `reload_config()` 重新加载 config 模块
3. `_show_config()` 通过 `from config import ...` 拿到新值 → GUI 显示"新 config.py 值"
4. 但主循环用的 globals() **没变**（可能被 Champion 覆盖的旧值）
5. 用户以为热重载生效了，但其实**实际交易用的还是旧值**

**影响**：
- 用户修改 config.py 后点热重载，GUI 显示已更新，但实际交易参数没变
- 用户会困惑："为什么我改了参数，但交易行为没变？"

**严重性**：P1（导致用户误操作，可能用错参数交易）

---

## P1 修复方案

### 方案 A：最小修复（推荐，改动小）

在 `_reload_config()` 里，调用 `reload_config()` 后，用返回值更新 globals()：

```python
def _reload_config():
    if HAS_CONFIG_HOT_RELOAD:
        try:
            from config_hot_reload import reload_config
            from config_adapter import apply_champion_overrides
            new_cfg = reload_config()  # 返回新 config 字典
            # 同步到 globals()（只同步大写参数，避免覆盖函数/模块）
            for k, v in new_cfg.items():
                if k.isupper() and not k.startswith('_'):
                    globals()[k] = v
            # 重新 apply Champion 覆盖（确保 Champion 参数优先级最高）
            apply_champion_overrides(globals())
            cfg_rlbl.config(text="热重载完成", fg=_GREEN)
            _show_config()
        except Exception as ex:
            cfg_rlbl.config(text=("失败: " + str(ex)), fg=_RED)
```

### 方案 B：架构修复（改动大，但更清晰）

不用 `from config import *`，而是**始终从 config 模块读值**：

1. 把 `from config import *` 改成 `import config as _cfg`
2. 所有读参数的地方改成 `_cfg.SIGNAL_THRESHOLD`
3. 热重载只需 `importlib.reload(_cfg)`，所有读操作自动拿到新值

**优点**：无需手动同步，架构清晰  
**缺点**：需要改所有读参数的地方（~100+ 处），改动大

---

## 其他观察（非阻塞）

### P2：Champion 覆盖在热重载后可能丢失语义

- 如果 Champion 覆盖是"优于 config.py 的优选参数"，热重载后应该**保留** Champion 覆盖
- 方案 A 的修复里已经包含 `apply_champion_overrides(globals())`，确保 Champion 参数优先级最高

### P2：`_show_config()` 的 `from config import` 可能拿到 Champion 覆盖后的值吗？

- **不会**。因为 `from config import SIGNAL_THRESHOLD` 是重新 import config 模块，拿到的是 config.py 里的值（可能被 `reload_config()` 更新）
- 但 globals() 里的 SIGNAL_THRESHOLD 可能是 Champion 覆盖的值
- 所以 `_show_config()` 显示的是 config.py 值，而实际交易用的是 globals() 值（可能被 Champion 覆盖）→ **这就是 P1 问题的根源**

---

## 综合评分：8.0/10 ⚠️

**实盘就绪，但 P1 问题需要修复后再实盘。**

- ✅ 止盈止损方向正确
- ✅ compute_signal 评分逻辑正确
- ✅ 双币并行完整
- ✅ 12 层风控到位
- ✅ 所有外部依赖有 try/except 保护
- ⚠️ **P1：热重载后参数不一致**（GUI 显示 ≠ 实际交易）
- ⚠️ P1-2（deserialize_tiers 未定义）仍未修复（但被 try/except 保护）

---

## 修复优先级

1. **P1（热重载参数不一致）** → 按方案 A 修复（改动小，风险低）
2. P1-2（deserialize_tiers） → 确认 progressive_take_profit.py 是否有定义，如果没有，补一个空函数
3. P2（save_state 无 _state_lock） → 加锁保护

---

## 实盘建议

**修复 P1 后再实盘**。否则可能出现"改了 config.py 点热重载，但实际交易参数没变"的情况，导致意外亏损。

如果现在就要实盘，建议：
1. **不要依赖热重载** → 每次改 config.py 后，重启程序
2. 或者，改完 config.py 后，**手动重启** trend_trader.py（确保 `from config import *` 拿到新值）

---

报告版本：R54  
审查人：顾庸  
下次审查角度建议：网络重试与代理切换逻辑 / 日志系统完整性与性能影响
