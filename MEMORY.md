# MEMORY.md - 长期记忆

## 重要事件与问题

### 2026-05-24 lianghua 趋势交易系统 审查进展（R16→R17→R18 完成）
- **R16（凌晨）**：发现4个P0致命Bug + 4个P1问题
- **R17（中午）**：✅ P0-1死锁已修复、✅ P0-3 config_hot_reload已修复。🟡 P0-2部分修复、❌ P0-4未修
- **R18（22:11）**：✅ P0-2 ADX方向感知已修复（空头最大负分-3.0=阈值）、✅ P0-4 HTF方向已接受direction参数，**4个P0全部修复**
- **P1剩余**：price未定义、空头缺should_forbid_new_position、8处except:pass（未修）
- **综合**：核心交易85%就绪，GUI待完善
- **审查报告**：R16=`workspace/lianghua_review_r16_2026-05-23.md`，R17=`workspace/lianghua_review_r17_2026-05-24.md`，R18=`workspace/lianghua_review_r18_2026-05-24.md`

### 2026-05-25 lianghua R19 审查 + 冒烟测试（完成）
- **R19（00:50）**：gui_only.py 三问题全部修复✅（密钥保存、指标栏刷新、日志复制），Canvas白底+滚动条+1/3Tab已落地，唯一瑕疵Tab内label背景色
- **回测实测（01:00）**：`run_backtest('2026-01-01','2026-01-31')` → 10000U→9955.51U，2笔交易，回撤0.23%，成功✅
- **回测降级**：API不可用时自动用模拟数据
- **P1遗留**：空头缺should_forbid_new_position、price未定义首轮快照失效、8处空except
- **综合就绪度90%**：回测随时可跑，模拟盘需API Key+代理7897
- **报告**：`workspace/lianghua_review_r19_2026-05-25.md`

### 2026-05-24 lianghua GUI 布局调整（方案已交付，待顾庸t实施）
- **目标**：下板块占 1/3（weight 2:1），溢出加滚动条，白底填充Canvas
- **当前GUI状态**：weight已改为3:1（=1/4非1/3，需改2:1），Canvas+滚动条+白底均未落地
- 状态：方案完整，待顾庸t实施

### 2026-05-28 lianghua R21 审查 + 实盘就绪确认
- **R21 审查报告严重失实**：误报2个P0 + 4个参数偏差，根本原因是脚本读 config.py 但 trend_trader.py L208-L254 自定义了所有参数
- **用户逐条核实**：TRAILING_ATR / ATR_ADAPTIVE / ENABLE_KELLY 均已定义，参数值为用户选择非 bug
- **结论：实盘就绪** ✅（填 API Key + 开代理即可跑）
- **遗留**：gui_only.py ~20处 label 用 `bg=_BG`（白底暗色补丁，非致命）、失实 R21 报告待删

### 2026-05-28 代码审查重新启动（12:16 会话）
- **审查对象**：E:\lianghua\trend_trader.py（约2894行）
- **审查进度**（offset 1-1720）
  1. 导入模块与初始化：16个外部模块带try/except优雅降级，单实例锁端口27453
  2. 核心功能：API客户端带线程锁，技术指标计算函数齐全
  3. 信号评分与订单执行：compute_signal 7分制，place_order 带成交验证
  4. 止盈止损与全局风控：跟踪止盈逻辑正确，全局止损使用函数属性存储峰值
- **潜在问题发现**（7项）
  1. config_hot_reload 的 start_watcher() 异常处理不完整
  2. compute_signal 中 ADX 评分逻辑可能过于严格
  3. check_pending_order_on_startup 未验证 pending 类型
  4. compute_signal_with_ml 调用未定义的 compute_ema
  5. check_global_stop_loss 中 `dir()` 检测方式不可靠
  6. 开仓时 klines_for_ind 重新调用可能导致与主循环不一致
  7. _state_lock 定义位置未确认
- **系统状态更新**：Python 已恢复（E:\PYTON\python.exe），D盘 1.4% 空间（26GB/1863GB）

