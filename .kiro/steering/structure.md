# Project Structure

## Organization Philosophy

**领域模块化**（Domain-Modular）架构。每个 `app/` 下的顶层包代表一个独立的领域关注点，模块间松耦合，通过 `__init__.py` 显式导出的符号通信，而非共享的"核心"层。

## Directory Patterns

### Agent 核心 (`app/agent/`)
**Purpose**: ReAct Agent 循环、LLM 交互、上下文构建、取消控制  
**Key modules**: `runner.py`（ReAct 循环）、`context.py`（上下文组装）、`prompts.py`（系统提示词）、`cancel.py`（取消事件注册表，含 TTL 过期）  
**Pattern**: 编排层，不涉及 HTTP 或 API 知识

### API 层 (`app/api/`)
**Purpose**: FastAPI 路由（HTTP + WebSocket）、Pydantic schema、会话 CRUD、Admin 管理端点  
**Key modules**: `routes.py`（SSE chat/WS 端点、会话 CRUD）、`admin_routes.py`（Admin API — HDC namespace 映射管理、SQL 记忆管理、存储概览、schema 搜索，通过 Bearer token 认证）、`schemas.py`（请求/响应模型，含 Admin 相关 schema）  
**Pattern**: 纯 HTTP/SSE 关注点（WebSocket 端点已实现但前端当前使用 SSE），无业务逻辑，通过 `app.` 导入调用下层服务

### NL2SQL 流水线 (`app/nl2sql/`)
**Purpose**: SQL 生成、验证、修复的独立流水线  
**Key modules**: `generator.py`（SQL 生成 prompt 构建 + `EnrichmentContext` ContextVar 侧信道）、`validator.py`、`repair.py`（SQL 修复 prompt，同样读取 ContextVar）、`schema.py`  
**Pattern**: 独立领域服务，与 Agent 循环解耦；通过 `ContextVar` 接收 Agent 层检索的 HDC 列描述和 SQL 历史记忆，在不修改工具 schema 的前提下富化 prompt

### 工具注册 (`app/tools/`)
**Purpose**: LLM 可调用的工具函数定义和执行  
**Key modules**: `__init__.py`（工具注册表 + `TOOLS` 列表 + `TOOL_HANDLERS` 字典）+ 独立工具模块  
**Pattern**: 中心化注册表是工具定义的唯一真相源，各工具模块为独立 async 函数。`ToolRegistry` 在执行 handler 前通过 `inspect.signature` 过滤 LLM 传入的幻影参数（幻觉防御），保证 handler 调用安全。

### 记忆与存储系统 (`app/memory/`)
**Purpose**: 会话持久化、偏好存储、SQL 历史记忆、HDC namespace 映射管理、统一生命周期管理  
**Key modules**: `store.py`（会话存储：`StorageBackend` Protocol + `InMemoryStore` + `SqliteStore`）、`preferences.py`（偏好存储：`PreferenceBackend` Protocol + `InMemoryPreferenceStore` + `SqlitePreferenceStore`）、`sql_memory.py`（SQL 历史记忆：`SqlMemoryBackend` Protocol + `InMemorySqlMemoryStore` + `SqliteSqlMemoryStore`，语义检索 + embedding 管理）、`admin_store.py`（HDC 映射管理：`AdminStoreBackend` Protocol + `InMemoryAdminStore` + `SqliteAdminStore`，始终 SQLite 持久化）、`manager.py`（`StorageManager` 四后端统一生命周期协调器 + `get_storage()` 工厂）、`viking.py`（OpenViking 客户端）  
**Pattern**: Protocol 驱动的可插拔多后端 + 统一生命周期管理；`__init__.py` 作为门面提供向后兼容包装；可选子系统失败不阻断主流程

### 观测 (`app/observation/`)
**Purpose**: Langfuse 可观测性（trace、metrics）  
**Pattern**: 可选子系统，try/except 包裹

### 知识 (`app/knowledge/`)
**Purpose**: OpenViking 长期记忆集成  
**Pattern**: 可选子系统

