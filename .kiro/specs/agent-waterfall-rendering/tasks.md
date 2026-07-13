# Implementation Plan

## 1. Foundation: 核心模块实现

- [ ] 1.1 实现 WaterfallRenderer 瀑布式渲染引擎
  - 创建 `createWaterfallRenderer()` 工厂函数，返回 `{ appendChunk, flush, stop, reset, setTarget, setOnRender, setOnComplete }` 接口
  - `appendChunk(text)` 将文本增量追加到内部 buffer，首次调用时启动 rAF 消费循环
  - rAF 消费循环按 `getRenderDelay()` 间隔从 buffer 取内容，批量写入目标 DOM 元素的 `textContent`
  - `flush()` 立即渲染所有剩余 buffer，停止循环，移除视觉指示器 CSS 类
  - `stop()` 停止 rAF 循环但保留 buffer（取消场景用），移除视觉指示器
  - `reset()` 停止循环并清空 buffer 和所有内部状态
  - `setTarget(el)` 设置渲染目标 DOM 元素，`setOnRender(cb)` 设置每次渲染后回调（自动滚动），`setOnComplete(cb)` 设置全部完成回调
  - 完成后：可独立于现有代码创建 WaterfallRenderer 实例并调用 appendChunk/flush/reset，验证 buffer 消费和 DOM 更新行为
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 3.1, 5.2, 5.3_

- [ ] 1.2 实现 SpeedConfig 渲染速度配置模块
  - 创建 `createSpeedConfig()` 工厂函数，返回 `{ getSpeed, setSpeed, getDelay, load }` 接口
  - 定义三种速度档位：`fast`（延迟 0ms）、`normal`（延迟 30ms）、`slow`（延迟 80ms）
  - `getDelay()` 根据当前 speed 值返回对应的渲染延迟毫秒数
  - `setSpeed(speed)` 校验 speed 值（非法值回退 `normal`），写入 `localStorage` key `vkdbagent.renderSpeed`
  - `load()` 从 `localStorage` 恢复设置，`localStorage` 不可用时静默降级为 `normal`
  - 完成后：可独立调用 speedConfig.setSpeed('fast') 并验证 getDelay() 返回 0，刷新页面后 load() 恢复上次设置
  - _Requirements: 2.1, 2.3, 2.4, 2.5_

## 2. Core: 集成替换与 UI

- [ ] 2.1 将 WaterfallRenderer 集成到流式消息管道
  - 在 `app.js` 中将全局单例 `typewriter` 替换为 `waterfall`（`createWaterfallRenderer()`）
  - 修改 `createStreamingBubble()`：将 `typewriter.setTarget(thinkingEl)` 替换为 `waterfall.setTarget(thinkingEl)`，同步替换 `setOnRender` 和 `setOnComplete` 回调
  - 修改 `updateStreamingMessage()`：将 `typewriter.appendText(text)` 替换为 `waterfall.appendChunk(text)`，将 `typewriter.reset()` 替换为 `waterfall.reset()`
  - 修改 `cleanupAnimations()`：将 `typewriter.stop()` 替换为 `waterfall.stop()`
  - 修改 `switchSession()`：将 `typewriter.reset()` 替换为 `waterfall.reset()`
  - 修改 `sendMessage()` 起始处：将 `typewriter.reset()` 替换为 `waterfall.reset()`
  - 保持 thinking 阶段与 tool 阶段的过渡逻辑不变（工具调用时清除思考预览）
  - 完成后：发送消息，thinking 文本以内容块批量出现在流式气泡中，不再逐字符显示；工具步骤正常渲染
  - _Requirements: 1.1, 1.2, 3.1, 3.2, 4.1, 4.4_
  - _Boundary: WaterfallRenderer, streaming message pipeline_

- [ ] 2.2 简化 finalizeReply：去除打字机预览，直接渲染 Markdown
  - 修改 `finalizeReply(replyText)` 函数：移除 `stripMarkdownForTypewriter` 调用、打字机配置（`setCharDelay`、`setUseTruncation`）、纯文本渲染和 `onComplete` 回调中的 Markdown 替换逻辑
  - 新流程：`waterfall.flush()` → 清空 body → `body.innerHTML = renderMarkdown(replyText)` → 移除 streaming 类 → 添加复制按钮 → 重置 streamingMessage
  - 完成后：Agent 回答完成时，格式化的 Markdown 内容（表格、代码块、列表）直接出现在气泡中，无纯文本过渡闪烁
  - _Requirements: 1.3, 1.5, 4.2_
  - _Depends: 2.1_

- [ ] 2.3 添加渲染速度配置 UI 控件
  - 在 `index.html` 侧边栏中添加渲染速度配置 panel（`<section class="panel">`），包含标签和 `<select>` 下拉菜单，三个选项：快速/标准/慢速
  - 在 `app.js` 中初始化：页面加载时调用 `speedConfig.load()`，同步 `<select>` 选中状态
  - 绑定 `<select>` 的 `change` 事件：调用 `speedConfig.setSpeed(value)`，更新内存中的渲染延迟
  - WaterfallRenderer 的 rAF 消费循环从 `speedConfig.getDelay()` 读取延迟值
  - 完成后：在侧边栏可见渲染速度下拉菜单，切换后 WaterfallRenderer 的渲染节奏立即变化（快速=即时，慢速=可感知间隔）
  - _Requirements: 2.1, 2.2_
  - _Boundary: SpeedControl UI, index.html_

