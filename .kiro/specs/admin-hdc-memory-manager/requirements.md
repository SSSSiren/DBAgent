# 需求文档

## 引言

DBAgent 运维管理员需要一个轻量 HTTP API 模块来管理 HDC namespace 映射和 SQL Memory 记录。当前 namespace 由客户端自由传入，管理员无法控制分配；SQL Memory 只能通过 CLI 工具在服务器上操作。

本模块新增 `/api/admin/*` 路由组，通过 Bearer token 认证，提供 HDC namespace 映射管理、SQL Memory 远程管理、namespace 目录浏览和系统概览功能。管理员通过 API 预配置 `(user_id, schema_id, database_name)` → `hdc_namespace` 映射后，chat 请求流程自动解析 namespace，用户无需手动指定。

## 边界上下文

- **范围内**: HDC namespace 映射 CRUD（主键含 `schema_id`）、SQL Memory 管理 HTTP API、HDC namespace 目录浏览、系统概览统计、Bearer token 认证（环境变量单 token）、chat 请求流程中的自动 namespace 解析
- **范围外**: 用户注册/登录系统、Web 管理面板 UI、细粒度 RBAC、运行时配置热更新、审计日志、多 token 管理（`admin_tokens` 表）
- **相邻期望**: 
  - `SqlMemoryBackend` Protocol 新增 `list_records`/`count_records`/`delete_records` 方法，两个实现类均需实现
  - `StorageBackend` Protocol 新增 `count_sessions()`/`count_distinct_users()` 方法，两个实现类均需实现；`/api/admin/overview` 通过 Protocol 方法获取会话/用户统计，不直接访问 SQLite
  - HDC namespace 目录浏览复用 `app.datavault.uploader._HDC_ROOT` 及相关 helper（`_db_uri`、`storage_key`），不硬编码路径
  - chat 和 chat/sync 共用同一个 `resolve_hdc_namespace()` 函数；WebSocket 当前不支持 mapping
  - HDC namespace 映射表存储于现有 SQLite 文件（`data/sessions.db`）

## 需求

### 需求 1：Admin API 认证

**目标：** 作为管理员，我希望管理端点受 Bearer token 保护，确保只有授权人员可以管理 HDC 映射和 SQL Memory。

#### 验收标准
1. DBAgent 应对所有 `/api/admin/*` 端点要求提供 `Authorization: Bearer <token>` 请求头。
2. If `ADMIN_API_TOKEN` 未配置（空字符串），则 DBAgent 应对所有 `/api/admin/*` 请求返回 HTTP 503，响应体包含 "Admin API not configured"。
3. If 请求中的 Bearer token 与 `ADMIN_API_TOKEN` 不匹配，则 DBAgent 应返回 HTTP 401，响应体包含 "Invalid admin token"。
4. If 请求完全缺少 `Authorization` 请求头，则 DBAgent 应返回 HTTP 401，响应体包含 "Missing admin token"。

### 需求 2：HDC Namespace 映射管理

**目标：** 作为管理员，我希望创建、查看和删除 `(user_id, schema_id, database_name)` 的 HDC namespace 映射，确保 namespace 分配由中心统一管控。

#### 验收标准
1. When 管理员向 `/api/admin/hdc-mappings` 发送 POST 请求，请求体为 `{"user_id": "...", "schema_id": N, "database_name": "...", "hdc_namespace": "..."}`, DBAgent 应创建或更新映射并返回 HTTP 201，响应体包含创建/更新后的映射。
2. When 管理员向 `/api/admin/hdc-mappings` 发送 GET 请求，可附带查询参数 `user_id`、`schema_id` 和 `database_name`, DBAgent 应返回匹配的映射列表。如果未提供任何过滤条件，应返回全部映射。
3. When 管理员向 `/api/admin/hdc-mappings` 发送 DELETE 请求，附带查询参数 `user_id`、`schema_id` 和 `database_name`, DBAgent 应删除该映射并返回 HTTP 200。如果映射不存在，DBAgent 应返回 HTTP 404。
4. If POST 请求体缺少任一必填字段（`user_id`、`schema_id`、`database_name`、`hdc_namespace`），则 DBAgent 应返回 HTTP 422，附带字段级校验错误。
5. `user_id`、`database_name` 和 `hdc_namespace` 应为非空字符串。`schema_id` 应为正整数。DBAgent 应拒绝无效值并返回 HTTP 422。
6. DBAgent 应将所有映射持久化到 `user_hdc_mappings` 表，复合主键为 `(user_id, schema_id, database_name)`。

