# 实现计划

## 任务格式说明
- `(P)` 标记表示该任务可与同组任务并行执行
- `_Requirements:` 列出需求编号（仅数字 ID）
- `_Boundary:` 声明任务所属的组件边界（设计文档中定义的组件名）
- `_Depends:` 声明跨组依赖

---

- [x] 1. CSS 基础设施：变量修复、动画关键帧定义与无障碍降级

- [x] 1.1 CSS 变量修复、动画关键帧定义、步骤过渡规则与无障碍降级
  - 修复缺失的 CSS 变量：定义 `--ok: #0f766e` 和 `--err: #b42318`
  - 修复 `pulse-border` 动画中硬编码的 `#93c5fd` 颜色，改用 CSS 变量引用
  - 新增 `@keyframes blink-cursor`：打字机光标闪烁动画（opacity 0↔1，step-end 时序）
  - 新增 `@keyframes pulse-dot`：工具步骤运行指示器动画（opacity + transform:scale，compositor-only）
  - 新增 `@keyframes text-pulse`：工具步骤标签文字脉冲动画（opacity 0.5↔1）
  - 新增 `.streaming-step` 和 `.streaming-step .step-icon` 的 `transition` 规则（color/opacity/transform，0.2-0.3s ease）
  - 新增 `.streaming-cursor::after` 样式：内联块级光标元素，使用 `blink-cursor` 动画
  - 新增 `.pulse-dot` 样式：内联块级圆形指示器，使用 `pulse-dot` 动画
  - 新增 `.phase-label` 样式：阶段标签文字样式
  - 新增 `@media (prefers-reduced-motion: reduce)` 块：停止所有动画，降级为静态展示
  - **完成标志**：浏览器中所有 CSS 动画正确渲染；系统开启"减少动画"后动画全部降级为静态
  - _Requirements: 2.1, 4.1, 4.3, 5.2_
  - _Boundary: CSS Animations_

- [x] 2. 核心渲染增强：打字机、步骤动画与阶段标签

- [x] 2.1 TypewriterRenderer 打字机状态机实现
  - 实现 TypewriterRenderer 对象，管理思考文本的逐字渲染
  - 实现 `appendText(text)`：追加文本到内部缓冲区，若定时器未运行则启动 rAF 循环
  - 实现 `flush()`：立即渲染所有剩余字符，停止定时器，移除光标
  - 实现 `stop()`：停止定时器，保持当前渲染内容
  - 实现 `reset()`：清空所有状态（fullText、displayedLength、rafId）
  - 实现 `setTarget(element)` 和 `setOnRender(callback)`：设置渲染目标 DOM 元素和每帧回调
  - rAF 定时器逻辑：基于 `lastTickTime` 控制 30ms 字符间隔，每个 tick 渲染 1 个字符
  - 加速模式：当 `queueStartTime` 距今超过 3 秒时，将 `charDelay` 降至 5ms
  - 后台标签页恢复：检测 `lastTickTime` 间隔超过 100ms 时，批量渲染 5 个字符
  - 异常降级：try-catch 包裹渲染逻辑，异常时立即 flush 全部缓冲文本
  - 编写单元测试：验证 appendText 正确累积、flush 渲染全部字符、加速模式触发、异常降级
  - **完成标志**：思考文本以约 30ms/字符的速度逐字出现，末尾有闪烁光标；3 秒积压时自动加速
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.1, 5.3_
  - _Boundary: TypewriterRenderer_

- [x] 2.2 StepRenderer 工具步骤增量 DOM 渲染
  - 实现 StepRenderer：维护 `stepId → HTMLElement` 的 Map 映射
  - 步骤新增时创建 DOM 元素（含 `pulse-dot` 动画指示器和标签文本）并追加到步骤容器
  - 步骤状态变更时仅更新对应元素的类名和图标，不重建整个容器
  - 提供 `createStep(stepId, label)`、`updateStep(stepId, status)`、`clearSteps()` 方法
  - 将 running 状态的 ⏳ emoji 替换为 CSS `pulse-dot` 动画指示器（`<span class="pulse-dot">`）
  - 保留 ✅ 和 ❌ 作为 completed/error 状态的静态图标
  - 实现状态过渡：步骤从 running→completed 时，先移除 `running` 类名 → `requestAnimationFrame` 延迟一帧 → 添加 `completed` 类名，触发 CSS transition
  - 仅对当前 status === "running" 的步骤元素保留动画类名
  - 编写单元测试：验证 createStep 创建正确 DOM 结构、updateStep 正确切换类名和图标
  - **完成标志**：StepRenderer 独立于管线可单独测试；状态变更时 DOM 类名和图标正确更新
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: StepRenderer_
  - _Depends: 2.1_

