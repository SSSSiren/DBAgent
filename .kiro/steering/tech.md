# Technology Stack

## Architecture

4 层管道架构：HTTP/WS 层（FastAPI，SSE 为主流式通道，WebSocket 端点已实现但前端未接入）→ Agent 编排层（deepagents/LangGraph 驱动，保留既有 `run_agent_stream` 与 SSE 契约）→ 领域服务层（NL2SQL、工具）→ 外部服务层（OneDBA、OpenViking、Langfuse）。LLM 通过 OpenAI 兼容 API 抽象，默认使用 DeepSeek-V4。

## Core Technologies

- **Language**: Python 3.12
- **Framework**: FastAPI (≥ 0.109.0) + Uvicorn
- **Runtime**: Docker (python:3.12-slim)，docker-compose 单服务部署
- **LLM**: DeepSeek-V4，通过 OpenAI 兼容代理（`dwai-data.dewu-inc.com`）访问
- **Agent Engine**: deepagents（LangGraph）单代理引擎，`app/agent/runner.py` 负责流式编排和事件契约兼容；底层模型经 LangChain `ChatOpenAI` 接入 OpenAI 兼容代理

## Key Libraries

| 类别 | 库 | 作用 |
|---|---|---|
| LLM 客户端 | `openai` (≥ 1.0.0) | NL2SQL、embedding、评测和兼容路径中的 OpenAI 兼容 API 调用 |
| Agent 引擎 | `deepagents` (≥ 0.6.8) + `langchain-openai` + `langgraph` | Agent 决策/工具循环，外层通过 adapter 投影为既有内部事件 |
| 数据校验 | `pydantic` (≥ 2.5.0) + `pydantic-settings` | API schema、配置管理、.env 自动加载 |
| 可观测性 | `langfuse` (≥ 2.0.0) | LLM 调用和工具执行的 trace 级别遥测 |
| 存储 | `aiosqlite` (≥ 0.20.0) | 异步 SQLite 会话持久化（WAL 模式），会话、偏好、SQL 记忆、Admin 映射四类数据共享同一数据库文件 |
| HTTP 客户端 | `httpx` (≥ 0.26.0) | OneDBA 平台 API 调用 |
| WebSocket | `websockets` (≥ 12.0) | WebSocket 双向通信（端点已实现于 `/api/ws/{id}`，含断开取消机制，但前端当前使用 SSE） |
| ID 生成 | `uuid6` (≥ 2024.0.0) | UUIDv7 会话 ID（时间有序、可排序） |

## Development Standards

### 类型安全
中等程度。使用 `from __future__ import annotations` 和 `typing`（`Optional`、`Protocol`、`AsyncIterator` 等），Pydantic v2 在 API 边界提供运行时校验，`StorageBackend` 使用 `Protocol` 结构化子类型。无 mypy/pyright 配置，无 CI 类型检查。

### 代码质量
无 linter 配置（无 flake8、pylint、ruff 配置），无 pre-commit hooks。无 `pyproject.toml`，依赖管理使用单文件 `requirements.txt`。

### 测试
- **框架**: pytest (≥ 8.0.0) + pytest-asyncio (≥ 0.23.0)
- **风格**: 所有测试为 `async def`，使用 `@pytest.mark.asyncio`
- **标记**: `integration` 自定义标记（需要 OpenViking 服务）
- **分类**: 单元测试（`test_*.py`）、集成测试（`_integration` 后缀）、E2E（`_e2e` 后缀）
- **覆盖**: 无覆盖率工具配置

## Development Environment

### 必需工具
- Python 3.12+
- Docker（生产部署）

### 常用命令
```bash
# 开发: uvicorn app.main:app --reload
# 测试: pytest tests/ -v
# 集成测试: pytest tests/ -v -m integration
# Docker: docker-compose up -d
```

## Key Technical Decisions

1. **deepagents 引擎 + 兼容外壳**：Agent 决策/工具循环由 deepagents/LangGraph 驱动，但 `run_agent_stream()`、SSE 事件类型、评测框架依赖的 `llm_call`/`tool_start`/`tool_end`/`final` 形状保持兼容。`event_adapter.py` 负责 LangChain 消息到内部事件的翻译，`tool_adapter.py` 负责把内部工具注册表适配为 `StructuredTool`，避免业务层直接依赖 LangChain 对象。

