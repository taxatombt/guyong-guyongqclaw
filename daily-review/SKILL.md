---
name: daily-review
description: 每日0点自动执行：回顾当日学习内容，删除无用临时文件，清理上下文，存储精华内容到知识库。Keywords: 每日回顾, 日结, 清理, 归档, daily cleanup
---

# Daily Review Skill

每日0点自动执行：
1. 回顾当日学习内容
2. 删除无用临时文件
3. 清理上下文
4. 存储精华到知识库

## 执行流程

```
1. 检查当日工作 → 提取精华
2. 删除临时文件 → _*.txt, _*.py, fetch*, test*, check*, stats*
3. 归档有用内容 → KNOWLEDGE.md / MEMORY.md
4. 创建/更新 memory/YYYY-MM-DD.md
5. 汇报结果
```

## 文件清理规则

### 删除（临时文件）
- `_*.txt` — 临时文本
- `_*.py` — 临时脚本
- `*fetch*.py` — 抓取脚本
- `*test*.py` — 测试脚本
- `*check*.py` — 检查脚本
- `*stats*.py` — 统计脚本

### 保留（重要文件）
- `SKILL.md` — Skill 定义
- `work.md` — 工作系统
- `persona.md` — 人格定义
- `meta.json` — 元数据
- `KNOWLEDGE.md` — 知识库
- `MEMORY.md` — 长期记忆
- `SOUL.md` — 身份认知
- `USER.md` — 用户信息
- `AGENTS.md` — 工作区规则
- `HEARTBEAT.md` — 心跳任务
- `evolver.py` — 进化程序
- `self_review.py` — 复盘程序
- `heartbeat_self_review.py` — 心跳自检

## 精华提取规则

### 存入 KNOWLEDGE.md
- 技术架构研究
- 项目分析总结
- 工具使用方法
- 最佳实践记录

### 存入 MEMORY.md
- 重要决策
- 用户偏好更新
- 规则变更
- 个人事件

### 存入 memory/YYYY-MM-DD.md
- 当日工作日志
- 完成事项
- 待办更新
- 临时想法

## 定时配置

```cron
0 0 * * *  # 每天0点执行
```

## 汇报格式

```
📅 每日回顾完成

✅ 学习内容：
   - xxx
   - xxx

🗑️ 清理文件：
   - 删除 x 个临时文件

💾 归档内容：
   - KNOWLEDGE.md 更新
   - MEMORY.md 更新
   - memory/2026-04-09.md 创建

📊 统计：
   - 工作文件：x 个
   - 临时文件：x 个（已清理）
```
