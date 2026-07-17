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

- [x] 4. PhaseTracker 阶段进度追踪

- [x] 4.1 PhaseTracker 核心实现
  - 定义 `TOOL_LABEL_MAP` 常量映射表，将 5 个工具名（find_table、describe_table、execute_sql、list_databases、confirm_sql）映射为人类可读的中文描述
  - 实现 `createPhaseTracker()` 工厂函数，返回 PhaseTracker 实例，维护 `phases[]` 数组和 `thinkingCount` 计数器（初始为 0，每次 thinking 阶段调用时递增 1）
  - 实现 `addPhase(step, status)`：判定阶段类型 — thinkingCount 为 0 时首次 thinking → "分析问题"，thinkingCount ≥ 1 时后续 thinking → "生成回答"；tool:* → 映射表查询，未知工具降级显示原始英文名。每次调用始终创建新阶段项（不更新已有项），使用 `id` 格式 `"thinking-{thinkingCount}"` 或 `"tool:{name}-{callIndex}"` 区分
  - 实现 `completePhase(step)`：根据传入的 step 字符串（如 `"tool:find_table"`）查找对应阶段项并标记为 `completed` 状态
  - 实现 `completeAll()`：将所有阶段项标记为 `completed` 状态
  - 实现 `cancelCurrent()`：将当前 running 状态阶段项标记为 `cancelled`
  - 实现 `reset()`：清空 phases 数组和 thinkingCount 计数器
  - 实现 `setContainer(element)`：设置阶段进度容器 DOM 元素引用
  - 实现 `setOnRender(callback)`：设置每次渲染后的回调（用于自动滚动，由集成任务 4.3 绑定到 `messages.scrollTop`）
  - 渲染逻辑：创建 `.phase-tracker` 容器，每个阶段项为 `.phase-item` 元素（含 `.phase-icon` 图标和 `.phase-label` 文本），增量更新已有阶段项、仅追加新阶段项，避免全量重建
  - 阶段图标：running → ⏳，completed → ✅，cancelled → ❌，对应类名 `.active`、`.completed`、`.cancelled`
  - 异常处理：container 不存在时静默跳过渲染；step 参数为 null/undefined 时忽略调用
  - **完成标志**：PhaseTracker 独立于渲染管线可单独测试；验证各阶段正确映射和状态切换
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - _Boundary: PhaseTracker_

- [x] 4.2 (P) 阶段进度指示器 CSS 样式
  - 新增 `.phase-tracker` 容器样式：margin-bottom: 12px、padding: 8px 12px、background: var(--panel)、border-radius: 8px、border: 1px solid var(--line)
  - 新增 `.phase-item` 基础样式：display: flex、align-items: center、gap: 8px、padding: 4px 0、font-size: 0.875rem、color: var(--muted)、transition: color 0.3s ease
  - 新增 `.phase-item.active` 进行中样式：color: var(--fg)、font-weight: 500
  - 新增 `.phase-item.completed` 已完成样式：color: var(--ok)
  - 新增 `.phase-item.cancelled` 已取消样式：color: var(--muted)、text-decoration: line-through
  - 新增 `.phase-icon` 样式：width: 16px、text-align: center、flex-shrink: 0
  - 新增 `.phase-label` 样式：flex: 1
  - 在 `@media (prefers-reduced-motion: reduce)` 块中追加 `.phase-item { transition: none }` 降级规则
  - **完成标志**：阶段进度指示器在浏览器中正确渲染，各状态样式区分明显，无障碍降级生效
  - _Requirements: 4.1, 5.2_
  - _Boundary: CSS Animations_

