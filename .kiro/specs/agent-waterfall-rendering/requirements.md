# Requirements Document

## Introduction
前端用户在使用 DBAgent 时，Agent 的回答采用打字机（typewriter）效果逐字渲染，渲染速度慢，导致一次完整回答的显示耗时过长，用户体验差。需要将渲染方式改为瀑布式（waterfall）渲染，即一次性批量渲染内容块，大幅提升显示速度，同时提供可调节的渲染速度参数，方便用户根据偏好调整。

## Boundary Context
- **In scope**: 前端 Agent 回答的渲染方式从打字机改为瀑布式；渲染速度的可配置与调节；渲染过程中的视觉反馈；对现有 SSE 事件流的兼容
- **Out of scope**: 后端 SSE 事件生成逻辑的修改；LLM 推理速度优化；API 协议变更；其他前端功能（会话管理、SQL 面板、侧边栏等）的修改
- **Adjacent expectations**: 后端 SSE 事件格式保持不变（`step`、`sql`、`final` 事件类型不变）；现有的 `createStreamingBubble` / `updateStreamingMessage` 流式消息生命周期不变

## Requirements

### Requirement 1: 瀑布式内容渲染
**Objective:** As a 前端用户, I want Agent 回答以批量内容块（瀑布式）渲染，而非逐字打字机效果, so that 回答显示速度大幅提升，减少等待时间。

#### Acceptance Criteria
1. When Agent 生成回答内容时，the 前端 shall 以批量内容块（chunk）为单位渲染文本，而非逐字符渲染。
2. When 新的内容块到达时，the 前端 shall 立即将该块完整追加到显示区域，一次渲染整个块的全部内容。
3. When 回答内容包含 Markdown 格式（表格、代码块、列表等），the 前端 shall 在内容块完整到达后直接渲染 Markdown，无需先用纯文本预览再替换。
4. While 瀑布式渲染进行中，the 前端 shall 在渲染区域显示视觉指示器（如闪烁光标或加载动画），表明内容仍在生成中。
5. When 全部内容渲染完成，the 前端 shall 移除视觉指示器，并将消息气泡标记为完成状态。

### Requirement 2: 渲染速度可配置
**Objective:** As a 前端用户, I want 能够调整瀑布式渲染的速度, so that 我可以根据个人偏好和网络条件选择适合的渲染节奏。

#### Acceptance Criteria
1. The 前端 shall 提供一个渲染速度配置项，支持至少三种速度档位：快速（即时渲染）、标准（轻微延迟）、慢速（可感知的块间延迟）。
2. When 用户切换渲染速度档位时，the 前端 shall 立即应用新的速度设置，无需刷新页面。
3. The 前端 shall 将用户选择的渲染速度持久化到浏览器本地存储（localStorage），页面刷新后保持用户偏好。
4. When 渲染速度设置为"快速"时，the 前端 shall 在每个内容块到达后立即渲染，块间无人工延迟。
5. When 渲染速度设置为"标准"或"慢速"时，the 前端 shall 在内容块之间插入可配置的延迟间隔。

### Requirement 3: 思考过程渲染优化
**Objective:** As a 前端用户, I want Agent 的思考过程（thinking 阶段）也使用瀑布式渲染, so that 思考内容的显示更加流畅高效。

#### Acceptance Criteria
1. When Agent 处于 thinking 阶段时，the 前端 shall 以瀑布式批量渲染思考文本，每次追加完整的内容增量而非逐字符。
2. When 思考文本在工具调用阶段被清除时，the 前端 shall 保持现有行为：清除思考预览，避免与工具步骤视觉混淆。
3. While 思考阶段进行中，the 前端 shall 显示适当的视觉指示器表明 Agent 正在思考。

### Requirement 4: 向后兼容
**Objective:** As a 系统, I want 瀑布式渲染与现有 SSE 事件流完全兼容, so that 后端无需任何修改即可支持新的渲染方式。

#### Acceptance Criteria
1. When 前端接收到 SSE `step` 事件（含 `thinking` 和 `tool:*` 类型），the 前端 shall 正确处理并渲染，不丢失任何事件数据。
2. When 前端接收到 SSE `final` 事件，the 前端 shall 正确完成流式消息的最终化，包含取消场景和正常完成场景。
3. When 用户取消 Agent 生成（点击停止按钮），the 前端 shall 正确终止瀑布式渲染，保留已渲染内容并追加取消标记。
4. The 前端 shall 保持现有的流式消息生命周期不变（消息气泡创建、更新、完成/取消），仅替换内部渲染机制。

### Requirement 5: 渲染性能保障
**Objective:** As a 前端用户, I want 瀑布式渲染不会导致页面卡顿或浏览器无响应, so that 在大量内容渲染时仍能保持流畅的交互体验。

#### Acceptance Criteria
1. When 单个内容块超过 500 字符时，the 前端 shall 分帧渲染该内容块，确保渲染过程不阻塞主线程导致页面无响应。
2. When 连续多个内容块快速到达时，the 前端 shall 合并相邻的渲染操作，避免不必要的 DOM 重排。
3. While 瀑布式渲染进行中，the 前端 shall 保持消息区域的自动滚动到底部，不因渲染方式改变而出现滚动抖动。
4. If 浏览器标签页处于后台（不可见），the 前端 shall 暂停渲染动画，待标签页恢复可见后立即渲染所有已累积内容。