### 数据底座 (`app/datavault/`)
**Purpose**: HDC（层次化数据上下文）知识库的生成、检索、上传和增量更新  
**Key modules**: `models.py`（采集层/生成层/检索层数据模型）、`collector.py`（SchemaCollector — OneDBA schema 采集）、`generator.py`（HDCGenerator — 四层 LLM 生成管线）、`uploader.py`（HDCUploader — OpenViking 目录结构 + tags 写入）、`retriever.py`（HDCRetriever — 两阶段 tags+向量检索）、`updater.py`（HDCUpdater — 列签名 hash 增量更新）  
**Pattern**: 离线生成管线 + 在线检索分离；asyncio.Semaphore LLM 并发限流；单表容错（失败不中断整体）；静默降级（OpenViking 不可用时回退到 find_table+describe_table）

### 客户端 (`app/client/`)
**Purpose**: OneDBA 平台 HTTP 客户端  
**Pattern**: 外部服务访问层

### 前端 (`app/static/`)
**Purpose**: Web UI 单页应用（主聊天界面 + Admin 管理界面）  
**Contents**: `index.html`、`app.js`（主聊天界面）、`admin.html`、`admin.js`（HDC namespace 映射管理 + SQL 记忆管理 + 存储概览）、`styles.css`、`favicon.svg`  
**Pattern**: 原生 HTML/CSS/JS，无构建步骤、无打包器、无框架，通过 FastAPI `StaticFiles` 挂载

### 配置 (`app/config.py`)
**Purpose**: Pydantic `BaseSettings` 集中配置，`.env` 自动加载  
**Pattern**: `@lru_cache` 装饰的 `get_settings()` 提供进程级单例，所有模块通过 `from app.config import get_settings` 读取

### 入口 (`app/main.py`)
**Purpose**: FastAPI 应用工厂、lifespan、静态文件挂载、路由注册  
**Pattern**: 组合根，将所有组件装配在一起

### 部署入口（根目录）
**Purpose**: 生产容器、compose 编排、环境变量样例和部署手册  
**Key files**: `Dockerfile`、`docker-compose.yml`、`gunicorn_conf.py`、`.env.example`、`DEPLOY.md`  
**Pattern**: 根目录只保留部署和开发入口文件；敏感配置通过环境变量或 `.env` 注入，`.env.example` 只记录键名、默认值和安全注释；`DEPLOY.md` 记录运维流程和生产检查清单

### 测试 (`tests/`)
**Purpose**: 单元测试、集成测试、E2E、独立评测框架  
**Key modules**: 
- `test_{module}.py` — 标准单元/集成/E2E 测试（镜像源模块命名）
- `evaluation/` — 独立评测框架（CLI → loader → runner → judges → scorer → reporter），支持 `--with-hdc`/`--compare-hdc`/`--verbose-hdc` 模式、`--repeat` 多次取平均、`--hdc-tables` 表白名单过滤、`--hdc-namespace` 命名空间变体隔离，输出 JSON+Markdown 双格式报告，含 `RunConfig` 运行时参数追溯和 `ToolCallRecord`/`LLMCallRecord` 完整 Agent 推理轨迹
- `datavault/` — HDC 采集/集成/新旧格式兼容的单元和集成测试
- `docs/` — 评测用例 Markdown 规格文件  
**Pattern**: 标准测试镜像源结构 + 独立评测子框架（自有 CLI、模型、运行器、评判器、渲染器）

### 工具脚本 (`tools/`)
**Purpose**: 开发和实验辅助脚本（非运行时模块，不 import 到 `app.*`）  
**Key modules**: `hdc/`（生成/演示/更新/对比/召回验证）、`llm_api_bench.py`（LLM API 性能压测）、`onedba_bench.py`（OneDBA 平台并发压测）、`comparison_experiment.sh`（HDC/SQL Memory 对比实验编排）、`comparison_viz.py`（对比结果可视化）、`convergence_analysis.py`（收敛性分析）、`sql_memory_admin.py`（SQL Memory 管理工具 — seed 测试数据、re-embed、统计、对比实验）  
**Pattern**: 由 `tests/datavault/` HDC demo 脚本迁移重构而来，独立于运行时模块；输出写入 `tools/output/`

