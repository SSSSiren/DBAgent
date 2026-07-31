# DBAgent Admin API 使用说明

## 1. 启用 Admin API

在 `.env` 中添加：

```bash
# ========== Admin API（可选）==========
ADMIN_API_TOKEN=your-admin-token-here
```

- `ADMIN_API_TOKEN` 为空时，所有 `/api/admin/*` 端点返回 503，不暴露管理功能
- 启动日志会显示 `[DBAgent] Admin API: configured` 或 `disabled (token not set)`

重启服务后生效：

```bash
bash scripts/start_demo.sh
```

## 2. 认证方式

所有管理端点要求 `Authorization: Bearer <token>` 请求头：

```bash
curl -H "Authorization: Bearer your-admin-token-here" http://localhost:8000/api/admin/overview
```

| 错误场景 | HTTP 状态码 | 响应 |
|----------|------------|------|
| 未配置 `ADMIN_API_TOKEN` | 503 | `{"detail": "Admin API not configured"}` |
| 缺少 `Authorization` 头 | 401 | `{"detail": "Missing admin token"}` |
| token 不匹配 | 401 | `{"detail": "Invalid admin token"}` |

## 3. 端点总览

所有端点路径以 `/api/admin` 为前缀。

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/admin/overview` | 系统概览 |
| `POST` | `/api/admin/hdc-mappings` | 创建/更新 HDC 映射 |
| `GET` | `/api/admin/hdc-mappings` | 查询 HDC 映射 |
| `DELETE` | `/api/admin/hdc-mappings` | 删除 HDC 映射 |
| `GET` | `/api/admin/hdc/namespaces/{schema_id}/{db}` | 浏览可用 namespace |
| `POST` | `/api/admin/sql-memory/seed` | 批量灌入 SQL Memory |
| `GET` | `/api/admin/sql-memory/status` | SQL Memory 状态概览 |
| `GET` | `/api/admin/sql-memory/records` | SQL Memory 记录列表 |
| `DELETE` | `/api/admin/sql-memory/clean` | 清理 SQL Memory 记录 |
| `POST` | `/api/admin/sql-memory/re-embed` | 重建 embedding |
| `GET` | `/api/admin/sql-memory/stats` | SQL Memory 统计分析 |

## 4. 系统概览

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/admin/overview
```

响应示例：

```json
{
  "distinct_users": 5,
  "total_sessions": 23,
  "sql_memory_records": 142,
  "mapped_hdc_namespaces": [
    {"schema_id": 65938636, "database_name": "dw_onedba", "namespace_count": 2}
  ]
}
```

- `mapped_hdc_namespaces` 仅统计已通过 admin API 创建映射的 namespace，不枚举 OpenViking 全量目录
- 各项统计独立计算，一项失败不影响其他项

## 5. HDC Namespace 映射管理

### 5.1 浏览可用 namespace

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/admin/hdc/namespaces/65938636/dw_onedba
```

响应示例：

```json
["recall_complete", "recall_extra", "recall_overcomplete", "recall_test"]
```

- 只返回显式创建的 namespace 目录，不包含 `_tables`、`_relationships` 等保留目录
- 无 namespace 或数据库不存在时返回 `[]`

### 5.2 创建映射

```bash
curl -X POST http://localhost:8000/api/admin/hdc-mappings \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "schema_id": 65938636,
    "database_name": "dw_onedba",
    "hdc_namespace": "recall_extra"
  }'
```

响应（HTTP 201）：

```json
{
  "user_id": "alice",
  "schema_id": 65938636,
  "database_name": "dw_onedba",
  "hdc_namespace": "recall_extra",
  "updated_at": "2026-07-30T12:00:00"
}
```

- 已存在时更新（upsert 语义）
- 所有字段必填：`user_id`/`database_name`/`hdc_namespace` 为非空字符串，`schema_id` 为正整数

### 5.3 查询映射

```bash
# 查询全部
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/admin/hdc-mappings

# 按条件过滤
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/hdc-mappings?user_id=alice&schema_id=65938636"
```

### 5.4 删除映射

```bash
curl -X DELETE -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/hdc-mappings?user_id=alice&schema_id=65938636&database_name=dw_onedba"
```

响应：

```json
{"deleted": true}
```

- 映射不存在时返回 404

### 5.5 Namespace 自动解析

创建映射后，用户发起 chat 请求时无需手动指定 `hdc_namespace`：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我查一下工单类型的分布",
    "session_id": "demo",
    "schema_id": 65938636,
    "database_name": "dw_onedba"
  }'
```

**解析优先级**：

| 优先级 | 来源 | 行为 |
|--------|------|------|
| 1（最高） | 请求中显式传入 `hdc_namespace` | 直接使用 |
| 2 | Admin mapping 命中 | 自动使用映射的 namespace |
| 3 | 无映射且未传入 | `namespace=None`（默认行为） |

## 6. SQL Memory 管理

> 前置条件：`SQL_MEMORY_ENABLED=true` 且 `STORAGE_BACKEND=sqlite`，否则所有端点返回 503。

### 6.0 批量灌入记录

