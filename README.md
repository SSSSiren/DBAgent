# SDK-DBAgent

基于 **OpenAI 兼容 API** 构建的 NL2SQL 智能数据库助手，运行于 OneDBA 平台之上。

## 功能

- **自然语言转 SQL**：用自然语言描述查询需求，自动生成并执行 SQL
- **数据库探索**：浏览数据库、表结构，了解数据分布
- **多轮对话**：支持追问、改条件、切换数据库等上下文交互
- **流式输出**：通过 SSE 实时推送 Agent 思考和工具调用过程
- **安全可控**：只读查询自动执行，写操作需确认，DDL 操作被拦截

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 和 ONEDBA_ACCESS_TOKEN
```

### 3. 启动服务

```bash
python -m app.main
```

### 4. 访问

- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## 架构

```
用户 → FastAPI → SSE 路由 → ReAct Agent → 工具集 → OneDBA API
                                                    ↓
                                              NL2SQL 管道
                                         (生成 → 验证 → 修复)
```

## 项目结构

```
app/
├── agent/          # Agent 层（ReAct runner、prompt、上下文、取消控制）
├── tools/          # 工具注册（list_databases、find_table、describe_table、query_database 等）
├── nl2sql/         # NL2SQL 管道（生成、验证、修复、语义规则）
├── datavault/      # HDC 数据底座（离线生成、在线检索、增量更新）
├── client/         # OneDBA HTTP 客户端
├── api/            # FastAPI 路由（SSE/WebSocket）
├── memory/         # 会话存储
├── knowledge/      # OpenViking 长期记忆集成
└── observation/    # Langfuse 可观测性
```

## 技术栈

- **Agent 框架**: 手写 ReAct 循环（基于 openai SDK）
- **Web 框架**: FastAPI + SSE
- **LLM**: DeepSeek (通过 OpenAI 兼容 API)
- **数据库**: OneDBA 平台
- **可观测性**: Langfuse