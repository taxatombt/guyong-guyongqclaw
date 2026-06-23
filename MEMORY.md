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

### 2026-05-31 R31 代码审查（完成）
- **🔴 高风险发现**：L1663/L1773 止损止盈方向可能反了（需人工验证）
- **审查方法改进**：聚焦实盘风险，只给建议不给操作步骤
- **边界意识提升**：学会了"给建议"≠"给修复步骤"的区别

### 2026-05-30 R29/R30 代码审查
- **R29审查**：发现compute_ema命名不一致问题，但给了过于具体的修复步骤（越界）
- **R30审查**：改进方法，只输出发现不给"怎么改"
- **教训**：lianghua项目 = 只提建议，不操作，甚至不给具体修复步骤

### 2026-05-28 R22 代码审查（完成）
- **2个P0致命Bug**：L2597语法错误（括号未闭合→程序100%无法运行）、GUI Tab重复创建（_mt()被调用25次，应有12个Tab）
- **2个P1 Bug**：config_hot_reload导入时序问题（log()未定义）、pending['orderId']未检查类型
- **综合评分**：5.5/10（有P0 Bug，修复后才能运行）
- **结论**：✅ 项目无致命问题，可跑实盘（R24验证）
- **方法论教训**：代码审查必须用脚本实测，不能凭肉眼/记忆判断（R21→R22→R23全误报，R24写实测脚本后才确认）
- **红线**：lianghua 项目 = 只提建议，不操作任何文件
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
- **2026-06-16 Python PATH问题**：PATH中残留python路径但二进制缺失，winget从python.org下载极慢，华为/Tuna镜像404，需手动安装或找其他源
- **D盘 1.4% 不足**（26GB/1863GB），较之前 0.1%（1.8GB）有所改善
- **Gateway runtime 已停止**，但连通性正常（127.0.0.1:28789）
- qclaw-text-file skill 未安装，write 工具被拦截时无替代方案
- **用户兴趣**：想学习 rag everything 项目并落地到自己的系统（2026-05-25）

### 2026-05-23 Git Token 泄露事件
- **问题**：`memory/2026-05-14.md` 中包含了 GitHub token 明文 (`ghp_...`)，git push 被 GitHub 拦截
- **原因**：之前在 memory 文件中记录了包含 token 的命令或配置
- **解决**：将 token 替换为 REDACTED，重新 commit push 成功（`3e1c940`→`origin/master`）
- **修正**：❌ "GitHub token 过期了" → ✅ token 没过期，是网络问题导致之前推送失败
- **远程分支**：`origin/master`（不是 `origin/main`）
- **R21/R22 误报澄清**：多次误报根因是没搞清 `config.py` 和 `trend_trader.py` 谁是真实数据源
- **真实 P0 Bug（3个）**：
  1. P0-1：`compute_ema` NameError（L1232未导入，多头信号时崩溃）
  2. P0-2：`config.py` L81 `PAPER_SIMULATE = False`（注释说模拟盘，实际跑实盘）
  3. P0-3：仓位参数硬编码（忽略 config.py 的 MAX_POSITION_PCT/RISK_BUDGET_PCT）
- **已验证正确**：should_forbid_new_position 已导入、testnet/proxies 已修复、文件语法正确、止损/跟踪/全局风控逻辑正确
- **结论**：修复3个P0后可运行，报告见 `workspace/lianghua_review_r23_2026-05-28.md`
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

### 2026-05-29 lianghua UnboundLocalError Bug（已修复）
- **事件**：运行时发现 `compute_adx` 的 UnboundLocalError（21:49）
- **根因**：`trading_loop()` 内部 L1642/L1747 有 `from indicators import ..., compute_adx`，Python 编译时把 `compute_adx` 标记为局部变量，但 L1573 在 L1642 之前就调用了它 → UnboundLocalError
- **修复**：删除 L1642 和 L1747 中的 `compute_adx` 导入（已在文件顶层定义，无需再导）
- **同类问题**：`compute_ema` 在 L734 定义为 `compute_emas`，但 L15 模块级导入 `compute_ema`（单数）— 这不会造成 UnboundLocalError（模块级导入），但函数名不匹配
- **R29 审查确认**：compute_adx 已修复，代码语法正确
- **红线**：lianghua 项目 = 只提建议，不操作任何文件

