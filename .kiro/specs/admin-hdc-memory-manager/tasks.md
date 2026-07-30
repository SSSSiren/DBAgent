# 实施计划

## Task Format Template

### Major + Sub-task structure
- [ ] {{MAJOR_NUMBER}}. {{MAJOR_TASK_SUMMARY}}
- [ ] {{MAJOR_NUMBER}}.{{SUB_NUMBER}} {{SUB_TASK_DESCRIPTION}}{{SUB_PARALLEL_MARK}}
  - {{DETAIL_ITEM_1}}
  - {{DETAIL_ITEM_2}}
  - {{OBSERVABLE_COMPLETION_ITEM}} *(至少一个详情项应说明可观察的完成条件。)*
  - _Requirements: {{REQUIREMENT_IDS}}_
  - _Boundary: {{COMPONENT_NAMES}}_
  - _Depends: {{TASK_IDS}}_

---

- [ ] 1. 基础配置与数据模型

  新增 admin 相关配置、Pydantic 模型，扩展 StorageBackend Protocol。

- [x] 1.1 新增 `admin_api_token` 配置项
  - 在 `Settings` 类中新增 `admin_api_token: str = ""`
  - 通过 `.env` 自动加载，与现有配置项风格一致
  - `get_settings()` 无需修改，已走 `@lru_cache` 单例
  - 启动日志中打印 `[DBAgent] Admin API: configured` 或 `[DBAgent] Admin API: disabled (token not set)`
  - _Requirements: 1.2_
  - _Boundary: app/config.py_

- [x] 1.2 新增 Admin API 请求/响应 Pydantic 模型
  - 创建 `HdcMappingCreate` — `user_id`, `schema_id`, `database_name`, `hdc_namespace`，全部必填
  - 创建 `HdcMappingResponse` — 含 `updated_at`
  - 创建 `SqlMemoryStatusResponse` — `total_records`, `embedding_coverage`, `status_distribution`, `earliest_record`, `latest_record`
  - 创建 `SqlMemoryRecordResponse` — 含 `table_names: list[str]`，不含 `embedding_json`
  - 创建 `SqlMemoryListResponse` — `records`, `total`, `limit`, `offset`
  - 创建 `SqlMemoryStatsResponse` — `table_distribution`, `database_distribution`, `daily_histogram`, `mined_patterns`
  - 创建 `HdcNamespaceSummary` — `schema_id`, `database_name`, `namespace_count`
  - 创建 `OverviewResponse` — `distinct_users`, `total_sessions`, `sql_memory_records`, `mapped_hdc_namespaces: list[HdcNamespaceSummary]`
  - 创建 `CleanRequest` — 可选 `user_id`, `database_name`, `older_than_days`（正整数）
  - 创建 `ReEmbedRequest` — 可选 `user_id`
  - 所有校验规则与 requirements（非空字符串、正整数、limit ≤ 500）一致
  - _Requirements: 2.4, 2.5, 5.3, 5.4, 5.6, 7.1_
  - _Boundary: app/api/schemas.py_

- [x] 1.3 扩展 StorageBackend Protocol：新增会话统计方法
  - 在 `StorageBackend` Protocol 中新增 `count_sessions() -> int` 和 `count_distinct_users() -> int` 方法声明
  - `InMemoryStore` 实现：遍历内存字典计算 session 数和去重用户数
  - `SqliteStore` 实现：SQL 聚合查询 `SELECT COUNT(*) FROM sessions` 和 `SELECT COUNT(DISTINCT user_id) FROM sessions`
  - 单元测试覆盖两个实现类的两个方法
  - _Requirements: 8.1, 8.2, 8.3_
  - _Boundary: app/memory/store.py_

- [ ] 2. AdminStoreBackend 实现与 StorageManager 集成

  创建 HDC namespace 映射持久化层。

- [x] 2.1 定义 AdminStoreBackend Protocol
  - 定义 Protocol 方法：`upsert_mapping`, `get_mapping`, `get_mappings`, `delete_mapping`, `initialize`, `close`
  - `upsert_mapping` 为 INSERT OR REPLACE 语义
  - `get_mapping` 按复合主键 `(user_id, schema_id, database_name)` 查询，返回 dict 或 None
  - `get_mappings` 支持可选过滤参数（空字符串表示不过滤），返回 `list[dict]`
  - `delete_mapping` 返回 bool 表示是否删除了行
  - 所有方法签名使用 Python 类型提示
  - _Requirements: 2.1, 2.2, 2.3, 2.6, 3.2_
  - _Boundary: app/memory/admin_store.py_

