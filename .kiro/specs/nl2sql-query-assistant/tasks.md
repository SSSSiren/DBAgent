# 实现计划

> **已有功能说明**：需求 3（数据库发现与选择）、需求 4（自然语言转 SQL 查询）、需求 5（查询结果展示）已由现有代码完整实现（`app/tools/`、`app/nl2sql/`、`app/static/` 中的 SSE 流式渲染）。本次实现聚焦于存储层持久化、多用户隔离和会话管理。

## 任务

- [ ] 1. 基础设施：依赖与存储后端
- [x] 1.1 添加依赖包和配置项
  - 在 `requirements.txt` 中添加 `aiosqlite` 和 `uuid6`
  - 在 `Settings` 类中添加 `storage_backend`（默认 `"memory"`）、`redis_url`、`storage_file_path`（默认 `"data/sessions.db"`）配置项
  - 确认 `docker-compose.yml` 中 `./data:/app/data` 卷挂载已存在，无需修改
  - 重启服务后 `Settings.storage_backend` 可读取且默认值为 `"memory"`
  - _Requirements: 2.5_

- [x] 1.2 实现 StorageBackend 协议和 InMemoryStore
  - 定义 `StorageBackend` 协议，包含 `create_session`、`get_session`、`save_session`、`delete_session`、`list_sessions`、`initialize`、`close` 七个异步方法
  - 所有方法接受 `user_id` 作为第一个参数，实现用户级命名空间隔离
  - `create_session(user_id, session_id, state)` 创建新会话并写入初始状态
  - `get_session(user_id, session_id)` 返回 `Optional[dict]`，不存在时返回 `None`
  - 将现有 `SESSION_STORE` dict 封装为 `InMemoryStore` 类，实现 `StorageBackend` 协议
  - 提供 `get_store()` 工厂函数，根据 `Settings.storage_backend` 返回对应实现
  - `InMemoryStore` 的 `list_sessions(user_id)` 返回属于该用户的所有会话摘要列表
  - _Requirements: 1.2, 1.3_
  - _Boundary: StorageBackend, InMemoryStore_

- [x] 1.3 实现 SqliteStore 持久化存储
  - 实现 `SqliteStore` 类，遵循 `StorageBackend` 协议
  - `initialize()` 方法创建 `sessions` 表（复合主键 `user_id, session_id`，`state_json` TEXT 列，`summary` TEXT 列，`created_at` 和 `last_active_at` 时间戳列）及两个索引
  - 启用 WAL 模式以支持并发读写
  - `save_session()` 将会话状态序列化为 JSON 存入 `state_json` 列，同步更新 `summary` 和 `last_active_at`
  - `delete_session()` 返回 `bool` 表示是否成功删除
  - `list_sessions()` 按 `last_active_at DESC` 排序返回摘要列表
  - 数据库文件路径为 `data/sessions.db`（位于已有 `./data` 卷中），服务重启后数据保持完整
  - _Requirements: 1.2, 1.3, 2.5, 6.3_
  - _Boundary: SqliteStore_
  - _Depends: 1.1, 1.2_

- [ ] 2. 会话 CRUD API
- [x] 2.1 添加会话数据模型
  - 在 `app/api/schemas.py` 中新增 `SessionCreateRequest`（`user_id: str`，必填非空）
  - 新增 `SessionSummary`（`session_id`、`summary`、`created_at`、`last_active_at`、`message_count` 字段）
  - 新增 `SessionListResponse`（`sessions: list[SessionSummary]`、`total_count: int`）
  - 新增 `SessionCreateResponse`（`session_id`、`user_id`、`created_at`）
  - 新增 `SessionDeleteResponse`（`deleted: bool`、`session_id: str`）
  - 所有模型可通过 Pydantic 校验且 JSON 序列化正确
  - _Requirements: 2.1, 2.3, 2.4_

- [x] 2.2 实现会话 CRUD REST 端点
  - `POST /api/sessions`：接收 `SessionCreateRequest`，使用 `uuid6.uuid7()` 生成会话 ID，调用 `store.create_session()` 创建会话，返回 `SessionCreateResponse`
  - `GET /api/sessions?user_id=xxx`：校验 `user_id` 非空，调用 `store.list_sessions(user_id)`，返回 `SessionListResponse`
  - `GET /api/sessions/{session_id}?user_id=xxx`：调用 `store.get_session(user_id, session_id)`，不存在返回 404，存在返回 `SessionState`
  - `DELETE /api/sessions/{session_id}?user_id=xxx`：调用 `store.delete_session(user_id, session_id)`，不存在返回 404，成功返回 `SessionDeleteResponse`
  - 所有端点对 `user_id` 为空的情况返回 400 错误
  - _Requirements: 2.1, 2.3, 2.4_
  - _Boundary: SessionAPI_
  - _Depends: 1.1, 1.2, 2.1_