### 重要系统原则
- ### 2026-05-31 lianghua R34 审查（最终确认 ✅）
- **🔴🔴🔴 之前多次误报**：R31-R33 全部误报止损止盈方向错误
- **R34 正确方法**：直接读文件（`read file offset=1790 limit=80`），肉眼确认 + 数值验证
- **✅ 最终结论**：多空止损止盈方向**完全正确**
- 多头：SL = entry - ATR（下方✅），TP = entry + ATR（上方✅）
- 空头：SL = entry + ATR（上方✅），TP = entry - ATR（下方✅）
- **实盘就绪**：配置 API_KEY + API_SECRET + 开代理（端口 7897）即可
- **建议**：先模拟盘跑 1-2 天，确认无异常再上实盘

### 2026-05-31 今日关键教训（审查方法论）
- **失败模式**（R31-R33）：
  1. 写复杂脚本 → 脚本有 bug → 输出错误 → 误报用户
  2. grep 找字符串 → 不理解语义 → 找到错误位置
  3. 不验证工具输出 → 直接相信 → 报告错误结论
- **正确做法**（R34 成功）：
  1. **Simple Stupid First**：直接读文件，逐段 eyeball
  2. **验证每个步骤**：读一段 → 确认 → 再下一段
  3. **数值验证**：用具体数字代入计算，确认方向
- **记住**：
- ❌ 不要写复杂脚本分析代码
- ✅ 直接 `read file offset=X limit=Y` 逐段看
- ✅ 用数值验证，不用逻辑推理

### 2026-06-01 lianghua 沙箱限制 + GitHub 推送积压
- **沙箱限制**：无法直接 read `E:\lianghua\trend_trader.py`（Path escapes sandbox root）
- 解决方案：用户手动复制到 workspace 或粘贴代码片段
- 用户回复「只有审核没有白名单」→ 阻塞中
- **GitHub 推送积压**：最后推送 2026-05-23（commit 3e1a940），待推送 R24-R34 + memory 更新
- **qclaw-text-file skill**：仍未安装，write 工具被拦截时无替代方案

### 2026-06-08/09 lianghua R38 审查完成（实盘就绪 ✅）
- **时间**：2026-06-08 16:37 GMT+8
- **范围**：trend_trader.py 全量 3812 行
- **审查方法**：直接读文件，逐段 eyeball，数值验证（坚持 R34 正确方法论）
- **结论**：P0/P1 均无，实盘就绪 ✅
- **唯一 P2**：`compute_signal_with_ml` 定义但主循环未调用（ML+SMC 增强功能未生效，不影响基础交易）
- **综合评分**：8.5/10
- **对比 R37 新增**：Regime 自适应阈值、MAO 毛选框架、多周期共振矩阵、波浪+缠论整合、量化增强系列

### 2026-06-17 lianghua R41 审查完成（实盘就绪 ✅）
- **时间**：2026-06-17 01:40 GMT+8 完成
- **审查对象**：trend_trader.py（E:\lianghua\，4022 行）
- **审查方法**：直接读文件，逐段 eyeball，数值验证（坚持 R34 正确方法论）
- **结论**：✅ 8.0/10，可跑实盘，无致命Bug
- **核心逻辑验证**：多空止损止盈方向正确、compute_signal 7分制、仓位计算Kelly+风险百分比、崩溃恢复逻辑、12层风控链
- **P1发现**：
  1. P1-1：`compute_signal_with_ml()` 调用 `compute_ema` 未做 HAS_INDICATORS 检查（L1818-L1820）
  2. P1-2：`check_stop_loss_and_profit()` PTP 分支误写 `return False`（L2320）
  3. P1-3：`deserialize_tiers` 未定义（PTP 功能无法工作）
- **P2发现**：参数覆盖问题 — config.py champion 参数 `STOP_LOSS_ATR=0.8/TAKE_PROFIT_ATR=3.0` 被 trend_trader.py L340 硬编码覆盖为 `1.5/2.0`，champion 参数实际不生效
- **审查报告**：`lianghua_review_r41_2026-06-15.md`（4864字节）
- **方法论验证**：坚持 R34 正确方法论，分多段读完全文件，未写复杂脚本，无误报

### 2026-06-11 lianghua R39 审查完成（全文件验收 ✅）
- **时间**：2026-06-11 22:58 GMT+8 完成
- **审查对象**：trend_trader.py（E:\lianghua\，3896 行）
- **审查进度**：从 R39 中断处（L700, ~18%）继续到文件末尾（L3896, 100%）
- **核心结论**：✅ 8.0/10，可跑实盘，无致命Bug
- **已确认正确**：
  1. 多空止损止盈方向正确（数值验证通过）
  2. compute_signal 7分制评分逻辑正确
  3. 仓位计算有保护（Kelly + 风险百分比）
  4. 崩溃恢复逻辑正确（check_pending_order_on_startup）
  5. wait_for_fill 超时后向币安确认真实状态