- [x] 2.2 实现 SqliteAdminStore
  - 在 `data/sessions.db` 中创建 `user_hdc_mappings` 表（`CREATE TABLE IF NOT EXISTS`）
  - 复合主键 `(user_id TEXT, schema_id INTEGER, database_name TEXT)`，`hdc_namespace TEXT NOT NULL`, `updated_at TEXT NOT NULL`
  - 使用 `aiosqlite` 异步操作，与现有 `SqliteStore` 模式一致
  - 实现 `initialize()` 时建表，`close()` 时关闭连接
  - 单元测试验证 CRUD 操作的正确性
  - _Requirements: 2.6_
  - _Boundary: app/memory/admin_store.py_

- [x] 2.3 实现 InMemoryAdminStore（仅测试用）
  - 用内存字典存储映射，主键为 `(user_id, schema_id, database_name)` 元组
  - 实现所有 Protocol 方法
  - 不用于生产环境
  - _Requirements: —（测试基础设施）_
  - _Boundary: app/memory/admin_store.py_

- [x] 2.4 扩展 StorageManager：新增 admin_store 参数
  - `StorageManager.__init__` 新增 `admin_store: AdminStoreBackend | None = None` keyword-only 参数
  - `initialize()` 和 `close()` 中处理 `admin_store` 生命周期（如果非 None）
  - `get_storage()` 工厂函数中始终创建 `SqliteAdminStore`（不跟随 `STORAGE_BACKEND` 切换，因为映射必须持久化）
  - 确保启动日志打印 admin_store 初始化状态
  - _Requirements: —_
  - _Boundary: app/memory/manager.py_

- [x] 2.5 更新 memory 包导出
  - 在 `app/memory/__init__.py` 中按现有风格导出 `AdminStoreBackend`、`SqliteAdminStore`
  - `InMemoryAdminStore` 仅在测试中直接从 `app.memory.admin_store` 导入，不作为运行时公共导出
  - _Requirements: —_
  - _Boundary: app/memory/__init__.py_

- [ ] 3. OpenVikingClient.list_directory 公开方法

  为 namespace 目录浏览提供目录列表能力。

- [x] 3.1 实现 list_directory 方法
  - 在 `OpenVikingClient` 中新增 `list_directory(uri: str) -> list[OpenVikingDirectoryEntry]` 公开方法
  - 内部调用 `_get_raw("/api/v1/fs/ls", uri)`
  - 归一化返回：每个条目包含 `name`（`entry["name"] or basename(entry["uri"])` 回退解析）、`uri`、`is_dir`
  - 原始 fs/ls 返回的 name 可能为空，必须用 uri 的 basename 回退
  - 解析失败时记录 WARN 日志并跳过该条目（不中断整个列表）
  - 单元测试覆盖：正常返回、name 为空回退、OpenViking 异常（通过 mock）
  - _Requirements: 4.1_
  - _Boundary: app/knowledge/openviking.py_

- [ ] 4. Admin Auth 依赖与路由挂载

  实现 Bearer token 认证依赖，创建 admin router 并在 main.py 挂载。

- [x] 4.1 实现 verify_admin_token 依赖
  - 从 `Authorization` header 提取 Bearer token
  - 与 `get_settings().admin_api_token` 比较
  - `admin_api_token` 为空 → 返回 503 `{"detail": "Admin API not configured"}`
  - token 缺失 → 401 `{"detail": "Missing admin token"}`
  - token 不匹配 → 401 `{"detail": "Invalid admin token"}`
  - 认证失败记录 WARN 日志，不记录 token 值
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Boundary: app/api/admin_routes.py_

- [ ] 4.2 创建 admin_router 并在 main.py 挂载
  - 创建 `admin_router = APIRouter(prefix="/admin", dependencies=[Depends(verify_admin_token)])`
  - 在 `main.py` 中 `from app.api.admin_routes import admin_router` + `app.include_router(admin_router, prefix="/api")`
  - 最终端点为 `/api/admin/*`
  - 验证：未配置 `ADMIN_API_TOKEN` 时，`GET /api/admin/overview` 返回 503；配置后缺少 Authorization header 返回 401 — 均不应返回 404
  - _Requirements: —（基础设施）_
  - _Boundary: app/api/admin_routes.py, app/main.py_

- [ ] 5. SqlMemoryBackend Protocol 扩展

  为 SQL Memory 管理 API 提供跨用户管理方法。

