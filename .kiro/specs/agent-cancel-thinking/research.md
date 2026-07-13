# Research & Design Decisions

## Summary
- **Feature**: `agent-cancel-thinking`
- **Discovery Scope**: Extension
- **Key Findings**:
  - OpenAI Python SDK 无内置取消机制，需通过 `asyncio.wait()` 竞速 LLM 任务与取消事件
  - Starlette `request.is_disconnected()` 可用于检测 SSE 客户端断开
  - `asyncio.Event` 是跨 task 取消信号的最佳选择
  - 浏览器 `AbortController` 可中断 fetch + ReadableStream 管道

## Research Log

### OpenAI SDK 取消机制
- **Context**: 需要中断正在进行的 `client.chat.completions.create()` 调用
- **Sources Consulted**: OpenAI SDK 源码、GitHub issues #2643、httpx 文档
- **Findings**: SDK 不提供 `cancel()` 方法或取消 token。当前项目使用非流式调用（`stream=False`），底层 httpx 连接在 task 被 cancel 时会自动关闭
- **Implications**: 使用 `asyncio.create_task()` + `asyncio.wait(return_when=FIRST_COMPLETED)` 竞速 LLM 任务与取消事件

### Starlette 客户端断开检测
- **Context**: SSE 端点需要感知客户端断开连接
- **Sources Consulted**: starlette.io 官方文档
- **Findings**: `await request.is_disconnected()` 返回 bool，通过 ASGI receive channel 检测断开事件
- **Implications**: 在 SSE event_stream 中轮询 `is_disconnected()`，检测到断开时设置取消事件

### asyncio.Event 跨任务信令
- **Context**: 需要在 HTTP 端点（取消请求）和 Agent 执行流之间传递取消信号
- **Sources Consulted**: Python 官方 asyncio 文档
- **Findings**: `Event.wait()` 阻塞直到 `set()` 被调用，所有等待者同时唤醒；`is_set()` 用于非阻塞轮询；`clear()` 重置状态
- **Implications**: 使用 session_id 为 key 的 Event 注册表，取消端点 `set()` 事件，Agent 循环中 `is_set()` 检查

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks | Notes |
|--------|-------------|-----------|-------|-------|
| asyncio.wait() 竞速 | 将 LLM 调用和取消等待包装为两个 task，使用 `asyncio.wait(FIRST_COMPLETED)` 竞速 | 精确中断 LLM 等待；无需修改 SDK 调用方式 | 每次 LLM 调用创建额外 task | 选中 ✓ |
| 仅迭代边界检查 | 只在 ReAct 循环迭代边界检查取消标志 | 简单 | 无法中断正在进行的 LLM 调用（需求 1.2 不满足） | 不满足需求 |
| 改用流式 LLM | 切换到 `stream=True`，在 chunk 迭代中检查取消 | 可精细控制中断粒度 | 需要重写 LLM 调用逻辑，影响范围大 | 过度设计 |

## Design Decisions

### Decision: 取消信号传递架构
- **Context**: HTTP 取消端点需要通知正在执行的 Agent 循环
- **Alternatives Considered**:
  1. 全局 dict + asyncio.Event — 以 session_id 为 key 存储取消事件
  2. 在 Agent 执行线程中直接注入 — 仅适用于同步模式
- **Selected Approach**: 全局 `CancelEventRegistry` 类，维护 `dict[str, asyncio.Event]`，提供 `create(session_id)`, `cancel(session_id)`, `remove(session_id)` 方法
- **Rationale**: 简单、无外部依赖、与现有 asyncio 架构一致
- **Trade-offs**: 需要手动清理过期事件（使用 `try/finally` 保证）

### Decision: LLM 调用中断策略
- **Context**: 需求 1.2 要求"中断等待并立即终止"
- **Alternatives Considered**:
  1. `asyncio.wait(FIRST_COMPLETED)` 竞速 — 两个 task 同时跑，先完成者胜
  2. `asyncio.wait_for()` 超时包装 — 只能做超时，不能做主动取消
- **Selected Approach**: `asyncio.wait(FIRST_COMPLETED)` 竞速 LLM task 和 cancel_event.wait() task
- **Rationale**: 无需修改 LLM 调用方式，取消时主动 cancel LLM task 触发 httpx 连接关闭
- **Trade-offs**: 每次 LLM 调用多一个 task 开销（可忽略）
- **Follow-up**: 验证 `task.cancel()` 后 httpx 连接是否正确释放

