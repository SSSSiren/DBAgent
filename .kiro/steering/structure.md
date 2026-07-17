# 结构

## 目录布局

```
app/
├── agent/          # Agent 核心：SDK 执行器、系统提示词、上下文构建
├── tools/          # 7 个数据库工具 + 格式化器 + SQL 工具函数
├── nl2sql/         # NL2SQL 管道：生成器、验证器、修复器、语义规则
├── client/         # OneDBA HTTP 客户端
├── api/            # FastAPI 路由、SSE/WebSocket 处理、数据模型
├── memory/         # 会话状态存储（进程内存字典）
├── observation/    # Langfuse trace/span/指标 采集
├── static/         # 静态前端资源（HTML、JS、CSS）
└── config.py       # Pydantic Settings（环境变量 + .env）
```

## 模块职责

| 模块 | 职责 | 核心文件 |
|--------|---------------|-------------|
| `agent/` | Agent 生命周期：提示词 → SDK 执行 → 事件流式输出 | `runner.py`（入口）、`prompts.py`、`context.py` |
| `tools/` | 通过 MCP Server 注册的数据库操作工具 | `__init__.py`（注册中心）、各工具文件 |
| `nl2sql/` | 独立于 Agent 层的 SQL 生成管道 | `generator.py`、`validator.py`、`repair.py`、`semantics.py` |
| `api/` | HTTP/WS 接口、SSE 格式化、会话协调 | `routes.py`、`schemas.py` |
| `client/` | OneDBA 平台 HTTP 客户端（鉴权、请求） | `onedba.py` |
| `memory/` | 进程内存会话 CRUD，可替换为 Redis | `store.py` |
| `observation/` | Langfuse v4.x 手动埋点 | `langfuse.py` |

## 命名规范

- **文件**：snake_case（`list_databases.py`、`agent/runner.py`）
- **函数**：snake_case（`run_agent_stream`、`build_context`、`get_settings`）
- **类**：PascalCase（`Settings`、`ChatRequest`、`LangfuseObserver`）
- **常量**：UPPER_SNAKE_CASE（`TOOLS`、`TOOL_HANDLERS`、`AGENT_SYSTEM_PROMPT`）
- **私有内部**：下划线前缀（`_run_with_sdk`、`_build_tool_schemas`、`_push_tool_result`）

## 导入模式

- 工具通过 `app/tools/__init__.py` 注册，导出 `TOOLS`、`TOOL_HANDLERS` 和 `get_tool_handler()`
- Agent 执行器从 `app.tools` 导入工具，从 `claude_agent_sdk` 导入 SDK
- API 路由通过 `app.agent.runner` 导入 Agent 执行器
- 配置通过 `app.config.get_settings()` 获取带 `@lru_cache` 的缓存单例
- 每个子模块有独立的 `__init__.py` 导出公共 API

## 关键模式

### 工具注册
```python
# app/tools/__init__.py
TOOLS = [{"name": "...", "description": "...", "handler": fn, "parameters": {...}}]
TOOL_HANDLERS = {t["name"]: t["handler"] for t in TOOLS}
```

### Agent 入口
```python
# app/agent/runner.py
async def run_agent_stream(user_input, session_state, trace_name) -> AsyncIterator[tuple[str, dict]]:
    # 构建上下文 → SDK 执行 → 产出 SSE 事件 → 更新会话
```

### API 路由模式
```python
# app/api/routes.py
@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    # 恢复会话 → 运行 Agent 流 → 格式化为 SSE → 保存会话
```

### 配置模式
```python
# app/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

## 测试结构
```
tests/
├── evaluation/         # 批量评测框架
├── test_nl2sql.py      # NL2SQL 管道单元测试
└── test_cases_onedba_evaluation.md  # 评测用例
```
