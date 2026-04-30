# 学习归档 - Codex / gstack / ECC / Nezha / Blender / Karpathy

> 从 MEMORY.md 迁出，2026-04-24 精简时归档

## Codex-rs 学习（2026-04-12，完成）

5个子任务全部完成并落地：codex_rs_study/（1.7MB，50个核心文件，2个SKILL文档）

| 子任务 | 模块 | 核心发现 |
|--------|------|---------|
| codex-execpolicy-parser | execpolicy/parser.rs | 两阶段解析+延迟验证、Starlark DSL |
| codex-coreskills-injection | core-skills/injection.rs | 100%显式注入、无歧义才匹配 |
| codex-hooks-dispatcher | hooks/dispatcher.rs | 泛型分发pipeline、正则matcher |
| codex-protocol | protocol/protocol.rs | 60+变体大枚举、cached_input_tokens |
| codex-hooks-types | hooks/types | HookResult三变体 |

**落地SKILL**：SKILL.md（8KB）+ SKILL-memory.md（4KB）

## gstack 学习（2026-04-12，完成）

**来源**：garrytan/gstack，135k stars，YC总裁Garry Tan的AI软件工厂

**落地**：gstack_study/（42.6KB，10文件）
- SKILL.md（13KB）：架构+skill路由+4大skill+voice+自改进
- browser_daemon/SKILL.md（6KB）
- skills/office_hours/SKILL.md（6.5KB）
- skills/investigate/SKILL.md（3KB）
- skills/review/SKILL.md（4.6KB）
- skills/retro/SKILL.md（1.8KB）

## ECC Study（2026-04-13，部分完成）

**来源**：everything-claude-code-main（1426 .md，260+ skills）

**落地**：ecc_study/（220KB，21文件）
- instinct_model.py ⭐⭐⭐⭐⭐ — instinct格式解析器（23KB）
- evolver.py ⭐⭐⭐⭐⭐ — IterationBudget + GraceCall
- lobster_gacha.py ⭐⭐⭐⭐⭐ — 龙虾灵魂抽卡机
- qclaw_eval.py ⭐⭐⭐ — EDD评估驱动开发
- qclaw_loops.py ⭐⭐⭐ — 6种循环模式
- memory_pipeline.py ⭐⭐⭐⭐⭐ — Selection Diff + render_workspace_tree

**关键认知**：instinct粒度=原子行为级 > evolver的Rule task级；项目隔离用git remote hash；promote机制=2+项目高置信度→全局scope

## Nezha 学习（2026-04-18，完成）

**来源**：hanshuaikang/nezha — "An Agent-First Vibecoding Desktop"

**落地**：nezha_study/SKILL.md（12.5KB）

核心：PTY虚拟终端 + Session自动发现 + Tauri(7MB) + isInputPending协作调度

## Blender-MCP 深度落地（2026-04-20，完成）

**来源**：ahujasid/blender-mcp v1.5.5

**落地**：blender_mcp_study/SKILL.md（14KB）

三层架构：server.py + addon.py + Blender bpy。最高价值=telemetry.py隐私优先遥测

## Karpathy 三项目扫描（2026-04-16）

nanoGPT / micrograd / llm.c，SKILL.md待精读完成
