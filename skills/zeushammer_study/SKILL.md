# ZeusHammer Study — qclaw 落地

## 来源

**项目**: [pengrambo3-tech/ZeusHammer](https://github.com/pengrambo3-tech/ZeusHammer)
**描述**: AI Super Agent，融合 ClaudeCode + Hermes + OpenClaw 三巨头
**版本**: v2.1.1（2026-04-25）
**许可证**: MIT

## 核心架构

```
ZeusHammer
├── src/brain/          ← 最有价值（本次落地重点）
│   ├── local_brain.py      (15.6KB) 意图→技能匹配→短路执行
│   ├── reflection.py       (11.1KB) 深度反思+冥想模式+CoT
│   ├── skill_learner.py    (10.2KB) 技能学习+质量评估+淘汰
│   └── workflow_engine.py  (10.9KB) 工作流编排
├── src/fusion/         ← 三巨头融合层
│   ├── claude_code/        工具执行+并发分区+OTel
│   ├── hermes/             记忆+安全+MCP
│   └── openclaw/           渠道+Canvas+技能市场
├── src/core/           ← 核心基础设施
│   ├── engine.py           (12.7KB)
│   ├── permission.py       (14.1KB)
│   ├── permission_manager.py (16.8KB)
│   └── config_protection.py (14.9KB)
└── src/llm/            ← LLM 路由
```

## 核心设计（源码级分析）

### 1. Local Brain — "80%不调LLM"

**工作流**：`输入 → 意图理解 → 技能匹配 → 命中?直接执行:调LLM → 学习新技能`

**意图理解** (IntentType enum + 关键词匹配)：
- 按优先级排序的12种意图类型
- 置信度 = 基础0.5 + 路径检测+0.15 + 代码检测+0.15

**技能匹配评分** (最核心的设计)：
```
score = intent_type_match(0.4) 
      + trigger_pattern_match(0.3)
      + usage_freq_bonus(0~0.1) 
      + success_rate(0~0.2)
阈值: >= 0.5
```

**自动学习**：
- 条件：成功 + 耗时>1s + 无已有类似技能
- 从工作记录自动创建 Skill 对象
- 持久化到 memory

### 2. Meditation Mode — "空闲时自动进化"

**4步冥想循环**（源码中大部分是 TODO，qclaw 已实现）：
1. `_analyze_recent_work()` → 读取 work_history.jsonl
2. `_extract_patterns()` → 从 evolver rules 提取高频模式
3. `_optimize_skills()` → 评估技能质量，淘汰低分
4. `_generate_insights()` → 基于数据生成洞察

### 3. Reflection Engine — "执行后深度反思"

**反思类型**：SUCCESS / FAILURE / OPTIMIZATION / INSIGHT

**流程**：确定类型 → 深度分析 → 提取洞察 → 生成改进 → 保存

**Chain of Thought 5步推理**：
1. 理解问题 → 2. 分解 → 3. 制定方案 → 4. 推理 → 5. 验证

### 4. Skill Quality — "4因素加权评分"

**评分公式**（0-100分）：
```
score = success_rate * 40           # 成功率(40%)
      + max(0, 30 - duration/1000*30)  # 速度(30%)
      + min(20, usage_count * 2)       # 频率(20%)
      + (6 - complexity) * 2           # 复杂度(10%)
```

**评级**：80+优秀 / 60-79良好 / 40-59一般 / 20-39较差 / <20淘汰

**淘汰条件**：
1. score < 20 → 立即淘汰
2. 超过30天未使用 → 淘汰

## qclaw 落地文件

| 文件 | 大小 | 来源模块 | 状态 |
|------|------|---------|------|
| `local_brain.py` | 19.5KB | ZeusHammer local_brain.py + workflow_engine.py | ✅ PASS |
| `meditation_mode.py` | 19.0KB | ZeusHammer reflection.py | ✅ PASS |
| `skill_quality.py` | 11.1KB | ZeusHammer skill_learner.py | ✅ PASS |

## qclaw 独有改进（vs ZeusHammer 原版）

| 改进 | ZeusHammer | qclaw |
|------|-----------|-------|
| 意图理解 | 纯关键词 | evolver 置信度 + 关键词 |
| 技能匹配 | 内存字典 | evolver + skill_metadata + 内存 |
| 冥想模式 | 全是 TODO | 真正实现（读JSONL+evolver集成） |
| 反思 | 空话分析 | 具体工具/时长分析 + evolver同步 |
| 持久化 | 无 | JSONL + JSON 文件 |
| 技能淘汰 | 仅判断 | 判断 + 自动执行 + 替换 |
| 模式提取 | 简单分词 | 中文动词识别 + 路径/扩展名 + 同义词 |

## 可移植设计点（尚未落地）

1. **ToolDetector** — 自动发现系统80+ CLI工具（ZeusHammer 独有）
2. **并发分区** — partitionToolCalls() 依赖分析（来自 ClaudeCode）
3. **OSV Scanner** — 恶意命令检测（来自 Hermes）
4. **CredentialGuard** — 凭证泄露检测（来自 Hermes）
5. **Voice System** — Whisper STT + Edge TTS + 唤醒词

## 与 qclaw 现有系统的集成点

| qclaw 模块 | ZeusHammer 对应 | 集成方式 |
|-----------|----------------|---------|
| evolver.py | Local Brain + ReflectionEngine | brain.think() 先查 evolver |
| self_review.py | ReflectionEngine | 反思结果同步到 evolver |
| heartbeat_self_review.py | MeditationMode | 心跳轮转触发冥想 |
| skill_metadata.py | Skill + PatternExtractor | 技能匹配 + 模式优化 |
| agents/agent_types.py | WorkflowEngine | 多角色调度 + 工作流 |
| agents/tool_pipeline.py | Skill.actions | 短路执行 vs LLM路由 |
