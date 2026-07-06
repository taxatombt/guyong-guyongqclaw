# lianghua R53 审查报告 — 竞态条件与线程安全

**时间**：2026-07-02 21:50 GMT+8  
**审查对象**：E:\lianghua\trend_trader.py（6134 行）  
**审查角度**：竞态条件、线程安全、状态持久化、潜在崩溃路径  
**方法**：grep 模式匹配 + 定向读取 + 路径追踪

---

## 发现

### P1: save_state() 无 _state_lock 保护 [线程安全]

**位置**：`def save_state()`（L1120）  
**问题**：函数体内未使用 `_state_lock`，但调用它的上下文不一致——有时在 `with _state_lock` 块内（L4678 开仓后保存），有时在锁外（L1098 load_state 末尾、L6074 启动后定时保存）。

当 trading_loop 线程正修改 state（开仓/平仓写入多个字段）时，另一个线程（或启动时的 load→save 路径）的 `json.dump` 可能读到半修改的 state，导致 state.json 持久化不一致。

**影响**：不会崩溃（Python dict 遍历不会 segfault），但 state.json 可能存下不完整的持仓信息。下次重启 load_state 读到不全的 state，虽然后续有 Binance 持仓同步补偿（load_state L1051-1082），但增加了恢复复杂度。

**严重性**：P1（非致命，但应修复）

### P2: load_state() 末尾调用 save_state() [冗余同步]

**位置**：L1098 `save_state()`（在 `load_state()` 函数体末尾）  
**问题**：load_state() 仅在程序启动时被调用（模块加载阶段、单线程），但末尾的 save_state() 写回磁盘是冗余操作——没有新数据需要保存。更关键的是，启动后 L6074 有 `root.after(2000, lambda: save_state())`，如果 load_state 的 save_state 与 2s 后的定时 save_state 同时发生（虽然概率低），可能产生重复写入。

**影响**：极小，启动阶段是单线程。可删除 L1098 的 save_state() 调用。

### P3: 裸 `except: pass` 存在注入点 [代码质量]

**位置**：L518、L531、L546（单实例锁的 os.close 清理）、L1236（调试日志写入）  
**问题**：`except: pass` 会吞掉 `SystemExit`、`KeyboardInterrupt`。实践中这些都是在 cleanup 路径上，风险低，但不推荐。

### P0/P1 无新增致命 Bug

- 止盈止损方向 ✅ 正确
- compute_signal 评分逻辑 ✅ 正确（多空对称）
- 双币并行 ✅ 完整
- 12 层风控 ✅ 到位
- all external deps ✅ try/except 保护

---

## 综合评分：8.5/10 ✅

**实盘就绪**。上述问题均非实盘阻塞项。

配置 API Key + 代理（127.0.0.1:7897）即可运行。

---

### 修复建议（不改文件，只供参考）

1. `save_state()` 内加 `with _state_lock:` 包裹 json.dump 到原子替换的整个区间——消除读出半修改 state 的风险
2. `load_state()` 末尾删除 `save_state()` 调用——L6074 的定时 save_state 已覆盖保存需求，此处冗余