- **历史P1已全部修复**：config_hot_reload启动顺序、SHORT_SIGNAL_THRESHOLD未定义、compute_ema NameError
- **P2遗留（低风险）**：compute_kelly_position硬编码、pending状态写入时序、模拟盘余额硬编码20.0
- **审查报告**：`lianghua_review_r39_2026-06-10.md`（6866字节）
- **方法论验证**：坚持 R34 正确的审查方法（Simple Stupid First、数值验证、增量交付），分4段读完全文件，未写复杂脚本，未误报

### 2026-06-10 lianghua R39 审查进度（进行中）
- **时间**：2026-06-10 00:56 GMT+8 开始
- **审查对象**：trend_trader.py（E:\lianghua\，3896 行）
- **审查进度**：L1-L700（约 18%）
- **已发现变化**：
- 新增 `signal_quality_tracker.py` 导入（L395，2026-06-09）
- `get_klines()` 增加了数据源 fallback（public API → client → public REST）
- `_safe_get_price()` 增加了超时保护
- **待继续**：L701+ 核心技术指标函数、compute_signal、主循环
- **审查方法**：直接读文件，逐段 eyeball，数值验证

### 2026-06-01 今日关键教训（审查方法论 — 精华版）
- **Simple Stupid First**：放弃复杂脚本，直接 `read file offset=X limit=Y` 逐段 eyeball
- **数值验证优先**：用具体数字代入计算，不用逻辑推理
- **增量交付**：确认一段再下一段，不追求一次性「完整报告」
- **验证工具本身**：脚本写完后先测试输出，不盲目信任
- **失败模式**：写复杂脚本（→ bug → 错误输出 → 误报）> grep 语义误判 > 不验证直接报告
- **2026-06-11 方法论验证**：R39 全文件审查坚持该方法论，分4段读完全文件（L2201→L2601→L3001→L3401→末尾），每段验证后继续，最终结论准确，无致命Bug，验证了该方法论在大型代码审查中的有效性

### 2026-06-02 lianghua R36 审查（最新代码确认）
- **🔴 关键教训**：审查前必须确认文件来源是最新版，不能默认用缓存/下载目录的副本
- **用户质疑**："你审的是最新的代码吗" → 暴露了读副本的问题 → 用户批准直接读 E:\lianghua\
- **与之前副本有差异**：之前读的是 `C:\Users\yiseg\.openclaw\media\qqbot\downloads\...` 下的旧副本
- **R36 审查结论**：核心交易逻辑无致命 Bug，可跑实盘
- **P1-1**：`SHORT_SIGNAL_THRESHOLD` 未定义（L1751），空单会 NameError
- **P1-2**：`config_hot_reload` L92 `start_watcher()` 在 `log()` 定义前调用
- **P2-1**：`place_order()` pending 状态写入在 `wait_for_fill()` 之前
- **P2-2**：`compute_kelly_position()` 未使用
- **P2-3**：模拟盘余额硬编码 20.0

### 2026-06-02 系统问题与修复
- **heartbeat-state.json 编码问题**：PowerShell `ConvertTo-Json | Out-File` 默认用系统编码（Windows GBK），写 JSON 必须用 `-Encoding UTF8`
- **2026-06-12 修复进展**：heartbeat-state.json 存在乱码/编码错误，已备份原文件到 `heartbeat-state.json.bak`，强制更新 `lastUpdate` 为 `2026-06-12`，但 `lastChecks` 仍为空，待后续进一步修复（需处理文件中的乱码字段）
- **待清理文件**（超过1天）：`_tmp_r32_fixed.py`, `_tmp_r32_verify.py`, `_tmp_r33_find_real.py`
- **用户偏好**：审查时不要反复确认，直接执行；不要废话，要直接给结果

### PowerShell 编码规则（2026-06-02 确认）
- ❌ `ConvertTo-Json | Out-File $path` → 默认 GBK（中文乱码）
- ✅ `ConvertTo-Json | Out-File $path -Encoding UTF8` → 正确
- ✅ 用 Python 脚本写入 JSON（自动 UTF-8）
- **影响**：所有 JSON 写入操作（heartbeat-state.json、配置等）

### 2026-06-02 系统状态
- **Python**：可用（E:\PYTON\python.exe）
- **磁盘**：D盘 1.4%（26GB），C盘低（13.3GB）
- **GitHub 备份**：最后推送 2026-05-23（commit 3e1a940），待推送 R24-R34 + memory 更新
- **待清理**：3个 `_tmp_*.py` 文件（超过1天）

