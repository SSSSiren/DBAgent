# 研究 & 设计决策

## 概要
- **特性**: admin-hdc-memory-manager
- **发现范围**: 扩展（Extension）— 轻量发现
- **关键发现**:
  - `StorageBackend` Protocol 现有 7 个方法，`SqlMemoryBackend` 现有 8 个方法，均需扩展
  - `StorageManager.__init__` 通过 keyword-only 依赖注入接收 backend 实例，新增 store 需遵循相同模式
  - OpenViking 没有独立的 `fs_ls` 方法，目录列表演示为 `_get_raw("/api/v1/fs/ls", uri)` 内联调用
  - 现有路由通过 `router = APIRouter()` 注册，`app.include_router(router, prefix="/api")` 挂载
  - HDC 检索入口条件为 `hdc_enabled AND selected_database`，namespace 从 `_hdc_namespace` 读取

## 研究日志

### Topic: Admin Store 存储模式
- **上下文**: 新增 HDC namespace 映射表的持久化方案
- **来源**: `app/memory/store.py`、`app/memory/manager.py`
- **发现**: 现有模式为 Protocol → InMemory/Sqlite 双实现 → `StorageManager` 统一生命周期。新增 AdminStore 需遵循相同模式。
- **影响**: 新增 `AdminStoreBackend` Protocol + `InMemoryAdminStore` + `SqliteAdminStore`，由 `StorageManager` 管理

### Topic: 路由注册模式
- **上下文**: 新增 admin API 路由的挂载方式
- **来源**: `app/main.py` 第 79 行、`app/api/routes.py` 第 46 行
- **发现**: 现有路由器为 `router = APIRouter()`，在 `main.py` 中 `app.include_router(router, prefix="/api")`。admin 路由可以 `app.include_router(admin_router, prefix="/api")` 挂载，因为 admin_router 自带 `/admin` 前缀。
- **影响**: `admin_router = APIRouter(prefix="/admin")` + `app.include_router(admin_router, prefix="/api")` → 最终 `/api/admin/*`

### Topic: OpenViking 目录列表
- **上下文**: HDC namespace 目录浏览的实现方式
- **来源**: `app/knowledge/openviking.py` 第 179 行
- **发现**: `_get_raw("/api/v1/fs/ls", uri)` 是内联调用，没有公开方法。需要新增 `list_directory(uri)` 公开方法。
- **影响**: 在 `OpenVikingClient` 新增 `list_directory(uri)` 方法，封装 `_get_raw("/api/v1/fs/ls", uri)`

## 架构模式评估

| 方案 | 描述 | 优势 | 风险/限制 | 备注 |
|------|------|------|-----------|------|
| Protocol + 双实现 | 遵循现有 `StorageBackend` 模式 | 与现有代码一致，测试友好 | 增加代码量 | 选用 |
| 直接 SQLite 访问 | admin 路由直接操作 SQLite | 代码量最小 | 违反分层原则，需求明确禁止 | 不选用 |
| 纯配置驱动 | 无新表，仅 `.env` 配置 | 零代码改动 | 无法远程管理，不可扩展 | 不选用 |

## 设计决策

### 决策: AdminStoreBackend Protocol
- **上下文**: HDC namespace 映射的持久化需求
- **备选方案**: 1) 新增 `AdminStoreBackend` Protocol + InMemory/Sqlite 双实现 2) 直接在 admin routes 中操作 SQLite
- **选定方案**: 方案 1 — 遵循现有分层模式
- **理由**: 与 `StorageBackend`/`SqlMemoryBackend` 一致，测试友好，支持未来切换存储后端
- **权衡**: 增加约 100 行模板代码，但换来类型安全和可测试性
- **后续跟进**: 实现时确保两个实现类通过 Protocol 的 `@runtime_checkable` 检查

### 决策: Admin Store 不纳入 StorageManager
- **上下文**: AdminStore 是独立于 session/preference/sql_memory 的第四种存储
- **备选方案**: 1) 纳入 `StorageManager` 统一管理 2) 独立模块级单例
- **选定方案**: 方案 1 — 纳入 `StorageManager`
- **理由**: 统一生命周期管理（initialize/close），与现有模式一致，复用 `get_storage()` 单例
- **权衡**: `StorageManager.__init__` 参数增加一个，但影响可控

### 决策: resolve_hdc_namespace 作为独立函数
- **上下文**: chat 和 chat/sync 都需要 namespace 解析
- **备选方案**: 1) 独立函数 `resolve_hdc_namespace()` 2) 内联在 `_execute_agent_stream` 中
- **选定方案**: 方案 1 — 独立函数
- **理由**: 两个端点复用，单点测试，职责清晰
- **权衡**: 多一个函数导出，但这是合理的抽象

### 决策: admin 认证作为 FastAPI 依赖
- **上下文**: Bearer token 验证需要应用于所有 `/api/admin/*` 端点
- **备选方案**: 1) FastAPI `Depends(verify_admin_token)` 2) 中间件 3) 每个端点手写检查
- **选定方案**: 方案 1 — FastAPI 依赖注入
- **理由**: 声明式、可复用、与 FastAPI 最佳实践一致，admin_router 级别统一应用
- **权衡**: 依赖 FastAPI 的依赖注入机制，但这是框架的标准用法

## 风险 & 缓解
- 风险: `_get_raw` 是 OpenVikingClient 的私有方法，`list_directory` 需要公开化 — 缓解: 新增公开方法，内部调用 `_get_raw`
- 风险: `StorageManager` 参数增多导致构造函数复杂 — 缓解: 保持 keyword-only 模式，向后兼容
- 风险: 映射表空时 chat 请求无影响 — 缓解: 三层优先级设计确保向后兼容，无映射时行为完全不变

## 引用
- `app/memory/store.py` — StorageBackend Protocol 定义
- `app/memory/sql_memory.py` — SqlMemoryBackend Protocol 定义
- `app/memory/manager.py` — StorageManager 生命周期
- `app/knowledge/openviking.py` — OpenVikingClient
- `app/datavault/uploader.py` — _HDC_ROOT 和 URI helper 函数
- `app/api/routes.py` — 现有路由和 chat 入口
- `app/main.py` — 应用工厂和路由挂载