### 需求 3：自动 HDC Namespace 解析

**目标：** 作为最终用户，我希望系统根据管理员配置的映射自动选择正确的 HDC namespace，无需手动指定。

#### 验收标准
1. When chat 请求显式提供 `hdc_namespace`, DBAgent 应直接使用该值，无论是否存在 admin mapping — 现有行为保持不变。
2. When chat 请求未提供 `hdc_namespace` 且存在与 `(user_id, schema_id, database_name)` 匹配的 admin mapping, DBAgent 应自动使用映射的 namespace 进行 HDC 检索。
3. When chat 请求未提供 `hdc_namespace` 且不存在 admin mapping, DBAgent 应以 `namespace=None` 继续执行 — 现有行为保持不变。
4. namespace 解析优先级应为：显式 `request.hdc_namespace` > admin mapping > `None`。
5. namespace 解析逻辑应同时适用于 `POST /api/chat` 和 `POST /api/chat/sync` 两个端点，使用同一套解析逻辑。
6. namespace 解析应在 chat 请求字段合并到 `session_state` 之后执行，并从 `session_state.selected_database.schemaId` 和 `.schemaName` 读取 `schema_id` 和 `database_name`。
7. If `session_state.selected_database` 中缺少 `schema_id` 或 `database_name`，则 namespace 解析应跳过 admin mapping 查询并返回 `None`，除非显式提供了 `hdc_namespace`（此时应直接使用该值）。

### 需求 4：HDC Namespace 目录浏览

**目标：** 作为管理员，我希望列出某数据库下所有可用的 HDC namespace，以便在创建映射时了解有哪些 namespace 可用。

#### 验收标准
1. When 管理员向 `/api/admin/hdc/namespaces/{schema_id}/{database_name}` 发送 GET 请求, DBAgent 应列出数据库 HDC 根路径 `_db_uri(storage_key(schema_id, database_name))` 下的子目录。
2. DBAgent 应从返回的 namespace 列表中排除保留的 HDC 目录，如 `_tables` 和 `_relationships`。
3. DBAgent 应仅返回显式创建的 namespace 目录。默认 namespace（`namespace=None`）不应作为 namespace 名称返回。
4. If 数据库根路径存在但没有显式 namespace 目录，则 DBAgent 应返回 HTTP 200 及空列表。
5. If 数据库根路径不存在，则 DBAgent 应返回 HTTP 200 及空列表。
6. If OpenViking 不可达或返回上游错误，则 DBAgent 应返回 HTTP 503，附带上游错误信息。

### 需求 5：SQL Memory 管理 API

**目标：** 作为管理员，我希望通过 HTTP API 端点管理 SQL 记忆记录，无需登录服务器即可执行维护操作。

#### 验收标准

**5.0 — 全局前置条件**
0. If `SQL_MEMORY_ENABLED` 为 false 或 `sql_memory_store` 未初始化，则所有 `/api/admin/sql-memory/*` 端点应返回 HTTP 503，响应体包含 "SQL Memory not enabled"。

**5.1 — 状态概览**
1. When 管理员向 `/api/admin/sql-memory/status` 发送 GET 请求, DBAgent 应返回总记录数、embedding 覆盖率、状态分布、最早和最晚记录时间戳。

**5.2 — 记录列表**
2. When 管理员向 `/api/admin/sql-memory/records` 发送 GET 请求，可附带查询参数 `user_id`、`database_name`、`status`、`limit` 和 `offset`, DBAgent 应返回分页的匹配记录。
3. `limit` 默认值为 100，上限为 500。`offset` 默认值为 0，且必须为非负数。
4. 每条返回的 SQL 记忆记录应包含：`id`、`user_id`、`question`、`sql_text`、`sql_truncated`、`table_names`、`database_name`、`schema_id`、`execution_status`、`created_at` 和 `has_embedding`。`embedding_json` 字段不应暴露。