### 2026-06-03 lianghua R37 审查（沙箱拦截）
- **审查范围**：L1-L2050 已读完，L2050-L3048 被沙箱拦截（Path escapes sandbox root）
- **沙箱限制**：`read` 工具无法读取 `E:\lianghua\trend_trader.py`（超出 workspace 根目录）
- **解决方案**：需要用户手动复制文件到 workspace 或粘贴代码片段
- **已确认正确**：L1-L2050 的所有核心逻辑（止盈止损、MAO预检、Iron Laws、多空开仓）
- **P0/P1 延续**：`PAPER_SIMULATE = False`（实盘默认开启）、`SHORT_SIGNAL_THRESHOLD = -3`（空头门槛过高）
- **关键教训**：沙箱限制是硬壁垒，无法绕过；增量审查是合理的（分段确认更安全）

### 2026-06-04 lianghua 项目调试（API -2015 错误）
- **错误**：`APIError(code=-2015): Invalid API-key,IP,or permissions for action.`
- **场景**：项目能启动、能读取行情，但下单时报错 -2015
- **根因（90% 概率）**：IP 白名单问题（币安官网 → API Management → 把服务器 IP 加白名单）
- **其他可能**：API Key 权限不足（没开通交易权限）、Testnet/Real API Key 混淆、Key 未正确加载
- **排查步骤**：
  1. 检查 IP 白名单（最常见）→ 把服务器 IP 加进去，或清空 IP 白名单（安全性低）
  2. 检查 API Key 权限 → ✅ Enable Spot & Margin Trading、✅ Enable Futures（如果做合约）
  3. 检查 Testnet/Real 混淆 → Testnet Key 不能用在实盘 API
  4. 检查 API Key 是否正确加载 → GUI 里点「连接」看日志，或检查 `api_keys.json`
- **关键教训**：
- API -2015 错误不要慌：90% 是 IP 白名单问题，不是 Key 本身无效
- 先问完整错误信息：包括请求路径（/ping 还是 /api/v3/order），能快速定位问题
- 用户说"再审一次" = 立即执行：不要犹豫，直接开始

### 用户偏好与交互风格
- **审查任务**：不要反复确认，直接执行；不要废话，要直接给结果
- **代码审查**：用户说"再审一次lianghua" → 立即执行，不问废话
- **文件来源**：审查前必须确认是最新版，不能默认用缓存/副本
- **沙箱限制**：无法读取 workspace 外的文件，必须让用户复制或粘贴

## 经验与决策

- lianghua评分系统有漏洞，永远达不到开单标准
- **外部信息需要验证**（2026-06-07）：抖音数据不准确，Agent-Reach 实际 2.3万⭐ 而非宣传的 700⭐，必须 GitHub 搜索确认
- **Subagent-Driven Development**（2026-06-07）：Superpowers 的 sessions_spawn 对标，值得深入学习
- **Pluggable Backend 设计**（2026-06-07）：MemPalace 的抽象接口可参考，用于 qclaw 记忆系统抽象化
- **Doctor 诊断模式**（2026-06-07）：Agent-Reach 的 health check 可借鉴到 qclaw heartbeat

### 2026-06-07 AI Agent 学习（完成）
- **学习成果**：深度研究 3 个 GitHub 项目（Superpowers/Agent-Reach/MemPalace）
- **SYSTEM.md 更新**：项目贡献矩阵 +3（感知层/Agent-Reach、记忆层/MemPalace、执行层/Superpowers）
- **SKILL 文件创建**：SKILL-superpowers.md（Subagent-Driven Development + TDD）、SKILL-mempalace.md（Wing/Room/Hall 4层结构 + Pluggable Backend）
- **关键经验**：外部信息需要验证（抖音数据不准确）、Subagent-Driven Development 对标、Pluggable Backend 设计参考、Doctor 诊断模式借鉴

### 2026-06-05 系统状态与任务执行
- **每日零点任务完成**：heartbeat_self_review.py ✅、workspace 清理 3 个临时文件 ✅
- **系统状态**：Gateway 运行中（端口 28789）、D盘 1.4%（26GB/1863GB）、Python 可用
- **GitHub 推送积压**：最后推送 2026-05-23（commit 3e1a940），待推送 R24-R34 + memory 更新
- **待清理**：3个 `_tmp_*.py` 文件（超过1天）
- 眼审大文件要逐段读完，跳行读代码易漏关键逻辑，导致误报