### Decision: 取消后工具执行超时保护
- **Context**: 当前设计等待工具完成后终止，但长时间工具调用（大表查询）会让取消无效
- **Alternatives Considered**:
  1. 不处理（等待完成）— 简单但用户体验差
  2. 强制 kill task — 可能导致数据库连接泄漏
  3. `asyncio.wait_for(tool(), timeout=30s)` — 超时后 Agent 终止，工具 task 后台继续跑
- **Selected Approach**: `asyncio.wait_for(tool(), timeout=30s)`
- **Rationale**: 超时后 Agent 终止响应给用户，工具 task 虽未被取消（防止连接泄漏），但结果被丢弃。30s 是合理上限
- **Trade-offs**: 工具超时后的 task 在后台继续运行直到自然完成，占用一个数据库连接直到查询完成

### Decision: CancelEventRegistry TTL 过期机制
- **Context**: 纯依赖 finally 清理可能导致事件泄漏
- **Alternatives Considered**:
  1. 纯 finally — 简单但不可靠
  2. `weakref` — 过于复杂
  3. TTL + 投机清理 — 简单有效
- **Selected Approach**: 5min TTL + `create()` 时投机清理 + finally 保证正常路径清理
- **Rationale**: 正常路径 finally 清理，异常路径 TTL 兜底，三重保障

### Decision: 前端双重 final 事件防抖 + 流式消息保留
- **Context**: 取消请求和 Agent 正常完成可能竞速，取消时删除流式气泡再重建会闪烁
- **Alternatives Considered**:
  1. 不加处理 — 可能显示错误状态
  2. 服务端排他 — 复杂度高
  3. 前端 `finalHandled` 标志 + 原地保留气泡 — 简单可靠
- **Selected Approach**: `finalHandled` 优先处理 cancelled；取消时不移除气泡，原地转为带标记的普通消息
- **Rationale**: 防抖逻辑简单明确；原地保留避免了 DOM 删除再插入的闪烁
- **Trade-offs**: 前端多一个状态变量，需要在 `sendMessage()` 开始处重置

### Decision: CancelledError 作为主断开检测机制
- **Context**: `request.is_disconnected()` 只在 yield 前检查，工具执行期间不轮询
- **Alternatives Considered**:
  1. 仅 is_disconnected — 检测不及时
  2. 仅 CancelledError — Starlette 行为依赖 ASGI 服务器实现
  3. CancelledError 为主 + is_disconnected 兜底 — 互补
- **Selected Approach**: 在 SSE generator 中捕获 `asyncio.CancelledError`（ASGI 任务在客户端断开时被取消），同时在每次 yield 前调用 `is_disconnected()` 兜底
- **Rationale**: `CancelledError` 响应及时（客户端断开后 ASGI 服务器立即取消任务），`is_disconnected()` 覆盖 ASGI 服务器不主动取消任务的场景

## Risks & Mitigations
- **LLM task 取消后 httpx 连接泄漏** — `task.cancel()` 后必须 `await task`（让 `CancelledError` 传播并触发 SDK 内部 finally 清理），集成测试验证端口不泄漏
- **长时间工具调用导致取消无响应** — 取消信号触发后，工具执行使用 `asyncio.wait_for(tool(), timeout=30s)` 包装，超时后 Agent 直接终止
- **CancelEventRegistry 内存泄漏** — 三重保障：(1) 5min TTL 自动过期，(2) `create()` 时投机清理，(3) `finally` 块保证 `remove()` 调用
- **前端双重 final 事件** — `finalHandled` 标志优先处理 cancelled 事件，收到 cancelled 后忽略后续 completed
- **客户端断开检测不及时** — 主检测通过 `CancelledError` 捕获（ASGI 任务被取消时立即触发），兜底通过 `request.is_disconnected()` 轮询
- **取消时流式消息闪烁** — 取消时不删除流式气泡，原地移除 `.streaming` class + 追加"[已停止生成]"标记
- **并发取消竞态** — `asyncio.Event.set()` 是幂等的，多次取消不会产生副作用

## References
- [Starlette Requests — is_disconnected()](https://www.starlette.io/requests/)
- [Python asyncio — Event](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event)
- [MDN — AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)