**5.3 — 记录清理**
5. When 管理员向 `/api/admin/sql-memory/clean` 发送 DELETE 请求，可附带请求体 `{"user_id": "...", "database_name": "...", "older_than_days": N}`, DBAgent 应删除匹配的记录并返回删除的记录数。
6. `older_than_days` 在提供时必须为正整数。如果值无效，DBAgent 应返回 HTTP 422。
7. If 未提供任何过滤参数，则 DBAgent 应删除所有超过配置 TTL（`SQL_MEMORY_TTL_DAYS`）的记录。

**5.4 — Embedding 重建**
8. When 管理员向 `/api/admin/sql-memory/re-embed` 发送 POST 请求，可附带请求体 `{"user_id": "..."}`, DBAgent 应为匹配的记录重建 embedding 并返回更新的记录数。

**5.5 — 统计分析**
9. When 管理员向 `/api/admin/sql-memory/stats` 发送 GET 请求，可附带查询参数 `user_id`、`database_name` 和 `status`, DBAgent 应返回表分布、数据库分布、每日记录直方图，以及（在记录数充足时）挖掘出的查询模式，统计范围限定在提供的过滤条件内。
10. If 未提供任何过滤条件，则 DBAgent 应计算跨所有用户的全局 SQL 记忆统计数据。

### 需求 6：SqlMemoryBackend Protocol 扩展

**目标：** 作为开发者，我希望 `SqlMemoryBackend` Protocol 包含跨用户管理方法，确保 admin API 端点通过与其他存储层相同的抽象进行操作。

#### 验收标准
1. `SqlMemoryBackend` Protocol 应定义 `list_records(user_id="", database_name="", status="", limit=100, offset=0) -> list[dict]`，允许空参数以支持跨用户查询。
2. `SqlMemoryBackend` Protocol 应定义 `count_records(user_id="", database_name="", status="") -> int`，允许空参数以支持跨用户计数。
3. `SqlMemoryBackend` Protocol 应定义 `delete_records(user_id="", database_name="", status="", older_than_days=None) -> int`，允许空 `user_id`/`database_name` 以支持跨用户删除。
4. `InMemorySqlMemoryStore` 和 `SqliteSqlMemoryStore` 均需实现新增的 Protocol 方法。
5. `SqlMemoryBackend` Protocol 应定义 `get_status_summary(user_id="", database_name="", status="") -> dict`，提供 status API 所需的聚合概览数据。
6. `SqlMemoryBackend` Protocol 应定义 `get_stats_summary(user_id="", database_name="", status="", min_records=20) -> dict`，提供 stats API 所需的分布和模式数据。

### 需求 7：系统概览

**目标：** 作为管理员，我希望通过一个端点获取系统级统计信息，快速了解 DBAgent 的健康状况和使用情况。

#### 验收标准
1. When 管理员向 `/api/admin/overview` 发送 GET 请求, DBAgent 应返回：活跃会话的不重复用户数、会话总数、SQL 记忆记录总数、每个数据库的 HDC namespace 数量。
2. 每项统计应独立计算；某一项计算失败（如 HDC 不可用）不应阻止其他项正常返回。
3. DBAgent 应通过 `StorageBackend` Protocol 方法（`count_sessions()`、`count_distinct_users()`）计算会话数和用户数，不得直接访问 SQLite 内部实现。
4. DBAgent 应通过 `SqlMemoryBackend.count_records()` Protocol 方法计算 SQL 记忆记录数。

### 需求 8：StorageBackend Protocol 扩展（Admin 统计）

**目标：** 作为开发者，我希望 `StorageBackend` Protocol 暴露会话级统计信息，使 admin 概览端点能够在不耦合特定存储实现的情况下计算用户数和会话数。

#### 验收标准
1. `StorageBackend` Protocol 应定义 `count_sessions() -> int`，返回跨所有用户的会话总数。
2. `StorageBackend` Protocol 应定义 `count_distinct_users() -> int`，返回至少拥有一个会话的不重复用户数。
3. `InMemoryStore` 和 `SqliteStore` 均需实现这些方法。