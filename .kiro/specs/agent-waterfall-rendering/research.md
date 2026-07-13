# Research & Design Decisions

## Summary
- **Feature**: agent-waterfall-rendering
- **Discovery Scope**: Extension（现有前端渲染层的修改）
- **Key Findings**:
  - 当前 TypewriterRenderer 的核心瓶颈在 `tick()` 的逐字符推进（20-30ms/字符），即使有极速模式（0.2ms）仍需数百毫秒完成
  - 现有 SSE 事件流已天然支持增量内容推送，无需后端改动
  - 瀑布式渲染只需将渲染单位从"字符"改为"内容块"，rAF 循环从"推进 cursor"改为"消费 buffer"
  - finalizeReply 的两阶段流程（纯文本打字机→Markdown 替换）是冗余的，瀑布式可一步到位

## Research Log

### 现有 TypewriterRenderer 性能分析
- **Context**: 分析当前打字机渲染的性能瓶颈
- **Sources Consulted**: `app/static/app.js` lines 597-774
- **Findings**:
  - 正常模式 20-30ms/字符，100 字符回答需要 2-3 秒
  - 极速模式 0.2ms/字符（2 秒后触发），但前提是回答足够长
  - 短回答（<2 秒完成）全程以慢速渲染，用户体验最差
  - rAF 在后台标签页被浏览器节流，导致恢复后积压
  - `finalizeReply` 有两阶段渲染：纯文本打字机（charDelay=2ms）→ Markdown 替换，浪费一次完整遍历
- **Implications**: 瀑布式从根源解决——取消逐字符单位，改为内容块单位，rAF 循环仅用于分帧而非推进 cursor

### 瀑布式渲染模式调研
- **Context**: 评估批量内容渲染的最佳实践
- **Sources Consulted**: Web 搜索 "waterfall text rendering pattern", "batch DOM updates requestAnimationFrame"
- **Findings**:
  - 标准模式：SSE chunk 到达 → buffer 累积 → rAF 批量消费 → DOM textContent 更新
  - 分帧策略：单帧超过 500 字符时拆分，保证 60fps
  - 速度控制：通过调整 rAF 消费间隔实现（0ms/30ms/80ms）
  - 无需引入虚拟 DOM 或第三方库，原生 JS 即可实现
- **Implications**: 设计保持零依赖，直接替换 TypewriterRenderer

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 瀑布式 + rAF 批量渲染 | buffer 累积 + rAF 定时消费 | 简单、零依赖、可控速度 | 长文本需分帧处理 | **选定方案** |
| 直接 innerHTML 替换 | 每次 SSE 事件直接替换整个内容区 | 最简单 | 闪烁、性能差、长内容卡顿 | 不采用 |
| 虚拟 DOM 增量更新 | 引入轻量虚拟 DOM diff | 精确更新 | 引入依赖、过度设计 | 不采用 |

## Design Decisions

### Decision: WaterfallRenderer 替代 TypewriterRenderer
- **Context**: 需求要求用瀑布式批量渲染替代逐字符打字机
- **Alternatives Considered**:
  1. 保留 TypewriterRenderer，仅调大 charDelay → 仍是逐字符，治标不治本
  2. 完全移除 rAF 循环，SSE 事件直接写 DOM → 大量小 DOM 操作，性能差
- **Selected Approach**: 新建 WaterfallRenderer，维护 buffer + rAF 消费循环，以内容块为单位批量写入
- **Rationale**: 保留 rAF 的分帧能力（防止大块内容阻塞主线程），同时消除逐字符推进的延迟
- **Trade-offs**: 相比直接 innerHTML 替换多一层 buffer 抽象，但换来可控的渲染节奏和更好的性能

### Decision: 三档速度配置（fast/normal/slow）
- **Context**: 需求要求可调节渲染速度
- **Alternatives Considered**:
  1. 连续滑块 → 用户难以感知差异，增加实现复杂度
  2. 仅快/慢两档 → 粒度不够
- **Selected Approach**: 三档（0ms/30ms/80ms），下拉菜单选择，localStorage 持久化
- **Rationale**: 三档覆盖了"即时/舒适/慢读"三种典型偏好，30ms 间隔对应 ~33fps 渲染，人眼感知流畅
- **Trade-offs**: 30ms 和 80ms 的差异在短回答中可能不明显

### Decision: finalizeReply 去除打字机预览
- **Context**: 当前 finalizeReply 先打字机渲染纯文本，完成后再替换为 Markdown
- **Alternatives Considered**:
  1. 保留两阶段，但用瀑布式渲染纯文本 → 用户仍看到纯文本闪变
  2. 直接渲染 Markdown → 一次性显示格式化的完整回答
- **Selected Approach**: 直接 `body.innerHTML = renderMarkdown(replyText)`，去除中间纯文本阶段
- **Rationale**: 瀑布式渲染的 thinking 阶段已经提供了"正在生成"的视觉反馈，final 时回答已完整到达，无需再逐段显示
- **Trade-offs**: 长回答可能一瞬间出现大量格式化内容，但 500 字符分帧策略可缓解

## Risks & Mitigations
- Markdown 渲染（`renderMarkdown`）在长文本时可能耗时 → 分帧策略：先显示纯文本 fallback，再异步替换为 Markdown
- localStorage 在隐私模式下不可用 → try/catch 包裹，静默降级为默认速度
- 速度切换时正在渲染的内容可能闪烁 → 速度变更仅影响后续 rAF 周期，不中断当前渲染
- 移除 TypewriterRenderer 后旧代码残留 → 确认所有 `typewriter.` 调用点已替换

## References
- 当前代码：`app/static/app.js` (TypewriterRenderer, StepRenderer, streaming message)
- 当前代码：`app/static/styles.css` (streaming animations)
- 当前代码：`app/static/index.html` (DOM structure)
- [requestAnimationFrame MDN](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame) — rAF API 参考