### 2026-06-17 lianghua R41 审查（完整文件眼审）
- **审查对象**：trend_trader.py（4022行），完整逐段眼审
- **综合评分**：8.0/10，✅ 可跑实盘，无致命 Bug
- **核心逻辑验证**：EMA/ADX/RSI/MACD/成交量/布林带/微观结构 7分制信号、Kelly+风险百分位仓位、12层风控链、崩溃恢复全部通过
- **P1-1**：`compute_signal_with_ml()` 调用 `compute_ema` 前未做 `HAS_INDICATORS` 检查，ML 路径在 indicators.py 不存在时会 NameError
- **P1-2**：`check_stop_loss_and_profit()` PTP 分支误写 `return False, "..."`（当前不崩溃但代码不干净）
- **P1-3**：`deserialize_tiers` 未定义，PTP 功能无法工作（被 try/except 吞掉，不会崩溃）
- **P2（参数覆盖）**：config.py 的 champion 参数 `STOP_LOSS_ATR=0.8 / TAKE_PROFIT_ATR=3.0` 被 trend_trader.py L340 硬编码覆盖为 1.5/2.0，champion 参数实际不生效，需用户确认
- **方法论验证**：R34 方法论（Simple Stupid First、直接读文件、数值验证、增量交付）在大型代码审查中持续有效，不分段易漏关键逻辑

### 2026-06-18 lianghua R42 审查（订单执行可靠性）
- **审查角度**：换角度审查订单执行可靠性，从另一个视角验证系统健壮性
- **综合评分**：8.0/10，✅ 设计合理，无致命 Bug
- **P1-1**：`attach_stop_loss_profit()` 无重试逻辑（网络抖动/币安瞬断可能导致止损失效）
- **P1-2**：`place_order()` pending 状态写入在 `wait_for_fill()` 调用前，存在状态不一致窗口（可恢复但非最优）

### 2026-06-18 lianghua R43 升级建议（已交付小谷）
- **🔴 P1 修复**（3项，必须修复）：
  1. `compute_signal_with_ml()` 调用前加 `if not HAS_INDICATORS: return score, regime, atr, detail`
  2. PTP 分支 `return False, "..."` 删除
  3. `deserialize_tiers` 补导入
- **🟡 策略级问题**（需用户确认）：
  4. 参数覆盖：config.py SL=0.8/TP=3.0 vs trend_trader.py L340 SL=1.5/TP=2.0 — 哪个是真正想要的 champion？
  5. 信号阈值负数：SIGNAL_THRESHOLD=-1.0 是负值，建议改回正数
- **🟢 增强建议**（可选）：
  6. attach_stop_loss_profit 加重试
  7. pending 写入时序移到 wait_for_fill 之后
  8. 冷却机制改为可配置时间

### 2026-06-21 lianghua R43 审查（P0 致命 Bug 确认 ❌ 不可实盘）
- **时间**：2026-06-21 20:00 GMT+8
- **审查对象**：E:\lianghua\trend_trader.py（4210 行，11:36 更新）
- **🔴 P0 确认**：`POTENTIAL_EXIT_MAP` 未定义（L3493），空头开仓 100% 失败
- 变量只有使用无定义，config.py 中也没有
- NameError 被外层 try/except 捕获不崩溃，但空头信号永远无法开仓
- **新增功能**（相比 R42）：
  1. 多币种回退（ETHUSDT）— 但 `from trend_trader import compute_signal` 可能循环依赖
  2. 去噪过滤（potential=0 跳过）
  3. potential 分级止损（空头用 POTENTIAL_EXIT_MAP，但未定义！）
  4. auto_start=True
  5. Signal Quality Tracker (SQT)
- **综合评分**：4.0/10（P0 致命 Bug，必须修复后才能实盘）
- **修复方案**：在 L480 附近添加 POTENTIAL_EXIT_MAP 字典定义
- **报告**：`lianghua_review_r43_2026-06-18.md`
- **当前状态（2026-06-22）**：待小谷确认修复，P0 未修复前不可实盘

## 用户身份与偏好

- 审查任务不要反复确认直接执行，不要废话；用户说再审一次立即执行不问废话
- 学习新项目时要动手落地（创建 SKILL 文件、更新 SYSTEM.md），不要只看不练
- 布局/UI方案通过语音消息传达（直接说方案，用户转给他人）

## 用户健康状态（重要）

- **2026-06-21 健康咨询**：用户出现头皮发麻+喘粗气+犯恶心三个症状同时存在（20:00-20:10）
- **建议**：强烈建议去急诊查心电图+血压+心肌酶（约200-300元）
- **状态**：未知用户是否已就医，待后续跟进
- **注意**：如用户再次出现类似症状，立即建议就医，不要拖延
