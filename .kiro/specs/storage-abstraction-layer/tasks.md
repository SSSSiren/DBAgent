# 实现计划

## Task Format Template

### Major + Sub-task structure
- [ ] {{MAJOR_NUMBER}}. {{MAJOR_TASK_SUMMARY}}
- [ ] {{MAJOR_NUMBER}}.{{SUB_NUMBER}} {{SUB_TASK_DESCRIPTION}}{{SUB_PARALLEL_MARK}}
  - {{DETAIL_ITEM_1}}
  - {{OBSERVABLE_COMPLETION_ITEM}}
  - _Requirements: {{REQUIREMENT_IDS}}_
  - _Boundary: {{COMPONENT_NAMES}}_

---

- [ ] 1. 基础：PreferenceBackend Protocol 定义
- [x] 1.1 在 preferences.py 中定义 PreferenceBackend Protocol
  - 新增 `@runtime_checkable PreferenceBackend` Protocol 类，包含 5 个方法：`record_query`、`retrieve_preferences`、`retrieve_top_preferences`、`initialize`、`close`
  - 每个方法签名从现有 `QueryPreferenceStore` 对应方法提取，保持参数名和类型注解一致
  - Protocol 通过 `isinstance(store, PreferenceBackend)` 运行时检查
  - _Requirements: 2.1, 2.2_

- [ ] 2. 核心实现
- [ ] 2.1 实现 InMemoryPreferenceStore
  - 实现 `PreferenceBackend` Protocol，使用进程内存 dict 存储偏好数据
  - 数据按 `(user_id, table_name, database_name)` 复合键索引，与 SQLite 表结构对应
  - `record_query`：UPSERT 语义，已有记录则 query_count+1；新记录检查每用户上限（默认 50），超限淘汰 query_count 最小的记录
  - `retrieve_preferences`：对 keywords 按空格/标点分词，LIKE 匹配 table_name 和 database_name，结果按 query_count 降序
  - `retrieve_top_preferences`：返回用户 query_count 最高的 N 条记录
  - `initialize` / `close` 为空操作（与 `InMemoryStore` 模式一致）
  - 完成状态：`InMemoryPreferenceStore` 的 CRUD 和 LRU 淘汰行为与 `SqlitePreferenceStore` 产生相同的返回数据结构和排序
  - _Requirements: 2.1, 2.2, 5.2_
  - _Boundary: InMemoryPreferenceStore_

- [ ] 2.2 重构 QueryPreferenceStore 为 SqlitePreferenceStore
  - 将类名从 `QueryPreferenceStore` 改为 `SqlitePreferenceStore`，声明实现 `PreferenceBackend` Protocol
  - 内部逻辑完全不变：相同的 SQL、相同的 LRU 淘汰、相同的 `query_preferences` 表结构
  - 保留 `QueryPreferenceStore` 为模块级别名指向 `SqlitePreferenceStore`，保证向后兼容
  - 更新 `get_preference_store()` 工厂函数：检查 `storage_backend` 配置，值为 `"memory"` 时返回 `InMemoryPreferenceStore`，值为 `"sqlite"` 时返回 `SqlitePreferenceStore`
  - 完成状态：现有 `test_preferences.py` 中的测试用例在类名引用更新后全部通过
  - _Requirements: 2.1, 2.2, 5.1_

- [ ] 2.3 实现 StorageManager 统一生命周期管理
  - 新建 `app/memory/manager.py`，包含 `StorageManager` 类
  - `session_store: StorageBackend` 属性，`preference_store: PreferenceBackend | None` 属性
  - 构造函数接受已创建的后端实例（依赖注入），不自行创建
  - `initialize()`：先调用 `session_store.initialize()`，若 `preference_store` 非 None 则随后调用
  - `close()`：先关闭 `preference_store`（若存在），再关闭 `session_store`（逆序）
  - 任一后端初始化失败时异常向上传播
  - 完成状态：通过 mock 后端验证 `initialize` 和 `close` 的调用顺序正确
  - _Requirements: 1.1, 1.3, 2.3, 4.1, 4.2, 4.3_

- [ ] 2.4 实现 get_storage() 工厂和 reset_storage()
  - 在 `manager.py` 中实现 `get_storage()` 函数：读取 `storage_backend` 配置，创建会话和偏好后端实例，注入 `StorageManager`，返回模块级单例
  - 偏好后端跟随会话后端类型选择（`"memory"` → `InMemoryPreferenceStore`，`"sqlite"` → `SqlitePreferenceStore`）
  - `preference_enabled=False` 时跳过偏好后端创建，`preference_store` 为 None
  - `storage_backend` 值非法时抛出 `ValueError` 并包含明确的错误信息
  - 实现 `reset_storage()` 重置全局 `StorageManager` 单例，用于测试隔离
  - 完成状态：`get_storage()` 根据配置返回包含正确后端类型的 `StorageManager` 实例
  - _Requirements: 1.2, 3.1, 3.2, 3.3, 5.3_
  - _Boundary: manager.py_

