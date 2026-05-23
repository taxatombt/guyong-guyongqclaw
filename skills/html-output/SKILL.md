# SKILL: HTML 输出模式

## 触发条件

**description:** 当用户要求生成 HTML artifact、HTML 页面、网页、或明确说"输出 HTML"时使用本 skill。

## 核心原则

1. **默认 Markdown** — 用户没说 HTML 时不要自作主张
2. **HTML 胜于 Markdown 的场景** — 空间信息（diff 图、模块图）、交互（原型、编辑器）、数据可视化（图表、时间线）
3. **浏览器直接打开** — 输出纯 HTML 文件，零依赖

## 输出质量标准

### 基础要求
- 完整 `<!DOCTYPE html>` + `<head>` + `<style>`
- 响应式设计，PC/移动都好看
- 深色/浅色双主题（`@media (prefers-color-scheme: dark)`）
- 中文支持（`charset=utf-8`）

### 高价值 HTML 模式

| 场景 | HTML 模式 |
|------|-----------|
| 代码 Diff / PR Review | 侧边栏注释 + 颜色标注 severity + 行号 |
| 模块/架构图 | 内联 SVG（boxes & arrows） |
| 研究报告/文档 | 可折叠 `<details>` + Tab 切换 + 侧边导航 |
| 数据展示 | CSS Grid 表格 + 颜色热力图 + 简单 Chart.js |
| 时间线/进度 | 彩色水平时间条 |
| 幻灯片 | `<section>` + 左右箭头键切换 |
| 定制编辑器 | 带 textarea + "导出" 按钮，输出可复制文本 |
| 交互原型 | 真实 easing 曲线（`cubic-bezier`）+ 点击响应 |

### SVG 图规范
- 用内联 SVG，不用外部图片
- 颜色和整体主题一致
- 注释文字可直接修改

### 可交付性
- **最后必须有导出按钮或复制按钮** — 让小谷能把内容转回 Markdown 或复制使用
- 代码块用 `<pre><code>` 语法高亮
- 关键数值用大字体突出

## 示例 Prompt（直接用）

```
帮我创建 HTML artifact 来描述这个 PR：
- 重点关注 streaming/backpressure 逻辑
- 用内联 SVG 画模块调用关系
- diff 用颜色标注严重程度（红色=高危，黄色=警告，绿色=建议）
- 右侧栏添加逐行注释
- 底部加"导出 Markdown"按钮
```

```
用 HTML 做一个这个算法的交互式解释页面：
- 可折叠的逐步执行演示
- 侧边栏变量状态实时显示
- SVG 流程图，可手动高亮当前节点
- "复制代码"按钮
```

## 技术要点

- CSS 写在 `<style>` 里，不要用外部 CDN
- JS 写在 `<script>` 里，最小化
- 动画用 `cubic-bezier` 或 CSS `@keyframes`，不用外部库
- 响应式：`@media (max-width: 768px)` 处理移动端

## Red Flags（违反这些就不是好 HTML）

- 纯文字 dump，没用任何 HTML 结构（`<table>`, `<details>`, SVG）
- 表格没用 `<th>` 或 `<thead>`
- 代码块没有语法高亮
- 没有导出/复制功能（大段文字无法复用）
- 用了外部图片/字体（必须自包含）