2. **OpenAI 兼容 API 抽象**：通过公司内部代理访问 DeepSeek-V4。在线 Agent 使用 LangChain `ChatOpenAI` 工厂接入，NL2SQL 生成、embedding 和评测工具仍在需要处直接使用 `openai.AsyncOpenAI`；切换模型主要通过配置完成。

3. **Protocol 驱动的可插拔存储**：四个 Protocol 定义清晰的持久化抽象——`StorageBackend`（会话）、`PreferenceBackend`（偏好）、`SqlMemoryBackend`（SQL 历史记忆）、`AdminStoreBackend`（HDC namespace 映射）。每种抽象均有 `InMemory*`/`Sqlite*` 两种实现。`StorageManager` 统一协调四个后端的生命周期（按依赖顺序初始化：会话→偏好→SQL 记忆→admin，逆序关闭）。`get_storage()` 工厂返回 `StorageManager` 单例。`app/memory/__init__.py` 提供向后兼容包装。通过 `STORAGE_BACKEND` 配置切换会话/偏好/SQL 记忆后端类型，Admin 存储始终使用 SQLite 持久化。

4. **NL2SQL 独立流水线**：`nl2sql/` 模块独立处理 SQL 生成→验证→修复闭环，与 Agent 循环解耦。

5. **事件驱动的 SSE 流式架构**：API 层通过异步生成器链产生类型化 SSE 事件（`step`、`sql`、`final`、`llm_call`），Agent runner 产出原始事件，routes 层包装为 SSE 格式。`llm_call` 事件完整记录每轮 LLM 调用的输入 messages 和输出（含 tool_calls），支持评测框架等外部消费者捕获 Agent 推理轨迹。

6. **多层记忆系统**：三层记忆并存——会话级对话历史（存储后端）、长期记忆（OpenViking 外部知识库，每 N 轮延迟提交）、操作偏好（`query_preferences` 表记录表使用模式），每次 Agent 运行前注入上下文。

7. **HDC 离线生成管线**：`app/datavault/` 模块实现 TiInsight HDC 方法论的离线 LLM 管线 — SchemaCollector（OneDBA 采集）→ HDCGenerator（三层自底向上 LLM 生成：列摘要→表描述→数据库摘要）→ HDCUploader（OpenViking 目录结构 + tags），HDCRetriever 负责在线两阶段检索（tags+向量双路召回），HDCUpdater 支持增量更新（列签名 hash 对比）。LLM 调用通过 `asyncio.Semaphore` 限流，单表失败不中断整体流程。

8. **asyncio.Event 取消机制**：`CancelEventRegistry`（`app/agent/cancel.py`）管理每个会话的取消信号，Agent 循环在多个安全点检查取消（迭代边界、LLM 调用竞态、工具执行），通过 REST 端点暴露。含 TTL 过期机制（5 分钟）防止内存泄漏。

9. **用户隔离的多租户会话**：所有会话操作使用 `(user_id, session_id)` 复合键，存储层实现多租户隔离。

10. **独立评测框架**：`tests/evaluation/` 实现 CLI 驱动的批量评测系统——TestCase 模型定义用例（自然语言问题+参考 SQL+预期行数+难度分级+分类+涉及表名），多维度评判（SQL 正确性 judge、质量 judge、效率 judge）打分聚合为总分，支持 `--with-hdc` 单轮、`--compare-hdc` 对比、`--verbose-hdc` 实时注入输出三种模式，生成 JSON+Markdown 双格式报告。支持 `repeat`（多次取平均）、`--hdc-tables`（表白名单过滤）、`--hdc-namespace`（命名空间变体隔离）及 LLM 调用完整追踪（`ToolCallRecord`/`LLMCallRecord` 记录 Agent 中间推理过程）。

11. **LLM 幻觉参数过滤**：`ToolRegistry` 在执行工具 handler 前，通过 `inspect.signature` 提取 handler 参数名，过滤掉 LLM 传入的幻影参数（如 JSON Schema 元字段名被误当作实际参数），避免 `TypeError`。过滤时记录 WARN 日志，不影响正常调用。这是针对 DeepSeek 等模型偶发幻觉的防御性措施。

