# hermes_study/display — 心情化 UI 系统

> 来源：Hermes agent/display.py 逆向
> 文件：emotion_display.py（18KB，430行）

---

## 核心模块

| 类 | 功能 |
|----|------|
| SkinAwareColors | 终端皮肤配色（亮/暗自动检测） |
| KawaiiFaces | 心情表情库（waiting/thinking/working/success/worried/resting） |
| SpinnerFrames | 9种动画帧库（sparkles/dots/bounce/grow/arrows/star/moon/pulse/brain） |
| KawaiiSpinner | 线程动画进度条，\\r 行覆写，TTY自动降级 |
| FileSnapshot | 写前快照 + unified_diff 预览 + 回滚 |
| MoodOutput | 心情化输出（带心情标签/表情/缩进） |

---

## KawaiiSpinner 用法

```python
from emotion_display import KawaiiSpinner, spin, spin_start, spin_stop

# 上下文管理器（推荐）
with spin("分析中", spinner_type="brain") as s:
    s.update("深入分析...")
# 退出时自动 stop，带心情表情

# 手动控制
sp = KawaiiSpinner("下载中", spinner_type="dots")
sp.start()
# work
sp.stop("下载完成", mood="success")
```

**9种动画类型：**
- dots — 加载点（默认）
- sparkles — 闪烁星
- bounce — 弹跳圆
- grow — 渐变条
- arrows — 旋转箭头
- star — 五角星旋转
- moon — 月相变化
- pulse — 脉冲
- brain — 大脑旋转（适合思考任务）

---

## SkinAwareColors

```python
s = SkinAwareColors(skin="dark")  # 或 auto/light/dark
s.success("操作成功")
s.supports_color()   # 检测是否支持颜色
```

配色：琥珀橙/天蓝/紫/绿/红/灰

---

## FileSnapshot（文件快照回滚）

```python
from emotion_display import FileSnapshot

snap = FileSnapshot.backup("config.json")
# 修改文件
print(snap.preview(new_content))  # 彩色 diff 预览
snap.restore()   # 回滚
snap.discard()   # 放弃快照
```

---

## MoodOutput（心情输出）

```python
from emotion_display import MoodOutput

out = MoodOutput(skin="dark", use_emoji=True)
out.thinking("正在检索记忆...")
out.success("找到3条相关记录")
out.error("文件不存在")
out.working("处理中")
out.block("分析结果", mood="success")
```

---

## 设计原则

1. TTY检测：非终端自动降级
2. 线程安全：KawaiiSpinner 用独立线程，不阻塞主线程
3. 心情化：每个状态有专属表情
4. 零依赖：纯标准库
5. 可组合：spin + MoodOutput 自由组合

---

## 可移植设计点

| 设计 | 在qclaw中应用 |
|------|------------|
| 心情表情 | 替换冰冷的[OK]/[ERROR]日志 |
| 动画进度条 | 长时间任务（搜索/生成）展示 |
| FileSnapshot | 写文件前自动快照，支持diff预览 |
| SkinAwareColors | 终端自动适配亮/暗主题 |
| TTY降级 | 非交互环境不输出控制符 |

---

## 落地状态

- emotion_display.py OK（430行，完整实现）
- SKILL.md OK（本文件）
- 待集成：可注入到 OpenClaw 的 exec hook 输出
