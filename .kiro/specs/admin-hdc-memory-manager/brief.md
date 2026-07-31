# Brief: admin-hdc-memory-manager

## Problem

**Who**: DBAgent 运维管理员（负责 HDC 知识库管理、SQL Memory 维护的团队）

**Pain**: 
- HDC namespace 由客户端（前端/用户）在请求中自行传入，管理员无法控制哪个用户使用哪个 namespace。namespace 变更需要改前端代码或用户手动指定。
- SQL Memory 管理只能在服务器上通过 CLI 工具 `sql_memory_admin.py` 操作，无法远程管理。
- 没有命名空间目录——管理员无法快速知道某数据库下有哪些可用的 namespace。
- 没有跨用户数据管理能力（如查看/清理某用户的 SQL 记忆）。

## Current State

- `ChatRequest.hdc_namespace` 字段已存在，由前端传入，服务端直接信任使用
- `/api/hdc/generate` 等 HDC 管理端点已存在，但无 namespace 列表/映射能力
- `tools/sql_memory_admin.py` 提供完整的 CLI 管理能力（status/list/clean/re-embed/stats），但无 HTTP API
- 存储层以 `user_id` 严格隔离，无跨用户操作接口
- 项目已有成熟的 Protocol 抽象模式（`StorageBackend`、`PreferenceBackend`、`SqlMemoryBackend`）和 SQLite 持久化

## Desired Outcome

管理员可以通过 HTTP API 完成以下操作，无需登录服务器：
1. 为 `(user_id, schema_id, database_name)` 分配 HDC namespace，用户请求时自动解析
2. 查看某数据库下所有可用的 HDC namespace 列表
3. 查看/清理/重建 SQL Memory 记录（支持跨用户操作）
4. 查看系统级统计（用户数、会话数、记忆记录数等）

## Approach

**方案 A — 轻量 Admin API**：

在现有架构上新增 `app/api/admin_routes.py`，挂载到 `/api/admin/*`。SQLite 新增一张映射表。用环境变量单 token 做管理端点保护。

核心变更：
1. **HDC namespace 映射表** `user_hdc_mappings(user_id, schema_id, database_name, hdc_namespace, updated_at)` — 管理员 CRUD
2. **Admin token** — `ADMIN_API_TOKEN` 环境变量（单 token，不做多 token 管理）
3. **Admin API 路由** `/api/admin/*` — HTTP 端点，复用现有 storage 层
4. **自动 namespace 解析** — `resolve_hdc_namespace()` 函数，优先级：`request.hdc_namespace > admin mapping > None`

## Design Decisions (Confirmed)

### 1. Admin Token — 环境变量单 token

- 新增配置：`admin_api_token: str = ""`
- 所有 `/api/admin/*` 端点要求 `Authorization: Bearer <token>`
- `ADMIN_API_TOKEN` 为空时，admin API 返回 `503 Admin API not configured`
- **不做** `admin_tokens` 表、不提供 token CRUD、不做轮换 API

### 2. HDC 根路径

- 以 `app.datavault.uploader._HDC_ROOT = "viking://resources/hdc"` 为准
- Namespace 目录浏览复用 `_HDC_ROOT` 及相关 helper 函数

### 3. HDC Mapping 主键 — 包含 schema_id

```sql
user_hdc_mappings(
  user_id TEXT NOT NULL,
  schema_id INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  hdc_namespace TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, schema_id, database_name)
)
```

API：
- `POST /api/admin/hdc-mappings` — 创建/更新映射
- `GET /api/admin/hdc-mappings?user_id=&schema_id=&database_name=` — 查询映射
- `DELETE /api/admin/hdc-mappings/{user_id}/{schema_id}/{database_name}` — 删除映射

### 4. 向后兼容 — 三层优先级

| 优先级 | 来源 | 行为 |
|--------|------|------|
| 1 (最高) | `request.hdc_namespace` 显式传入 | 行为完全不变，直接使用 |
| 2 | Admin mapping 命中 | 服务端自动使用 mapping namespace |
| 3 | 未传且无 mapping | 行为不变，namespace 为 None |

### 5. SQL Memory 管理 — 扩展 Protocol

不允许 admin API 直接访问 SQLite `_conn`。扩展 `SqlMemoryBackend` Protocol：

