# DBAgent 用户端 API 使用说明

本文档覆盖非 Admin 的用户端接口，包括对话、会话、WebSocket、schema 列表和 HDC 管理接口。Admin API 见 `docs/admin-api-guide.md`。

默认服务地址：

```bash
export BASE_URL=http://localhost:8000
```

## 1. 健康检查和页面入口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 服务健康检查 |
| `GET` | `/` | 内置前端页面 |
| `GET` | `/docs` | FastAPI OpenAPI 页面 |
| `GET` | `/static/admin.html` | Admin 管理页面 |

健康检查：

```bash
curl "$BASE_URL/health"
```

响应：

```json
{"status":"ok","engine":"openai-fallback"}
```

## 2. 对话接口

### 2.1 SSE 流式对话

`POST /api/chat` 是推荐的用户对话入口，返回 `text/event-stream`。

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `message` | string | 是 | 无 | 用户问题 |
| `session_id` | string | 否 | `default` | 会话 ID |
| `user_id` | string | 否 | `default` | 用户 ID，用于会话和记忆隔离 |
| `schema_id` | integer | 否 | `null` | OneDBA schema ID |
| `database_name` | string | 否 | `null` | 数据库名称 |
| `hdc_namespace` | string | 否 | `null` | HDC namespace，显式传入时优先级最高 |

示例：

```bash
curl -N -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "session_id": "session-main",
    "message": "统计每种工单状态的数量，按数量降序排列",
    "schema_id": 65938636,
    "database_name": "dw_onedba"
  }'
```

SSE 事件类型：

| 事件 | 说明 |
|---|---|
| `step` | Agent 工具调用进度 |
| `sql` | 当前生成或提取的 SQL |
| `final` | 最终回复、会话 ID、工具调用记录等 |
| `error` | 执行异常 |

### 2.2 同步 JSON 对话

`POST /api/chat/sync` 等待 Agent 完整执行后返回 JSON，适合测试和简单集成。

```bash
curl -X POST "$BASE_URL/api/chat/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "session_id": "session-sync",
    "message": "查询 dataExport 类型的工单",
    "schema_id": 65938636,
    "database_name": "dw_onedba"
  }'
```

响应：

```json
{
  "response": "查询结果摘要...",
  "session_id": "session-sync",
  "needs_confirmation": false
}
```

### 2.3 取消正在执行的对话

```bash
curl -X POST "$BASE_URL/api/chat/session-main/cancel"
```

响应：

```json
{
  "cancelled": true,
  "session_id": "session-main",
  "message": "取消信号已发送"
}
```

当会话没有活跃任务时，HTTP 仍返回 200，`cancelled=false`。

## 3. WebSocket 对话

路径：

```text
ws://localhost:8000/api/ws/{session_id}?user_id=alice
```

客户端发送纯文本问题，服务端返回 JSON 事件：

```json
{"type":"step","status":"running","tool":"find_table"}
```

WebSocket 断开时，服务端会尝试取消对应 session 的活跃 Agent 任务。

## 4. 会话接口

所有会话读写接口通过 `user_id` 做用户隔离。除创建接口外，`user_id` 通过 query 参数传入。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/sessions` | 创建会话 |
| `GET` | `/api/sessions?user_id={user}` | 列出用户会话 |
| `GET` | `/api/sessions/{session_id}?user_id={user}` | 获取会话状态 |
| `PUT` | `/api/sessions/{session_id}?user_id={user}` | 更新会话标题 |
| `DELETE` | `/api/sessions/{session_id}?user_id={user}` | 删除会话 |

创建会话：

```bash
curl -X POST "$BASE_URL/api/sessions" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice"}'
```

列出会话：

```bash
curl "$BASE_URL/api/sessions?user_id=alice"
```

获取会话：

```bash
curl "$BASE_URL/api/sessions/session-main?user_id=alice"
```

更新会话标题：

```bash
curl -X PUT "$BASE_URL/api/sessions/session-main?user_id=alice" \
  -H "Content-Type: application/json" \
  -d '{"summary":"工单分析会话"}'