- [x] 5.1 新增管理方法声明
  - `list_records(user_id="", database_name="", status="", limit=100, offset=0) -> list[dict]`
  - `count_records(user_id="", database_name="", status="") -> int`
  - `delete_records(user_id="", database_name="", status="", older_than_days=None) -> int`
  - `get_status_summary(user_id="", database_name="", status="") -> dict`
  - `get_stats_summary(user_id="", database_name="", status="", min_records=20) -> dict`
  - 空参数表示匹配所有用户/数据库/状态
  - `list_records` 返回字段契约：`id`, `user_id`, `question`, `sql_text`, `sql_truncated`, `table_names: list[str]`, `database_name`, `schema_id`, `execution_status`, `created_at`, `has_embedding`，不含 `embedding_json`
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_
  - _Boundary: app/memory/sql_memory.py_

- [ ] 5.2 实现 InMemorySqlMemoryStore 新增方法
  - `list_records` — 内存列表过滤 + 分页
  - `count_records` — 内存列表过滤 + 计数
  - `delete_records` — 内存列表过滤 + 删除；**安全不变量**：全空过滤且 `older_than_days is None` 时必须拒绝返回 0
  - `get_status_summary` — 聚合计算总数、embedding 覆盖率、状态分布、时间范围
  - `get_stats_summary` — 聚合计算表分布、数据库分布、每日直方图；`table_names` 为 JSON 文本时在 Python 中解析，解析失败跳过表分布但不影响其他统计
  - `mined_patterns` 仅在提供单一 `database_name` 且过滤后记录数 >= min_records 时返回，否则为 None
  - _Requirements: 6.4_
  - _Boundary: app/memory/sql_memory.py_

- [ ] 5.3 实现 SqliteSqlMemoryStore 新增方法
  - `list_records` — SQL 查询 `sql_memories` 表，支持可选 WHERE 过滤 + LIMIT/OFFSET 分页
  - `count_records` — SQL COUNT 查询，支持可选 WHERE 过滤
  - `delete_records` — SQL DELETE 查询，支持可选 WHERE 过滤；**安全不变量同上**：全空过滤且 `older_than_days is None` 时必须拒绝返回 0
  - `get_status_summary` — SQL 聚合查询：COUNT、SUM(CASE WHEN embedding_json IS NOT NULL)、status 分组、MIN/MAX created_at
  - `get_stats_summary` — 不依赖 SQLite JSON1 扩展：从 SQL 查询出匹配记录后，在 Python 中解析 `table_names` JSON 文本并聚合表分布；JSON 解析失败的记录跳过表分布统计，但仍计入总记录数、数据库分布和每日统计
  - `mined_patterns` 仅在提供单一 `database_name` 且过滤后记录数 >= min_records 时返回；未提供 `database_name` 或记录不足时返回 None
  - 单元测试验证所有新方法的正确性和安全不变量
  - _Requirements: 6.4_
  - _Boundary: app/memory/sql_memory.py_

- [ ] 6. (P) HDC Mappings 管理端点

  实现 HDC namespace 映射的 CRUD API 端点。

- [ ] 6.1 实现 POST /api/admin/hdc-mappings
  - 接收 `HdcMappingCreate` 请求体，创建或更新映射（upsert 语义）
  - 通过 `get_storage().admin_store.upsert_mapping()` 持久化
  - 返回 HTTP 201 + `HdcMappingResponse`（含 `updated_at`）
  - admin_store 为 None 时返回 503
  - _Requirements: 2.1, 2.4, 2.5_
  - _Boundary: app/api/admin_routes.py_

- [ ] 6.2 实现 GET /api/admin/hdc-mappings
  - 接收可选查询参数 `user_id`, `schema_id`, `database_name`
  - 通过 `get_storage().admin_store.get_mappings()` 查询
  - 无过滤参数时返回全部映射
  - 返回 `list[HdcMappingResponse]`
  - _Requirements: 2.2_
  - _Boundary: app/api/admin_routes.py_

- [ ] 6.3 实现 DELETE /api/admin/hdc-mappings
  - 从查询参数 `user_id`, `schema_id`, `database_name` 获取主键
  - 通过 `get_storage().admin_store.delete_mapping()` 删除
  - 存在时返回 HTTP 200 `{"deleted": true}`，不存在时返回 404 `{"detail": "Mapping not found"}`
  - _Requirements: 2.3_
  - _Boundary: app/api/admin_routes.py_