```python
list_records(user_id="", database_name="", status="", limit=100, offset=0) -> list[dict]
count_records(user_id="", database_name="", status="") -> int
delete_records(user_id="", database_name="", status="", older_than_days=None) -> int
```

`re_embed_all(user_id="")` 已支持全量/按用户，保留即可。

### 6. 路由挂载

```python
# app/api/admin_routes.py
admin_router = APIRouter(prefix="/admin")

# app/main.py
from app.api.admin_routes import admin_router
app.include_router(admin_router, prefix="/api")
```

最终端点：`/api/admin/...`

### 7. Chat & Chat/Sync 统一 resolver

`/api/chat` 和 `/api/chat/sync` 共用同一个 namespace resolver 函数：

```python
async def resolve_hdc_namespace(user_id, schema_id, database_name, explicit_namespace) -> str | None
```

WebSocket 当前没有 `schema_id`/`database_name` 输入，暂不支持 mapping。

## Scope

- **In**: 
  - HDC namespace 映射 CRUD（`POST/GET/DELETE /api/admin/hdc-mappings`，主键含 `schema_id`）
  - SQL Memory 管理 API（`GET /api/admin/sql-memory/status|records|stats`、`DELETE /api/admin/sql-memory/clean`、`POST /api/admin/sql-memory/re-embed`）
  - `SqlMemoryBackend` Protocol 扩展（`list_records`/`count_records`/`delete_records`）
  - HDC namespace 目录（`GET /api/admin/hdc/namespaces/{schema_id}/{database_name}`）
  - 系统概览统计（`GET /api/admin/overview`）
  - Bearer token 认证（环境变量单 token）
  - `resolve_hdc_namespace()` 函数 + chat/chat_sync 集成

- **Out**: 
  - 用户注册/登录系统（用户来自 OneDBA 平台，不在此管理）
  - Web 管理面板 UI
  - 细粒度 RBAC
  - 运行时配置热更新
  - 审计日志（Langfuse 已覆盖）
  - `admin_tokens` 表及多 token 管理

## Boundary Candidates

- **Admin API 层** (`app/api/admin_routes.py`) — 纯 HTTP 端点，调用现有 service/storage 层
- **Admin store** (`app/memory/admin_store.py`) — HDC mapping 表的 Protocol + Sqlite 实现
- **Namespace resolver** (`app/api/routes.py` 中的 `resolve_hdc_namespace()` 函数)
- **SqlMemoryBackend 扩展** (`app/memory/sql_memory.py`) — 新增管理方法

## Out of Boundary

- 不修改 `ChatRequest` 的前端传参逻辑（`hdc_namespace` 保留为可选覆盖项）
- 不改变 OpenViking 的 HDC 存储结构
- 不改变 SQL Memory 的存储结构

## Upstream / Downstream

- **Upstream**: 
  - `app/memory/manager.py`（StorageManager 生命周期）
  - `app/memory/sql_memory.py`（SqlMemoryBackend Protocol）
  - `app/datavault/uploader.py`（`_HDC_ROOT` 及 helper 函数）
  - `app/datavault/retriever.py`（HDCRetriever）
  - `app/knowledge/openviking.py`（OpenVikingClient，用于列出 namespace 目录）
  - `.env` 配置（`ADMIN_API_TOKEN` 环境变量）

- **Downstream**: 
  - 前端管理员面板（可基于这些 API 构建）
  - 自动化 namespace 分配策略（当前手动，未来可规则驱动）

## Existing Spec Touchpoints

- **Extends**: 无（全新的独立 spec）
- **Adjacent**: 
  - `hdc-datavault-knowledge-base` — HDC 生成/检索，本 spec 增加 namespace 映射管理层
  - `sql-memory-store` — SQL Memory 存储，本 spec 增加 HTTP 管理接口 + Protocol 扩展
  - `storage-abstraction-layer` — 存储抽象，本 spec 遵循同一 Protocol 模式

## Constraints

- 与现有 Protocol 模式一致：定义 Protocol → Sqlite 实现 → StorageManager 管理生命周期
- Admin store 复用现有 `data/sessions.db`（同一 SQLite 文件）
- Bearer token 从 `ADMIN_API_TOKEN` 环境变量读取，不做 token 表
- 不引入新的外部依赖
- 向后兼容三层优先级：`request.hdc_namespace > admin mapping > None`
