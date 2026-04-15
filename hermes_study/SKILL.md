# SKILL-hermes-study.md
# Hermes Agent 源码研究 → 我的系统落地

**状态**: 已完成  
**来源**: NousResearch/Hermes-Agent (v0.8.0, E:\Hermes)  
**落地目录**: `hermes_study/`

---

## 文件结构

```
hermes_study/
├── SKILL.md                    ← 本文件
├── __init__.py
├── display/
│   ├── __init__.py
│   └── emotion_display.py      ← A+B+E+F 心情符号/进度条/皮肤/快照
├── memory/
│   ├── __init__.py
│   └── memory_plugin.py        ← D 记忆层插件系统
└── exec_engine/
    ├── __init__.py
    └── thread_pool.py       ← G ThreadPool 并发执行（改名避免与标准库 concurrent 冲突）
```

---

## A+B+F: 心情符号 + 进度条 + 皮肤系统

### KawaiiSpinner
9种动画 + 思考动词轮换 + `\r` 行覆写，非 TTY 自动降级。

```python
from hermes_study.display import KawaiiSpinner, spin, MoodOutput

# 方式1：上下文管理器（一句话）
with spin('分析中', spinner_type='dots') as s:
    s.update('读取文件')
    # ...
# 自动停止，显示心情表情

# 方式2：手动控制
s = KawaiiSpinner('思考中', spinner_type='brain')
s.start()
# ... 做事情 ...
s.update('整理结果')
s.stop('完成！', mood='success')
```

### MoodOutput
心情化输出（[思考]/[完成]/[错误]）。

```python
from hermes_study.display import MoodOutput

out = MoodOutput()
out.thinking('检索经验...')
out.success('找到 3 条相关记录')

out.block('分析结果', mood='thinking')
out.thinking('发现新模式')
out.success('已记录')
out.block_end()
```

### SkinAwareColors
自动检测亮/暗主题，256色 ANSI 适配。

```python
from hermes_study.display import SkinAwareColors

skin = SkinAwareColors()  # 自动检测
skin = SkinAwareColors(skin='dark')  # 强制暗色
print(skin.success('操作成功'))
print(skin.error('出错了'))
```

### FileSnapshot
写前快照 + unified_diff 彩色预览 + 一键回滚。

```python
from hermes_study.display import FileSnapshot

snap = FileSnapshot.backup('config.json')
# ... 修改文件 ...
print(snap.preview(new_content))  # 彩色 diff 预览
snap.restore()  # 回滚
```

---

## C: skill_manage 工具升级

`workspace/evolver.py` 新增 `suggest-skill` 命令：

```bash
python evolver.py suggest-skill
```

5种触发条件（对标 Hermes skill_manage 描述）：
- 复杂任务成功（5+调用，成功≥60%）→ 建议创建 skill
- 重复模式（3+次，成熟方案）→ 建议创建 skill
- 克服错误（失败→成功）→ 建议创建 skill
- 指令过时（发现坑点）→ 建议更新 skill
- 高频低效（需改进）→ 建议更新 skill

---

## D: 记忆层插件系统

对标 Hermes memory_manager.py（内置 + Honcho + Mem0 插件架构）。

```python
from hermes_study.memory import (
    set_provider, get_provider, list_providers,
    log_decision, get_decisions, log_lesson, get_lessons,
    recall, summary, BuiltinMemoryProvider,
)

# 切换记忆提供者
set_provider('builtin')  # 内置 JSONL（默认）
set_provider('hermes', api_url='http://localhost:18765')  # 对接 Hermes

# 记录
log_decision(task='安装skill', decision='使用cn镜像', success=True)
log_lesson('不要在guyong-juhuo里操作代码', '那是顾庸x的项目')

# 检索
results = recall('skill 安装')
print(summary())

# 列出可用提供者
print(list_providers())
```

---

## G: ThreadPool 并发执行

对标 Hermes run_agent.py（`_MAX_TOOL_WORKERS=3`，ThreadPoolExecutor）。

```python
from hermes_study.exec_engine import (
    execute_concurrent, execute_sequential, execute,
    register_executor, get_stats, summarize_results,
)

# 注册自定义执行器
def my_executor(action):
    return {'success': True, 'result': 'done', 'error': ''}
register_executor('http_request', my_executor)

# 并发执行（默认3线程，30秒超时）
actions = [
    {'action_id': 1, 'description': 'Task A'},
    {'action_id': 2, 'description': 'Task B'},
    {'action_id': 3, 'description': 'Task C'},
]
results = execute_concurrent(actions, max_workers=3)

for r in results:
    if r['success']:
        print('OK: action-{}'.format(r['action_id']))
    else:
        print('FAIL: {}'.format(r['error']))

# 或 auto 模式
results = execute(actions, mode='concurrent')

# 统计
print(summarize_results(results))
print(get_stats())
```

---

## 灵感来源对照

| 我的实现 | 来源文件 | 核心机制 |
|---------|---------|---------|
| KawaiiSpinner | Hermes `agent/display.py` | Thread动画 + 行覆写 + 非TTY降级 |
| SkinAwareColors | Hermes `agent/display.py` | 皮肤引擎动态配色 |
| FileSnapshot | Hermes `agent/display.py` | LocalEditSnapshot + unified_diff |
| memory_plugin | Hermes `agent/memory_manager.py` | Plugin Architecture + 多提供者 |
| concurrent | Hermes `run_agent.py` | ThreadPoolExecutor + _MAX_TOOL_WORKERS |

---

## 重要规则

**guyong-juhuo 是顾庸x 的项目**：只给建议，不动手操作。  
**落地只走自己的 workspace**：`~/.qclaw/workspace/hermes_study/`