- [ ] 7. (P) HDC Namespace 目录浏览端点

  实现 `/api/admin/hdc/namespaces/{schema_id}/{database_name}` 端点。

- [ ] 7.1 实现 GET /api/admin/hdc/namespaces/{schema_id}/{database_name}
  - 使用 `_HDC_ROOT`, `storage_key`, `_db_uri` 等 helper 构建数据库 HDC 根路径 URI
  - 通过 OpenViking `list_directory()` 获取子目录列表
  - 仅返回 `is_dir=True` 的条目
  - 排除保留目录 `_tables` 和 `_relationships`
  - 不返回默认 namespace（root 本身不算）
  - 数据库根路径不存在 → HTTP 200 + `[]`
  - 无 namespace 目录 → HTTP 200 + `[]`
  - OpenViking 不可达或错误 → HTTP 503 + upstream 错误信息
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: app/api/admin_routes.py_

- [ ] 8. (P) SQL Memory 管理端点

  实现 SQL Memory 的 status/list/clean/re-embed/stats HTTP 端点。

- [ ] 8.1 实现全局前置条件检查
  - 所有 `/api/admin/sql-memory/*` 端点共用前置检查：`sql_memory_enabled` 为 false 或 `sql_memory_store` 为 None → 503 `{"detail": "SQL Memory not enabled"}`
  - _Requirements: 5.0_
  - _Boundary: app/api/admin_routes.py_

- [ ] 8.2 实现 GET /api/admin/sql-memory/status
  - 通过 `sql_memory_store.get_status_summary()` 获取概览数据
  - 返回 `SqlMemoryStatusResponse`
  - 不使用分页 `list_records()` 拼接统计
  - _Requirements: 5.1_
  - _Boundary: app/api/admin_routes.py_

- [ ] 8.3 实现 GET /api/admin/sql-memory/records
  - 接收可选查询参数 `user_id`, `database_name`, `status`, `limit`（默认 100，上限 500）, `offset`（默认 0，≥ 0）
  - 通过 `sql_memory_store.list_records()` 查询
  - 返回 `SqlMemoryListResponse`，每条记录含 12 个字段，不含 `embedding_json`
  - _Requirements: 5.2, 5.3, 5.4_
  - _Boundary: app/api/admin_routes.py_

- [ ] 8.4 实现 DELETE /api/admin/sql-memory/clean
  - 接收可选请求体 `CleanRequest: {user_id, database_name, older_than_days}`
  - 通过 `sql_memory_store.delete_records()` 执行删除
  - **安全不变量**：无任何过滤参数时，route 层必须传入 `older_than_days=settings.sql_memory_ttl_days`
  - `older_than_days` 必须为正整数，无效时返回 422
  - 返回 `{"deleted_count": N}`
  - _Requirements: 5.5, 5.6, 5.7_
  - _Boundary: app/api/admin_routes.py_

- [ ] 8.5 实现 POST /api/admin/sql-memory/re-embed
  - 接收可选请求体 `{"user_id": "..."}`
  - 请求体为空或未提供 `user_id` 时，调用 `re_embed_all(embed_fn=embed_text, user_id="")` 表示全量重建
  - 提供 `user_id` 时仅重建该用户记录
  - 返回 `{"updated_count": N}`
  - _Requirements: 5.8_
  - _Boundary: app/api/admin_routes.py_

- [ ] 8.6 实现 GET /api/admin/sql-memory/stats
  - 接收可选查询参数 `user_id`, `database_name`, `status`
  - 通过 `sql_memory_store.get_stats_summary()` 获取统计数据
  - `mined_patterns` 仅在提供单一 `database_name` 且过滤后记录数 >= min_records 时返回；未提供 `database_name` 或记录不足时返回 None
  - 无过滤参数时计算全局统计
  - 返回 `SqlMemoryStatsResponse`
  - _Requirements: 5.9, 5.10_
  - _Boundary: app/api/admin_routes.py_

- [ ] 9. (P) 系统概览端点

  实现 `/api/admin/overview` 端点，聚合多项系统级统计。

- [ ] 9.1 实现 GET /api/admin/overview
  - 通过 `StorageBackend.count_sessions()` 和 `count_distinct_users()` 获取会话统计
  - 通过 `SqlMemoryBackend.count_records()` 获取 SQL 记忆记录数
  - HDC namespace 统计为 best-effort：仅统计 admin mappings 中引用过的 namespace，不枚举 OpenViking 全量目录
  - 返回字段名为 `mapped_hdc_namespaces`
  - 各项统计独立计算：一个失败不影响其他返回 — 失败的统计返回 0 或空列表
  - 返回 `OverviewResponse`
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - _Boundary: app/api/admin_routes.py_

