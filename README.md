# SDK-DBAgent

SDK-DBAgent 是一个面向 OneDBA 平台的 NL2SQL 智能数据库助手。服务通过 OpenAI 兼容 API 调用大模型，使用 ReAct Agent 编排数据库发现、表结构查询、SQL 生成、SQL 校验、只读执行、会话记忆、SQL 历史记忆和 HDC 数据底座检索。

项目当前交付形态是 FastAPI 后端 + 静态前端 + docker-compose 单机部署。生产部署可在此基础上迁移到 K8s、镜像仓库和统一 Secret 管理。

## 核心能力

- 自然语言生成 SQL，并在 OneDBA 上执行只读查询
- 多轮会话，支持上下文追问、数据库选择和会话隔离
- SSE 流式对话、同步 JSON 对话、WebSocket 对话
- 会话存储、查询偏好记忆、SQL Memory 历史 SQL 检索
- HDC 数据底座：生成、更新、状态查询和按 namespace 注入语义上下文
- Admin API：管理 HDC namespace 映射、SQL Memory、用户数据清理
- Langfuse 可观测性接入

## 架构概览

```text
Browser / Client
      |
      v
FastAPI API layer
      |
      +-- /api/chat, /api/chat/sync, /api/ws
      +-- /api/sessions, /api/hdc, /api/admin
      |
      v
ReAct Agent runner
      |
      +-- list_databases / find_table / describe_table / query_database
      +-- NL2SQL generate -> validate -> repair
      +-- Session / Preference / SQL Memory / HDC context
      |
      v
OneDBA API + OpenAI-compatible LLM + optional OpenViking + optional Langfuse
```

## 项目结构

```text
app/
  agent/          ReAct runner、prompt、上下文、取消控制
  api/            FastAPI 用户接口和 Admin API
  client/         OneDBA HTTP 客户端
  datavault/      HDC 数据底座生成、上传、检索、增量更新
  knowledge/      OpenViking 长期记忆和 HDC 存储集成
  memory/         会话、偏好、SQL Memory、Admin 映射存储
  nl2sql/         SQL 生成、校验、修复
  observation/    Langfuse trace
  static/         内置前端页面
  tools/          Agent 工具集
docs/             API、HDC 和交付文档
scripts/          本地启动、冒烟检查和交付验收脚本
tests/            单元、集成和评测用例
tools/            评测、分析和管理脚本
```

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要填写：

```bash
LLM_API_KEY=<your_llm_key>
ONEDBA_ACCESS_TOKEN=<your_onedba_token>
ONEDBA_ENV=prd
```

如需使用 Admin API，填写：

```bash
ADMIN_API_TOKEN=<strong_random_token>
```

`.env.example` 是本项目配置默认值的标准入口。代码、compose 和部署文档应与它保持一致。

### 3. 本地启动

```bash
python -m app.main
```

或使用启动脚本：

```bash
bash scripts/start.sh 8000
```

访问入口：

- 前端页面: http://localhost:8000/
- Admin 页面: http://localhost:8000/static/admin.html
- OpenAPI: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

### 4. Docker Compose 启动

```bash
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8000/health
```

compose 模式要求 `LLM_API_KEY`、`ONEDBA_ACCESS_TOKEN`、`ONEDBA_ENV`、`ADMIN_API_TOKEN` 均非空，否则容器拒绝启动。

## API 文档

- 用户端 REST/SSE/WebSocket/session/HDC 接口: [docs/api-guide.md](docs/api-guide.md)
- Admin API: [docs/admin-api-guide.md](docs/admin-api-guide.md)
- 在线 OpenAPI: http://localhost:8000/docs

常用调用：

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "session_id": "session-main",
    "message": "统计每种工单状态的数量",
    "schema_id": 65938636,
    "database_name": "dw_onedba"
  }'
```

## 部署入口

- 单机 docker-compose 部署: [DEPLOY.md](DEPLOY.md)
- 交付验收、回滚、备份恢复、监控告警、安全检查: [docs/delivery-checklist.md](docs/delivery-checklist.md)

## 测试与评测

基础测试：

```bash
pytest
```

交付验收入口：

```bash
bash scripts/acceptance.sh
```

评测框架：

```bash
python -m tests.evaluation.cli list
python -m tests.evaluation.cli run --ids TC-001
```

更多评测说明见 [tests/evaluation/README.md](tests/evaluation/README.md)。

## 运维入口

常用命令：

```bash
docker compose logs -f dbagent
docker compose restart
docker compose kill -s HUP dbagent
docker compose down
```

数据默认持久化到 `data/sessions.db`，其中包含会话、偏好、SQL Memory 和 Admin HDC 映射。升级或重启前不要删除 `data/`。

## 关键配置

| 配置 | `.env.example` 默认值 | 说明 |
|---|---:|---|
| `STORAGE_BACKEND` | `sqlite` | 持久化会话和记忆 |
| `SQL_MEMORY_ENABLED` | `false` | SQL 历史记忆默认关闭，启用后需 embedding 服务可用 |
| `LLM_EMBEDDING_PROVIDER` | `auto` | OpenAI embedding 优先，回退 Ollama |
| `HDC_ENABLED` | `false` | HDC 数据底座默认关闭 |
| `KB_ENABLED` | `false` | OpenViking 长期对话记忆默认关闭 |
| `LANGFUSE_ENABLED` | `false` | Langfuse trace 默认关闭 |
| `ADMIN_API_TOKEN` | `test-token` | 示例 token；生产必须替换为强随机值 |

生产建议见 [DEPLOY.md](DEPLOY.md)。
