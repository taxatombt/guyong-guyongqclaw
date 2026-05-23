# SKILL - 量化AI项目设计模式

> 顾庸整理 | 2026-05-13 | Qlib + 金策智算 + QuantDinger

---

## 概述

本文档汇总三个AI量化项目的核心设计模式，对qclaw六层架构的贡献。

---

## 1. Qlib（微软亚洲研究院）

**GitHub:** https://github.com/microsoft/qlib
**定位:** AI驱动的量化投资开源平台，17.5k+ stars

### 三层架构

```
基础设施层: DataServer + Trainer + Model Manager
工作流层: Information Extractor → Forecast Model → Decision Generator → Meta Controller
接口层: Analyser
```

### 核心设计模式

#### 1.1 Meta Controller（自适应策略调整）
- **来源:** 工作流层核心模块
- **功能:** 根据回测结果自动调整模型/策略参数
- **价值:** 实现"学习-调整-再学习"的闭环
- **qclaw借鉴:** ⑥进化层 → evolver.py 参数自适应

#### 1.2 Information Extractor（信息提取器）
- **来源:** 工作流层入口
- **功能:** 将多源异构数据转换为有效特征
- **价值:** 解耦数据源与模型
- **qclaw借鉴:** ③记忆层 → 知识提取机制

#### 1.3 完整ML管道
- **来源:** 整体架构
- **功能:** Data → 特征 → 训练 → 回测 → 部署
- **价值:** 端到端自动化
- **qclaw借鉴:** ④执行层 → tool_pipeline 扩展

---

## 2. 金策智算（ScottZt）

**GitHub:** https://github.com/ScottZt/jin-ce-zhi-suan
**定位:** 基于唐朝三省六部的量化系统，分权协同、风控闭环

### 核心功能

#### 2.1 实时一致性追踪与诊断系统

**快照收集器 (LiveSnapshotCollector)**
- 在实盘运行时自动记录关键事件
- 记录内容: 信号生成、风控审核、成交执行
- qclaw借鉴: ①感知层 → 环境状态追踪

**一致性比较器 (DiffComparator)**
- 对比回测与实盘快照
- 识别: 信号差异、风控否决、成交偏差
- qclaw借鉴: ⑤安全层 → 预期vs实际对比

**诊断报告**
- 根因分析
- 影响评估
- 修复建议
- qclaw借鉴: 复盘机制扩展

**回放构建器 (ReplayBuilder)**
- 从历史快照重建回测场景
- 用于复现和调试
- qclaw借鉴: 复盘机制

#### 2.2 策略进化反馈机制

**分析代理 (AnalysisAgent)**
- 自动分析策略回测结果
- 提取: 性能指标、风险特征、不一致原因
- qclaw借鉴: ②认知层 → 自动推理分析

**基因策略适配器**
- 根据诊断结果调整基因参数
- 调整内容: 信号阈值、风控参数
- qclaw借鉴: ⑥进化层 → 参数自动调优

**策略谱系**
- 记录策略演化历史
- 追踪: 策略血缘、版本变迁
- qclaw借鉴: 记忆层 → 经验谱系追踪

#### 2.3 三省六部制设计理念
- 分权协同
- 风控闭环
- qclaw借鉴: MultiAgentDispatcher 分权设计

---

## 3. QuantDinger

**GitHub:** https://github.com/brokermr810/QuantDinger
**定位:** Local-first开源AI量化交易工作台，TradingView+QuantConnect替代

### 核心理念
> "会说会分析，但落不到执行" vs "能跑策略，但缺少AI与产品化能力" → QuantDinger解决两极分裂

### 核心功能

#### 3.1 多源数据引擎（工厂模式）
- **加密货币:** CCXT（10+交易所，100+数据源）
- **美股:** Yahoo Finance / Finnhub / Tiingo
- **A股/港股:** AkShare
- **外汇/期货:** 统一OHLCV格式
- qclaw借鉴: ①感知层 → 数据源抽象

#### 3.2 LLM多代理研究团队
- **AI研究分析师:** 基于OpenRouter/LLM
- **多代理协作:** 基本面分析、情绪分析、技术分析
- **不只是代码补全:** 是真正的投研助手
- qclaw借鉴: ②认知层 → MultiAgentDispatcher

#### 3.3 端到端工作流
```
数据获取 → AI研究 → 策略开发 → 回测验证 → 实盘交易
```
- qclaw借鉴: ④执行层 → 完整pipeline

#### 3.4 本地优先架构
- **SQLite本地存储:** 隐私优先
- **Docker一键部署:** 可复现环境
- **API密钥本地保管:** 安全
- qclaw借鉴: 记忆层持久化 + 部署架构

---

## qclaw六层架构贡献矩阵

| 模式 | ①感知 | ②认知 | ③记忆 | ④执行 | ⑤安全 | ⑥进化 |
|------|--------|--------|--------|--------|--------|--------|
| Qlib Meta Controller | | ✅✅ | | | | ✅✅ |
| Qlib Information Extractor | | | ✅✅ | | | |
| Qlib ML Pipeline | | | | ✅✅✅ | | |
| 金策智算 快照收集器 | ✅✅ | | | | | |
| 金策智算 分析代理 | | ✅✅ | | | | |
| 金策智算 一致性比较器 | | | | | ✅✅ | |
| 金策智算 诊断报告 | | | | | ✅✅ | |
| 金策智算 基因策略适配器 | | | | | | ✅✅✅ |
| 金策智算 策略谱系 | | | | | | ✅✅ |
| 金策智算 三省六部 | | | | ✅✅ | | |
| QuantDinger 数据工厂 | ✅✅ | | | | | |
| QuantDinger LLM多代理 | | ✅✅✅ | | | | |
| QuantDinger SQLite | | | ✅ | | | |
| QuantDinger 端到端 | | | | ✅✅✅ | | |
| QuantDinger Docker | | | | | | ✅✅ |

---

## 最高价值设计模式（qclaw最需借鉴）

### 🥇 第一优先级：基因策略适配器（金策智算）
- 自动调整策略参数（信号阈值、风控参数）
- 实现真正的"策略进化"
- qclaw落地: evolver.py 参数自适应机制

### 🥈 第二优先级：LLM多代理研究团队（QuantDinger）
- 多角色协作推理
- 基本面/情绪/技术三维度分析
- qclaw落地: agent_types.py 多角色扩展

### 🥉 第三优先级：一致性追踪（金策智算）
- 回测vs实盘对比
- 诊断报告生成
- qclaw落地: self_review.run_review() 增强

---

## 使用场景

- **学新项目:** 对照矩阵快速定位贡献层
- **设计新功能:** 参考已有模式避免重复造轮子
- **evolver规则:** 记录最佳实践到经验库

---

_本文档随学新项目持续更新_
