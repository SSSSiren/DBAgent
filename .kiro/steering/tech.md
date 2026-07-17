# 技术

## 技术栈
| 层级 | 技术 | 用途 |
|-------|-----------|---------|
| Agent 框架 | **claude-agent-sdk** | Agent 循环、工具编排、MCP 服务 |
| Web 框架 | **FastAPI** + SSE + WebSocket | HTTP API、流式响应 |
| 大模型 | **DeepSeek**（OpenAI 兼容 API） | 推理、SQL 生成、回复格式化 |
| 数据库访问 | **OneDBA 平台**（HTTP API） | 统一多数据库接入层 |
| 可观测性 | **Langfuse** | Trace、Span、指标采集 |
| 配置管理 | **Pydantic Settings**（.env） | 环境变量驱动配置 |
| 容器化 | **Docker**（python:3.12-slim） | 部署 |

## 架构

```
用户 → FastAPI → SSE 路由 → claude-agent-sdk Agent → MCP 工具 → OneDBA API
                                                       ↓
                                                 NL2SQL 管道
                                            (生成 → 验证 → 修复)
```

## 关键设计决策

### 1. MCP Server 工具注册
工具通过 `create_sdk_mcp_server()` 注册为进程内 MCP Server，工具名带有 `mcp__onedba__` 前缀。这是 SDK 原生支持的自定义工具集成模式。

### 2. 单引擎策略
主引擎为 `claude-agent-sdk`（`_run_with_sdk()`）。SDK 必须可用——已移除 OpenAI ReAct 回退循环以简化维护。

### 3. 工具结果队列模式
SDK MCP 模式下工具在 SDK 内部执行，`ToolResultBlock` 不出现在流式消息中。因此 SDK 工具包装器将结果推入 `contextvars.ContextVar` 队列，由流处理器消费以合成 `tool_end` 事件，供 Langfuse 记录完整的工具输入输出。

### 4. NL2SQL 管道
SQL 生成是多步骤管道：生成候选 SQL → 根据 Schema 验证 → 无效则修复 → 应用语义规则。此管道独立于 Agent 工具层。

### 5. 进程内存会话
会话状态存储在进程内存 `dict`（`SESSION_STORE`）中，进程重启后丢失。设计上可轻松替换为 Redis 用于生产环境。

## 约定

### LLM 配置
- 默认模型：`deepseek-chat`
- 基础 URL：`https://api.deepseek.com/v1`
- 模型特有问题：DeepSeek 要求 assistant 消息中 tool_calls 附带 `signature` 字段；SDK 重放消息时可能丢失，作为软错误处理。

### 错误处理模式
- SDK bug：正常完成时返回 `is_error=True, subtype="success"` → 视为成功
- DeepSeek signature 错误 → 作为软错误处理，使用已收集的文本作为回退
- 使用 `asyncio.shield()` 保护 Langfuse flush 不被取消

### 工具设计
- 7 个工具：`list_databases`、`select_database`、`find_table`、`describe_table`、`query_database`、`execute_sql`
- 自然语言查询优先使用 `query_database`；`execute_sql` 仅在用户给出明确 SQL 时使用
- `find_table` 支持多关键词并集搜索和兜底全量列举模式

### API 模式
- `POST /api/chat` — SSE 流式（主接口）
- `POST /api/chat/sync` — 同步（测试/集成）
- `WS /api/ws/{session_id}` — WebSocket 双向通信
- `GET /api/sessions/{session_id}` — 会话状态查询