- [ ] 2.3 修改现有聊天端点传递 user_id 到存储层
  - `POST /api/chat`：将 `ChatRequest.user_id` 传递给 `store.get_session(user_id, session_id)` 和 `store.save_session(user_id, session_id, state)`
  - `POST /api/chat/sync`：同上
  - `WS /api/ws/{session_id}`：将 `user_id` 查询参数传递给 `store.get_session(user_id, session_id)`
  - 未提供 `user_id` 的旧客户端使用默认值 `"default"` 保持向后兼容
  - _Requirements: 1.3, 1.4, 2.2_
  - _Depends: 1.2_

- [ ] 3. 前端：用户身份与会话管理
- [ ] 3.1 添加用户身份输入与持久化
  - 在侧边栏顶部添加"用户标识"输入框，页面加载时从 `localStorage` 键 `"vkdbagent.userId"` 恢复
  - 用户修改标识后同步写入 `localStorage` 并刷新会话列表
  - `POST /api/chat` 请求体中包含 `user_id` 字段
  - 所有会话 API 调用自动携带当前 `user_id`
  - 页面刷新后用户标识保持不变
  - _Requirements: 1.1, 7.4_
  - _Boundary: UserIdentityProvider_

- [ ] 3.2 添加会话管理 UI 组件
  - 侧边栏展示当前用户的会话列表（调用 `GET /api/sessions?user_id=xxx`），每项显示会话摘要和最近活动时间
  - "新建会话"按钮调用 `POST /api/sessions` 创建会话并自动切换
  - 点击会话项切换到该会话，重新加载其上下文
  - 每个会话项有删除按钮，点击弹出确认对话框，确认后调用 `DELETE /api/sessions/{id}?user_id=xxx` 并刷新列表
  - 当前活跃会话在列表中高亮显示
  - 切换用户标识后会话列表自动刷新
  - _Requirements: 2.1, 2.3, 2.4, 7.4_
  - _Boundary: SessionManager_

- [ ] 4. 集成与接线
- [ ] 4.1 将存储生命周期接入应用启动和关闭
  - 在 `app/main.py` 的 `lifespan` 中调用 `store.initialize()` 初始化存储（创建数据库表和索引）
  - 在 `lifespan` 的 shutdown 阶段调用 `store.close()` 关闭连接
  - `store` 实例通过 `get_store()` 工厂函数获取，与应用生命周期绑定
  - 启动日志中输出当前使用的存储后端类型
  - _Requirements: 2.5, 6.3_
  - _Depends: 1.2, 1.3_

- [ ] 4.2 更新 Agent Runner 传递 user_id 到观测层
  - 在 `run_agent_stream()` 中将 `session_state.get("user_id", "")` 传递给 `LangfuseObserver` 构造函数
  - Langfuse trace 中正确标记 `user_id`，便于按用户筛选追踪数据
  - _Requirements: 1.3_
  - _Depends: 4.1_

- [ ] 5. 测试与验证
- [ ] 5.1 (P) 存储后端单元测试
  - 使用 `:memory:` SQLite 测试 `SqliteStore` 的 `get_session`、`save_session`、`delete_session`、`list_sessions`
  - 验证多用户隔离：用户 A 的 `get_session` 无法获取用户 B 的会话
  - 验证 `list_sessions` 只返回指定用户的会话
  - 验证 `delete_session` 只删除目标会话，不影响同用户其他会话
  - 验证 `InMemoryStore` 行为与 `SqliteStore` 一致
  - 所有测试用例通过
  - _Requirements: 1.2, 1.3, 2.5_
  - _Boundary: SqliteStore, InMemoryStore_
  - _Depends: 1.2, 1.3_

- [ ] 5.2 (P) 会话 API 集成测试
  - 使用 `TestClient` 测试完整会话生命周期：创建 → 列表（验证存在）→ 获取详情 → 删除 → 列表（验证不存在）
  - 测试 `user_id` 为空时返回 400
  - 测试访问不存在的会话返回 404
  - 测试不同 `user_id` 的会话列表互相隔离
  - 所有测试用例通过
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: SessionAPI_
  - _Depends: 2.1, 2.2_

- [ ] 5.3 (P) 多用户隔离端到端测试
  - 模拟两个不同 `user_id` 各自创建会话并发送查询消息
  - 验证用户 A 的会话列表不包含用户 B 的会话
  - 验证用户 A 无法通过直接指定 session_id 访问用户 B 的会话数据
  - 验证两个用户同时操作时互不干扰
  - 所有测试用例通过
  - _Requirements: 1.3, 7.5_
  - _Boundary: SessionAPI, StorageBackend_
  - _Depends: 4.1_

- [ ] 5.4 已有功能回归验证
  - 运行现有 `tests/test_nl2sql.py` 确认 NL2SQL 生成和校验逻辑不受影响
  - 运行现有 `tests/test_knowledge_memory.py` 确认 OpenViking 集成不受影响
  - 手动验证 SSE 流式响应和 WebSocket 端点正常工作
  - 确认需求 3（数据库发现）、4（NL2SQL 查询）、5（查询结果展示）功能完整
  - 已有测试套件全部通过
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.4, 7.1, 7.2, 7.3_
  - _Depends: 4.1, 4.2_
