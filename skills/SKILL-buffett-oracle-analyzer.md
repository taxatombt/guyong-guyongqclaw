# SKILL-buffett-oracle-analyzer.md

> 来源：BruceLanLan/buffett-oracle-analyzer | 学习日期：2026-05-14

## 项目概要

AI驱动上市公司深度分析 OpenClaw Skill，融合巴菲特投资智慧 + 12模块分析框架，覆盖美股/港股/A股。

GitHub: https://github.com/BruceLanLan/buffett-oracle-analyzer

## 核心设计模式

### 1. 评估驱动开发（EDD）

`evals.json` 定义断言式评估用例，Skill上线前先写评估标准。

**qclaw借鉴**：新 Skill 上线前应写 evals.json，自动验证输出质量。当前 evolver + self_review 是事后复盘，EDD 是事前门控，互补。

### 2. 12模块结构化分析框架

| # | 模块 | 内容 |
|---|------|------|
| 1 | 巴菲特裁决摘要 | 一句话判定：买/不买/观望 |
| 2 | 护城河5维度 | 品牌/转换成本/网络效应/成本优势/规模 |
| 3 | 所有者盈余 | 净利润+折旧-资本支出 |
| 4 | 8种估值模型 | DCF/PE/PB/PS/PEG/EV-EBITDA/FCF Yield/DDM |
| 5 | 巴菲特计分卡 | 36分制综合评分 |
| 6 | 买入区间 | 安全边际价格区间 |
| 7 | 卖出区间 | 高估/合理估值上沿 |
| 8 | 仓位建议 | 凯利公式/风险预算 |
| 9 | 管理层评估 | 资本配置+诚信度 |
| 10 | 财务健康 | ROE/ROIC/负债率/FCF |
| 11 | 行业分析 | 护城河宽度+集中度 |
| 12 | 风险提示 | 核心风险清单 |

**qclaw借鉴**：结构化分析模板可改造为 qclaw "项目分析 Skill"，强制输出结构而非自由文本。

### 3. 知识文件分离

- `buffett-principles.md`（投资原则，不变）
- `valuation-methods.md`（估值方法，可更新）
- `SKILL.md`（工作流定义）

**qclaw借鉴**：现有 SKILL.md 塞满内容时，应拆为 原则+方法+流程 三文件。

## 文件结构

```
buffett-oracle-analyzer/
├── SKILL.md               ← 主Skill定义（v1.1简化版）
├── buffett-principles.md  ← 巴菲特投资原则（4大基石）
├── valuation-methods.md   ← 8种估值模型
├── example-prompts.md     ← 使用示例
├── evals.json             ← 评估用例（质量门控）
├── scripts/               ← Yahoo Finance API 数据抓取
└── cases/analysis-reports/← MSTR/GOOGL 深度分析报告
```

## 六层贡献

| 层 | 贡献 | 价值 |
|---|------|------|
| ②认知 | 12模块分析框架 + 巴菲特计分卡 | 🔥🔥🔥 结构化分析模板 |
| ③记忆 | cases/ 案例记忆库 | 分析报告存档模式 |
| ④执行 | OpenClaw Skill 标准工作流 | Skill格式规范 |
| ⑤安全 | evals.json 评估驱动门控 | EDD 质量保障 🔥🔥 |
