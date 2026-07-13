# 研究日志：Agent 流式展示增强

## 摘要
- **功能**：agent-streaming-display
- **发现范围**：Extension（扩展现有前端渲染管线）
- **关键发现**：
  1. `updateStreamingMessage` 每次调用使用 `innerHTML` 全量重建 DOM，需要重构为增量操作以支持 CSS 动画
  2. 现有 CSS 中 `--ok` 和 `--err` 变量缺失，`pulse-border` 动画使用硬编码颜色 #93c5fd，需要修复
  3. 纯 CSS 打字机效果不适用于动态 SSE 流（需要预知字符总数），应采用 JS 驱动的逐字渲染 + CSS 光标动画

## 研究日志

### 前端 SSE 渲染管线分析
- **背景**：需要了解现有 SSE 事件到 DOM 的完整渲染链路以确定动画集成点
- **来源**：`app/static/app.js`（第 597-851 行）、`app/api/routes.py`（第 308-380 行）、`app/agent/runner.py`（第 288-484 行）
- **发现**：
  - SSE 事件流：`step (thinking)` → `step (tool:*)` → `sql` → `final`
  - `updateStreamingMessage` 用 `innerHTML` 全量重建 `.content`，每次调用销毁并重建所有子元素
  - `finalizeStreamingMessage` 在正常完成时删除流式气泡，取消时保留并添加标记
  - 思考文本以 `streamingText += text` 累积，无块级身份
  - 工具步骤以 `streamingSteps` 数组管理，key 为 `step` 标识
- **影响**：需要将 `innerHTML` 全量重建改为增量 DOM 操作，否则 CSS transition 无法生效

### CSS 动画最佳实践研究
- **背景**：需要确定在不引入第三方库的前提下实现打字机效果和工具步骤动画的最佳方案
- **来源**：Web 搜索（CSS animation、typewriter effect、compositor-only properties）
- **发现**：
  - CSS `steps()` 打字机效果需要预知字符数，不适用于动态 SSE 流
  - 推荐 JS 驱动的逐字渲染 + CSS `blink-cursor` 伪元素光标
  - 所有动画应仅使用 `opacity` 和 `transform`（compositor-only，不触发 layout/paint）
  - `prefers-reduced-motion` 媒体查询是无障碍必需项
  - `will-change` 应谨慎使用，动画结束后必须移除
  - 工具步骤 running 状态推荐 `pulse-dot`（缩放+透明度脉冲点）替代 emoji ⏳
- **影响**：确定采用 JS 打字机 + CSS 动画组合方案，不使用第三方库

### 现有 CSS 变量缺口
- **背景**：流式步骤 CSS 引用了 `--ok` 和 `--err` 变量，但 `:root` 中未定义
- **来源**：`app/static/styles.css`（第 1-14 行、第 682-687 行）
- **发现**：
  - `.streaming-step.completed { color: var(--ok); }` — `--ok` 未定义，回退到 `currentColor`
  - `.streaming-step.error { color: var(--err); }` — `--err` 未定义，回退到 `currentColor`
  - `pulse-border` 动画中使用硬编码 `#93c5fd`，偏离了 CSS 变量体系
- **影响**：需要定义 `--ok: #0f766e` 和 `--err: #b42318`（复用 `--danger`），修复 `pulse-border` 中的硬编码颜色

## 架构模式评估

| 方案 | 描述 | 优势 | 风险/局限 | 备注 |
|---|---|---|---|---|
| JS 打字机 + 增量 DOM | JS 定时器逐字渲染 + DOM 元素引用管理 | 完全控制渲染节奏，支持队列和加速 | 需要重构现有 `innerHTML` 逻辑 | 选定方案 |
| CSS steps() 打字机 | 纯 CSS `@keyframes steps()` 逐字揭示 | 零 JS 开销，GPU 加速 | 需要预知字符总数，不支持动态追加 | 不适用 |
| Web Animation API | 使用 `element.animate()` JS API | 精细控制，支持动态参数 | 相比 CSS 动画增加 JS 复杂度，无显著收益 | 不必要 |
| 引入动画库（如 anime.js） | 第三方库管理动画 | 功能丰富，API 简洁 | 增加依赖，违反"不引入第三方库"要求 | 已排除 |

## 设计决策

### 决策：JS 驱动的打字机渲染 + CSS 动画组合

- **背景**：需求 1.1 要求思考文本逐字渲染，需求 4.1 要求不引入第三方动画库
- **备选方案**：
  1. CSS `steps()` 动画 — 需要预知字符数，不适用
  2. Web Animation API — 增加复杂度，无额外收益
  3. JS `requestAnimationFrame` 定时器 + CSS 光标动画 — 灵活且轻量
- **选定方案**：方案 3
- **理由**：JS 控制渲染节奏可以处理动态追加、队列、加速等场景；CSS 仅处理纯视觉效果（光标闪烁、脉冲动画）
- **权衡**：相比纯 CSS 方案增加了 JS 复杂度，但换取了动态内容处理的灵活性
- **后续**：实施时验证 rAF 定时器在后台标签页暂停后的恢复行为

### 决策：增量 DOM 操作替代全量 innerHTML

- **背景**：当前 `updateStreamingMessage` 每次用 `innerHTML` 重建全部内容，CSS transition 无法在元素间保持
- **备选方案**：
  1. 保持 `innerHTML` + `requestAnimationFrame` 延迟类名应用 — 复杂且脆弱
  2. 增量 DOM 操作（维护元素引用，仅更新变化部分）— 更精确
- **选定方案**：方案 2
- **理由**：StepRenderer 维护步骤 DOM 引用，状态变更时仅修改类名和图标；TypewriterRenderer 直接操作 `textContent`
- **权衡**：增加了 DOM 引用管理的代码量，但使 CSS 动画和过渡可正常工作

### 决策：CSS 动画指示器替代 emoji 图标

- **背景**：当前使用 emoji ⏳/✅/❌ 表示步骤状态，需求 2.1 要求动态加载指示器
- **备选方案**：
  1. 保留 emoji + CSS text-pulse 动画 — 简单但 emoji 跨平台不一致
  2. CSS 动画 pulse-dot + SVG 图标 — 一致性好，GPU 加速
- **选定方案**：方案 2（pulse-dot 替代 ⏳，保留 ✅/❌ 作为静态图标）
- **理由**：pulse-dot 是 compositor-only 动画（`opacity` + `transform: scale()`），不触发重排；emoji 渲染因操作系统和字体而异
- **权衡**：需要额外的 DOM 元素（span.step-icon），但换来一致的视觉效果

## 风险与缓解

- **风险 1**：`requestAnimationFrame` 在后台标签页暂停，恢复时一次性渲染大量字符 → 通过 `lastTickTime` 检测时间差，超过 100ms 时批量渲染 5 个字符
- **风险 2**：增量 DOM 操作中元素引用丢失（如流式气泡被意外删除）→ 每次操作前检查元素是否存在，丢失时回退到全量重建
- **风险 3**：CSS 动画在低端设备上导致帧率下降 → 仅动画 `opacity` 和 `transform`，使用 `prefers-reduced-motion` 降级
- **风险 4**：多轮对话间动画状态泄漏 → 在 `sendMessage` 和 `switchSession` 入口处显式调用清理函数

## 参考

- [MDN: CSS Animations](https://developer.mozilla.org/en-US/docs/Web/CSS/animation) — CSS 动画规范
- [MDN: prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) — 无障碍动画降级
- [web.dev: Animations Guide](https://web.dev/animations-guide/) — compositor-only 属性最佳实践
- [MDN: requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame) — rAF API 文档
