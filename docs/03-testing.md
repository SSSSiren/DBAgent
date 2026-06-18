# DBAgent 测试说明

本文档说明 DBAgent 当前测试覆盖范围、运行方式、如何验证测试有效性，以及后续应补充的集成测试。

## 1. 测试环境

推荐使用项目约定的 `DBR` conda 环境：

```bash
cd /Users/admin/DBR/DBAgent
conda run -n DBR python -m pip install -r requirements.txt
```

运行测试：

```bash
conda run -n DBR python -m pytest -q
```

当前测试不需要真实 `DEEPSEEK_API_KEY` 或 `ONEDBA_ACCESS_TOKEN`，也不会访问真实 DeepSeek 或 OneDBA 服务。

## 2. 当前测试文件

| 文件 | 目标 | 覆盖重点 |
|---|---|---|
| `tests/test_tools.py` | 工具层 | OneDBA 结果转 Markdown、SQL 安全检查、写操作确认 |
| `tests/test_onedba_client.py` | OneDBA 客户端 | 请求参数、认证 Header、API 响应解析 |
| `tests/test_agent.py` | Agent 基础逻辑 | LLM JSON 提取、降级意图识别、LangGraph 分支判断 |

## 3. 分模块运行

工具层：

```bash
conda run -n DBR python -m pytest tests/test_tools.py -q
```

OneDBA 客户端：

```bash
conda run -n DBR python -m pytest tests/test_onedba_client.py -q
```

Agent 逻辑：

```bash
conda run -n DBR python -m pytest tests/test_agent.py -q
```

查看详细用例名：

```bash
conda run -n DBR python -m pytest -vv
```

## 4. 如何判断测试是有效的

仅看到 `passed` 只能说明当前代码满足测试断言。要验证测试不是“假通过”，可以做反向验证：临时引入一个明确错误，确认对应测试会失败，然后恢复代码。

### 4.1 Markdown 转义验证

临时修改 `app/tools/formatters.py`：

```python
return text.replace("|", "\\|")
```

改成：

```python
return text
```

运行：

```bash
conda run -n DBR python -m pytest tests/test_tools.py -q
```

预期：`test_format_as_markdown_table_converts_onedba_result` 失败，因为测试要求表格单元格里的 `|` 必须转义。

### 4.2 DDL 拦截验证

临时修改 `app/tools/sql_executor.py`，从 `BLOCKED_PREFIXES` 中移除 `"DROP"`。

运行：

```bash
conda run -n DBR python -m pytest tests/test_tools.py -q
```

预期：DDL 安全检查相关测试失败。

### 4.3 写操作确认验证

临时修改 `needs_confirmation()`，让 `UPDATE` 返回 `False`。

运行：

```bash
conda run -n DBR python -m pytest tests/test_tools.py -q
```

预期：`test_needs_confirmation_for_write_sql` 失败。

完成反向验证后，务必恢复临时改动。

## 5. 当前测试边界

当前测试偏单元测试，重点验证纯函数、请求组装和基础 Agent 分支。它们不能证明以下内容：

| 未覆盖内容 | 原因 | 建议补充 |
|---|---|---|
| 真实 DeepSeek 调用 | 需要 API key 和外网 | 使用 mock LLM 或单独的可选集成测试 |
| 真实 OneDBA 查询 | 需要 accessToken 和内部网络 | 使用 mock transport；真实环境单独跑 smoke test |
| SSE 完整事件序列 | 当前未用 TestClient 覆盖 | 增加 FastAPI TestClient 测试 |
| WebSocket 对话 | 当前未覆盖 | 增加 WebSocket client 测试 |
| 写操作确认的跨请求流程 | 当前只测底层判断 | 增加 `/api/chat/sync` 多轮会话测试 |

## 6. 建议新增的集成测试

后续建议补充 `tests/test_api.py`，覆盖：

1. `GET /health` 返回 `{"status": "ok"}`。
2. `POST /api/chat/sync` 对 `"你好"` 返回正常回复。
3. `POST /api/chat` 返回标准 SSE 格式，每个事件以 `data:` 开头。
4. 同一 `session_id` 下写 SQL 先返回 `needs_confirmation=true`，再输入 `确认执行` 执行挂起动作。
5. `GET /api/sessions/{session_id}` 能读取摘要、已选库和确认状态。

这些测试应继续使用 mock，避免依赖真实 DeepSeek 和 OneDBA。

## 7. 手动 Smoke Test

启动服务：

```bash
cd /Users/admin/DBR/DBAgent
/Users/admin/miniconda3/envs/DBR/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

同步聊天：

```bash
curl -X POST http://127.0.0.1:8000/api/chat/sync \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke","message":"你好"}'
```

SSE：

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke-sse","message":"你好"}'
```

预期 SSE 输出包含多段：

```text
data: {"type": "step", ...}
data: {"type": "final", ...}
```