```bash
curl -X POST http://localhost:8000/api/admin/sql-memory/seed \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "records": [
      {
        "question": "查询 dataExport 类型的工单",
        "sql": "SELECT id, committer_name, status_desc FROM order_record WHERE order_type = '\''dataExport'\''",
        "table_names": ["order_record"],
        "database_name": "dw_onedba",
        "schema_id": 65938636,
        "execution_result": {"status": "success", "row_count": 50, "column_names": ["id","committer_name","status_desc"]}
      },
      {
        "question": "统计每种工单类型的数量",
        "sql": "SELECT order_type, COUNT(*) AS cnt FROM order_record GROUP BY order_type",
        "table_names": ["order_record"],
        "database_name": "dw_onedba",
        "schema_id": 65938636
      }
    ]
  }'
```

响应：

```json
{"user_id": "alice", "total": 2, "success": 2, "failed": 0}
```

- 每条 record 最小字段：`question`、`sql`
- 可选字段：`table_names`（默认 `[]`）、`database_name`（默认 `""`）、`schema_id`（默认 `0`）、`execution_result`（默认 `{}`）
- 自动为每条 `question` 生成 embedding 向量
- 跳过 `question` 或 `sql` 为空的记录，计入 `failed`

### 6.1 状态概览

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/admin/sql-memory/status
```

响应：

```json
{
  "total_records": 142,
  "embedding_coverage": 0.85,
  "status_distribution": {"success": 120, "error": 22},
  "earliest_record": "2026-07-01T08:00:00",
  "latest_record": "2026-07-30T17:00:00"
}
```

### 6.2 记录列表

```bash
# 分页查询
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/sql-memory/records?limit=20&offset=0"

# 按用户过滤
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/sql-memory/records?user_id=alice&limit=10"

# 按数据库过滤
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/sql-memory/records?database_name=dw_onedba"

# 组合过滤
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/sql-memory/records?user_id=alice&database_name=dw_onedba&status=success"
```

参数说明：

| 参数 | 默认值 | 约束 |
|------|--------|------|
| `user_id` | `""`（全部） | 可选 |
| `database_name` | `""`（全部） | 可选 |
| `status` | `""`（全部） | 可选 |
| `limit` | 100 | 上限 500 |
| `offset` | 0 | ≥ 0 |

每条记录包含 12 个字段，**不暴露** `embedding_json` 原始向量数据。

### 6.3 清理记录

```bash
# 按 TTL 清理（默认 90 天前）
curl -X DELETE http://localhost:8000/api/admin/sql-memory/clean \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# 按用户清理 30 天前的记录
curl -X DELETE http://localhost:8000/api/admin/sql-memory/clean \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "older_than_days": 30}'

# 按数据库清理
curl -X DELETE http://localhost:8000/api/admin/sql-memory/clean \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"database_name": "dw_onedba", "older_than_days": 60}'
```

**安全约束**：不传任何过滤参数时，只删除超过 TTL（默认 90 天）的记录。全空过滤不会清空全部数据。

### 6.4 重建 Embedding

```bash
# 全量重建
curl -X POST http://localhost:8000/api/admin/sql-memory/re-embed \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# 按用户重建
curl -X POST http://localhost:8000/api/admin/sql-memory/re-embed \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice"}'
```

### 6.5 统计分析

```bash
# 全局统计
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/admin/sql-memory/stats

# 按用户 + 数据库过滤
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/admin/sql-memory/stats?user_id=alice&database_name=dw_onedba"
```

响应包含：表分布、数据库分布、每日记录直方图、查询模式挖掘（仅单数据库场景且记录数足够时）。

## 7. 典型运维场景

### 场景 1：为新用户分配 namespace

```bash
# 1. 查看可用 namespace
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/admin/hdc/namespaces/65938636/dw_onedba

# 2. 创建映射
curl -X POST http://localhost:8000/api/admin/hdc-mappings \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"bob","schema_id":65938636,"database_name":"dw_onedba","hdc_namespace":"recall_extra"}'

# 3. 用户 bob 发起 chat 时自动使用 recall_extra namespace
```

### 场景 2：定期清理过期 SQL 记忆

```bash
# 清理 30 天前的所有记录
curl -X DELETE http://localhost:8000/api/admin/sql-memory/clean \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"older_than_days": 30}'
```

### 场景 3：切换用户的 namespace

```bash
# 更新映射（upsert 语义）
curl -X POST http://localhost:8000/api/admin/hdc-mappings \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","schema_id":65938636,"database_name":"dw_onedba","hdc_namespace":"recall_complete"}'
```

### 场景 4：查看系统健康状态

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/admin/overview
```

## 8. 注意事项

- **Admin token 建议**：使用随机字符串（如 `openssl rand -hex 32` 生成），不要使用弱密码
- **Namespace 优先级**：即使配置了 admin mapping，用户在请求中显式传入的 `hdc_namespace` 仍优先
- **Namespace 清理**：同一 session 内，上一轮解析的 namespace 不会泄漏到下一轮——如果新请求无映射且无显式传入，旧 namespace 会被清除
- **SQL Memory 安全**：`clean` 端点不会无条件清空全部数据，无过滤参数时只删除超过 TTL 的记录
- **Embedding 重建**：重建操作可能耗时较长（取决于记录数），建议在低峰期执行