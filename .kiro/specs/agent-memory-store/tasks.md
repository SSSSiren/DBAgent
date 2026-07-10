# Implementation Plan

- [ ] 1. 前置改造与数据层基础
- [x] 1.1 存储层同步兼容层移除
  - 删除 `app/memory/store.py` 中的 `_run_async()` 函数及所有 `isinstance(store, InMemoryStore)` 分支
  - 删除 `_SessionStoreProxy` 类和 `SESSION_STORE` 全局变量
  - 删除 6 个同步包装函数（`get_session`、`save_session`、`delete_session`、`list_sessions`、`session_count`）及 `__all__` 导出
  - `routes.py` 中 3 处 `get_session()` 调用改为 `await get_store().get_session()`，1 处 `save_session()` 改为 `await get_store().save_session()`
  - 全局变量 `_store` 类型从 `Optional[InMemoryStore]` 改为 `Optional[StorageBackend]`
  - `app/memory/__init__.py` 移除 `SESSION_STORE` 和同步包装函数导出
  - `tests/test_knowledge_memory.py` 移除 `SESSION_STORE` 引用，改用 `reset_store()`
  - 任务完成后，`pytest tests/test_store.py tests/test_session_api.py tests/test_knowledge_memory.py -v` 全部通过，代码中无 `SESSION_STORE` 引用
  - _Requirements: 5.1_
  - _Boundary: app/memory/store.py, app/memory/__init__.py, app/api/routes.py_

- [x] 1.2 添加偏好功能开关配置
  - 在 Settings 中新增 `preference_enabled: bool = True` 配置项
  - 配置项可通过环境变量 `PREFERENCE_ENABLED` 覆盖
  - 启动日志中打印偏好功能状态
  - _Requirements: 5.1_
  - _Boundary: app.config.Settings_

- [x] 1.3 实现查询偏好存储及模块导出
  - 创建 `QueryPreferenceStore` 类，管理 `query_preferences` 表的 DDL 和 CRUD
  - 实现 `get_preference_store()` 工厂函数（进程级单例，与 `get_store()` 模式一致）和 `reset_preference_store()`（测试用）
  - DDL：表包含 user_id、table_name、database_name（复合主键）、schema_id、query_count、last_query_at、sql_patterns（预留）；创建 `idx_pref_user_freq` 和 `idx_pref_user_table` 索引
  - `record_query()`：使用 `ON CONFLICT DO UPDATE` 实现 UPSERT（query_count+1, 更新 last_query_at 和 schema_id）
  - 每用户上限控制：`record_query` 写入前检查该用户记录数，若已达上限（默认 50）且新记录不命中已有行，则淘汰 query_count 最小的记录（LRU 策略）
  - `retrieve_preferences()`：按空格/标点分词，对 table_name 和 database_name 执行 LIKE 匹配，按 query_count DESC 排序，limit 默认 5
  - `retrieve_top_preferences()`：返回用户 query_count 最高的记录（无关键词匹配时的回退策略）
  - 所有方法通过 WHERE user_id 确保用户隔离
  - 在 `app/memory/__init__.py` 中导出 `QueryPreferenceStore`、`get_preference_store`、`reset_preference_store`
  - 任务完成后，可直接 import 并调用所有 CRUD 方法
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 5.1_
  - _Boundary: QueryPreferenceStore_

- [ ] 2. Agent 上下文增强
- [x] 2.1 (P) 偏好信息注入 Agent 上下文
  - 在 `build_context()` 中新增第 5 段：读取 `session_state["_preferences"]`
  - 非空时构建 `[操作记忆 — 查询偏好]` 段落，格式为 `- {database_name}.{table_name}（查询 {query_count} 次）`
  - 偏好段落位于 `[长期记忆 — 来自之前的对话]` 之后，两类信息并列展示
  - 偏好为空时不添加空段落（仅非空时 `context_parts.append`）
  - 任务完成后，有偏好数据的会话在 prompt 中可见格式化的偏好段落
  - _Requirements: 3.1, 3.2, 3.3_
  - _Boundary: build_context_

- [x] 2.2 (P) 偏好使用规则注入系统提示词
  - 在 `AGENT_SYSTEM_PROMPT` 中"长期记忆"段落之后新增"查询偏好"段落
  - 说明偏好信息的来源（自动记录的成功查询）、内容（表名、数据库名、查询次数）和与长期记忆的区别
  - 使用规则：优先检查偏好表匹配、优先使用偏好中的 schema_id/database_name、回答中自然提及偏好来源、偏好是辅助参考仍需验证
  - 任务完成后，Agent 在回答中能自然引用偏好信息
  - _Requirements: 4.2_
  - _Boundary: AGENT_SYSTEM_PROMPT_

- [x] 2.3 (P) 偏好数量前端展示
  - 在 `SessionState` schema 中新增 `preference_count: int = Field(default=0)` 字段
  - 该字段通过 API 响应返回给前端，用于记忆指示器展示
  - 任务完成后，`GET /api/sessions/{id}` 响应中包含 `preference_count` 字段
  - _Requirements: 4.1_
  - _Boundary: SessionState_

