# DBAgent

DBAgent 是一个基于 LangGraph + FastAPI 的智能数据库分析助手，支持数据库探索、自然语言转 SQL、多步骤查询分析、SSE 流式输出和 WebSocket 双向通信。

## 快速开始

```bash
cd /Users/admin/DBR/DBAgent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
ONEDBA_ACCESS_TOKEN=your_onedba_access_token
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

启动服务：

```bash
python -m app.main
```

健康检查：

```bash
curl http://localhost:8000/health
```

## API

SSE 对话：

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","message":"帮我看看 onedba 相关的数据库"}'
```

同步调试接口：

```bash
curl -X POST http://localhost:8000/api/chat/sync \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","message":"你好"}'
```

WebSocket：

```text
ws://localhost:8000/api/ws/{session_id}
```

会话状态：

```bash
curl http://localhost:8000/api/sessions/demo
```

## 工具确认机制

`SELECT`、`SHOW`、`DESCRIBE` 会自动执行。`UPDATE`、`DELETE`、`INSERT` 会返回确认提示；同一会话下一条消息输入 `确认执行` 后继续执行挂起动作。`CREATE`、`ALTER`、`DROP`、`TRUNCATE` 会被拒绝，需走 OneDBA 工单。

## 测试

```bash
conda run -n DBR python -m pytest -q
```

测试默认不访问真实 DeepSeek 或 OneDBA 服务。详细说明见 [docs/03-testing.md](docs/03-testing.md)。