12. **ContextVar 侧信道上下文注入**：Agent 层检索的 HDC 列描述和 SQL 历史记忆，通过 `asyncio.ContextVar` 作为隐式侧信道传递到 NL2SQL 引擎层（`generator.py`/`repair.py`），在不修改 LLM 可见工具 schema 的前提下富化 SQL 生成的 prompt。Runner 在 Agent 执行前设置 ContextVar，`generate_sql()`/`repair_sql()` 在构建 prompt 时读取。未设置时优雅降级（prompt 与富化前完全一致）。此模式适用于任何需要从请求入口跨多层异步调用传递补充上下文的场景。`tests/evaluation/` 中 `_run_one()` 通过 `[NL2SQL富化]` 日志段输出每用例的注入状态（HDC 匹配列数、SQL 示例安全/总计条数）。

13. **Agent 可观测性侧信道**：`app/agent/runner.py` 通过跨模块 ContextVar `_nl2sql_timings`（定义在 `app/tools/query_database.py`）收集 NL2SQL 引擎内部阶段级耗时（generator/repair/validator），`context.py` 的 `build_context()` 返回 `(context_str, ctx_tokens)` 双元组，`_execute_tool()` 返回 `(result, elapsed_ms)` 双元组。`runner.py` 在每个 Agent 迭代中收集 `tool_timings`、`ctx_prep_timings` 等指标并在最后一条 SSE `step` 事件中 `metadata.timings` 和 `metadata.tokens` 字段随 `final` 事件发出。评测框架 `scorer.py` 解析这些 metadata 并写入 `EvaluationReport` 的 `llm_calls` 和 `tool_calls` 记录，实现在评测报告中输出 TTFB、prep_ms、token 分布等细粒度性能指标。

14. **HDC Demo 脚本迁移**：原 `tests/datavault/` 下的 HDC demo 脚本（`demo_hdc.py`、`demo_hdc_generate.py`、`demo_hdc_update.py`、`demo_hdc_e2e.py`、`demo_hdc_compare.py`、`hdc_debug.py`）已迁移至 `tools/hdc/`（`demo.py`、`generate.py`、`update.py`、`e2e.py`、`compare.py`、`debug.py`），职责从测试/演示分离为独立工具集，`tests/datavault/` 保留纯测试（采集、集成、新旧格式兼容）。

15. **SQL 历史记忆（Semantic SQL Memory）**：`SqlMemoryBackend` 协议定义 Agent 成功执行的 SQL 记录的持久化与语义检索接口，`InMemorySqlMemoryStore`/`SqliteSqlMemoryStore` 提供双实现。每条记录包含自然语言问题、SQL、表名、数据库名、执行结果和 embedding 向量。在线检索时，通过余弦相似度匹配历史 SQL 并注入 Agent 上下文。支持 `scope` 配置（user/database/mixed）和 `ttl_days` 自动过期清理。`sql_memory_admin.py` 提供 CLI 管理工具（seed 测试数据、re-embed、统计、对比实验）。

16. **Admin HDC Memory Manager**：`AdminStoreBackend` 协议定义 HDC namespace 映射的 CRUD 接口，`SqliteAdminStore`（始终使用 SQLite 持久化，不跟随 `STORAGE_BACKEND` 切换）提供 `(user_id, schema_id, database_name)` 复合主键的 upsert/get/list/delete 操作。`admin_routes.py` 通过 Bearer token 认证的 `/api/admin/*` 端点暴露管理功能（namespace 映射 CRUD、SQL 记忆管理、存储概览、schema 搜索）。`admin.html`/`admin.js` 为原生 Web 管理界面（无构建步骤），与主前端共享 `app/static/` 目录。

17. **StorageManager 四后端架构**：`StorageManager` 从原有的双后端（会话+偏好）演进为四后端（会话+偏好+SQL 记忆+Admin），按依赖顺序初始化、逆序关闭。Admin 后端始终启用（SQLite 持久化），SQL 记忆后端通过 `sql_memory_enabled` 配置开关。`get_storage()` 工厂根据配置创建所有后端实例并注入 `StorageManager`。

18. **LLM 工具适配防御**：deepagents 路径复用既有 `ToolRegistry`，通过 `StructuredTool` 包装和 handler 签名默认值清洗来防御模型把可选参数传成 `null` 或产生幻影参数。工具 schema 的源头仍是 `app/tools/__init__.py`，不要在 LangChain 适配层复制一套工具定义。

---
_updated_at: 2026-08-17_