```

删除会话：

```bash
curl -X DELETE "$BASE_URL/api/sessions/session-main?user_id=alice"
```

## 5. Schema 列表

```bash
curl "$BASE_URL/api/schemas"
```

返回可用的 `(schema_id, database_name)` 列表。该接口从 OpenViking HDC 文件系统读取；当 `KB_ENABLED=false` 或 OpenViking 不可用时返回空数组。

响应示例：

```json
[
  {"schema_id": 65938636, "database_name": "dw_onedba"}
]
```

## 6. HDC 用户端管理接口

HDC 接口默认不需要 Admin token，但要求 `HDC_ENABLED=true`。默认 `.env.example` 中 `HDC_ENABLED=false`，未启用时接口返回 503。

### 6.1 生成 HDC

```bash
curl -X POST "$BASE_URL/api/hdc/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_id": 65938636,
    "database_name": "dw_onedba",
    "namespace": "recall_extra",
    "tables": ["order_record", "order_audit_record"]
  }'
```

响应：

```json
{"task_id":"0198...","status":"started"}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_id` | integer | 是 | OneDBA schema ID |
| `database_name` | string | 是 | 数据库名称 |
| `namespace` | string | 否 | HDC namespace 变体 |
| `tables` | array/string | 否 | 表白名单；为空则生成全库 |

### 6.2 增量更新 HDC

```bash
curl -X POST "$BASE_URL/api/hdc/update" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_id": 65938636,
    "database_name": "dw_onedba",
    "namespace": "recall_extra",
    "dry_run": true,
    "rebuild": false
  }'
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_id` | integer | 是 | OneDBA schema ID |
| `database_name` | string | 是 | 数据库名称 |
| `namespace` | string | 否 | HDC namespace |
| `tables` | array/string | 否 | 限定更新表 |
| `dry_run` | boolean | 否 | 只检查变化，不写入 |
| `rebuild` | boolean | 否 | 强制重建关系和数据库摘要 |

### 6.3 查询 HDC 状态

```bash
curl "$BASE_URL/api/hdc/status/dw_onedba?schema_id=65938636&namespace=recall_extra"
```

响应：

```json
{
  "database_name": "dw_onedba",
  "schema_id": 65938636,
  "namespace": "recall_extra",
  "exists": true,
  "namespace_count": 1,
  "total_tables": 12,
  "namespaces": [{"name": "recall_extra", "table_count": 12}]
}
```

### 6.4 查询任务状态

```bash
curl "$BASE_URL/api/hdc/tasks/{task_id}"
```

响应包含任务参数、`status`、`progress` 和 `result`。任务状态通常为 `started`、`running`、`completed` 或 `failed`。

### 6.5 删除 HDC

```bash
curl -X DELETE "$BASE_URL/api/hdc/dw_onedba?schema_id=65938636&namespace=recall_extra"
```

不传 `namespace` 时删除该数据库的全部 HDC namespace；不传 `schema_id` 时会遍历所有 schema 中同名数据库，生产操作建议始终传入 `schema_id`。

## 7. HDC Namespace 解析优先级

用户对话请求中，HDC namespace 的解析顺序为：

| 优先级 | 来源 |
|---:|---|
| 1 | 请求体显式传入 `hdc_namespace` |
| 2 | Admin API 中配置的用户、schema、database 映射 |
| 3 | 无 namespace，按默认 HDC 行为处理 |

如果新请求没有显式 namespace 且没有命中 Admin mapping，服务会清理 session 中上一轮遗留的 namespace，避免跨轮污染。

## 8. 常见状态码

| 状态码 | 场景 |
|---:|---|
| 200 | 请求成功 |
| 400 | 缺少必要参数或 `user_id` 为空 |
| 404 | 会话、HDC 任务或待删除资源不存在 |
| 503 | HDC、SQL Memory、Admin API 未启用或依赖不可用 |

## 9. 集成建议

- 客户端优先使用 `POST /api/chat`，需要完整响应时使用 `POST /api/chat/sync`。
- 每个终端用户传稳定的 `user_id`，每个对话窗口传独立 `session_id`。
- 有确定数据库上下文时传 `schema_id` 和 `database_name`，可以提升 HDC 和 SQL Memory 检索准确度。
- HDC 生成、更新、删除属于高成本或破坏性操作，生产环境建议通过网关或网络策略限制调用方。