- [ ] 2.4 (P) 更新 CSS 样式：移除打字机动画，添加瀑布式进度指示器
  - 移除 `@keyframes blink-cursor` 和 `.streaming-cursor::after` 规则
  - 新增 `@keyframes waterfall-pulse` 动画：底部边框或下划线从透明到主题色脉冲（周期 1.2s）
  - 新增 `.waterfall-progress` 类：应用 `waterfall-pulse` 动画，用于渲染进行中的视觉反馈
  - WaterfallRenderer 在渲染开始/running 时为目标元素添加 `.waterfall-progress`，flush/stop/reset 时移除
  - 保留 `.pulse-dot`、`.pulse-border`、步骤过渡等现有动画规则不变
  - 保留 `@media (prefers-reduced-motion: reduce)` 无障碍降级规则
  - 添加 `#renderSpeedPanel` 和速度选择控件的样式（与现有 sidebar panel 风格一致）
  - 完成后：流式渲染时底部显示脉冲进度线（替代闪烁光标），渲染完成后消失；侧边栏速度控件样式与现有 UI 协调
  - _Requirements: 1.4, 1.5, 3.3_
  - _Boundary: styles.css_

## 3. Integration: 端到端验证

- [ ] 3.1 取消场景兼容与流式消息生命周期验证
  - 验证 `stopGeneration()` → `abortController.abort()` → `finalizeStreamingMessage(true)` 路径：瀑布渲染器正确停止，buffer 保留，取消标记追加
  - 验证 `switchSession()` 路径：`cleanupAnimations()` 停止瀑布渲染器，`reset()` 清空状态，新会话正常启动
  - 验证 `sendMessage()` 起始清理路径：上一轮瀑布渲染器正确 reset
  - 确保 `finalizeStreamingMessage(false)` 在正常完成时正确调用 `waterfall.flush()`（在 `finalizeReply` 中处理）
  - 确保双重 `final` 事件防抖（`finalHandled`）仍然生效
  - 完成后：点击停止按钮后渲染立即停止，已渲染内容保留，显示"[已停止生成]"；切换会话后渲染器状态干净
  - _Requirements: 4.3, 4.4_
  - _Depends: 2.1, 2.2_

- [ ] 3.2 性能保障：大块内容分帧渲染与后台标签页处理
  - 在 WaterfallRenderer 的 rAF 消费循环中实现分帧策略：单次渲染内容超过 500 字符时，只渲染前 500 字符，剩余内容留待下个 rAF 周期
  - 在 rAF 回调中检测 `elapsed` 时间差：若距上次渲染超过 200ms（标签页恢复），批量渲染所有累积 buffer 而不再分帧
  - 验证 `onRender` 回调每次渲染后触发自动滚动，无抖动
  - 完成后：发送长回答时页面不卡顿；切换到其他标签页再切回，累积内容立即全部渲染
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Depends: 2.1_

## 4. Validation: 测试

- [ ] 4.1 (P) WaterfallRenderer 与 SpeedConfig 单元测试
  - `test_waterfall_renderer.py` 或前端测试：验证 `appendChunk` 累积 buffer、`flush` 清空 buffer 并写入 DOM、`reset` 完全清空状态、`stop` 停止循环但保留 buffer
  - 验证 `getDelay()` 在 fast/normal/slow 下返回正确值（0/30/80）
  - 验证 `setSpeed` 的非法值回退逻辑（传入 "invalid" 回退到 "normal"）
  - 验证 `load()` 从 localStorage 恢复设置，以及 localStorage 不可用时的降级行为
  - 完成后：`pytest tests/test_waterfall_renderer.py -v` 全部通过（或等效前端测试）
  - _Requirements: 1.1, 1.2, 2.1, 2.3, 2.4, 2.5, 5.2_

- [ ] 4.2 集成测试与 E2E 验证
  - 验证完整 SSE 流：发送消息 → thinking 文本瀑布式批量渲染 → 工具步骤正常显示 → final 事件直接渲染 Markdown
  - 验证速度切换端到端：切换为"慢速"后发送消息，观察块间有可感知延迟；切换为"快速"后延迟消失
  - 验证速度持久化：切换速度 → 刷新页面 → 速度设置保持
  - 验证取消流程：发送消息 → 中途停止 → 已渲染内容保留 → 取消标记显示
  - 验证 Markdown 渲染正确性：表格、代码块、列表、标题均正常显示
  - 完成后：手动测试全部通过，或 E2E 测试脚本 `tests/test_waterfall_e2e.sh` 执行成功
  - _Requirements: 1.3, 2.2, 4.1, 4.2, 4.3_
  - _Depends: 3.1, 3.2_