## Naming Conventions

- **Files**: `snake_case`（`runner.py`、`find_table.py`、`sql_utils.py`）
- **Classes**: `PascalCase`（`OneDBAClient`、`CancelEventRegistry`、`StorageBackend`）
- **Functions**: `snake_case`（`run_agent_stream`、`build_context`、`get_store`）
- **Private functions**: `_leading_underscore`（`_execute_tool`、`_security_check`）
- **Factory/getter functions**: `get_` 前缀（`get_store()`、`get_settings()`、`get_cancel_registry()`）
- **Stream generators**: `_stream` 后缀（`run_agent_stream`、`event_stream`）
- **Constants**: `UPPER_SNAKE_CASE`（`AGENT_SYSTEM_PROMPT`、`TOOLS`、`TOOL_HANDLERS`）
- **Test files**: `test_{module}.py`（匹配源模块名），集成测试 `_integration` 后缀，E2E `_e2e` 后缀

## Import Organization

所有导入使用绝对路径，以 `app.` 为包根：

```python
# 标准库
import asyncio
from typing import Any

# 第三方
from fastapi import APIRouter
from pydantic import BaseModel

# 内部模块（始终 app. 前缀）
from app.config import get_settings
from app.agent.runner import run_agent_stream
from app.api.schemas import ChatRequest
from app.tools import TOOLS, TOOL_HANDLERS
```

**无相对导入**（无 `from . import ...`），无路径别名。项目根在 `PYTHONPATH` 中，`app.` 全局可解析。可选依赖使用函数内延迟导入。

## Code Organization Principles

1. **`__init__.py` 作为门面**：每个包的 `__init__.py` 通过 `__all__` 列表显式重新导出公共 API，消费者不应直接从子模块导入 `__all__` 中的符号。

2. **工具注册表模式**：`app/tools/__init__.py` 维护中心化的 `TOOLS` 列表和 `TOOL_HANDLERS` 字典，各工具模块为独立 async 函数，无交叉引用。

3. **Protocol 抽象**：`StorageBackend` 和 `PreferenceBackend` 使用 `typing.Protocol`（`@runtime_checkable`），各自有 `InMemory*`/`Sqlite*` 两种实现。`StorageManager` 统一管理多后端生命周期，`get_storage()` 工厂返回 `StorageManager` 单例。

4. **模块级延迟初始化单例**：重量级资源（LLM 客户端、OneDBA 客户端、取消注册表、偏好存储）通过模块级 `_global: T | None = None` 变量 + `get_xxx()` 函数延迟初始化。

5. **关注点分离**：Agent 流程各环节独立——`runner.py`（ReAct 引擎）、`context.py`（上下文组装）、`prompts.py`（系统提示词）、`cancel.py`（取消事件注册表）、`routes.py`（装配编排）。

6. **错误隔离**：可选子系统（OpenViking、偏好追踪、Langfuse）包裹在 try/except 中，单点失败不影响主 Agent 流程。

7. **测试镜像源结构**：`tests/test_{module}.py` 匹配源模块，`evaluation/` 子包为独立评估框架（本仓库无根级 `conftest.py`，fixtures 由各测试文件或 `evaluation/` 内部定义）。

8. **中文文档**：模块级和函数级 docstring 使用中文，代码注释中英混合。

9. **根级部署文件是运行入口，不是领域模块**：Docker/gunicorn/compose 配置位于仓库根目录，服务逻辑仍只在 `app/` 内演进。部署文件负责进程模型、端口、健康检查、卷挂载和环境变量约束；业务配置读取统一收敛到 `app/config.py`。

---
_updated_at: 2026-08-17_