- [ ] 3. 请求流集成
- [x] 3.1 偏好检索钩子及计数持久化
  - 在 `_execute_agent_stream()` 中，OpenViking 记忆检索之后、Agent 执行之前，添加偏好检索逻辑
  - 仅当 `preference_enabled=True` 时执行，使用独立的 try/except 静默降级
  - 通过 `get_preference_store()` 获取持久连接，调用 `retrieve_preferences(user_id, user_input)` 检索，无匹配时回退到 `retrieve_top_preferences(user_id)`
  - 检索结果注入 `initial_state["_preferences"]`，数量写入 `initial_state["_preference_count"]`
  - 在 final 事件中将 `_preference_count` 写入 `updated_state`，确保偏好计数随会话持久化
  - 检索失败时打印 `[Pref]` 日志并继续（不依赖 `kb_enabled`）
  - 任务完成后，有历史偏好的用户在新对话开始时 prompt 中包含偏好信息
  - _Requirements: 2.1, 2.2, 2.3, 4.1, 5.2_
  - _Depends: 1.3, 2.1_
  - _Boundary: _execute_agent_stream_

- [x] 3.2 偏好记录钩子
  - 在 `_execute_agent_stream()` 中，Agent 执行完成后、状态保存之前，添加偏好记录逻辑
  - 仅当 `preference_enabled=True` 时执行，使用独立的 try/except 静默降级
  - 遍历 `final_payload["tool_calls"]`，过滤 `tool == "query_database"` 且 `result is not None` 的成功调用
  - 从 `args` 提取 `table_name` 和 `schema_id`，从 `session_state["selected_database"]["schemaName"]` 获取 `database_name`
  - 多表 JOIN 场景：按逗号拆分 `table_name`，逐表调用 `record_query(user_id, t_name, database_name, schema_id)`
  - 记录失败时打印 `[Pref]` 日志并继续，不影响 OpenViking 记录流程
  - 任务完成后，成功执行 query_database 的用户偏好被自动记录到数据库
  - _Requirements: 1.1, 1.3, 1.4, 5.3_
  - _Depends: 1.3_
  - _Boundary: _execute_agent_stream_

- [x] 3.3 应用生命周期集成偏好存储
  - 在 `app/main.py` 的 `lifespan` 启动阶段调用 `get_preference_store().initialize()` 初始化偏好表
  - 在 `lifespan` 关闭阶段调用 `get_preference_store().close()` 释放数据库连接
  - 启动日志中打印偏好存储初始化状态
  - 任务完成后，应用启动时自动创建 `query_preferences` 表和索引，关闭时释放连接
  - _Requirements: 5.1_
  - _Boundary: app.main.lifespan_

- [ ] 4. 测试验证
- [x] 4.1 (P) 偏好存储单元测试
  - 使用 `QueryPreferenceStore(":memory:")` 创建测试实例
  - `record_query`：新记录创建后 `query_count=1`、重复记录 `query_count` 递增、不同 user_id 隔离、空参数校验
  - `record_query` LRU 淘汰：写入第 51 条不同表时最不常用记录被淘汰、命中已有行不触发淘汰
  - `retrieve_preferences`：精确关键词匹配成功、部分关键词匹配成功、无匹配返回空列表、结果按 `query_count` 降序、limit 限制
  - `retrieve_top_preferences`：返回最常用表、新用户返回空列表、limit 限制
  - `get_preference_store()` 返回单例、`reset_preference_store()` 重置后获取新实例
  - 任务完成后，`pytest tests/test_preferences.py -v` 全部通过
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4_
  - _Boundary: QueryPreferenceStore_

- [x] 4.2 (P) 偏好上下文注入单元测试 — 已于 Task 2.1 中完成（14 tests in test_context.py）
  - 测试 `build_context()` 在 `session_state["_preferences"]` 非空时生成正确的 `[操作记忆 — 查询偏好]` 段落
  - 验证段落格式 `- {database}.{table}（查询 N 次）`
  - 验证偏好段落位于长期记忆段落之后
  - 验证 `_preferences` 为空列表时不生成空段落
  - 验证 `_preferences` 缺失时不生成段落
  - 任务完成后，`pytest tests/test_context.py -v -k preference` 全部通过
  - _Requirements: 3.1, 3.2, 3.3_
  - _Boundary: build_context_

- [x] 4.3 偏好钩子集成测试
  - 检索钩子：用户输入包含已记录表名关键词 → `_preferences` 被注入；无匹配关键词 → 回退到 top 偏好；`preference_enabled=False` → 跳过检索
  - 记录钩子：模拟 `query_database` 成功的 `tool_calls_info` → 偏好被写入；多表 JOIN（逗号分隔 table_name）→ 每表各一条记录；记录异常 → 对话响应正常返回
  - 用户隔离：用户 A 的偏好检索不含用户 B 的数据；用户 A 的记录不影响用户 B 的检索结果
  - 任务完成后，`pytest tests/test_preferences_integration.py -v` 全部通过
  - _Requirements: 1.1, 1.3, 1.4, 2.1, 2.2, 2.4, 5.2, 5.3_
  - _Depends: 3.1, 3.2_
  - _Boundary: _execute_agent_stream_

- [ ] 4.4 E2E 完整生命周期测试
  - 完整流程：用户查询表 → 偏好自动记录 → 新对话中检索到偏好 → Agent 上下文 prompt 包含偏好信息
  - 偏好累积：多次查询同一表 → `query_count` 递增 → 检索结果按频率排序正确
  - 静默降级：模拟数据库文件不可写 → 偏好功能降级 → 对话正常返回（不抛异常）
  - OpenViking 共存：`kb_enabled=False` 时偏好检索和记录仍正常工作
  - 任务完成后，`bash tests/test_preferences_e2e.sh` 全部场景通过
  - _Requirements: 1.1, 1.2, 2.1, 3.1, 5.2_
  - _Depends: 4.3_
  - _Boundary: E2E_
