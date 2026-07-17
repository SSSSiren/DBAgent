# Technology Stack

## Architecture

4 层管道架构：HTTP/WS 层（FastAPI）→ Agent 编排层（手写 ReAct 循环）→ 领域服务层（NL2SQL、工具）→ 外部服务层（OneDBA、OpenViking、Langfuse）。LLM 通过 OpenAI 兼容 API 抽象，默认使用 DeepSeek-V4。

## Core Technologies

- **Language**: Python 3.12
- **Framework**: FastAPI (≥ 0.109.0) + Uvicorn
- **Runtime**: Docker (python:3.12-slim)，docker-compose 单服务部署
- **LLM**: DeepSeek-V4，通过 OpenAI 兼容代理（`dwai-data.dewu-inc.com`）访问
- **Agent Engine**: 手写 ReAct 循环（`app/agent/runner.py`），基于 `openai` SDK 的 function calling，非 Claude Agent SDK

## Key Libraries

| 类别 | 库 | 作用 |
|---|---|---|
| LLM 客户端 | `openai` (≥ 1.0.0) | Agent 循环核心，通过 OpenAI 兼容 API 调用 LLM |
| 数据校验 | `pydantic` (≥ 2.5.0) + `pydantic-settings` | API schema、配置管理、.env 自动加载 |
| 可观测性 | `langfuse` (≥ 2.0.0) | LLM 调用和工具执行的 trace 级别遥测 |
| 存储 | `aiosqlite` (≥ 0.20.0) | 异步 SQLite 会话持久化（WAL 模式） |
| HTTP 客户端 | `httpx` (≥ 0.26.0) | OneDBA 平台 API 调用 |
| WebSocket | `websockets` (≥ 12.0) | WebSocket 实时通信 |
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

1. **手写 ReAct Agent 而非 SDK**：Agent 引擎是直接基于 `openai` Python SDK 构建的自定义 ReAct 循环，手动管理对话循环、工具调用（OpenAI function calling 格式）、token 计数、取消和 SSE 事件发射。这使得模型选择完全灵活，任何 OpenAI 兼容端点均可接入。

2. **OpenAI 兼容 API 抽象**：通过公司内部代理访问 DeepSeek-V4，代码天然模型无关，切换 LLM 只需更改配置。

3. **Protocol 驱动的可插拔存储**：`StorageBackend` Protocol（会话）和 `PreferenceBackend` Protocol（偏好）定义清晰的持久化抽象，`InMemoryStore`/`SqliteStore`（会话）和 `InMemoryPreferenceStore`/`SqlitePreferenceStore`（偏好）两种实现。`StorageManager` 统一协调两个后端的生命周期，`get_storage()` 工厂返回 `StorageManager` 单例。`app/memory/__init__.py` 提供向后兼容包装（`get_store()` → `get_storage().session_store`）。通过 `STORAGE_BACKEND` 配置切换。

4. **NL2SQL 独立流水线**：`nl2sql/` 模块独立处理 SQL 生成→验证→修复闭环，与 Agent 循环解耦，包含语义规则注入（`semantics.py`）。

5. **事件驱动的 SSE 流式架构**：API 层通过异步生成器链产生类型化 SSE 事件（`step`、`sql`、`final`），Agent runner 产出原始事件，routes 层包装为 SSE 格式。

6. **多层记忆系统**：三层记忆并存——会话级对话历史（存储后端）、长期记忆（OpenViking 外部知识库，每 N 轮延迟提交）、操作偏好（`query_preferences` 表记录表使用模式），每次 Agent 运行前注入上下文。

7. **asyncio.Event 取消机制**：`CancelEventRegistry`（`app/agent/cancel.py`）管理每个会话的取消信号，Agent 循环在多个安全点检查取消（迭代边界、LLM 调用竞态、工具执行），通过 REST 端点暴露。含 TTL 过期机制（5 分钟）防止内存泄漏。

8. **用户隔离的多租户会话**：所有会话操作使用 `(user_id, session_id)` 复合键，存储层实现多租户隔离。

---
_updated_at: 2026-07-15_