- [x] 4.3 管线集成：PhaseTracker 接入渲染管线
  - 创建全局单例：`const phaseTracker = createPhaseTracker();`（与 `waterfall`、`stepRenderer` 并列，位于文件顶部全局作用域）
  - 在 `createStreamingBubble` 中创建 `.phase-tracker` 容器 DOM 元素（插入到 `.thinking-text` 之前），并调用 `phaseTracker.setContainer()`
  - 在 `createStreamingBubble` 中绑定自动滚动：`phaseTracker.setOnRender(() => { messages.scrollTop = messages.scrollHeight; })`
  - 在 `updateStreamingMessage` 中移除 `updatePhaseLabel` 调用，替换为 `phaseTracker.addPhase(step, status)`
  - 在 `updateStreamingMessage` 中 tool 状态为 completed 时追加调用 `phaseTracker.completePhase(step)`
  - 在 `finalizeStreamingMessage` 正常完成路径中依次调用 `phaseTracker.completeAll()` 和 `phaseTracker.reset()`
  - 在 `finalizeStreamingMessage` 取消路径中调用 `phaseTracker.cancelCurrent()`
  - 在 `cleanupAnimations` 中追加 `phaseTracker.reset()` 调用
  - 删除旧的 `updatePhaseLabel` 函数（第 988-1001 行）和 `lastPhase` 变量（第 1041 行）
  - 在 `sendMessage` 入口处追加 `phaseTracker.reset()` 调用（与 `cleanupAnimations` 中的调用形成双重保障）
  - 在 `switchSession` 中追加 `phaseTracker.reset()` 调用
  - 此任务为显式集成任务：跨 PhaseTracker、AnimationCleanup、渲染管线三个边界
  - **完成标志**：完整 Agent 执行流程中阶段进度指示器正确显示，取消/完成/切换会话时状态正确清理，无内存泄漏
  - _Depends: 4.1, 4.2_
  - _Requirements: 3.1, 3.5, 3.6, 3.7, 3.8, 3.9, 4.2, 4.4_

- [x] 5. 测试与验证

- [x] 5.1 PhaseTracker 单元测试
  - 模拟首次 `addPhase("thinking")` → 验证阶段标签为"分析问题"，`thinkingCount` 为 1
  - 模拟工具调用后再次 `addPhase("thinking")` → 验证阶段标签为"生成回答"
  - 模拟 `addPhase("tool:find_table")` → 验证阶段标签为"搜索数据库表"
  - 模拟 `addPhase("tool:unknown_tool")` → 验证降级显示原始英文名 "unknown_tool"
  - 模拟 `completePhase("tool:find_table")` → 验证对应阶段状态变为 `completed`
  - 模拟 `completeAll()` → 验证所有阶段状态变为 `completed`
  - 模拟 `cancelCurrent()` → 验证当前 running 阶段标记为 `cancelled`，已完成阶段不变
  - 模拟 `reset()` → 验证 phases 数组清空，thinkingCount 归零
  - 渲染验证：检查 DOM 中 `.phase-item` 元素数量与 phases 数组一致，类名与状态对应
  - **完成标志**：所有单元测试通过，PhaseTracker 各方法行为符合预期
  - _Depends: 4.1_
  - _Requirements: 3.2, 3.3, 3.5, 3.7, 3.9_

- [x] 5.2 (P) 集成与 E2E 验证
  - 完整流程 E2E：发送真实查询，验证阶段进度指示器依次显示"分析问题"→"搜索数据库表"→"查看表结构"→"执行 SQL 查询"→"生成回答"，所有阶段最终标记为完成
  - 取消流程：Agent 执行中点击停止按钮，验证已完成阶段保留（✅ 图标），当前阶段标记为取消（❌ 图标）
  - 多轮对话：连续发送 3 条消息，验证每轮阶段追踪独立，上一轮阶段列表被清理
  - prefers-reduced-motion：操作系统启用"减少动画"，验证阶段项 transition 被禁用，内容完整
  - 阶段自动滚动：验证阶段进度指示器新增阶段时，消息区域自动滚动到底部
  - **完成标志**：所有 E2E 场景通过，阶段进度指示器行为与设计预期一致
  - _Depends: 4.3_
  - _Requirements: 3.1, 3.4, 3.6, 3.8, 3.9, 5.2_