# 研究日志：Agent 流式展示增强

## 摘要
- **功能**：agent-streaming-display（扩展更新 — 新增阶段进度追踪）
- **发现范围**：Extension — 在现有流式渲染管道上扩展阶段进度追踪
- **关键发现**：
  - 现有 `updatePhaseLabel` 仅显示两种通用标签（"思考中..." / "正在查询数据库..."），缺乏具体阶段信息
  - 后端不提供 `phase` 字段，阶段判定完全由前端根据 `step` 字段推断
  - 当前工具共 5 个：`find_table`、`describe_table`、`execute_sql`、`list_databases`、`confirm_sql`
  - 现有 DOM 结构（`.content > .thinking-text + .streaming-steps`）可扩展插入 `.phase-tracker` 容器

## 研究日志

### 现有阶段显示机制分析
- **Context**: 需要理解当前阶段显示的实现方式，确定扩展点
- **Sources Consulted**: `app/static/app.js`（第 988-1001 行 `updatePhaseLabel` 函数）
- **Findings**:
  - `updatePhaseLabel` 仅设置 `.meta` 元素的 `textContent`，无状态追踪
  - 仅区分两种阶段：`thinking` → "思考中..."，`tool:*` → "正在查询数据库..."
  - 无已完成阶段列表，无进度追踪，无工具名映射
- **Implications**: 需要新增 `PhaseTracker` 组件替换 `updatePhaseLabel`，在 `.content` 中新增阶段进度容器

### 工具名称映射
- **Context**: 需要将后端工具名映射为人类可读的中文描述
- **Sources Consulted**: `app/tools/__init__.py`（TOOLS 注册表）
- **Findings**:
  - 5 个工具：`find_table`（搜索表）、`describe_table`（查看表结构）、`execute_sql`（执行 SQL）、`list_databases`（浏览数据库）、`confirm_sql`（确认执行）
  - 工具名使用英文下划线命名，前端 `step` 事件格式为 `"tool:find_table"`
- **Implications**: 在前端维护 `TOOL_LABEL_MAP` 常量映射表，新增工具时需同步更新

### 思考阶段区分
- **Context**: 需要区分首次思考（"分析问题"）和后续思考（"生成回答"）
- **Sources Consulted**: `app/agent/runner.py`（ReAct 循环逻辑）
- **Findings**:
  - Agent 循环：thinking → tool → thinking → tool → ... → final thinking → final response
  - 首次 thinking 是分析用户问题，工具调用后的 thinking 是综合信息生成回答
- **Implications**: 通过 `thinkingCount` 计数器区分首次和后续思考

## 架构模式评估

略（本扩展不涉及架构模式变更，在现有管道增强模式上叠加新组件）

## 设计决策

### 决策：新增 PhaseTracker 组件替换 updatePhaseLabel
- **Context**: 需求 3.1-3.9 要求展示阶段进度，现有 `updatePhaseLabel` 仅支持简单文本更新
- **备选方案**:
  1. 在 `updatePhaseLabel` 中扩展逻辑 — 会导致函数职责膨胀
  2. 新增独立 `PhaseTracker` 组件 — 职责清晰，可独立测试
- **选定方案**: 新增 `PhaseTracker` 组件，与 `WaterfallRenderer`、`StepRenderer` 并列
- **理由**: 保持单一职责，与现有组件模式一致（`createXxxRenderer()` 工厂函数模式）
- **权衡**: 增加一个组件，但换取了清晰的边界和可测试性
- **后续跟进**: 实现时确保 `PhaseTracker` 的 DOM 容器插入位置正确（在 `.content` 顶部）

### 决策：前端静态映射表实现工具名翻译
- **Context**: 需求 3.3 要求工具名映射为人类可读描述
- **备选方案**:
  1. 后端新增 `label` 字段 — 需要修改 SSE 事件格式，变更范围大
  2. 前端静态映射表 — 零后端变更，维护简单
- **选定方案**: 前端 `TOOL_LABEL_MAP` 常量映射表
- **理由**: 不跨越前后端边界，符合"不修改后端 SSE 事件"的约束
- **权衡**: 新增工具时需同步更新映射表，但工具变更频率低
- **后续跟进**: 在 `app/tools/__init__.py` 的注释中提醒新增工具时同步更新前端映射表

## 风险与缓解
- **工具名变更未同步**：新增/重命名工具时前端映射表未更新 → 降级显示原始英文名，不影响功能
- **阶段事件乱序**：SSE 事件到达顺序异常 → `PhaseTracker` 按 `stepId` 查找更新，不依赖事件顺序
- **DOM 容器不存在**：`.content` 元素未找到 → PhaseTracker 静默跳过，不抛异常

## 参考资料
- `app/agent/runner.py` — SSE 事件生成逻辑
- `app/static/app.js` — 现有前端渲染管线
- `app/tools/__init__.py` — 工具注册表
- `app/static/styles.css` — 现有 CSS 变量和动画定义