- [x] 2.3 阶段标签与动画清理（集成任务）
  - 实现 `updatePhaseLabel` 函数：根据当前 step 参数更新流式气泡 `.meta` 元素文本
  - 思考阶段（step === "thinking"）：显示 "DBAgent · 思考中..."
  - 工具调用阶段（step 以 "tool:" 开头）：提取工具名称，显示 "DBAgent · 正在查询数据库..."
  - 实现动画清理函数 `cleanupAnimations()`：停止 TypewriterRenderer、清除所有步骤动画类名和 `will-change` 属性
  - 在 `finalizeStreamingMessage`（正常完成路径）中调用 `cleanupAnimations()`，恢复 `.meta` 为 "DBAgent"
  - 在 `finalizeStreamingMessage`（取消路径）中同样调用 `cleanupAnimations()`，保留取消标记
  - 在 `switchSession` 入口处调用 `cleanupAnimations()` 和 `TypewriterRenderer.reset()`
  - 在 `sendMessage` 入口处调用 `cleanupAnimations()` 和 `TypewriterRenderer.reset()`
  - 此任务为显式集成任务：跨越 MetaLabel 和 AnimationCleanup 两个组件边界，因其共享同一组生命周期调用点
  - **完成标志**：气泡标签随执行阶段实时变化；切换会话或发送新消息时所有动画立即停止并重置
  - _Requirements: 3.1, 3.2, 3.3, 4.2, 4.4_
  - _Depends: 2.2_

- [x] 2.4 流式消息管线重构与组件集成（集成任务）
  - 重构 `updateStreamingMessage`：将 `innerHTML` 全量重建改为增量 DOM 操作
  - 创建独立的 `thinkingEl` 元素（用于 TypewriterRenderer 直接操作 `textContent`）和 `stepsContainer` 元素（用于 StepRenderer 管理子元素）
  - 在 `createStreamingBubble` 中初始化这些持久 DOM 元素：`<div class="thinking-text streaming-cursor">` + `<div class="streaming-steps">`
  - 集成 TypewriterRenderer：`step === "thinking"` 时调用 `appendText(text)`，其他 step 时调用 `flush()`
  - 集成 StepRenderer：在 `updateStreamingMessage` 中对 `streamingSteps` 数组进行 diff，调用 `createStep`/`updateStep`
  - 集成 MetaLabel：在 `updateStreamingMessage` 中调用 `updatePhaseLabel` 更新阶段标签
  - 确保 `sendMessage` 开始时调用 `TypewriterRenderer.reset()` 和 `StepRenderer.clearSteps()` 清理上一轮状态
  - 此任务为显式集成任务：负责将 TypewriterRenderer、StepRenderer、MetaLabel 三个组件接入统一的渲染管线，并定义它们共享的 DOM 结构约定
  - **完成标志**：完整的 thinking→tool→final 流式渲染通过 SSE 事件驱动，动画和标签按预期联动
  - _Requirements: 1.1, 1.4, 3.1, 3.2, 3.3_
  - _Depends: 2.1, 2.2, 2.3_

- [x] 3. 集成测试与端到端验证

- [x] 3.1 SSE 事件管道集成测试
  - 模拟 SSE thinking 事件序列（多个 text chunk）→ 验证 TypewriterRenderer 逐字渲染，DOM 中文本逐字符增加
  - 模拟 thinking→tool_start 事件序列 → 验证 TypewriterRenderer.flush() 被触发，阶段标签从"思考中"切换到工具名称
  - 模拟 tool_start→tool_end (completed) 事件序列 → 验证步骤从 pulse-dot 动画过渡到 ✅ 静态图标
  - 模拟 tool_start→tool_end (error) 事件序列 → 验证步骤显示 ❌ 图标，动画停止
  - 模拟 cancel 事件 → 验证 TypewriterRenderer 停止、动画类名清除、取消标记渲染
  - 模拟 switchSession 调用 → 验证所有动画状态（TypewriterRenderer、StepRenderer）被重置
  - 模拟 null/undefined text → 验证降级为静态文本展示，不抛异常
  - **完成标志**：所有集成测试通过，动画状态转换与预期一致
  - _Requirements: 1.1, 1.4, 3.1, 3.2, 4.2, 4.4, 5.1_
  - _Depends: 2.4_

- [x] 3.2 (P) E2E 用户流程验证
  - 完整思考-工具-回答流程：发送真实查询，验证思考文本逐字出现、工具步骤动画展示、最终回答正常渲染到独立消息气泡
  - 取消中流程：在 Agent 执行中点击停止按钮，验证动画立即停止、流式气泡保留并显示"[已停止生成]"标记
  - 多轮对话：连续发送 3 条消息，验证每轮动画独立启动和清理，上一轮动画不泄漏到下一轮
  - prefers-reduced-motion：在操作系统设置中启用"减少动画"，验证所有动画降级为静态展示，消息内容完整
  - **完成标志**：所有 E2E 场景通过，视觉行为与设计预期一致
  - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3, 4.2, 4.4, 5.2_
  - _Depends: 3.1_

- [x] 3.3 (P) 性能与边缘场景验证
  - 快速 SSE 事件：以 10ms 间隔模拟 SSE 事件，验证 3 秒超时加速机制触发，`charDelay` 降至 5ms
  - 多动画并发：同时运行打字机 + 3 个工具步骤动画，使用 Performance API 测量帧率，验证保持 30fps 以上
  - 内存泄漏检测：连续 10 轮对话后检查 TypewriterRenderer 状态和 StepRenderer Map 是否正确释放（无残留引用）
  - 后台标签页恢复：切换到其他标签页 5 秒后切回，验证批量渲染恢复（一次性渲染积压字符）且无视觉闪烁
  - **完成标志**：性能测试全部通过，无内存泄漏，帧率达标
  - _Requirements: 1.2, 4.3, 5.3_
  - _Depends: 3.1_