- [ ] 3. 集成
- [ ] 3.1 更新 __init__.py 公共 API 导出和向后兼容包装
  - 新增导出：`StorageManager`、`PreferenceBackend`、`InMemoryPreferenceStore`、`SqlitePreferenceStore`、`get_storage`、`reset_storage`
  - 保留所有现有导出（`get_store`、`get_preference_store`、`StorageBackend`、`InMemoryStore`、`SqliteStore` 等）
  - 添加 `QueryPreferenceStore` 别名指向 `SqlitePreferenceStore`
  - 将 `get_store()` 实现为兼容包装，内部委托给 `get_storage().session_store`
  - 将 `get_preference_store()` 实现为兼容包装，内部委托给 `get_storage().preference_store`
  - 将 `reset_store()` 和 `reset_preference_store()` 实现为兼容包装，内部委托给 `reset_storage()`
  - 完成状态：`from app.memory import get_storage, StorageManager, PreferenceBackend` 可正常导入；旧 API 调用方行为不变
  - _Requirements: 1.2_

- [ ] 3.2 (P) 更新 main.py lifespan 使用 get_storage()
  - 将 `from app.memory.store import get_store` 替换为 `from app.memory import get_storage`
  - 将两套独立的 `get_store()` + `get_preference_store()` 调用替换为单一的 `storage = get_storage()`
  - 将 `await store.initialize()` + `await pref_store.initialize()` 替换为 `await storage.initialize()`
  - 移除启动和关闭路径中所有 `if settings.preference_enabled:` 条件判断和延迟导入（由 `get_storage()` 内部处理）
  - 将 `await get_preference_store().close()` + `await store.close()` 替换为 `await storage.close()`
  - 完成状态：应用使用单一存储入口正常启动和关闭
  - _Requirements: 1.1, 4.1, 4.2_
  - _Boundary: main.py_

- [ ] 3.3 (P) 更新 routes.py 存储访问方式
  - 将 `from app.memory.store import DEFAULT_SESSION, get_store` 替换为 `from app.memory import get_storage` 和 `from app.memory.store import DEFAULT_SESSION`
  - `_get_or_create_session` 中 `get_store()` 替换为 `get_storage().session_store`
  - `_execute_agent_stream` 中偏好检索（行 195-201）：`get_preference_store()` 替换为 `get_storage().preference_store`，并增加 None 检查
  - `_execute_agent_stream` 中偏好记录（行 258-280）：同上替换
  - `_execute_agent_stream` 中会话保存（行 295）：`get_store()` 替换为 `get_storage().session_store`
  - 会话管理接口（行 506、535、554、580）：`get_store()` 替换为 `get_storage().session_store`
  - 完成状态：所有 API 端点在替换导入后功能行为不变
  - _Requirements: 1.1, 1.2_
  - _Boundary: routes.py_
  - _Depends: 3.1_

- [ ] 4. 测试与验证
- [ ] 4.1 (P) 新组件的单元测试
  - 新建 `tests/test_storage_manager.py`：验证 `StorageManager.initialize()` 按序初始化、`close()` 逆序关闭、偏好禁用时 `preference_store` 为 None、初始化失败时异常传播
  - 在 `tests/test_preferences.py` 中新增 `InMemoryPreferenceStore` 的 CRUD 测试和 LRU 淘汰测试
  - 更新 `tests/test_preferences.py` 中 `QueryPreferenceStore` 引用为 `SqlitePreferenceStore`
  - 完成状态：所有新单元测试通过 `pytest tests/test_storage_manager.py tests/test_preferences.py -v`
  - _Requirements: 2.1, 2.2, 2.3, 4.1, 4.2, 4.3, 5.2_
  - _Boundary: tests/_

- [ ] 4.2 (P) 更新现有测试的导入路径和 monkeypatch
  - `tests/test_preferences_e2e.py`：将 `app.memory.preferences.get_preference_store` 的 monkeypatch 路径更新为 `app.memory.get_storage`
  - `tests/test_preferences_integration.py`：同上更新 monkeypatch 路径
  - `tests/test_store.py`：确认现有 `StorageBackend` 测试不受影响
  - `tests/test_knowledge_memory.py`：确认 `get_store()` 和 `reset_store()` 兼容包装行为正常
  - `tests/test_cancel_integration.py`、`tests/test_session_api.py`：确认 `reset_store()` 兼容包装行为正常；按需更新引用
  - 完成状态：所有现有测试在路径更新后通过
  - _Requirements: 5.1, 5.3_
  - _Boundary: tests/_

- [ ] 4.3 全量回归验证
  - 运行 `pytest tests/ -v` 确认零失败
  - 分别使用 `STORAGE_BACKEND=memory` 和 `STORAGE_BACKEND=sqlite` 启动应用，验证正常启动
  - 手动发送聊天请求，验证会话持久化和偏好记录功能正常
  - 完成状态：两种后端配置下测试全部通过、应用正常启动、功能行为一致
  - _Requirements: 5.1, 5.2, 5.3_
  - _Depends: 4.1, 4.2_