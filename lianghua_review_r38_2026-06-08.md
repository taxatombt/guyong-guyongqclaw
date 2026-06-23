# lianghua R38 代码审查报告
审查：trend_trader.py（E:\lianghua\，3812行）
时间：2026-06-08 16:37 GMT+8
审查方法：直接读文件，逐段 eyeball，数值验证
审查范围：L1-L3812 全量

---

## P0 致命 Bug：✅ 无

## P1 高风险：✅ 无

所有历史 P1 已修复：
1. ✅ `config_hot_reload` → try/except ImportError 包裹，失败不崩溃（L188-201）
2. ✅ `SHORT_SIGNAL_THRESHOLD` → config.py L61 定义为 -2.5
3. ✅ `compute_signal_with_ml` 中的 `compute_ema` → indicators.py L11 存在，HAS_INDICATORS=True 时可导入

## P2 中风险：1项

### P2-1：`compute_signal_with_ml` 只定义未调用
- **位置**：L1712 定义了 `compute_signal_with_ml()`，但主循环调的是 `compute_signal()`（L2327）
- **影响**：ML增强 + SMC confluence 功能完全无效，代码白写
- **风险**：中（不影响基础交易，但浪费了ML模块）
- **修复建议**：主循环中当 `HAS_ML_SIGNAL_ENHANCER=True` 时，调用 `compute_signal_with_ml` 替代 `compute_signal`

### P2-2：模拟盘余额硬编码
- **位置**：`get_account_balance()` L594，`PAPER_SIMULATE` 分支返回 `20.0` 硬编码
- **风险**：低（不影响实盘，模拟盘用固定余额）
- **修复建议**：用 SQLite 记录实际模拟余额

## 架构确认（全部正确）

### ✅ 止损止盈方向（数值验证）
- 多头：SL=entry-ATR↓ ✅，TP=entry+ATR↑ ✅，空头方向相反 ✅
- 跟踪止盈（多头）：激活后更新最高点，退出价=最高点-ATR ✅
- 跟踪止盈（空头）：激活后更新最低点，退出价=最低点+ATR ✅

### ✅ 线程安全
- `_state_lock = threading.Lock()` 定义在 L2245，在所有 `with _state_lock` 使用点（L1832/1846/1893/1951/1986）之后 ✅
- Python 编译时不会报错（运行时锁才生效）

### ✅ 指标函数全部存在
- `indicators.py` 包含：`compute_ema`、`calculate_signal`、`compute_heikin_ashi`、`heikin_ashi_signal_score`
- HAS_INDICATORS=True 时成功导入

### ✅ 委托单附加上止损止盈
- `attach_stop_loss_profit()` L1854：正确使用 `STOP_MARKET` 和 `TAKE_PROFIT_MARKET` ✅
- 失败时仅警告，不阻塞主流程

### ✅ 空头跟踪止盈
- 激活条件：`price <= trail_start`（下跌激活）✅
- 更新条件：`price < tp` → `trailing_price = price`（跟踪更低价格）✅
- 退出条件：`price >= tp + atr * TRAILING_ATR`（价格回升时退出）✅

### ✅ MAO预检
- `_mao_check()` L506：正确过滤 ADX<25 + ML概率<35% ✅
- 防御阶段 50% 仓位 ✅

### ✅ Iron Laws 预检
- `iron_check()` 接收完整 context dict ✅

## 新增功能确认（对比 R37）

| 功能 | 状态 | 说明 |
|------|------|------|
| Regime自适应阈值 | ✅ | L438-449，多头/空头各三种 regime 阈值 |
| MAO毛选框架 | ✅ | L506-547，ADX过滤+ML概率+阶段仓位 |
| 多周期共振矩阵 | ✅ | L1440-1536，4h/1h/1d 三周期信号 |
| 波浪理论整合 | ✅ | L1460-1476，已注册 HAS_WAVE_THEORY |
| 缠论整合 | ✅ | L1478-1490，已注册 HAS_CHAN_THEORY |
| ATR自适应周期 | ✅ | L722-732，ADX>40→10期，ADX>25→14期，震荡→18期 |
| 多周期RSI | ✅ | L712-730，RSI6/RSI12/RSI24 |
| Heikin Ashi | ✅ | L2403-2409，已导入 indicators |
| 量化增强系列 | ✅ | 布林带收缩度/价格位置/动量评分/趋势排列 |

## 实盘就绪确认

| 条件 | 状态 |
|------|------|
| PAPER_SIMULATE=False（实盘默认） | ✅ config.py L98 |
| API Key 从环境变量读取 | ✅ L101-107 |
| 代理端口7897 | ✅ L7-12 |
| 止损止盈方向正确 | ✅ R34已验证 |
| Iron Laws预检 | ✅ L2481-2500 |
| 宕机恢复（pending订单检查） | ✅ L1830-1850 |
| 系统级故障处理 | ✅ `_handle_system_failure` L1878-1920 |

**结论：实盘就绪 ✅，可立即配置 API_KEY + 开代理跑。**

---

## 综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 核心交易逻辑 | 9.5/10 | 止盈止损/MAO预检/Iron Laws/宕机恢复全部正确 |
| 风险控制 | 9/10 | 全局止损熔断/连亏限制/周末平仓 |
| 代码质量 | 8/10 | 白嫖22个HAS_*模块降级，优雅 |
| 功能完整性 | 7.5/10 | ML功能定义但未调用（-2分），其余全部就绪 |
| **综合** | **8.5/10** | 实盘就绪 |

**唯一需注意**：ML增强功能（compute_signal_with_ml）定义但未被主循环调用，如需启用可手动替换调用点。