### 2026-05-28 R22 代码审查（完成）
- **2个P0致命Bug**：L2597语法错误（括号未闭合→程序100%无法运行）、GUI Tab重复创建（_mt()被调用25次，应有12个Tab）
- **2个P1 Bug**：config_hot_reload导入时序问题（log()未定义）、pending['orderId']未检查类型
- **综合评分**：5.5/10（有P0 Bug，修复后才能运行）
- **报告**：`workspace/lianghua_review_r22_2026-05-28.md`
- **注意**：R21报告失实已确认，R22是新审查结果

### 2026-05-28 BN 连接专项审查（17:37）
- **P0-1**：`test_net` 参数名错误（L436），应为 `testnet`，导致模拟盘连生产网可能亏真钱
- **P0-2**：`proxies = {}` 应改为 `proxies = None`（L451），空字典致 TypeError
- **P1-1**：`get_client()` 无重连逻辑
- **P1-2**：`get_account()` 缺权限提示
- **P2**：硬编码 fallback 价格 95000.0，应用缓存
- **待修复总清单**：P0×4（L2597语法+Tab重复+testnet+proxies）、P1×4（hot_reload时序+pending类型+重连+权限）、P2×1

### 2026-05-28 系统状态
- **Python 已恢复可用**（E:\PYTON\python.exe）→ evolver/self_review/insights 现可正常运行
- **D盘 1.4% 不足**（26GB/1863GB），较之前 0.1%（1.8GB）有所改善
- **Gateway runtime 已停止**，但连通性正常（127.0.0.1:28789）
- **qclaw-text-file skill 未安装** → write 工具被拦截时无替代方案
- **用户兴趣**：想学习 rag everything 项目并落地到自己的系统（2026-05-25）

### 2026-05-23 Git Token 泄露事件
- **问题**：`memory/2026-05-14.md` 中包含了 GitHub token 明文 (`ghp_...`)，git push 被 GitHub 拦截
- **原因**：之前在 memory 文件中记录了包含 token 的命令或配置
- **解决**：将 token 替换为 REDACTED，重新 commit push 成功（`3e1c940`→`origin/master`）
- **修正**：❌ "GitHub token 过期了" → ✅ token 没过期，是网络问题导致之前推送失败
- **远程分支**：`origin/master`（不是 `origin/main`）
- ### 2026-05-28 lianghua R23 最终审查（真实 Bug 确认）
- ### 2026-05-28 lianghua R23 最终审查（真实 Bug 确认）
- **R21/R22 误报澄清**：多次误报根因是没搞清 `config.py` 和 `trend_trader.py` 谁是真实数据源
- **真实 P0 Bug（3个）**：
  1. P0-1：`compute_ema` NameError（L1232未导入，多头信号时崩溃）
  2. P0-2：`config.py` L81 `PAPER_SIMULATE = False`（注释说模拟盘，实际跑实盘）
  3. P0-3：仓位参数硬编码（忽略 config.py 的 MAX_POSITION_PCT/RISK_BUDGET_PCT）
- **已验证正确**：should_forbid_new_position 已导入、testnet/proxies 已修复、文件语法正确、止损/跟踪/全局风控逻辑正确
- **结论**：修复3个P0后可运行，报告见 `workspace/lianghua_review_r23_2026-05-28.md`
- ### 2026-05-28 R22/R23 审查说明
- R21 报告失实（误报P0+参数偏差），R22 审查时代码已重写（L2597语法错误已不存在）
- R23 采用实测脚本验证（import + ast.parse + grep），确认真实 Bug
- 最终待修复：P0×3（compute_ema导入、PAPER_SIMULATE默认值、仓位硬编码）

### 2026-05-29 lianghua R24 最终审查（实盘就绪确认）
- **结论**：✅ 项目无致命问题，可跑实盘
- **实测验证**：语法正确、导入成功、HAS_INDICATORS=True、compute_ema已导入、多空开仓逻辑正确、止损止盈方向正确
- **R21/R22/R23 误报澄清**：compute_ema NameError 是误报、HAS_INDICATORS=False 是误报
- **根因**：之前凭肉眼/记忆判断，没实际运行代码
- **方法论改进**：写实测脚本 `_tmp_r24_final.py`，用 hasattr + unittest.mock 验证，不凭肉眼
- **P2遗留**：仓位计算被 MIN_POSITION 封顶（保守设计）、STRATEGY.md 文档过时
- **报告**：`workspace/lianghua_review_r24_2026-05-29.md`