- [ ] 10. resolve_hdc_namespace 实现与路由集成

  实现 namespace 自动解析函数，集成到 chat 和 chat/sync 流程。

- [ ] 10.1 实现 resolve_hdc_namespace 函数
  - 函数签名：`async def resolve_hdc_namespace(user_id, schema_id, database_name, explicit_namespace) -> str | None`
  - 优先级：显式传入 `explicit_namespace` > admin mapping 查询 > None
  - 显式传入时有值直接返回，不查映射表
  - `schema_id` 或 `database_name` 缺失时：有显式传入则直接返回，否则返回 None
  - 通过 `get_storage().admin_store.get_mapping()` 查询映射
  - 单元测试覆盖：显式传入胜出、映射命中、映射不存在、字段缺失四种场景
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_
  - _Boundary: app/api/routes.py_

- [ ] 10.2 实现 _apply_hdc_namespace_resolution helper
  - 创建 `_apply_hdc_namespace_resolution(session_state, request, user_id)` helper 函数
  - 内部调用 `resolve_hdc_namespace()` 并处理 `session_state["_hdc_namespace"]` 的写入或清理
  - **关键清理策略**：如果 `resolve_hdc_namespace()` 返回 `None`，必须执行 `session_state.pop("_hdc_namespace", None)`，确保不会复用上一轮持久化的旧 namespace 值；如果返回非 None，写入 `session_state["_hdc_namespace"]`
  - `/api/chat` 和 `/api/chat/sync` 都调用该 helper，避免重复逻辑
  - 验证：发送 chat 请求（有 mapping 无显式传入）→ 检查日志 `[HDC]` 是否使用了 mapping namespace；再发送同一 session（无 mapping 无显式传入）→ 检查是否清除旧值
  - _Requirements: 3.5_
  - _Boundary: app/api/routes.py_

- [ ] 11. 集成测试与验证

  编写测试覆盖关键场景，确保所有端点正确工作。

- [ ] 11.1 编写 Admin Store 单元测试
  - `SqliteAdminStore` 的 CRUD 操作：upsert、get、get_mappings（含过滤）、delete、not found
  - 使用 `:memory:` SQLite 数据库隔离测试
  - _Requirements: 2.1, 2.2, 2.3, 2.6_
  - _Boundary: tests/_

- [ ] 11.2 编写 Auth Dependency 单元测试
  - token 正确、token 错误、无 header、未配置四种场景
  - 每种场景验证 HTTP 状态码和响应 detail
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Boundary: tests/_

- [ ] 11.3 编写 resolve_hdc_namespace 单元测试
  - 显式传入胜出、映射命中、映射不存在、字段缺失时的行为
  - 使用 `InMemoryAdminStore` 进行测试
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - _Boundary: tests/_

- [ ] 11.4 编写 SQL Memory 管理方法单元测试
  - 同时覆盖 `InMemorySqlMemoryStore` 和 `SqliteSqlMemoryStore`（`:memory:` 模式）
  - `list_records` 分页正确性、`count_records` 组合过滤（status+ database+user）、`delete_records` 安全不变量验证（全空过滤 + no older_than_days → 0）
  - SQLite 专有测试：`table_names` JSON 文本解析（正常解析、解析失败跳过表分布）、status/database/user 组合过滤的 SQL WHERE 正确性
  - `get_status_summary` 和 `get_stats_summary` 结果结构与字段完整性
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - _Boundary: tests/_

- [ ] 11.5 编写 StorageBackend 统计方法单元测试
  - `count_sessions` 和 `count_distinct_users` 在 InMemory/Sqlite 两种实现上的正确性
  - _Requirements: 8.1, 8.2, 8.3_
  - _Boundary: tests/_

- [ ] 11.6 编写 E2E 集成测试
  - 管理员创建映射 → 用户发起 chat 请求 → 验证 namespace 自动解析到 session_state
  - 同一 session 再次发起 chat（无 mapping）→ 验证旧 namespace 被清除
  - 管理员清理 SQL Memory → 验证记录被删除
  - 管理员重建 embedding → 验证 has_embedding 为 True
  - _Requirements: —（跨需求集成验证）_
  - _Boundary: tests/_
